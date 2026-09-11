"""Record immutable validator artifacts; reject stale or misdirected passes."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from sync_common import atomic_json, digest, file_digest, read_json, result_binding_errors

VALIDATORS = {"child":"child_validator", "vendor":"vendor_validator", "tables":"tables_validator"}
FIELDS = {"status","violation_count","operational_error","error_type","error","document","wiki_node",
          "parent_node","model_entry","manifest","vendor","validation_scope","require_social_visual_proof",
          "require_artificial_analysis","run_id","validated_at","manifest_input_sha256","document_revision_id",
          "snapshot_sha256","audit_only"}


def validate_result(result, manifest=None, validator=None):
    status, count = result.get("status"), result.get("violation_count")
    if status not in {"pass","fail"} or isinstance(count,bool) or not isinstance(count,int) or count<0:
        raise ValueError("result requires pass/fail and a non-negative integer violation_count")
    if (status=="pass") != (count==0):
        raise ValueError("status and violation_count disagree")
    if result.get("operational_error") and status != "fail":
        raise ValueError("operational error cannot pass")
    if status=="pass" and manifest is not None:
        errors = result_binding_errors(result,manifest)
        expected_doc = manifest["child_wiki_doc"]["obj_token"] if validator=="child" else manifest["sync_target"]["parent_doc"]
        if result.get("document")!=expected_doc or result.get("model_entry")!=manifest["parent_section"]["model_entry"]:
            errors.append("validator target differs from manifest")
        if validator=="child" and (result.get("wiki_node")!=manifest["child_wiki_doc"]["node_token"] or result.get("parent_node")!=manifest["sync_target"]["parent_wiki_node"]):
            errors.append("child Wiki relationship differs from manifest")
        if validator=="vendor" and (result.get("vendor")!=manifest["parent_section"]["vendor"] or result.get("validation_scope")!="current_entry"):
            errors.append("vendor result is not for this current entry")
        if result.get("audit_only") or "snapshot" not in result or digest(result["snapshot"])!=result.get("snapshot_sha256"):
            errors.append("full bound snapshot required for pass")
        if errors:
            raise ValueError("; ".join(errors))
    return {key:result[key] for key in FIELDS if key in result}


def record(manifest_path, validator, result):
    path=Path(manifest_path).resolve()
    manifest=read_json(path)
    recorded=validate_result(result,manifest,validator)
    output=path.parent/"evidence"/(validator+"-"+digest(result)+".json")
    atomic_json(output,result)
    recorded.update(result_file=str(output.relative_to(path.parent)),result_sha256=file_digest(output))
    verification=manifest.setdefault("verification",{})
    verification[VALIDATORS[validator]]=recorded
    verification.pop("freshness",None)
    atomic_json(path,manifest)
    return recorded


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",required=True); parser.add_argument("--validator",required=True,choices=sorted(VALIDATORS))
    parser.add_argument("--result-file",required=True)
    args=parser.parse_args()
    try:
        result=json.loads(sys.stdin.read()) if args.result_file=="-" else read_json(args.result_file)
        recorded=record(args.manifest,args.validator,result)
    except Exception as exc:
        print(json.dumps({"status":"fail","error":str(exc)},ensure_ascii=False)); return 1
    print(json.dumps({"status":"pass","recorded":recorded},ensure_ascii=False,indent=2)); return 0


if __name__=="__main__":
    sys.exit(main())
