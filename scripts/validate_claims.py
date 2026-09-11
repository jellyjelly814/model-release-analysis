"""Validate a claim ledger's evidence bindings; do not claim semantic fact checking."""
from __future__ import annotations
import argparse
import json
import sys
from urllib.parse import urlparse
from sync_common import file_digest, local_file, parse_time, read_json

KINDS = {"fact", "official_benchmark", "independent_benchmark", "external_opinion", "inference", "unknown"}
CONDITIONS = {"dataset_version", "harness", "tools", "sampling", "measured_at"}


def validate_claims(manifest, manifest_path, complete=False):
    errors, warnings = [], []
    claims = manifest.get("claims")
    coverage = manifest.get("claim_coverage")
    if not isinstance(claims, list) or not isinstance(coverage, dict):
        return ["claims array and claim_coverage object are required"], warnings
    if complete and not claims:
        errors.append("at least one sourced claim is required for delivery")
    ids = [c.get("id") for c in claims if isinstance(c, dict)]
    if len(ids) != len(claims) or len(ids) != len(set(ids)) or not all(isinstance(i,str) and i for i in ids):
        errors.append("claims need unique non-empty IDs")
    covered = set()
    for category, status in coverage.items():
        if not complete and isinstance(status, dict) and status.get("status") == "pending":
            continue
        if not isinstance(status, dict) or status.get("status") not in {"covered", "not_public", "not_applicable"}:
            errors.append(f"invalid coverage for {category}"); continue
        if status["status"] == "covered":
            bindings = status.get("claim_ids", [])
            if not bindings or not set(bindings) <= set(ids):
                errors.append(f"coverage {category} must bind existing claims")
            covered.update(bindings)
        elif not status.get("reason") or not status.get("checked_urls"):
            errors.append(f"coverage {category} needs checked sources and reason")
    for category in ("identity", "availability", "pricing", "capabilities", "benchmarks", "release", "community"):
        if category not in coverage:
            errors.append(f"claim_coverage missing {category}")
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        cid = claim.get("id", "?")
        if claim.get("kind") not in KINDS or not claim.get("statement"):
            errors.append(f"claim {cid}: kind and statement required")
        if claim.get("model_version") != manifest.get("model_identity", {}).get("version"):
            errors.append(f"claim {cid}: wrong model version")
        if claim.get("kind") == "inference" and (not claim.get("basis_claim_ids") or not set(claim["basis_claim_ids"]) <= (set(ids)-{cid})):
            errors.append(f"claim {cid}: inference needs other supporting claim IDs")
        sources = claim.get("sources", [])
        if claim.get("kind") not in {"unknown", "inference"} and not sources:
            errors.append(f"claim {cid}: original source required")
        for source in sources:
            parsed = urlparse(source.get("url", ""))
            if parsed.scheme not in {"https", "http"} or not parsed.hostname:
                errors.append(f"claim {cid}: source URL invalid")
            try:
                parse_time(source["retrieved_at"])
                if not source.get("locator"):
                    raise ValueError("missing page section / paragraph locator")
                if complete:
                    path = local_file(manifest_path, source["local_path"])
                    if file_digest(path) != source.get("content_sha256"):
                        raise ValueError("source cache hash mismatch")
            except (KeyError, ValueError, TypeError, OSError) as exc:
                errors.append(f"claim {cid}: source evidence incomplete: {exc}")
        if claim.get("kind") in {"official_benchmark", "independent_benchmark"}:
            conditions = claim.get("conditions", {})
            if not CONDITIONS <= set(conditions) or any(not conditions.get(k) for k in CONDITIONS):
                errors.append(f"claim {cid}: benchmark conditions must be explicit (use unknown when undisclosed)")
            if any(conditions.get(k) == "unknown" for k in CONDITIONS):
                warnings.append(f"claim {cid}: incomplete benchmark conditions; no precise ranking")
                if claim.get("comparable") is not False:
                    errors.append(f"claim {cid}: unknown conditions require comparable=false")
        if complete and claim.get("review_status") != "verified":
            errors.append(f"claim {cid}: source/statement alignment needs explicit review")
        if complete and not claim.get("placements"):
            errors.append(f"claim {cid}: must identify published target/block or sheet range")
        if complete:
            placements=claim.get("placements",[])
            scope=set(manifest.get("sync_target",{}).get("scope",[]))
            if not isinstance(placements,list) or not any(isinstance(p,dict) and p.get("target") in scope for p in placements):
                errors.append(f"claim {cid}: placement must include a target in the current scope")
            for placement in placements if isinstance(placements,list) else []:
                if not isinstance(placement,dict) or placement.get("target") not in {"A","B","C"} or not placement.get("block_id"):
                    errors.append(f"claim {cid}: invalid publication placement")
    if complete:
        errors.extend(f"claim {cid}: not assigned to coverage" for cid in set(ids)-covered)
    return errors, warnings


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",required=True); parser.add_argument("--require-complete",action="store_true")
    args=parser.parse_args()
    try:
        errors,warnings=validate_claims(read_json(args.manifest),args.manifest,args.require_complete)
    except Exception as exc:
        errors,warnings=[str(exc)],[]
    print(json.dumps({"status":"fail" if errors else "pass","violation_count":len(errors),"errors":errors,"warnings":warnings,
                      "semantic_accuracy":"requires source review; not established by this structural check"},ensure_ascii=False,indent=2))
    return bool(errors)


if __name__=="__main__":
    sys.exit(main())
