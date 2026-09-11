"""Shared, standard-library-only evidence and readback contracts."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, unquote

SCHEMA_VERSION = 3
RESULT_KEYS = {"A": "vendor_validator", "B": "tables_validator", "C": "child_validator"}
SOURCE_CLASSES = {"official_page", "official_social", "github_or_model_repo", "independent_benchmark", "external_media_or_kol"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def parse_time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    return value


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as out:
            name = out.name
            json.dump(value, out, ensure_ascii=False, indent=2, allow_nan=False)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def local_file(manifest_path, value):
    path = Path(value).expanduser()
    path = path if path.is_absolute() else Path(manifest_path).resolve().parent / path
    path = path.resolve()
    path.relative_to(Path(manifest_path).resolve().parent)
    return path


def input_digest(manifest):
    """Exclude derived reports/status only; every plan/evidence change invalidates results."""
    value = copy.deepcopy(manifest)
    for key in ("verification", "target_status", "journal", "preflight", "migration"):
        value.pop(key, None)
    for key in ("parent_section", "child_wiki_doc"):
        if isinstance(value.get(key), dict):
            value[key].pop("status", None)
    for table in value.get("related_tables", []):
        if isinstance(table, dict):
            for key in ("status", "checked_rows", "remaining_mismatches", "readback"):
                table.pop(key, None)
    return digest(value)


def required_permissions(manifest):
    scope = set(manifest["sync_target"]["scope"])
    required = {"docx_read"} if scope else set()
    if scope & {"A", "C"}:
        required |= {"docx_read_write", "media_read_write"}
    if "B" in scope:
        required.add("sheets_read_write")
    if "C" in scope and manifest.get("child_wiki_doc", {}).get("operation") == "create":
        required.add("wiki_node_manage")
    return required


def load_helper(path):
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"helper does not exist: {path}")
    spec = importlib.util.spec_from_file_location("feishu_adapter", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ("api", "_all_blocks"):
        if not callable(getattr(module, name, None)):
            raise ValueError(f"helper missing {name}")
    return module


def api_data(helper, path):
    _, response = helper.api("GET", path)
    if not isinstance(response, dict) or response.get("code") != 0:
        raise RuntimeError(f"read failed for {path}: {response.get('code') if isinstance(response, dict) else 'invalid envelope'}")
    if not isinstance(response.get("data"), dict):
        raise RuntimeError("API response missing data object")
    return response["data"]


def document_meta(helper, token):
    doc = api_data(helper, f"/open-apis/docx/v1/documents/{token}").get("document", {})
    revision = doc.get("revision_id")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise RuntimeError("document revision_id missing; cannot establish a stable readback")
    return doc


def document_snapshot(helper, token):
    before = document_meta(helper, token)
    blocks = helper._all_blocks(token)
    after = document_meta(helper, token)
    if before != after:
        raise RuntimeError("document changed during block readback; retry from a fresh snapshot")
    ids = [b.get("block_id") for b in blocks]
    if not ids or None in ids or len(ids) != len(set(ids)):
        raise RuntimeError("incomplete or duplicate document blocks")
    by_id = {b["block_id"]: b for b in blocks}
    if token not in by_id or any(child not in by_id for b in blocks for child in b.get("children", [])):
        raise RuntimeError("document snapshot contains missing root/children")
    snapshot = {"document": token, "metadata": after, "blocks": sorted(blocks, key=lambda b: b["block_id"])}
    return snapshot


def assert_document_unchanged(helper, snapshot):
    if document_meta(helper, snapshot["document"]) != snapshot["metadata"]:
        raise RuntimeError("document changed during validation; old pass result is invalid")


def provenance(manifest, snapshot):
    return {"run_id": manifest["run_id"], "validated_at": utc_now(),
            "manifest_input_sha256": input_digest(manifest),
            "document_revision_id": snapshot["metadata"]["revision_id"],
            "snapshot_sha256": digest(snapshot)}


def linked_target(element, expected_doc, expected_wiki, allowed_hosts):
    """Match complete path tokens and an explicitly resolved tenant host."""
    mention = element.get("mention_doc", {})
    token = mention.get("token")
    url = mention.get("url") or element.get("text_run", {}).get("text_element_style", {}).get("link", {}).get("url")
    if token and token not in {expected_doc, expected_wiki}:
        return False
    if not url:
        return bool(token and token in {expected_doc, expected_wiki})
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in allowed_hosts or parsed.username or parsed.password:
        return False
    parts = unquote(parsed.path).strip("/").split("/")
    return len(parts) == 2 and ((parts[0] == "wiki" and parts[1] == expected_wiki) or (parts[0] == "docx" and parts[1] == expected_doc))


def invalidate(manifest, reason):
    for target in manifest["sync_target"]["scope"]:
        manifest["target_status"][target] = "pending"
    manifest["parent_section"]["status"] = "pending"
    manifest["child_wiki_doc"]["status"] = "pending"
    for key in RESULT_KEYS.values():
        manifest.setdefault("verification", {})[key] = {"status": "pending", "violation_count": None}
    for key in ("parent_readback", "tables_checked", "screenshots_checked", "child_readback"):
        manifest["verification"][key] = False
    manifest["verification"].pop("freshness", None)
    manifest["verification"]["invalidated_reason"] = reason


def result_binding_errors(result, manifest):
    errors = []
    if result.get("run_id") != manifest.get("run_id"):
        errors.append("validator run_id differs from current run")
    if result.get("manifest_input_sha256") != input_digest(manifest):
        errors.append("validator input hash is stale; rerun validation")
    for key in ("snapshot_sha256",):
        if not re.fullmatch(r"[0-9a-f]{64}", str(result.get(key, ""))):
            errors.append(f"validator {key} missing")
    if isinstance(result.get("document_revision_id"), bool) or not isinstance(result.get("document_revision_id"), int):
        errors.append("validator document_revision_id missing")
    try:
        if parse_time(result["validated_at"]) < parse_time(manifest["created_at"]):
            errors.append("validator result predates this run")
        if parse_time(result["validated_at"]) > parse_time(utc_now()):
            errors.append("validator result is dated in the future")
    except (KeyError, ValueError, TypeError):
        errors.append("validator validated_at missing/invalid")
    return errors
