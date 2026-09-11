import copy
import tempfile
import unittest
from tests.fixtures import manifest,FakeHelper
from validate_tables import validate,plan_errors


class TableTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.m=manifest(self.temp.name,["B"]);self.helper=FakeHelper()
    def test_real_readback_has_counts_and_snapshots(self):
        result=validate(self.helper,self.m)
        self.assertEqual(result["status"],"pass")
        self.assertEqual(result["tables"][0]["checked_rows"],4)
        self.assertEqual(result["tables"][0]["remaining_mismatches"],0)
        self.assertIn("model_scan",result["snapshot"]["tables"]["sheetBlock"])
    def test_missing_expected_values_fails(self):
        del self.m["related_tables"][0]["checks"][0]["expected_values"]
        self.assertTrue(plan_errors(self.m))
    def test_formula_overwritten_with_equal_value_fails(self):
        self.helper.formulas[1][2]=None
        self.assertEqual(validate(self.helper,self.m)["status"],"fail")
    def test_wrong_value_fails(self):
        self.helper.values[1][1]=3
        self.assertEqual(validate(self.helper,self.m)["status"],"fail")
    def test_duplicate_model_after_blank_row_fails(self):
        self.helper.values[3][0]="Fixture v1"
        result=validate(self.helper,self.m)
        self.assertTrue(any("occurrences" in e for e in result["violations"]))
    def test_missing_embedded_table_fails(self):
        self.helper.blocks[0]["children"].append("second")
        self.helper.blocks.append({"block_id":"second","block_type":30,"sheet":{"token":"another_sheet"}})
        with self.assertRaisesRegex(ValueError,"inventory"):validate(self.helper,self.m)
    def test_empty_inventory_cannot_pass_when_sheet_exists(self):
        self.m["table_inventory"]=[];self.m["related_tables"]=[]
        with self.assertRaises(ValueError):validate(self.helper,self.m)
    def test_missing_sheet_token_cannot_be_silently_omitted(self):
        self.helper.blocks[1]["sheet"]={}
        with self.assertRaisesRegex(RuntimeError,"missing its token"):validate(self.helper,self.m)
    def test_omitted_relevant_table_fails(self):
        self.m["related_tables"]=[]
        self.assertTrue(plan_errors(self.m))
    def test_retargeted_table_fails(self):
        self.m["related_tables"][0]["sheet_id"]="other"
        with self.assertRaisesRegex(ValueError,"token"):validate(self.helper,self.m)
    def test_sheet_changed_during_readback_fails(self):
        self.helper.change_after=4
        with self.assertRaisesRegex(RuntimeError,"changed"):validate(self.helper,self.m)
    def test_clipped_rows_fail(self):
        original=self.helper.read_sheet_range
        def truncated(*args):
            result=original(*args);result["row_indices"]=[];return result
        self.helper.read_sheet_range=truncated
        with self.assertRaises(RuntimeError):validate(self.helper,self.m)
    def test_missing_formula_matrix_fails(self):
        del self.m["related_tables"][0]["checks"][0]["expected_formulas"]
        self.assertTrue(plan_errors(self.m))
    def test_no_model_row_expected_check_fails(self):
        self.m["related_tables"][0]["checks"]=[{"range":"B2:C2","expected_values":[[2,4]],"expected_formulas":[[None,"=B2*2"]]}]
        self.assertEqual(validate(self.helper,self.m)["status"],"fail")
    def test_checked_no_change_still_reads_actual_data(self):
        self.m["related_tables"][0]["action"]="checked_no_change"
        self.helper.values[1][1]=8
        self.assertEqual(validate(self.helper,self.m)["status"],"fail")
    def test_type_changed_number_to_string_fails(self):
        self.helper.values[1][1]="2"
        self.assertEqual(validate(self.helper,self.m)["status"],"fail")
