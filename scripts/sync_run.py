"""Local run state + read-only remote preflight, resume and verification.

Content writes remain with the authenticated Lark tools. This runner never
executes a mutation or blindly retries an uncertain remote operation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path
from sync_common import (RESULT_KEYS, atomic_json, api_data, digest, document_snapshot, file_digest,
                         input_digest, invalidate, load_helper, local_file, read_json, required_permissions, utc_now)
from record_validator_result import record
from validate_tables import embedded_sheets, read_table
from validate_business_analysis import new_business_analysis, validate_business

ROOT=Path(__file__).resolve().parent


def initialize(args):
    directory=Path(args.directory).expanduser().resolve()
    if directory.exists():
        raise ValueError("run directory already exists; use resume or choose a new directory")
    config=read_json(args.targets)
    for key in ("parent_doc","parent_wiki_node","vendor_heading","allowed_link_hosts"):
        if not config.get(key) or (isinstance(config[key],str) and config[key].startswith("<")):
            raise ValueError(f"resolved target config missing {key}")
    manifest={"schema_version":3,"run_id":str(uuid.uuid4()),"created_at":utc_now(),"mutation_generation":0,
              "mode":"read_only" if args.read_only else "feishu_sync",
              "model_identity":{"company":args.company,"name":args.model,"version":args.version,"release_date":args.release_date},
              "evidence_policy":{"artificial_analysis":{"status":"unchecked"}},
              "sync_target":{"parent_doc":config["parent_doc"],"parent_wiki_node":config["parent_wiki_node"],
                             "vendor_heading":config["vendor_heading"],"allowed_link_hosts":config["allowed_link_hosts"],
                             "scope":args.scope.split(","),"permission_preflight":{"identity":"user_access_token","status":"pending",
                             "docx_read":False,"docx_read_write":False,"media_read_write":False,"sheets_read_write":False,"wiki_node_manage":False}},
              "target_status":{"A":"pending","B":"pending","C":"pending"},
              "parent_section":{"wiki_node":config["parent_wiki_node"],"vendor":config["vendor_heading"],
                                "model_entry":args.model_entry,"status":"pending"},
              "table_inventory":[],"related_tables":[],"screenshots":[],"screenshot_candidates":[],
              "child_wiki_doc":{"parent_node":config["parent_wiki_node"],"parent_node_token":config["parent_wiki_node"],
                                "node_token":"<pending>","obj_token":"<pending>","title":args.model_entry,"status":"pending","operation":"create"},
              "claims":[],"claim_coverage":{k:{"status":"pending"} for k in ("identity","availability","pricing","capabilities","benchmarks","release","community")},
              "business_analysis":new_business_analysis(getattr(args, "analysis_topics", "pricing,leaderboards").split(",")),
              "verification":{},"journal":[]}
    if not set(manifest["sync_target"]["scope"]) <= {"A","B","C"}:
        raise ValueError("scope must be comma-separated A,B,C")
    invalidate(manifest,"new run")
    directory.mkdir(parents=True)
    for name in ("images","html","pdf","evidence"):
        (directory/name).mkdir()
    path=directory/"update-manifest.json"
    atomic_json(path,manifest)
    return {"status":"prepared","manifest":str(path),"run_id":manifest["run_id"],"mode":manifest["mode"]}


def preflight(path, helper):
    manifest=read_json(path)
    parent=document_snapshot(helper,manifest["sync_target"]["parent_doc"])
    wiki=api_data(helper,"/open-apis/wiki/v2/spaces/get_node?token="+manifest["sync_target"]["parent_wiki_node"])["node"]
    if wiki.get("obj_token") != manifest["sync_target"]["parent_doc"]:
        raise ValueError("parent Wiki token does not resolve to configured parent document")
    inventory=embedded_sheets(parent["blocks"])
    previous={i["block_id"]:i for i in manifest["table_inventory"]}
    current=[]
    for bid,token in inventory.items():
        old=previous.get(bid,{})
        current.append(old if old.get("sheet_token")==token else {"block_id":bid,"sheet_token":token,"relevant":None,"reason":""})
    changed=digest(manifest["table_inventory"])!=digest(current)
    if changed:
        invalidate(manifest,"embedded Sheet inventory changed; classify every entry")
    manifest["table_inventory"]=current
    permissions=manifest["sync_target"]["permission_preflight"]
    permissions["docx_read"]=True
    missing=sorted(k for k in required_permissions(manifest) if permissions.get(k) is not True)
    manifest["preflight"]={"checked_at":utc_now(),"parent_revision":parent["metadata"]["revision_id"],
                           "snapshot_sha256":digest(parent),"missing_capabilities":missing,
                           "note":"read success does not establish write permission"}
    artifact=Path(path).parent/"evidence"/("preflight-"+digest(parent)+".json")
    atomic_json(artifact,parent)
    manifest["preflight"]["snapshot_file"]=str(artifact.relative_to(Path(path).parent))
    atomic_json(path,manifest)
    return {"status":"needs_capabilities" if missing else "read_preflight_pass","missing_capabilities":missing,
            "unclassified_sheets":[i["block_id"] for i in current if i["relevant"] is None],
            "parent_revision":parent["metadata"]["revision_id"]}


def capture_target(helper,manifest,target):
    if target=="C":
        token=manifest["child_wiki_doc"]["obj_token"]
    else:
        token=manifest["sync_target"]["parent_doc"]
    snapshot=document_snapshot(helper,token)
    if target=="B":
        return {"parent":snapshot,"tables":{t["block_id"]:read_table(helper,t) for t in manifest["related_tables"]}}
    return snapshot


def begin_write(path,helper,step_id,target,description):
    manifest=read_json(path)
    if manifest.get("mode")!="feishu_sync" or target not in manifest["sync_target"]["scope"]:
        raise ValueError("write outside explicit mode/scope")
    if any(j["step_id"]==step_id for j in manifest["journal"]):
        raise ValueError("step already exists; resume and reconcile instead of replaying it")
    permissions=manifest["sync_target"]["permission_preflight"]
    if permissions.get("status")!="complete" or any(permissions.get(k) is not True for k in required_permissions(manifest)):
        raise ValueError("required capabilities have not been verified")
    # A new child has no snapshot yet; parent snapshot protects the creation context.
    new_child=target=="C" and manifest["child_wiki_doc"]["obj_token"].startswith("<")
    before=capture_target(helper,manifest,"A" if new_child else target)
    manifest["mutation_generation"]+=1
    invalidate(manifest,"write started: "+step_id)
    manifest["journal"].append({"step_id":step_id,"target":target,"description":description,"state":"started",
                                "started_at":utc_now(),"before_sha256":digest(before)})
    atomic_json(path,manifest)
    return {"status":"journaled","step_id":step_id,"next":"perform the authorized Lark operation; save its receipt, then checkpoint"}


def checkpoint(path,helper,step_id,receipt_file,receipt_kind="operation"):
    manifest=read_json(path)
    matches=[j for j in manifest["journal"] if j["step_id"]==step_id]
    if len(matches)!=1 or matches[0]["state"]!="started":
        raise ValueError("checkpoint needs one started step")
    receipt=read_json(receipt_file)
    if receipt.get("ok") is not True and receipt.get("code")!=0:
        raise ValueError("receipt does not report an accepted operation")
    if receipt_kind not in {"operation","recovery_readback"}:
        raise ValueError("receipt_kind must distinguish original operation from recovery readback")
    entry=matches[0]
    after=capture_target(helper,manifest,entry["target"])
    artifact=Path(path).parent/"evidence"/("checkpoint-"+digest(after)+".json")
    atomic_json(artifact,after)
    saved_receipt=Path(path).parent/"evidence"/("receipt-"+digest(receipt)+".json")
    atomic_json(saved_receipt,receipt)
    entry.update(state="written",finished_at=utc_now(),after_sha256=digest(after),
                 receipt_kind=receipt_kind,
                 snapshot_file=str(artifact.relative_to(Path(path).parent)),
                 receipt_file=str(saved_receipt.relative_to(Path(path).parent)),receipt_sha256=file_digest(saved_receipt))
    atomic_json(path,manifest)
    return {"status":"checkpointed","step_id":step_id,"delivery_verified":False}


def resume(path,helper):
    manifest=read_json(path)
    steps=[]
    # Only the most recent write per target can match current content.
    latest={j["target"]:j["step_id"] for j in manifest.get("journal",[])}
    for step in manifest.get("journal",[]):
        state="uncertain_do_not_replay" if step["state"]=="started" else "superseded"
        if step["state"]!="started" and latest[step["target"]]==step["step_id"]:
            live=capture_target(helper,manifest,step["target"])
            state="already_written" if digest(live)==step.get("after_sha256") else "changed_reconcile"
        steps.append({"step_id":step["step_id"],"target":step["target"],"state":state})
    stale=[]
    for key in RESULT_KEYS.values():
        result=manifest.get("verification",{}).get(key,{})
        if result.get("status")=="pass" and result.get("manifest_input_sha256")!=input_digest(manifest):
            stale.append(key)
    # Resumption always requires fresh remote validation; cached pass is never returned as completion.
    invalidate(manifest,"resumed; fresh remote verification required")
    atomic_json(path,manifest)
    return {"status":"resume_plan","steps":steps,"invalidated_results":stale,
            "mode":manifest.get("mode"),"automatic_writes":0,"next":"reconcile uncertain steps, then verify"}


def live_recheck(helper,manifest,path):
    results={}
    for target,key in RESULT_KEYS.items():
        if target not in manifest["sync_target"]["scope"]:
            continue
        result=manifest["verification"][key]
        artifact=read_json(local_file(path,result["result_file"]))
        current=capture_target(helper,manifest,target)
        if digest(current)!=result["snapshot_sha256"]:
            raise RuntimeError(f"{target} changed since validator; rerun verification")
        if target in {"A","C"}:
            blocks={b["block_id"]:b for b in current["blocks"]}
            for bid,expected in artifact.get("image_hash_by_block",{}).items():
                token=blocks[bid]["image"]["token"]
                if hashlib.sha256(helper.download_media(token)).hexdigest()!=expected:
                    raise RuntimeError("media content changed after validation")
        if target=="C":
            wiki=api_data(helper,"/open-apis/wiki/v2/spaces/get_node?token="+manifest["child_wiki_doc"]["node_token"])["node"]
            if wiki.get("parent_node_token")!=manifest["sync_target"]["parent_wiki_node"] or wiki.get("obj_token")!=manifest["child_wiki_doc"]["obj_token"]:
                raise RuntimeError("child Wiki relationship changed")
        results[key]=result["result_sha256"]
    return {"status":"pass","checked_at":utc_now(),"manifest_input_sha256":input_digest(manifest),"results_sha256":digest(results)}


def verify(path,helper_path):
    manifest=read_json(path)
    if manifest.get("mode")!="feishu_sync":
        raise ValueError("explicit read_only run cannot execute delivery verification")
    if any(j.get("state")=="started" for j in manifest.get("journal",[])):
        raise ValueError("uncertain write remains; reconcile and checkpoint before verification")
    invalidate(manifest,"verification started")
    atomic_json(path,manifest)
    scope=set(manifest["sync_target"]["scope"])
    commands={
        "C":("child",["--doc",manifest["child_wiki_doc"]["node_token"],"--parent-node",manifest["sync_target"]["parent_wiki_node"]]),
        "A":("vendor",["--doc",manifest["sync_target"]["parent_doc"],"--vendor",manifest["parent_section"]["vendor"],"--model-entry",manifest["parent_section"]["model_entry"],"--require-social-visual-proof","--require-artificial-analysis"]),
        "B":("tables",[])}
    filenames={"child":"validate_child_document.py","vendor":"validate_vendor_section.py","tables":"validate_tables.py"}
    summary={}
    artifacts={}
    for target in ("C","A","B"):
        if target not in scope:
            continue
        kind,flags=commands[target]
        command=[sys.executable,"-B",str(ROOT/filenames[kind]),"--manifest",str(path),"--helper",str(helper_path),*flags]
        completed=subprocess.run(command,capture_output=True,text=True,timeout=900)
        try:
            result=json.loads(completed.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"{kind} validator did not return JSON (exit {completed.returncode})")
        record(path,kind,result)
        artifacts[target]={"snapshot": result.get("snapshot")}
        manifest=read_json(path)
        passed=result["status"]=="pass" and completed.returncode==0
        manifest["target_status"][target]="verified" if passed else "failed"
        if target=="A":
            manifest["parent_section"]["status"]="verified" if passed else "failed"
            manifest["verification"]["parent_readback"]=passed
        elif target=="C":
            manifest["child_wiki_doc"]["status"]="verified" if passed else "failed"
            manifest["verification"]["child_readback"]=passed
            manifest["verification"]["screenshots_checked"]=passed
        else:
            manifest["verification"]["tables_checked"]=passed
            by_id={t["block_id"]:t for t in result.get("tables",[])}
            for table in manifest["related_tables"]:
                if table["block_id"] in by_id:
                    for field in ("status","checked_rows","remaining_mismatches"):
                        table[field]=by_id[table["block_id"]][field]
        atomic_json(path,manifest)
        summary[target]={"status":result["status"],"violation_count":result["violation_count"]}
    if any(item["status"]!="pass" for item in summary.values()):
        return {"status":"fail","targets":summary,"delivery_complete":False}
    manifest=read_json(path)
    business_errors, business_warnings = validate_business(manifest, path, complete=True, artifacts=artifacts)
    if business_errors:
        return {"status":"fail","targets":summary,"business_analysis":{"status":"fail","errors":business_errors,"warnings":business_warnings},"delivery_complete":False}
    manifest["verification"]["freshness"]=live_recheck(load_helper(helper_path),manifest,path)
    atomic_json(path,manifest)
    from validate_update_manifest import ManifestValidator
    gate=ManifestValidator(Path(path),True).run()
    if gate["status"]!="pass":
        manifest["verification"].pop("freshness",None)
        atomic_json(path,manifest)
    return {"status":gate["status"],"targets":summary,"manifest_gate":gate,"delivery_complete":gate["status"]=="pass"}


def migrate(path,output):
    manifest=read_json(path)
    if manifest.get("schema_version")!=2 or Path(output).exists():
        raise ValueError("migration requires a v2 source and a new output path")
    manifest.update(schema_version=3,run_id=str(uuid.uuid4()),created_at=utc_now(),mutation_generation=0,mode="feishu_sync",
                    model_identity={},table_inventory=[],claims=[],claim_coverage={},journal=[],
                    migration={"source":str(Path(path).resolve()),"source_sha256":file_digest(path),"needs_review":True})
    manifest["sync_target"].setdefault("allowed_link_hosts",[])
    manifest["sync_target"]["permission_preflight"]["docx_read"]=False
    manifest["sync_target"]["permission_preflight"]["status"]="pending"
    manifest["child_wiki_doc"].setdefault("operation","update")
    invalidate(manifest,"v2 migrated; fill new fields and re-read remote evidence")
    atomic_json(output,manifest)
    return {"status":"migrated_needs_review","manifest":str(output),"old_file_unchanged":True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest="command",required=True)
    init=commands.add_parser("init")
    for flag in ("directory","targets","company","model","version","release-date","model-entry"):
        init.add_argument("--"+flag,required=True)
    init.add_argument("--scope",default="A,B,C"); init.add_argument("--read-only",action="store_true")
    init.add_argument("--analysis-topics",default="pricing,leaderboards",help="comma-separated pricing and/or leaderboards")
    for name in ("preflight","resume","verify","begin-write","checkpoint"):
        command=commands.add_parser(name); command.add_argument("--manifest",required=True); command.add_argument("--helper",required=True)
        if name in {"begin-write","checkpoint"}:
            command.add_argument("--step-id",required=True)
        if name=="begin-write":
            command.add_argument("--target",required=True,choices=["A","B","C"]); command.add_argument("--description",required=True)
        if name=="checkpoint":
            command.add_argument("--receipt-file",required=True)
            command.add_argument("--receipt-kind",choices=["operation","recovery_readback"],default="operation")
    migration=commands.add_parser("migrate"); migration.add_argument("--manifest",required=True); migration.add_argument("--output",required=True)
    args=parser.parse_args()
    try:
        if args.command=="init": result=initialize(args)
        elif args.command=="migrate": result=migrate(args.manifest,args.output)
        elif args.command=="verify": result=verify(Path(args.manifest).resolve(),Path(args.helper).resolve())
        else:
            path=Path(args.manifest).resolve(); helper=load_helper(args.helper)
            if args.command=="preflight": result=preflight(path,helper)
            elif args.command=="resume": result=resume(path,helper)
            elif args.command=="begin-write": result=begin_write(path,helper,args.step_id,args.target,args.description)
            else: result=checkpoint(path,helper,args.step_id,args.receipt_file,args.receipt_kind)
    except Exception as exc:
        result={"status":"fail","error_type":type(exc).__name__,"error":str(exc)}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 1 if result["status"] in {"fail","needs_capabilities"} else 0


if __name__=="__main__":
    sys.exit(main())
