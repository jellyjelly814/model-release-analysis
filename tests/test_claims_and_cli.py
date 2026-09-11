import argparse
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tests.fixtures import manifest
from sync_common import atomic_json, file_digest
from sync_run import initialize
from validate_claims import validate_claims
from validate_update_manifest import ManifestValidator
import feishu_lark_cli_helper as adapter


class ClaimsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.m=manifest(self.temp.name,["B"]);self.path=Path(self.temp.name)/"manifest.json"
    def errors(self):return validate_claims(self.m,self.path,True)[0]
    def test_sourced_claim_passes(self):self.assertEqual(self.errors(),[])
    def test_wrong_model_version_fails(self):
        self.m["claims"][0]["model_version"]="v0";self.assertTrue(self.errors())
    def test_missing_source_fails(self):
        self.m["claims"][0]["sources"]=[];self.assertTrue(self.errors())
    def test_source_cache_tamper_fails(self):
        (self.path.parent/"html/source.txt").write_text("changed");self.assertTrue(self.errors())
    def test_search_summary_without_locator_fails(self):
        del self.m["claims"][0]["sources"][0]["locator"];self.assertTrue(self.errors())
    def test_unknown_benchmark_conditions_forbid_precise_ranking(self):
        self.m["claims"][0].update(kind="official_benchmark",conditions={k:"unknown" for k in ("dataset_version","harness","tools","sampling","measured_at")},comparable=True)
        self.assertTrue(self.errors())
    def test_unknown_conditions_explicit_noncomparable_passes_with_warning(self):
        self.m["claims"][0].update(kind="official_benchmark",conditions={k:"unknown" for k in ("dataset_version","harness","tools","sampling","measured_at")},comparable=False)
        errors,warnings=validate_claims(self.m,self.path,True);self.assertFalse(errors);self.assertTrue(warnings)
    def test_inference_cannot_cite_itself(self):
        self.m["claims"][0].update(kind="inference",basis_claim_ids=["identity"]);self.assertTrue(self.errors())
    def test_claim_without_published_location_fails(self):
        del self.m["claims"][0]["placements"];self.assertTrue(self.errors())
    def test_missing_category_fails(self):
        del self.m["claim_coverage"]["community"];self.assertTrue(self.errors())


class InitializationTests(unittest.TestCase):
    def test_init_generates_valid_preparation_without_fabricating_AA_check(self):
        with tempfile.TemporaryDirectory() as temp:
            config=Path(temp)/"targets.json"
            atomic_json(config,{"parent_doc":"parent","parent_wiki_node":"wiki","vendor_heading":"Vendor","allowed_link_hosts":["fixture.feishu.cn"]})
            args=argparse.Namespace(directory=str(Path(temp)/"new"),targets=str(config),company="Fixture",model="M",version="v1",release_date="2026-09-11",model_entry="【2026/09/11】M: fixture",scope="B",read_only=False)
            result=initialize(args);path=Path(result["manifest"])
            self.assertEqual(json.loads(path.read_text())["evidence_policy"]["artificial_analysis"]["status"],"unchecked")
            self.assertEqual(ManifestValidator(path,False).run()["errors"],[])
            with self.assertRaises(ValueError):initialize(args)
    def test_manifest_wrong_shape_returns_json_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"bad.json";path.write_text('{"sync_target":null}')
            command=[sys.executable,"-B",str(Path(__file__).resolve().parents[1]/"scripts/validate_update_manifest.py"),"--manifest",str(path)]
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,1);self.assertEqual(json.loads(result.stdout)["status"],"fail")


class AdapterTests(unittest.TestCase):
    def test_helper_rejects_remote_mutations(self):
        with self.assertRaisesRegex(ValueError,"read-only"):adapter.api("POST","/open-apis/docx/v1/documents")
    def test_repeated_pagination_token_stops(self):
        response=(None,{"code":0,"data":{"items":[],"has_more":True,"page_token":"same"}})
        with patch.object(adapter,"api",return_value=response):
            with self.assertRaisesRegex(RuntimeError,"repeated"):adapter._all_blocks("doc")
    def test_missing_pagination_token_stops(self):
        with patch.object(adapter,"api",return_value=(None,{"code":0,"data":{"items":[],"has_more":True}})):
            with self.assertRaises(RuntimeError):adapter._all_blocks("doc")
    def payload(self):
        return {"ranges":[{"actual_range":"A2:B2","row_indices":[2],"col_indices":["A","B"],
                           "cells":[[{"value":"M"},{"value":2,"formula":"=1+1"}]]}]}
    def test_cell_coordinates_and_formula_preserved(self):
        with patch.object(adapter,"_shortcut",return_value=self.payload()):
            result=adapter.read_sheet_range("s","sheet","A2:B2")
            self.assertEqual(result["row_indices"],[2]);self.assertEqual(result["formulas"],[[None,"=1+1"]])
    def test_cli_warning_never_treated_as_complete(self):
        payload=self.payload();payload["warning_message"]="partial result"
        with patch.object(adapter,"_shortcut",return_value=payload):
            with self.assertRaises(RuntimeError):adapter.read_sheet_range("s","sheet","A2:B2")
    def test_cli_unknown_schema_fails_closed(self):
        with patch.object(adapter,"_shortcut",return_value={"different":[]}):
            with self.assertRaises(RuntimeError):adapter.read_sheet_range("s","sheet","A2:B2")
