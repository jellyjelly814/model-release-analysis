#!/usr/bin/env python3
"""Validate the v3 Feishu synchronization manifest without network access."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from sync_common import (SCHEMA_VERSION, SOURCE_CLASSES, required_permissions, input_digest, digest,
                         local_file, file_digest, result_binding_errors, parse_time, utc_now, read_json)
from validate_tables import plan_errors
from validate_claims import validate_claims
from validate_business_analysis import validate_business


TOP_LEVEL_REQUIRED = {
    "schema_version",
    "evidence_policy",
    "sync_target",
    "target_status",
    "parent_section",
    "related_tables",
    "screenshots",
    "child_wiki_doc",
    "verification",
}
SCREENSHOT_REQUIRED = {
    "id",
    "model_entry",
    "kind",
    "source_class",
    "source_url",
    "source_section",
    "source_original",
    "method",
    "local_path",
    "content_sha256",
    "parent_image_block",
    "child_image_block",
    "caption",
    "caption_block",
    "caption_before_image",
    "display_width",
    "display_height",
    "size_policy",
    "template_reference",
    "parent_placement",
    "child_placement",
    "visual_check",
    "status",
}
SCREENSHOT_KINDS = {
    "social",
    "artificial_analysis",
    "capability",
    "benchmark",
    "case",
    "pricing",
    "safety",
    "hero",
}
AA_STATUSES = {"available", "checked_unavailable", "not_applicable"}
TABLE_STATUSES = {"updated", "checked_no_change", "pending", "blocked", "failed"}
TARGET_STATUSES = {
    "updated",
    "checked_no_change",
    "pending",
    "blocked",
    "failed",
    "pass",
    "complete",
    "verified",
}
COMPLETE_STATUSES = {"pass", "complete", "updated", "checked_no_change", "verified"}
VALIDATOR_STATUSES = {"pending", "pass", "fail"}
PERMISSION_STATUSES = {"pending", "complete", "blocked", "failed"}
SCREENSHOT_STATUSES = {"pending", "verified", "rejected", "blocked"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def is_http_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def is_artificial_analysis_url(value: Any) -> bool:
    if not is_http_url(value):
        return False
    host = (urlparse(value).hostname or "").lower().rstrip(".")
    return host == "artificialanalysis.ai" or host.endswith(".artificialanalysis.ai")


def image_signature(path: Path) -> str | None:
    """Identify common web image formats by bytes, not by filename extension."""
    head = path.read_bytes()[:16]
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


class ManifestValidator:
    def __init__(self, manifest_path: Path, require_complete: bool) -> None:
        self.manifest_path = manifest_path
        self.require_complete = require_complete
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.data: dict[str, Any] = {}
        self.aa_status: str | None = None

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)

    def require_mapping(self, value: Any, name: str) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            self.error(f"{name} must be an object")
            return None
        return value

    def require_nonempty(self, obj: dict[str, Any], key: str, name: str) -> Any:
        value = obj.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            self.error(f"{name}.{key} is required and must be non-empty")
            return None
        return value

    @staticmethod
    def is_placeholder(value: Any) -> bool:
        if not isinstance(value, str):
            return True
        lowered = value.strip().lower()
        return (
            not lowered
            or (lowered.startswith("<") and lowered.endswith(">"))
            or lowered in {"todo", "tbd", "temporary", "uploaded", "not_used"}
        )

    def require_actual(self, obj: dict[str, Any], key: str, name: str) -> Any:
        value = self.require_nonempty(obj, key, name)
        if value is not None and self.require_complete and self.is_placeholder(value):
            self.error(f"{name}.{key} must contain an actual value in require-complete mode")
        return value

    def validate_schema(self) -> None:
        if self.data.get("schema_version") != SCHEMA_VERSION:
            self.error("schema_version must be 3; migrate old manifests and revalidate")

    def validate_evidence_policy(self) -> None:
        policy = self.require_mapping(self.data.get("evidence_policy"), "evidence_policy")
        if policy is None:
            return
        aa = self.require_mapping(policy.get("artificial_analysis"), "evidence_policy.artificial_analysis")
        if aa is None:
            return
        status = aa.get("status")
        if status == "unchecked" and not self.require_complete:
            self.aa_status = status
            return
        if status not in AA_STATUSES:
            self.error(
                "evidence_policy.artificial_analysis.status must be available, "
                "checked_unavailable, or not_applicable"
            )
            return
        self.aa_status = status
        if status in {"checked_unavailable", "not_applicable"}:
            checked_urls = aa.get("checked_urls")
            if not isinstance(checked_urls, list) or not checked_urls:
                self.error(
                    "evidence_policy.artificial_analysis.checked_urls must be a non-empty array "
                    f"when status is {status}"
                )
            elif not all(is_http_url(url) for url in checked_urls):
                self.error("evidence_policy.artificial_analysis.checked_urls must contain valid HTTP(S) URLs")
            self.require_actual(aa, "reason", "evidence_policy.artificial_analysis")
            alternatives = aa.get("alternatives")
            if not isinstance(alternatives, list) or not alternatives or not all(
                isinstance(item, str) and item.strip() for item in alternatives
            ):
                self.error(
                    "evidence_policy.artificial_analysis.alternatives must be a non-empty string array "
                    f"when status is {status}"
                )

    def validate_sync_target(self) -> None:
        target = self.require_mapping(self.data.get("sync_target"), "sync_target")
        if target is None:
            return
        for key in ("parent_doc", "parent_wiki_node", "vendor_heading", "scope", "permission_preflight"):
            if key not in target:
                self.error(f"sync_target.{key} is required")
        for key in ("parent_doc", "parent_wiki_node", "vendor_heading"):
            self.require_actual(target, key, "sync_target")
        if self.require_complete and isinstance(target.get("parent_wiki_node"), str) and target[
            "parent_wiki_node"
        ].startswith(("http://", "https://")):
            self.error("sync_target.parent_wiki_node must be the canonical parent node token, not a URL")
        scope = target.get("scope")
        if not isinstance(scope, list) or not scope or not all(item in {"A", "B", "C"} for item in scope):
            self.error("sync_target.scope must be a non-empty list containing only A, B, or C")
        elif len(scope) != len(set(scope)):
            self.error("sync_target.scope must not contain duplicates")
        permissions = self.require_mapping(target.get("permission_preflight"), "sync_target.permission_preflight")
        if permissions is None:
            return
        required = (
            "identity",
            "docx_read_write",
            "media_read_write",
            "sheets_read_write",
            "wiki_node_manage",
            "status",
        )
        for key in required:
            if key not in permissions:
                self.error(f"sync_target.permission_preflight.{key} is required")
        if permissions.get("status") not in PERMISSION_STATUSES:
            self.error("sync_target.permission_preflight.status must be pending, complete, blocked, or failed")
        if permissions.get("identity") != "user_access_token":
            self.error("sync_target.permission_preflight.identity must be user_access_token")
        boolean_keys = ("docx_read", "docx_read_write", "media_read_write", "sheets_read_write", "wiki_node_manage")
        for key in boolean_keys:
            if not isinstance(permissions.get(key), bool):
                self.error(f"sync_target.permission_preflight.{key} must be boolean")
        if self.require_complete:
            if permissions.get("status") != "complete":
                self.error("sync_target.permission_preflight.status must be complete in require-complete mode")
            for key in required_permissions(self.data):
                if permissions.get(key) is not True:
                    self.error(f"sync_target.permission_preflight.{key} must be true in require-complete mode")

    def validate_target_status(self) -> None:
        statuses = self.require_mapping(self.data.get("target_status"), "target_status")
        if statuses is None:
            return
        scope = self.data.get("sync_target", {}).get("scope", [])
        for target in ("A", "B", "C"):
            value = statuses.get(target)
            if not isinstance(value, str) or not value.strip():
                self.error(f"target_status.{target} is required and must be a non-empty string")
                continue
            if value not in TARGET_STATUSES:
                self.error(f"target_status.{target} is invalid: {value!r}")
            if self.require_complete and target in scope and value not in COMPLETE_STATUSES:
                self.error(f"target_status.{target} must be complete in require-complete mode")

    def validate_sections(self) -> None:
        parent = self.require_mapping(self.data.get("parent_section"), "parent_section")
        if parent is not None:
            for key in ("wiki_node", "vendor", "model_entry", "status"):
                self.require_actual(parent, key, "parent_section")
            if parent.get("status") not in TARGET_STATUSES:
                self.error(f"parent_section.status is invalid: {parent.get('status')!r}")
            if self.require_complete and "A" in self.data.get("sync_target", {}).get("scope", []):
                if parent.get("status") not in COMPLETE_STATUSES:
                    self.error("parent_section.status is not complete")

        tables = self.data.get("related_tables")
        if not isinstance(tables, list):
            self.error("related_tables must be an array")
            return
        for index, table in enumerate(tables):
            name = f"related_tables[{index}]"
            item = self.require_mapping(table, name)
            if item is None:
                continue
            for key in ("block_id", "header", "reason", "status"):
                if key not in item:
                    self.error(f"{name}.{key} is required")
            if not isinstance(item.get("header"), list) or not item.get("header") or not all(
                isinstance(header, str) and header.strip() for header in item.get("header", [])
            ):
                self.error(f"{name}.header must be a non-empty string array")
            if self.require_complete:
                self.require_actual(item, "block_id", name)
                self.require_actual(item, "reason", name)
            if item.get("status") not in TABLE_STATUSES:
                self.error(f"{name}.status is invalid")
            if self.require_complete and "B" in self.data.get("sync_target", {}).get("scope", []):
                if item.get("status") not in {"updated", "checked_no_change"}:
                    self.error(f"{name}.status must be updated or checked_no_change")
            for key in ("checked_rows", "remaining_mismatches"):
                if self.require_complete and "B" in self.data.get("sync_target", {}).get("scope", []) and key not in item:
                    self.error(f"{name}.{key} is required for a completed table")
                if key in item and (
                    isinstance(item[key], bool) or not isinstance(item[key], int) or item[key] < 0
                ):
                    self.error(f"{name}.{key} must be a non-negative integer")
            if self.require_complete and item.get("remaining_mismatches") != 0 and "B" in self.data.get("sync_target", {}).get("scope", []):
                self.error(f"{name}.remaining_mismatches must be 0")

    def validate_screenshot(
        self,
        screenshot: Any,
        index: int,
        seen_ids: set[str],
        seen_blocks: set[str],
        seen_paths: set[str],
        seen_hashes: set[str],
    ) -> None:
        name = f"screenshots[{index}]"
        item = self.require_mapping(screenshot, name)
        if item is None:
            return
        for key in sorted(SCREENSHOT_REQUIRED - item.keys()):
            self.error(f"{name}.{key} is required")

        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id.strip():
            self.error(f"{name}.id must be non-empty")
        elif item_id in seen_ids:
            self.error(f"{name}.id is duplicated: {item_id}")
        else:
            seen_ids.add(item_id)

        kind = item.get("kind")
        if kind not in SCREENSHOT_KINDS:
            self.error(f"{name}.kind is invalid: {kind!r}")
        if not is_http_url(item.get("source_url")):
            self.error(f"{name}.source_url must be a valid HTTP(S) URL")
        for key in (
            "model_entry",
            "source_class",
            "source_section",
            "source_original",
            "method",
            "caption",
            "size_policy",
            "template_reference",
        ):
            self.require_actual(item, key, name)

        model_entry = self.data.get("parent_section", {}).get("model_entry")
        if isinstance(model_entry, str) and item.get("model_entry") != model_entry:
            self.error(f"{name}.model_entry must match parent_section.model_entry")

        parent_block = item.get("parent_image_block")
        child_block = item.get("child_image_block")
        for key, value in (("parent_image_block", parent_block), ("child_image_block", child_block)):
            if value is not None and self.is_placeholder(value):
                self.error(f"{name}.{key} must be null or an actual block ID")
            elif isinstance(value, str):
                if value in seen_blocks:
                    self.error(f"{name}.{key} is duplicated: {value}")
                else:
                    seen_blocks.add(value)
        if parent_block and child_block and parent_block == child_block:
            self.error(f"{name} parent and child image blocks must be different")
        scope = set(self.data["sync_target"]["scope"])
        if kind == "social":
            if "A" in scope and self.is_placeholder(parent_block):
                self.error(f"{name} social evidence requires parent_image_block for scope A")
            if "C" in scope and self.is_placeholder(child_block):
                self.error(f"{name} social evidence requires child_image_block for scope C")
        if kind == "artificial_analysis" and self.is_placeholder(child_block):
            self.error(f"{name} Artificial Analysis evidence requires child_image_block")
        if self.require_complete and self.is_placeholder(parent_block) and self.is_placeholder(child_block):
            self.error(f"{name} must reference at least one actual Feishu image block")
        if not self.is_placeholder(parent_block):
            self.require_actual(item, "parent_placement", name)
        if not self.is_placeholder(child_block):
            self.require_actual(item, "child_placement", name)

        local_path = item.get("local_path")
        path: Path | None = None
        if self.is_placeholder(local_path):
            self.error(f"{name}.local_path must be an actual local file path")
        else:
            path = Path(local_path)
            if not path.is_absolute():
                path = self.manifest_path.parent / path
            resolved = path.resolve()
            research_root = self.manifest_path.parent.resolve()
            try:
                resolved.relative_to(research_root)
            except ValueError:
                message = f"{name}.local_path must stay inside the research folder: {research_root}"
                self.error(message) if self.require_complete else self.warning(message)
            normalized = str(resolved)
            if normalized in seen_paths:
                self.error(f"{name}.local_path is duplicated: {local_path}")
            else:
                seen_paths.add(normalized)
            if not path.is_file():
                message = f"{name}.local_path does not point to a readable local file: {path}"
                self.error(message) if self.require_complete else self.warning(message)

        declared_hash = item.get("content_sha256")
        if not isinstance(declared_hash, str) or not SHA256_RE.fullmatch(declared_hash.lower()):
            self.error(f"{name}.content_sha256 must be a 64-character hexadecimal SHA-256")
        elif declared_hash.lower() in seen_hashes:
            self.error(f"{name}.content_sha256 duplicates another screenshot: {declared_hash.lower()}")
        else:
            seen_hashes.add(declared_hash.lower())
        if path is not None and path.is_file():
            if image_signature(path) is None:
                self.error(f"{name}.local_path is not a supported image by file signature")
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            if isinstance(declared_hash, str) and actual_hash != declared_hash.lower():
                self.error(f"{name}.content_sha256 does not match local_path")

        if item.get("source_class") not in SOURCE_CLASSES:
            self.error(f"{name}.source_class must be an allowed evidence category")
        if self.require_complete and item.get("child_placement") != "opening_evidence_wall":
            self.require_actual(item, "caption_block", name)
        if not isinstance(item.get("caption_before_image"), bool):
            self.error(f"{name}.caption_before_image must be boolean")
        elif self.require_complete and item.get("child_placement") != "opening_evidence_wall" and not parent_block and item["caption_before_image"] is not True:
            self.error(f"{name}.caption_before_image must be true in require-complete mode")
        for key in ("display_width", "display_height"):
            value = item.get(key)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0
            ):
                self.error(f"{name}.{key} must be a non-negative number or null")

        visual = self.require_mapping(item.get("visual_check"), f"{name}.visual_check")
        if visual is not None:
            for key in ("status", "verification_method"):
                self.require_nonempty(visual, key, f"{name}.visual_check")
            if kind in {"social", "artificial_analysis"} and visual.get("blank") is not False:
                self.error(f"{name}.visual_check.blank must be false for {kind}")
            if kind == "social":
                if visual.get("login_wall") is not False:
                    self.error(f"{name}.visual_check.login_wall must be false for social")
                if visual.get("complete_post") is not True:
                    self.error(f"{name}.visual_check.complete_post must be true for social")
            if self.require_complete and (
                visual.get("status") != "verified" or visual.get("verification_method") != "view_image"
            ):
                self.error(f"{name}.visual_check must be verified with view_image")
        if item.get("status") not in SCREENSHOT_STATUSES:
            self.error(f"{name}.status must be pending, verified, rejected, or blocked")
        elif self.require_complete and item.get("status") != "verified":
            self.error(f"{name}.status must be verified")
        if kind == "artificial_analysis":
            if item.get("source_class") != "independent_benchmark":
                self.error(f"{name}.source_class must be independent_benchmark")
            if not is_artificial_analysis_url(item.get("source_url")):
                self.error(f"{name}.source_url must point to artificialanalysis.ai")

    def validate_screenshots(self) -> None:
        screenshots = self.data.get("screenshots")
        if not isinstance(screenshots, list):
            self.error("screenshots must be an array")
            return
        seen_ids: set[str] = set()
        seen_blocks: set[str] = set()
        seen_paths: set[str] = set()
        seen_hashes: set[str] = set()
        for index, screenshot in enumerate(screenshots):
            self.validate_screenshot(screenshot, index, seen_ids, seen_blocks, seen_paths, seen_hashes)

        aa = [item for item in screenshots if isinstance(item, dict) and item.get("kind") == "artificial_analysis"]
        if self.aa_status == "available" and "C" in self.data.get("sync_target", {}).get("scope", []):
            if len(aa) < 2:
                self.error("available Artificial Analysis evidence requires at least two screenshots")
            if len({item.get("source_section") for item in aa}) < 2:
                self.error("Artificial Analysis screenshots must use at least two distinct source_section values")
            if len({item.get("child_image_block") for item in aa if item.get("child_image_block")}) < 2:
                self.error("Artificial Analysis screenshots must use at least two distinct child_image_block values")
            if len({item.get("content_sha256") for item in aa if item.get("content_sha256")}) < 2:
                self.error("Artificial Analysis screenshots must use at least two distinct content_sha256 values")
        elif self.aa_status in {"checked_unavailable", "not_applicable"} and aa:
            self.error(
                "Artificial Analysis screenshots conflict with evidence_policy status "
                f"{self.aa_status}"
            )

        candidates = self.data.get("screenshot_candidates", [])
        if not isinstance(candidates, list):
            self.error("screenshot_candidates must be an array when present")
            return
        for index, candidate in enumerate(candidates):
            name = f"screenshot_candidates[{index}]"
            item = self.require_mapping(candidate, name)
            if item is None:
                continue
            for key in ("id", "source_url", "reason", "status"):
                self.require_nonempty(item, key, name)
            if not is_http_url(item.get("source_url")):
                self.error(f"{name}.source_url must be a valid HTTP(S) URL")
            if item.get("status") not in {"pending", "manual_screenshot_required"}:
                self.error(f"{name}.status must be pending or manual_screenshot_required")
            if any(key in item for key in ("image_block", "parent_image_block", "child_image_block")):
                self.error(f"{name} must not contain image block IDs; candidates are not completed screenshots")

    def validate_child_doc(self) -> None:
        child = self.require_mapping(self.data.get("child_wiki_doc"), "child_wiki_doc")
        if child is None:
            return
        for key in ("parent_node", "node_token", "obj_token", "parent_node_token", "title", "status"):
            if self.require_complete and key in {"node_token", "obj_token", "title"} and not set(self.data["sync_target"]["scope"]) & {"A", "C"}:
                continue
            self.require_actual(child, key, "child_wiki_doc")
        if self.require_complete and "C" in self.data.get("sync_target", {}).get("scope", []):
            for key in ("parent_node", "parent_node_token"):
                value = child.get(key)
                if isinstance(value, str) and value.startswith(("http://", "https://")):
                    self.error(f"child_wiki_doc.{key} must be the canonical parent node token, not a URL")
        if child.get("status") not in TARGET_STATUSES:
            self.error(f"child_wiki_doc.status is invalid: {child.get('status')!r}")
        if self.require_complete and "C" in self.data.get("sync_target", {}).get("scope", []):
            if child.get("status") not in COMPLETE_STATUSES:
                self.error("child_wiki_doc.status is not complete")

    def validate_validator_result(
        self,
        verification: dict[str, Any],
        key: str,
        must_complete: bool,
    ) -> dict[str, Any] | None:
        name = f"verification.{key}"
        result = self.require_mapping(verification.get(key), name)
        if result is None:
            return None
        status = result.get("status")
        count = result.get("violation_count")
        if status not in VALIDATOR_STATUSES:
            self.error(f"{name}.status must be pending, pass, or fail")
        if count is not None and (isinstance(count, bool) or not isinstance(count, int) or count < 0):
            self.error(f"{name}.violation_count must be a non-negative integer or null")
        if status == "pending" and count is not None:
            self.error(f"{name} cannot be pending with a violation_count")
        if status == "pass" and count != 0:
            self.error(f"{name} cannot be pass without violation_count 0")
        if status == "fail" and (isinstance(count, bool) or not isinstance(count, int) or count <= 0):
            self.error(f"{name} cannot be fail without a positive violation_count")
        if "operational_error" in result:
            operational_error = result.get("operational_error")
            if not isinstance(operational_error, bool):
                self.error(f"{name}.operational_error must be boolean")
            elif operational_error:
                if status != "fail":
                    self.error(f"{name}.operational_error can only be true when status is fail")
                for detail in ("error_type", "error"):
                    if not isinstance(result.get(detail), str) or not result[detail].strip():
                        self.error(f"{name}.{detail} is required for an operational error")
        if must_complete and (status != "pass" or count != 0):
            self.error(f"{name} must be pass with violation_count 0")
        return result

    def validate_verification(self) -> None:
        verification = self.require_mapping(self.data.get("verification"), "verification")
        if verification is None:
            return
        scope = set(self.data.get("sync_target", {}).get("scope", []))
        required_readbacks = {
            "parent_readback": "A",
            "tables_checked": "B",
            "screenshots_checked": "C",
            "child_readback": "C",
        }
        for key in ("parent_readback", "tables_checked", "screenshots_checked", "child_readback"):
            if not isinstance(verification.get(key), bool):
                self.error(f"verification.{key} must be boolean")
            elif self.require_complete and required_readbacks[key] in scope and verification[key] is not True:
                self.error(f"verification.{key} must be true in require-complete mode")
        child_result = self.validate_validator_result(verification, "child_validator", self.require_complete and "C" in scope)
        vendor_result = self.validate_validator_result(verification, "vendor_validator", self.require_complete and "A" in scope)
        if not self.require_complete:
            return
        parent = self.data.get("parent_section", {})
        child = self.data.get("child_wiki_doc", {})
        target = self.data.get("sync_target", {})
        if isinstance(child_result, dict) and child_result.get("status") == "pass":
            expected = {
                "document": child.get("obj_token"),
                "wiki_node": child.get("node_token"),
                "parent_node": child.get("parent_node_token"),
                "model_entry": parent.get("model_entry"),
            }
            for key, value in expected.items():
                if child_result.get(key) != value:
                    self.error(f"verification.child_validator.{key} must match the manifest target")
        if isinstance(vendor_result, dict) and vendor_result.get("status") == "pass":
            expected = {
                "document": target.get("parent_doc"),
                "vendor": parent.get("vendor"),
                "model_entry": parent.get("model_entry"),
            }
            for key, value in expected.items():
                if vendor_result.get(key) != value:
                    self.error(f"verification.vendor_validator.{key} must match the manifest target")
            if vendor_result.get("validation_scope") != "current_entry":
                self.error("verification.vendor_validator.validation_scope is required")

    def validate_cross_consistency(self) -> None:
        statuses = self.data.get("target_status")
        if not isinstance(statuses, dict):
            return
        parent = self.data.get("parent_section")
        target = self.data.get("sync_target")
        child = self.data.get("child_wiki_doc")
        verification = self.data.get("verification")
        if isinstance(parent, dict) and isinstance(target, dict):
            if parent.get("wiki_node") != target.get("parent_wiki_node"):
                self.error("parent_section.wiki_node must match sync_target.parent_wiki_node")
        scope = set(target.get("scope", [])) if isinstance(target, dict) else set()
        if statuses.get("A") in COMPLETE_STATUSES and "A" in scope and isinstance(parent, dict):
            if parent.get("status") not in COMPLETE_STATUSES:
                self.error("target_status.A is complete but parent_section.status is not complete")
        tables = self.data.get("related_tables")
        if statuses.get("B") in COMPLETE_STATUSES and "B" in scope and isinstance(tables, list):
            incomplete = [
                index
                for index, table in enumerate(tables)
                if not isinstance(table, dict) or table.get("status") not in {"updated", "checked_no_change"}
            ]
            if incomplete:
                self.error(f"target_status.B is complete but related_tables are incomplete: {incomplete}")
        if isinstance(child, dict) and isinstance(target, dict):
            expected_parent = target.get("parent_wiki_node")
            if child.get("parent_node") != expected_parent:
                self.error("child_wiki_doc.parent_node must match sync_target.parent_wiki_node")
            if child.get("parent_node_token") != expected_parent:
                self.error("child_wiki_doc.parent_node_token must match sync_target.parent_wiki_node")
        if statuses.get("C") in COMPLETE_STATUSES and "C" in scope:
            if not isinstance(child, dict) or child.get("status") not in COMPLETE_STATUSES:
                self.error("target_status.C is complete but child_wiki_doc.status is not complete")
            child_validator = verification.get("child_validator") if isinstance(verification, dict) else None
            if not isinstance(child_validator, dict) or child_validator.get("status") != "pass" or child_validator.get(
                "violation_count"
            ) != 0:
                self.error("target_status.C is complete but child_validator is not pass with violation_count 0")

    def validate_v3_evidence(self):
        for key in ("run_id", "created_at", "mode", "model_identity", "mutation_generation", "table_inventory"):
            if key not in self.data:
                self.error(f"v3 field is required: {key}")
        if self.data.get("mode") not in {"feishu_sync", "read_only"}:
            self.error("mode must be feishu_sync or explicit read_only")
        if self.require_complete and self.data.get("mode") != "feishu_sync":
            self.error("read_only runs cannot claim Feishu delivery complete")
        target = self.data.get("sync_target", {})
        hosts = target.get("allowed_link_hosts")
        if not isinstance(hosts, list) or not hosts or any(not isinstance(h,str) or not re.fullmatch(r"[a-z0-9.-]+",h) for h in hosts):
            self.error("sync_target.allowed_link_hosts must contain currently resolved tenant hosts")
        if not isinstance(self.data.get("model_identity"),dict) or not all(self.data["model_identity"].get(k) for k in ("company","name","version","release_date")):
            self.error("model_identity requires company, name, version and release_date")
        try:
            parse_time(self.data["created_at"])
        except (KeyError, TypeError, ValueError):
            self.error("created_at must be a timezone-aware timestamp")
        scope = set(target.get("scope", []))
        if "B" in scope and (self.require_complete or self.data.get("related_tables")):
            self.errors.extend(plan_errors(self.data))
        claim_errors, claim_warnings = validate_claims(self.data, self.manifest_path, self.require_complete)
        self.errors.extend(claim_errors); self.warnings.extend(claim_warnings)
        if not self.require_complete:
            return
        verification = self.data.get("verification", {})
        results = {}
        artifacts = {}
        for label, key in (("A","vendor_validator"),("B","tables_validator"),("C","child_validator")):
            if label not in scope:
                continue
            result = verification.get(key, {})
            if result.get("status") != "pass" or result.get("violation_count") != 0:
                self.error(f"verification.{key} must pass with zero violations")
            self.errors.extend(f"{key}: {message}" for message in result_binding_errors(result, self.data))
            if result.get("audit_only"):
                self.error(f"{key}: structural audit cannot establish delivery")
            try:
                path = local_file(self.manifest_path, result["result_file"])
                if file_digest(path) != result.get("result_sha256"):
                    raise ValueError("result file hash mismatch")
                artifact = read_json(path)
                artifacts[label] = artifact
                for field, value in result.items():
                    if field not in {"result_file", "result_sha256"} and artifact.get(field) != value:
                        raise ValueError(f"recorded field differs from original result: {field}")
                if digest(artifact["snapshot"]) != result.get("snapshot_sha256"):
                    raise ValueError("snapshot hash mismatch")
                if label == "B":
                    tables = {t["block_id"]:t for t in artifact["tables"]}
                    if set(tables) != {t["block_id"] for t in self.data["related_tables"]}:
                        raise ValueError("table result coverage differs from manifest")
                    for table in self.data["related_tables"]:
                        for field in ("status","checked_rows","remaining_mismatches"):
                            if table.get(field) != tables[table["block_id"]].get(field):
                                raise ValueError(f"table {field} differs from validator readback")
                results[key] = result["result_sha256"]
            except (KeyError, ValueError, TypeError, OSError) as exc:
                self.error(f"{key}: missing or inconsistent readback artifact: {exc}")
        for claim in self.data.get("claims", []):
            for placement in claim.get("placements", []):
                if not isinstance(placement, dict):
                    continue
                target_label = placement.get("target")
                if target_label not in scope or target_label not in artifacts:
                    continue
                artifact = artifacts[target_label]
                if target_label in {"A", "C"}:
                    ids = {b["block_id"] for b in artifact["snapshot"]["blocks"]}
                    if placement.get("block_id") not in ids:
                        self.error(f"claim {claim.get('id')}: placement block missing from live snapshot")
                else:
                    table = artifact["snapshot"]["tables"].get(placement.get("block_id"))
                    if not table or placement.get("range") not in table["ranges"]:
                        self.error(f"claim {claim.get('id')}: placement Sheet/range missing from validated readback")
        freshness = verification.get("freshness", {})
        if freshness.get("status") != "pass" or freshness.get("manifest_input_sha256") != input_digest(self.data) or freshness.get("results_sha256") != digest(results):
            self.error("fresh live recheck is missing or bound to different inputs/results; run sync_run.py verify")
        try:
            age = (parse_time(utc_now()) - parse_time(freshness["checked_at"])).total_seconds()
            if not 0 <= age <= 900:
                self.error("live recheck older than 15 minutes or dated in the future; rerun verify")
        except (KeyError, ValueError, TypeError):
            self.error("freshness.checked_at missing/invalid")

    def run(self) -> dict[str, Any]:
        if not self.manifest_path.is_file():
            self.error(f"manifest file does not exist: {self.manifest_path}")
            return self.output()
        try:
            loaded = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            self.error(f"cannot read valid JSON manifest: {type(exc).__name__}: {exc}")
            return self.output()
        if not isinstance(loaded, dict):
            self.error("manifest root must be a JSON object")
            return self.output()
        self.data = loaded
        for key in sorted(TOP_LEVEL_REQUIRED - self.data.keys()):
            self.error(f"top-level field is required: {key}")
        self.validate_schema()
        self.validate_evidence_policy()
        self.validate_sync_target()
        self.validate_target_status()
        self.validate_sections()
        self.validate_screenshots()
        self.validate_child_doc()
        self.validate_verification()
        self.validate_cross_consistency()
        self.validate_v3_evidence()
        business_errors, business_warnings = validate_business(self.data, self.manifest_path, self.require_complete)
        self.errors.extend(business_errors)
        self.warnings.extend(business_warnings)
        return self.output()

    def output(self) -> dict[str, Any]:
        return {
            "status": "pass" if not self.errors else "fail",
            "manifest": str(self.manifest_path),
            "mode": "require-complete" if self.require_complete else "structure",
            "schema_version": self.data.get("schema_version") if self.data else None,
            "error_count": len(self.errors),
            "violation_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": self.errors,
            "warnings": self.warnings,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a v3 update-manifest.json without external calls")
    parser.add_argument("--manifest", required=True, help="Path to update-manifest.json")
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Require completed Feishu readbacks, valid image files, matching hashes, and passing validators",
    )
    args = parser.parse_args()
    try:
        result = ManifestValidator(Path(args.manifest).expanduser(), args.require_complete).run()
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        result = {"status": "fail", "error_count": 1, "violation_count": 1, "errors": [f"invalid manifest shape: {exc}"]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
