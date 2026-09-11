"""Read every embedded Sheet; compare planned values, formulas and model rows."""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path
from sync_common import (assert_document_unchanged, digest, document_snapshot, load_helper,
                         provenance, read_json)


def column_number(value):
    number = 0
    for char in value:
        number = number * 26 + ord(char) - 64
    return number


def range_shape(value):
    match = re.fullmatch(r"([A-Z]+)([1-9][0-9]*):([A-Z]+)([1-9][0-9]*)", value)
    if not match:
        raise ValueError("range must be a bounded A1 rectangle, e.g. A1:D20")
    c1, r1, c2, r2 = match.groups()
    r1, r2, c1, c2 = int(r1), int(r2), column_number(c1), column_number(c2)
    if r2 < r1 or c2 < c1:
        raise ValueError("range end precedes start")
    return r1, r2, c1, c2


def embedded_sheets(blocks):
    sheets=[b for b in blocks if b.get("block_type")==30]
    if any(not b.get("sheet",{}).get("token") for b in sheets):
        raise RuntimeError("embedded Sheet is missing its token; inventory is incomplete")
    return {b["block_id"]:b["sheet"]["token"] for b in sheets}


def plan_errors(manifest):
    errors = []
    inventory = manifest.get("table_inventory", [])
    if not isinstance(inventory, list):
        return ["table_inventory must be an array"]
    ids = [i.get("block_id") for i in inventory if isinstance(i, dict)]
    if len(ids) != len(inventory) or None in ids or len(ids) != len(set(ids)):
        errors.append("table_inventory requires unique block_id values")
    for item in inventory:
        if not isinstance(item, dict):
            continue
        if not isinstance(item.get("relevant"), bool) or not item.get("reason") or not item.get("sheet_token"):
            errors.append("each inventoried sheet needs relevance, reason and live sheet_token")
    tables = manifest.get("related_tables", [])
    related_ids = [t.get("block_id") for t in tables if isinstance(t, dict)]
    expected = {i["block_id"] for i in inventory if isinstance(i, dict) and i.get("relevant")}
    if len(related_ids) != len(tables) or len(related_ids) != len(set(related_ids)) or set(related_ids) != expected:
        errors.append("related_tables must cover every relevant embedded Sheet exactly once")
    for table in tables:
        try:
            for field in ("spreadsheet_token", "sheet_id", "model_column", "header_range", "reason"):
                if not isinstance(table.get(field), str) or not table[field]:
                    raise ValueError(f"missing {field}")
            if not re.fullmatch("[A-Z]+", table["model_column"]):
                raise ValueError("model_column must be a column letter")
            if not isinstance(table.get("header"), list) or not table["header"]:
                raise ValueError("header must contain actual column names")
            hr1, hr2, hc1, hc2 = range_shape(table["header_range"])
            if hr1 != hr2 or hc2-hc1+1 != len(table["header"]):
                raise ValueError("header range dimensions differ from header")
            keys = table.get("model_keys")
            if not isinstance(keys, list) or not keys or any(not isinstance(k, str) or not k for k in keys):
                raise ValueError("model_keys must list precise model/version aliases")
            count = table.get("expected_occurrences")
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError("expected_occurrences must be explicit")
            if table.get("action") not in {"updated", "checked_no_change"}:
                raise ValueError("action must describe intended change")
            checks = table.get("checks")
            if not isinstance(checks, list) or not checks:
                raise ValueError("checks must contain expected value/formula rectangles")
            for check in checks:
                r1,r2,c1,c2 = range_shape(check["range"])
                for field in ("expected_values", "expected_formulas"):
                    matrix = check.get(field)
                    if not isinstance(matrix, list) or len(matrix) != r2-r1+1 or any(not isinstance(row,list) or len(row)!=c2-c1+1 for row in matrix):
                        raise ValueError(f"{field} must cover the complete range, including explicit nulls")
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            errors.append(f"table {table.get('block_id') if isinstance(table,dict) else '?'}: {exc}")
    return errors


def read_rectangle(helper, table, a1):
    result = helper.read_sheet_range(table["spreadsheet_token"], table["sheet_id"], a1)
    r1,r2,c1,c2 = range_shape(a1)
    if result.get("range") != a1 or result.get("row_indices") != list(range(r1,r2+1)):
        raise RuntimeError("sheet range/row readback incomplete")
    if [column_number(c) for c in result.get("col_indices", [])] != list(range(c1,c2+1)):
        raise RuntimeError("sheet column readback incomplete")
    for key in ("values", "formulas"):
        matrix = result.get(key)
        if not isinstance(matrix, list) or len(matrix) != r2-r1+1 or any(len(row)!=c2-c1+1 for row in matrix):
            raise RuntimeError(f"sheet {key} matrix incomplete")
    return result


