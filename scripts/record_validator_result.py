#!/usr/bin/env python3
"""Record an actual remote-validator JSON result in update-manifest.json.

The script is deliberately local-only: it reads a validator's captured JSON
output and updates the manifest.  It never calls Feishu, opens a URL, or
executes a helper.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


VALIDATORS = {
    "child": "child_validator",
    "vendor": "vendor_validator",
}


def load_json(path: str) -> dict[str, Any]:
    if path == "-":
        raw = sys.stdin.read()
    else:
        result_path = Path(path).expanduser()
        if not result_path.is_file():
            raise ValueError(f"result file does not exist: {result_path}")
        raw = result_path.read_text(encoding="utf-8")
    try:
        result = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"validator result is not valid JSON: {exc}") from exc
    if not isinstance(result, dict):
        raise ValueError("validator result root must be a JSON object")
    return result


def validate_result(result: dict[str, Any]) -> dict[str, Any]:
    status = result.get("status")
    violation_count = result.get("violation_count")
    if status not in {"pass", "fail"}:
        raise ValueError("validator result.status must be pass or fail")
    if isinstance(violation_count, bool) or not isinstance(violation_count, int) or violation_count < 0:
        raise ValueError("validator result.violation_count must be a non-negative integer")
    if status == "pass" and violation_count != 0:
        raise ValueError("validator result cannot be pass with non-zero violation_count")
    if status == "fail" and violation_count == 0:
        raise ValueError("validator result cannot be fail with violation_count 0")
    recorded: dict[str, Any] = {"status": status, "violation_count": violation_count}
    if "operational_error" in result:
        operational_error = result["operational_error"]
        if not isinstance(operational_error, bool):
            raise ValueError("validator result.operational_error must be boolean")
        if operational_error and status != "fail":
            raise ValueError("operational_error can only be true when status is fail")
        recorded["operational_error"] = operational_error
        for key in ("error_type", "error"):
            value = result.get(key)
            if operational_error and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"validator result.{key} is required for an operational error")
            if isinstance(value, str) and value.strip():
                recorded[key] = value
    return recorded


def atomic_write(path: Path, data: dict[str, Any]) -> None:
    path = path.expanduser()
    if not path.is_file():
        raise ValueError(f"manifest file does not exist: {path}")
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"manifest is not valid JSON: {exc}") from exc
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a captured validator JSON result in update-manifest.json")
    parser.add_argument("--manifest", required=True, help="Path to update-manifest.json")
    parser.add_argument("--validator", required=True, choices=sorted(VALIDATORS), help="Validator result to record")
    parser.add_argument("--result-file", required=True, help="Captured validator JSON file, or - for stdin")
    args = parser.parse_args()

    try:
        manifest_path = Path(args.manifest).expanduser()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("manifest root must be a JSON object")
        verification = manifest.get("verification")
        if not isinstance(verification, dict):
            raise ValueError("manifest.verification must be an object")
        recorded = validate_result(load_json(args.result_file))
        verification[VALIDATORS[args.validator]] = recorded
        atomic_write(manifest_path, manifest)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "fail", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps({"status": "pass", "manifest": str(manifest_path), "recorded": recorded}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
