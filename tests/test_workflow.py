import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from tests.fixtures import manifest
from sync_common import atomic_json


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(__file__).resolve().parents[1]
        self.path=Path(self.temp.name)/"manifest.json"
        self.helper=Path(self.temp.name)/"helper.py"
        self.m=manifest(self.temp.name,["B"])
        self.m["sync_target"]["permission_preflight"].update(docx_read_write=False,media_read_write=False,wiki_node_manage=False)
        atomic_json(self.path,self.m)
        self.helper.write_text("import sys\nsys.path.insert(0,"+repr(str(self.root))+")\nfrom tests.fixtures import FakeHelper\nh=FakeHelper()\napi=h.api\n_all_blocks=h._all_blocks\nread_sheet_range=h.read_sheet_range\nsheet_metadata=h.sheet_metadata\ndownload_media=h.download_media\n")
    def call(self,command,*args):
        result=subprocess.run([sys.executable,"-B",str(self.root/"scripts/sync_run.py"),command,"--manifest",str(self.path),"--helper",str(self.helper),*args],capture_output=True,text=True,timeout=30)
        return result,json.loads(result.stdout)
    def test_unified_verify_B_passes_complete_gate(self):
        process,result=self.call("verify")
        self.assertEqual(process.returncode,0,result)
        self.assertTrue(result["delivery_complete"])
        saved=json.loads(self.path.read_text())
        self.assertEqual(saved["verification"]["tables_validator"]["status"],"pass")
        self.assertEqual(saved["target_status"]["A"],"pending")
        self.assertEqual(saved["target_status"]["C"],"pending")
    def test_repeated_verify_uses_new_readback(self):
        self.assertTrue(self.call("verify")[1]["delivery_complete"])
        first=json.loads(self.path.read_text())["verification"]["tables_validator"]["validated_at"]
        self.assertTrue(self.call("verify")[1]["delivery_complete"])
        second=json.loads(self.path.read_text())["verification"]["tables_validator"]["validated_at"]
        self.assertNotEqual(first,second)
    def test_unified_verify_formula_failure_does_not_mark_complete(self):
        self.helper.write_text(self.helper.read_text()+"\nh.formulas[1][2]=None\n")
        process,result=self.call("verify")
        self.assertEqual(process.returncode,1);self.assertFalse(result["delivery_complete"])
        self.assertEqual(json.loads(self.path.read_text())["target_status"]["B"],"failed")
    def test_read_only_verify_refuses_delivery_claim(self):
        self.m["mode"]="read_only";atomic_json(self.path,self.m)
        process,result=self.call("verify")
        self.assertEqual(process.returncode,1);self.assertIn("read_only",result["error"])
    def test_preflight_does_not_infer_write_permissions_from_reads(self):
        self.m["sync_target"]["permission_preflight"]["sheets_read_write"]=False;atomic_json(self.path,self.m)
        process,result=self.call("preflight")
        self.assertEqual(process.returncode,1);self.assertEqual(result["missing_capabilities"],["sheets_read_write"])
    def test_uncertain_step_blocks_verify(self):
        self.m["journal"]=[{"step_id":"one","target":"B","state":"started"}];atomic_json(self.path,self.m)
        self.assertEqual(self.call("verify")[0].returncode,1)
    def test_other_targets_still_report_when_child_fails(self):
        self.m["sync_target"]["scope"]=["B","C"]
        self.m["sync_target"]["permission_preflight"].update(docx_read_write=True,media_read_write=True)
        atomic_json(self.path,self.m)
        process,result=self.call("verify")
        self.assertEqual(result["targets"]["C"]["status"],"fail")
        self.assertEqual(result["targets"]["B"]["status"],"pass")
        self.assertFalse(result["delivery_complete"])
