import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from tests.fixtures import manifest,FakeHelper,parent_entry
from sync_common import (atomic_json,digest,file_digest,input_digest,document_snapshot,linked_target,
                         required_permissions,provenance,invalidate)
from validate_tables import validate
from validate_update_manifest import ManifestValidator
from record_validator_result import record,validate_result
from sync_run import live_recheck,begin_write,checkpoint,resume,migrate
import validate_vendor_section as vendor


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"manifest.json";self.m=manifest(self.temp.name,["B"]);self.helper=FakeHelper()
        atomic_json(self.path,self.m)
    def completed(self):
        result=validate(self.helper,self.m);record(self.path,"tables",result)
        m=json.loads(self.path.read_text());m["target_status"]["B"]="verified";m["verification"]["tables_checked"]=True
        for field in ("status","checked_rows","remaining_mismatches"):
            m["related_tables"][0][field]=result["tables"][0][field]
        m["verification"]["freshness"]=live_recheck(self.helper,m,self.path)
        atomic_json(self.path,m);return m
    def test_full_B_gate_passes_with_evidence(self):
        self.completed();result=ManifestValidator(self.path,True).run()
        self.assertEqual(result["errors"],[])
    def test_B_scope_does_not_need_media_or_wiki_permissions(self):
        self.m["sync_target"]["permission_preflight"].update(media_read_write=False,wiki_node_manage=False,docx_read_write=False)
        atomic_json(self.path,self.m);self.completed()
        self.assertEqual(ManifestValidator(self.path,True).run()["errors"],[])
    def test_B_scope_still_needs_sheet_permission(self):
        self.m["sync_target"]["permission_preflight"]["sheets_read_write"]=False
        atomic_json(self.path,self.m);self.completed()
        self.assertTrue(ManifestValidator(self.path,True).run()["errors"])
    def test_new_child_requires_wiki_management(self):
        self.m["sync_target"]["scope"]=["C"];self.m["child_wiki_doc"]["operation"]="create"
        self.assertIn("wiki_node_manage",required_permissions(self.m))
    def test_existing_child_update_not_require_management(self):
        self.m["sync_target"]["scope"]=["C"]
        self.assertNotIn("wiki_node_manage",required_permissions(self.m))
    def test_missing_table_counts_fails(self):
        m=self.completed();del m["related_tables"][0]["checked_rows"];del m["related_tables"][0]["remaining_mismatches"]
        atomic_json(self.path,m);self.assertEqual(ManifestValidator(self.path,True).run()["status"],"fail")
    def test_modified_plan_invalidates_recorded_pass(self):
        m=self.completed();m["related_tables"][0]["checks"][0]["expected_values"][0][1]=9
        atomic_json(self.path,m);self.assertTrue(any("stale" in e for e in ManifestValidator(self.path,True).run()["errors"]))
    def test_result_file_tamper_fails(self):
        m=self.completed();p=self.path.parent/m["verification"]["tables_validator"]["result_file"]
        p.write_text("{}")
        self.assertEqual(ManifestValidator(self.path,True).run()["status"],"fail")
    def test_missing_freshness_fails(self):
        m=self.completed();del m["verification"]["freshness"];atomic_json(self.path,m)
        self.assertEqual(ManifestValidator(self.path,True).run()["status"],"fail")
    def test_expired_freshness_fails(self):
        m=self.completed();m["verification"]["freshness"]["checked_at"]="2000-01-01T00:00:00Z";atomic_json(self.path,m)
        self.assertEqual(ManifestValidator(self.path,True).run()["status"],"fail")
    def test_revision_change_fails_live_recheck(self):
        m=self.completed();self.helper.revision=2
        with self.assertRaisesRegex(RuntimeError,"changed"):live_recheck(self.helper,m,self.path)
    def test_sheet_change_fails_live_recheck(self):
        m=self.completed();self.helper.values[1][1]=5
        with self.assertRaisesRegex(RuntimeError,"changed"):live_recheck(self.helper,m,self.path)
    def test_missing_revision_is_operational_failure(self):
        self.helper.revision=None
        with self.assertRaisesRegex(RuntimeError,"revision"):document_snapshot(self.helper,"parentDoc")
    def test_document_changing_during_pagination_fails(self):
        old=self.helper._all_blocks
        def change(token):
            self.helper.revision+=1;return old(token)
        self.helper._all_blocks=change
        with self.assertRaisesRegex(RuntimeError,"changed"):document_snapshot(self.helper,"parentDoc")
    def test_recorder_preserves_revision_time_and_snapshot(self):
        result=validate(self.helper,self.m);recorded=record(self.path,"tables",result)
        for key in ("document_revision_id","validated_at","snapshot_sha256","manifest_input_sha256","run_id"):
            self.assertEqual(recorded[key],result[key])
    def test_other_run_result_is_rejected(self):
        result=validate(self.helper,self.m);result["run_id"]="different"
        with self.assertRaisesRegex(ValueError,"run_id"):record(self.path,"tables",result)
    def test_old_result_without_snapshot_is_rejected(self):
        with self.assertRaises(ValueError):record(self.path,"tables",{"status":"pass","violation_count":0})
    def test_future_validator_time_is_rejected(self):
        result=validate(self.helper,self.m);result["validated_at"]="2099-01-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError,"future"):record(self.path,"tables",result)
    def test_nonexistent_claim_placement_fails(self):
        self.m["claims"][0]["placements"][0]["range"]="A9:C9"
        atomic_json(self.path,self.m);self.completed()
        self.assertTrue(any("placement" in e for e in ManifestValidator(self.path,True).run()["errors"]))
    def test_failed_result_can_be_recorded(self):
        result={"status":"fail","violation_count":1,"operational_error":True,"error_type":"TimeoutError","error":"fixture timeout"}
        self.assertEqual(record(self.path,"tables",result)["status"],"fail")
    def test_begin_write_invalidates_previous_results(self):
        self.completed();begin_write(self.path,self.helper,"price-update","B","fixture update")
        m=json.loads(self.path.read_text());self.assertEqual(m["verification"]["tables_validator"]["status"],"pending")
        self.assertEqual(m["mutation_generation"],1)
    def test_duplicate_step_never_replayed(self):
        begin_write(self.path,self.helper,"one","B","fixture")
        with self.assertRaisesRegex(ValueError,"already exists"):begin_write(self.path,self.helper,"one","B","fixture")
    def test_read_only_begin_write_rejected(self):
        self.m["mode"]="read_only";atomic_json(self.path,self.m)
        with self.assertRaisesRegex(ValueError,"mode/scope"):begin_write(self.path,self.helper,"one","B","fixture")
    def test_resume_uncertain_write_does_not_replay(self):
        begin_write(self.path,self.helper,"one","B","fixture")
        result=resume(self.path,self.helper)
        self.assertEqual(result["steps"][0]["state"],"uncertain_do_not_replay")
        self.assertEqual(result["automatic_writes"],0)
    def test_checkpoint_then_resume_detects_completed_write(self):
        begin_write(self.path,self.helper,"one","B","fixture")
        receipt=self.path.parent/"receipt.json";atomic_json(receipt,{"ok":True,"data":{"fixture":True}})
        checkpoint(self.path,self.helper,"one",receipt)
        self.assertEqual(resume(self.path,self.helper)["steps"][0]["state"],"already_written")
    def test_recovery_receipt_cannot_be_confused_with_original_operation(self):
        begin_write(self.path,self.helper,"one","B","fixture")
        receipt=self.path.parent/"query.json";atomic_json(receipt,{"ok":True,"data":{"fixture_query":True}})
        checkpoint(self.path,self.helper,"one",receipt,"recovery_readback")
        self.assertEqual(json.loads(self.path.read_text())["journal"][0]["receipt_kind"],"recovery_readback")
    def test_migration_preserves_old_file_and_clears_pass(self):
        self.m["schema_version"]=2;atomic_json(self.path,self.m);before=file_digest(self.path)
        out=self.path.parent/"v3.json";migrate(self.path,out)
        self.assertEqual(before,file_digest(self.path));self.assertEqual(json.loads(out.read_text())["schema_version"],3)
        self.assertEqual(json.loads(out.read_text())["verification"]["child_validator"]["status"],"pending")


class ParentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.m=manifest(self.temp.name,["A"]);self.ids,self.blocks=parent_entry()
    def result(self):return vendor.validate_entry(self.ids,0,5,self.blocks,self.m,True)["violations"]
    def test_correct_mention_passes(self):self.assertEqual(self.result(),[])
    def test_wrong_mention_fails(self):
        self.blocks["detail"]["text"]["elements"][1]["mention_doc"]["token"]="wrong"
        self.assertTrue(any("target" in e for e in self.result()))
    def test_correct_text_link_passes(self):
        self.blocks["detail"]["text"]["elements"]=[{"text_run":{"content":"详细追踪","text_element_style":{"link":{"url":"https://fixture.feishu.cn/wiki/childWiki"}}}}]
        self.assertEqual(self.result(),[])
    def test_token_substring_in_wrong_url_fails(self):
        self.blocks["detail"]["text"]["elements"][1]["mention_doc"]["url"]="https://fixture.feishu.cn/wiki/wrong?childWiki"
        self.assertTrue(self.result())
    def test_other_domain_reusing_token_fails(self):
        self.blocks["detail"]["text"]["elements"][1]["mention_doc"]["url"]="https://wrong.example/wiki/childWiki"
        self.assertTrue(self.result())
    def run_vendor_cli(self,hash_value=None):
        helper=FakeHelper();root={"block_id":"parentDoc","block_type":1,"children":["vendor",*self.ids]}
        heading={"block_id":"vendor","block_type":4,"parent_id":"parentDoc","heading2":{"elements":[{"text_run":{"content":"Fixture Vendor"}}]}}
        helper.blocks=[root,heading,*self.blocks.values()];helper.media["fixtureMedia"]=b"fixture media bytes"
        image=Path(self.temp.name)/"image.png";image.write_bytes(b"fixture media bytes")
        self.m["screenshots"]=[] if hash_value is None else [{"parent_image_block":"image","local_path":str(image),"content_sha256":hash_value}]
        path=Path(self.temp.name)/"manifest.json";atomic_json(path,self.m)
        argv=["validator","--doc","parentDoc","--vendor","Fixture Vendor","--model-entry",self.m["parent_section"]["model_entry"],"--manifest",str(path),"--helper","fixture"]
        out=io.StringIO()
        with patch.object(vendor,"load_helper",return_value=helper),patch("sys.argv",argv),redirect_stdout(out):
            with self.assertRaises(SystemExit):vendor.main()
        return json.loads(out.getvalue())
    def test_parent_missing_image_binding_fails(self):self.assertEqual(self.run_vendor_cli()["status"],"fail")
    def test_parent_wrong_image_hash_fails(self):self.assertEqual(self.run_vendor_cli("0"*64)["status"],"fail")
    def test_parent_matching_remote_image_hash_passes(self):
        import hashlib
        self.assertEqual(self.run_vendor_cli(hashlib.sha256(b"fixture media bytes").hexdigest())["status"],"pass")