def read_table(helper, table):
    meta = helper.sheet_metadata(table["spreadsheet_token"], table["sheet_id"])
    if column_number(table["model_column"]) > meta["column_count"]:
        raise ValueError("model column outside the sheet")
    reads = {table["header_range"]: read_rectangle(helper,table,table["header_range"])}
    for check in table["checks"]:
        reads[check["range"]] = read_rectangle(helper,table,check["range"])
    scan = []
    col = table["model_column"]
    for start in range(1,meta["row_count"]+1,500):
        end = min(start+499,meta["row_count"])
        scan.append(read_rectangle(helper,table,f"{col}{start}:{col}{end}"))
    return {"metadata":meta,"ranges":reads,"model_scan":scan}


def compare_table(table, snapshot):
    mismatches = []
    if digest(snapshot["ranges"][table["header_range"]]["values"]) != digest([table["header"]]):
        mismatches.append("header differs from plan")
    for check in table["checks"]:
        actual = snapshot["ranges"][check["range"]]
        for key, expected in (("values","expected_values"),("formulas","expected_formulas")):
            if digest(actual[key]) != digest(check[expected]):
                mismatches.append(f"{check['range']}: {key} differ from plan")
    matched = [row for scan in snapshot["model_scan"] for row,values in zip(scan["row_indices"],scan["values"])
               if values[0] in table["model_keys"]]
    if len(matched) != table["expected_occurrences"]:
        mismatches.append(f"model occurrences expected {table['expected_occurrences']}, found {len(matched)}")
    for row in matched:
        col = column_number(table["model_column"])
        if not any(r1<=row<=r2 and c1<=col<=c2 for r1,r2,c1,c2 in (range_shape(c["range"]) for c in table["checks"])):
            mismatches.append(f"model row {row} has no expected value/formula check")
    return mismatches


def validate(helper, manifest):
    errors = plan_errors(manifest)
    if errors:
        raise ValueError("; ".join(errors))
    parent = document_snapshot(helper,manifest["sync_target"]["parent_doc"])
    live = embedded_sheets(parent["blocks"])
    inventoried = {i["block_id"]:i["sheet_token"] for i in manifest["table_inventory"]}
    if live != inventoried:
        raise ValueError("embedded Sheet inventory changed or is incomplete; run preflight and classify every Sheet")
    results, snapshots, errors = [], {}, []
    for table in manifest["related_tables"]:
        expected_token = table["spreadsheet_token"] + "_" + table["sheet_id"]
        if live.get(table["block_id"]) != expected_token:
            raise ValueError("table token is not bound to the live embedded Sheet")
        before = read_table(helper,table)
        after = read_table(helper,table)
        if digest(before) != digest(after):
            raise RuntimeError("Sheet changed during readback; rerun this table")
        problems = compare_table(table,after)
        errors.extend(f"{table['block_id']}: {p}" for p in problems)
        snapshots[table["block_id"]] = after
        results.append({"block_id":table["block_id"],"status":table["action"] if not problems else "failed",
                        "checked_rows":after["metadata"]["row_count"],"remaining_mismatches":len(problems),
                        "snapshot_sha256":digest(after)})
    assert_document_unchanged(helper,parent)
    snapshot = {"parent":parent,"tables":snapshots}
    return {"status":"fail" if errors else "pass","violation_count":len(errors),"violations":errors,
            "document":manifest["sync_target"]["parent_doc"],"model_entry":manifest["parent_section"]["model_entry"],
            **provenance(manifest,parent),"snapshot_sha256":digest(snapshot),"snapshot":snapshot,
            "inventory":live,"tables":results}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",required=True); parser.add_argument("--helper",required=True)
    args=parser.parse_args()
    try:
        result=validate(load_helper(args.helper),read_json(args.manifest))
    except Exception as exc:
        result={"status":"fail","violation_count":1,"operational_error":True,"error_type":type(exc).__name__,"error":str(exc)}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result["status"]=="pass" else 1


if __name__=="__main__":
    sys.exit(main())
