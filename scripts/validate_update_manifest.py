#!/usr/bin/env python3
"""Validate update-manifest.json without contacting external services.

The script checks the manifest contract documented in SKILL.md.  It has two
modes: the default structural check, and --require-complete for the final
feishu_sync gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urlparse
from pathlib import Path
from typing import Any


TOP_LEVEL_REQUIRED = {
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
    "kind",
    "source_class",
    "source_url",
    "source_section",
    "source_original",
    "method",
    "local_path",
    "image_block",
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


def is_artificial_analysis_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    return parsed.scheme in {"http", "https"} and (
        host == "artificialanalysis.ai" or host.endswith(".artificialanalysis.ai")
    )


class ManifestValidator:
    def __init__(self, manifest_path: Path, require_complete: bool) -> None:
        self.manifest_path = manifest_path
        self.require_complete = require_complete
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.data: dict[str, Any] = {}

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
            or lowered in {"todo", "tbd", "temporary", "uploaded"}
        )

    def require_actual(self, obj: dict[str, Any], key: str, name: str) -> Any:
        value = self.require_nonempty(obj, key, name)
        if value is not None and self.require_complete and self.is_placeholder(value):
            self.error(f"{name}.{key} must contain an actual value in require-complete mode")
        return value

    def validate_sync_target(self) -> None:
        target = self.require_mapping(self.data.get("sync_target"), "sync_target")
        if target is None:
            return
        for key in ("parent_doc", "parent_wiki_node", "vendor_heading", "scope", "permission_preflight"):
            if key not in target:
                self.error(f"sync_target.{key} is required")
        for key in ("parent_doc", "parent_wiki_node", "vendor_heading"):
            self.require_actual(target, key, "sync_target")
        if self.require_complete and isinstance(target.get("parent_wiki_node"), str) and target["parent_wiki_node"].startswith(("http://", "https://")):
            self.error("sync_target.parent_wiki_node must be the canonical parent node token, not a URL")
        scope = target.get("scope")
        if not isinstance(scope, list) or not scope or not all(item in {"A", "B", "C"} for item in scope):
            self.error("sync_target.scope must be a non-empty list containing only A, B, or C")
        elif self.require_complete and set(scope) != {"A", "B", "C"}:
            self.error("sync_target.scope must contain A, B, and C in require-complete mode")
        permissions = self.require_mapping(target.get("permission_preflight"), "sync_target.permission_preflight")
        if permissions is None:
            return
        for key in ("identity", "docx_read_write", "media_read_write", "sheets_read_write", "wiki_node_manage", "status"):
            if key not in permissions:
                self.error(f"sync_target.permission_preflight.{key} is required")
        if permissions.get("status") not in PERMISSION_STATUSES:
            self.error(
                "sync_target.permission_preflight.status must be pending, complete, blocked, or failed"
            )
        if permissions.get("identity") != "user_access_token":
            self.error("sync_target.permission_preflight.identity must be user_access_token")
        boolean_keys = ("docx_read_write", "media_read_write", "sheets_read_write", "wiki_node_manage")
        for key in boolean_keys:
            if not isinstance(permissions.get(key), bool):
                self.error(f"sync_target.permission_preflight.{key} must be boolean")
        if self.require_complete:
            if permissions.get("status") not in COMPLETE_STATUSES:
                self.error("sync_target.permission_preflight.status must be complete in require-complete mode")
            for key in boolean_keys:
                if permissions.get(key) is not True:
                    self.error(f"sync_target.permission_preflight.{key} must be true in require-complete mode")

    def validate_target_status(self) -> None:
        statuses = self.require_mapping(self.data.get("target_status"), "target_status")
        if statuses is None:
            return
        for target in ("A", "B", "C"):
            value = statuses.get(target)
            if not isinstance(value, str) or not value.strip():
                self.error(f"target_status.{target} is required and must be a non-empty string")
                continue
            if value not in TARGET_STATUSES:
                self.error(f"target_status.{target} is invalid: {value!r}")
            if self.require_complete and value not in COMPLETE_STATUSES:
                self.error(f"target_status.{target} must be complete in require-complete mode")

    def validate_sections(self) -> None:
        parent = self.require_mapping(self.data.get("parent_section"), "parent_section")
        if parent is not None:
            for key in ("wiki_node", "vendor", "model_entry", "status"):
                self.require_actual(parent, key, "parent_section")
            if parent.get("status") not in TARGET_STATUSES:
                self.error(f"parent_section.status is invalid: {parent.get('status')!r}")
            if self.require_complete and parent.get("status") not in COMPLETE_STATUSES:
                self.error("parent_section.status is not complete")

        tables = self.data.get("related_tables")
        if not isinstance(tables, list):
            self.error("related_tables must be an array")
        else:
            for index, table in enumerate(tables):
                name = f"related_tables[{index}]"
                table_obj = self.require_mapping(table, name)
                if table_obj is None:
                    continue
                for key in ("block_id", "header", "reason", "status"):
                    if key not in table_obj:
                        self.error(f"{name}.{key} is required")
                if not isinstance(table_obj.get("header"), list) or not table_obj.get("header"):
                    self.error(f"{name}.header must be a non-empty array")
                elif not all(isinstance(header, str) and header.strip() for header in table_obj["header"]):
                    self.error(f"{name}.header must contain non-empty strings")
                if self.require_complete:
                    self.require_actual(table_obj, "block_id", name)
                    self.require_actual(table_obj, "reason", name)
                if table_obj.get("status") not in TABLE_STATUSES:
                    self.error(f"{name}.status is invalid")
                if self.require_complete and table_obj.get("status") not in {"updated", "checked_no_change"}:
                    self.error(f"{name}.status must be updated or checked_no_change")
                if "checked_rows" in table_obj and (
                    isinstance(table_obj["checked_rows"], bool)
                    or not isinstance(table_obj["checked_rows"], int)
                    or table_obj["checked_rows"] < 0
                ):
                    self.error(f"{name}.checked_rows must be a non-negative integer")
                if "remaining_mismatches" in table_obj and (
                    isinstance(table_obj["remaining_mismatches"], bool)
                    or not isinstance(table_obj["remaining_mismatches"], int)
                    or table_obj["remaining_mismatches"] < 0
                ):
                    self.error(f"{name}.remaining_mismatches must be a non-negative integer")
                if self.require_complete and "remaining_mismatches" in table_obj and table_obj["remaining_mismatches"] != 0:
                    self.error(f"{name}.remaining_mismatches must be 0")

    def validate_screenshot(self, screenshot: Any, index: int, seen_ids: set[str], seen_blocks: set[str], seen_paths: set[str]) -> None:
        name = f"screenshots[{index}]"
        item = self.require_mapping(screenshot, name)
        if item is None:
            return
        missing = sorted(SCREENSHOT_REQUIRED - item.keys())
        for key in missing:
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
        source_url = item.get("source_url")
        if not isinstance(source_url, str) or not source_url.startswith(("http://", "https://")):
            self.error(f"{name}.source_url must start with http:// or https://")
        screenshot_text_fields = (
            "source_class",
            "source_section",
            "source_original",
            "method",
            "caption",
            "caption_block",
            "size_policy",
            "template_reference",
            "parent_placement",
            "child_placement",
        )
        for key in screenshot_text_fields:
            if self.require_complete or key in {"source_original", "caption_block", "template_reference"}:
                self.require_actual(item, key, name)
            else:
                self.require_nonempty(item, key, name)
        image_block = item.get("image_block")
        if self.is_placeholder(image_block):
            self.error(f"{name}.image_block must be an actual non-empty block ID")
        elif image_block in seen_blocks:
            self.error(f"{name}.image_block is duplicated: {image_block}")
        else:
            seen_blocks.add(image_block)
        local_path = item.get("local_path")
        if self.is_placeholder(local_path):
            self.error(f"{name}.local_path must be an actual local file path")
        else:
            path = Path(local_path)
            if not path.is_absolute():
                path = self.manifest_path.parent / path
            normalized = str(path.resolve())
            research_root = self.manifest_path.parent.resolve()
            try:
                path.resolve().relative_to(research_root)
                inside_research_folder = True
            except ValueError:
                inside_research_folder = False
            if not inside_research_folder:
                message = f"{name}.local_path must stay inside the research folder: {research_root}"
                if self.require_complete:
                    self.error(message)
                else:
                    self.warning(message)
            if normalized in seen_paths:
                self.error(f"{name}.local_path is duplicated: {local_path}")
            else:
                seen_paths.add(normalized)
            if self.require_complete and not path.is_file():
                self.error(f"{name}.local_path does not point to a readable local file: {path}")
            elif not path.is_file():
                self.warning(f"{name}.local_path does not exist yet: {path}")
        if not isinstance(item.get("caption_before_image"), bool):
            self.error(f"{name}.caption_before_image must be boolean")
        elif self.require_complete and item["caption_before_image"] is not True:
            self.error(f"{name}.caption_before_image must be true in require-complete mode")
        for key in ("display_width", "display_height"):
            value = item.get(key)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or value < 0
            ):
                self.error(f"{name}.{key} must be a non-negative number or null")
        visual = self.require_mapping(item.get("visual_check"), f"{name}.visual_check")
        if visual is not None:
            for key in ("status", "verification_method"):
                self.require_nonempty(visual, key, f"{name}.visual_check")
            if kind in {"social", "artificial_analysis"} and visual.get("blank") is not False:
                self.error(f"{name}.visual_check.blank must be false for {kind}")
            if kind == "social":
                for key in ("login_wall", "blank", "complete_post"):
                    if visual.get(key) is not False and key != "complete_post":
                        self.error(f"{name}.visual_check.{key} must be false for social")
                if visual.get("complete_post") is not True:
                    self.error(f"{name}.visual_check.complete_post must be true for social")
            if self.require_complete:
                if visual.get("status") != "verified" or visual.get("verification_method") != "view_image":
                    self.error(f"{name}.visual_check must be verified with view_image")
        if self.require_complete and item.get("status") != "verified":
            self.error(f"{name}.status must be verified")
        elif item.get("status") not in SCREENSHOT_STATUSES:
            self.error(f"{name}.status must be pending, verified, rejected, or blocked")
        if kind == "artificial_analysis":
            if item.get("source_class") != "independent_benchmark":
                self.error(f"{name}.source_class must be independent_benchmark")
            if not is_artificial_analysis_url(source_url):
                self.error(f"{name}.source_url must point to artificialanalysis.ai")

    def validate_screenshots(self) -> None:
        screenshots = self.data.get("screenshots")
        if not isinstance(screenshots, list):
            self.error("screenshots must be an array")
            return
        seen_ids: set[str] = set()
        seen_blocks: set[str] = set()
        seen_paths: set[str] = set()
        for index, screenshot in enumerate(screenshots):
            self.validate_screenshot(screenshot, index, seen_ids, seen_blocks, seen_paths)
        candidates = self.data.get("screenshot_candidates", [])
        if not isinstance(candidates, list):
            self.error("screenshot_candidates must be an array when present")
        else:
            for index, candidate in enumerate(candidates):
                name = f"screenshot_candidates[{index}]"
                item = self.require_mapping(candidate, name)
                if item is None:
                    continue
                for key in ("id", "source_url", "reason", "status"):
                    if self.require_complete and key == "source_url":
                        source_url = self.require_actual(item, key, name)
                        if isinstance(source_url, str) and not source_url.startswith(("http://", "https://")):
                            self.error(f"{name}.source_url must start with http:// or https://")
                    else:
                        self.require_nonempty(item, key, name)
                if item.get("status") not in {"pending", "manual_screenshot_required"}:
                    self.error(f"{name}.status must be pending or manual_screenshot_required")
                if "image_block" in item:
                    self.error(f"{name} must not contain image_block; candidates are not completed screenshots")
        aa = [item for item in screenshots if isinstance(item, dict) and item.get("kind") == "artificial_analysis"]
        if self.require_complete:
            if len(aa) < 2:
                self.error("at least two Artificial Analysis screenshots are required")
            sections = {item.get("source_section") for item in aa}
            if len(sections) < 2:
                self.error("Artificial Analysis screenshots must use at least two distinct source_section values")
            if not any(isinstance(item, dict) and item.get("kind") == "social" for item in screenshots):
                self.error("at least one social screenshot is required in require-complete mode")

    def validate_child_doc(self) -> None:
        child = self.require_mapping(self.data.get("child_wiki_doc"), "child_wiki_doc")
        if child is None:
            return
        for key in ("parent_node", "node_token", "obj_token", "parent_node_token", "title", "status"):
            self.require_actual(child, key, "child_wiki_doc")
        if self.require_complete:
            for key in ("parent_node", "parent_node_token"):
                value = child.get(key)
                if isinstance(value, str) and value.startswith(("http://", "https://")):
                    self.error(f"child_wiki_doc.{key} must be the canonical parent node token, not a URL")
        if child.get("status") not in TARGET_STATUSES:
            self.error(f"child_wiki_doc.status is invalid: {child.get('status')!r}")
        if self.require_complete and child.get("status") not in COMPLETE_STATUSES:
            self.error("child_wiki_doc.status is not complete")

    def validate_verification(self) -> None:
        verification = self.require_mapping(self.data.get("verification"), "verification")
        if verification is None:
            return
        for key in ("parent_readback", "tables_checked", "screenshots_checked", "child_readback"):
            if not isinstance(verification.get(key), bool):
                self.error(f"verification.{key} must be boolean")
            elif self.require_complete and verification[key] is not True:
                self.error(f"verification.{key} must be true in require-complete mode")
        for key in ("child_validator", "vendor_validator"):
            result = self.require_mapping(verification.get(key), f"verification.{key}")
            if result is None:
                continue
            result_name = f"verification.{key}"
            if "status" not in result or "violation_count" not in result:
                self.error(f"{result_name} requires status and violation_count")
            status = result.get("status")
            violation_count = result.get("violation_count")
            if status not in VALIDATOR_STATUSES:
                self.error(f"{result_name}.status must be pending, pass, or fail")
            if (
                violation_count is not None
                and (isinstance(violation_count, bool) or not isinstance(violation_count, int) or violation_count < 0)
            ):
                self.error(f"{result_name}.violation_count must be a non-negative integer or null")
            if status == "pending" and violation_count is not None:
                self.error(f"{result_name} cannot be pending with a violation_count")
            if status == "pass" and violation_count != 0:
                self.error(f"{result_name} cannot be pass without violation_count 0")
            if status == "fail" and (
                isinstance(violation_count, bool)
                or not isinstance(violation_count, int)
                or violation_count <= 0
            ):
                self.error(f"{result_name} cannot be fail without a positive violation_count")
            if "operational_error" in result:
                operational_error = result.get("operational_error")
                if not isinstance(operational_error, bool):
                    self.error(f"{result_name}.operational_error must be boolean")
                elif operational_error:
                    if status != "fail":
                        self.error(f"{result_name}.operational_error can only be true when status is fail")
                    for detail in ("error_type", "error"):
                        value = result.get(detail)
                        if not isinstance(value, str) or not value.strip():
                            self.error(f"{result_name}.{detail} is required for an operational error")
            if self.require_complete and (result.get("status") != "pass" or result.get("violation_count") != 0):
                self.error(f"{result_name} must be pass with violation_count 0")

    def validate_cross_consistency(self) -> None:
        """Reject a completed target whose corresponding evidence is incomplete."""
        statuses = self.data.get("target_status")
        if not isinstance(statuses, dict):
            return

        parent = self.data.get("parent_section")
        sync_target = self.data.get("sync_target")
        if isinstance(parent, dict) and isinstance(sync_target, dict):
            if parent.get("wiki_node") != sync_target.get("parent_wiki_node"):
                self.error("parent_section.wiki_node must match sync_target.parent_wiki_node")
        if isinstance(parent, dict) and statuses.get("A") in COMPLETE_STATUSES:
            if parent.get("status") not in COMPLETE_STATUSES:
                self.error("target_status.A is complete but parent_section.status is not complete")

        tables = self.data.get("related_tables")
        if statuses.get("B") in COMPLETE_STATUSES and isinstance(tables, list):
            incomplete = [
                index for index, table in enumerate(tables)
                if not isinstance(table, dict) or table.get("status") not in {"updated", "checked_no_change"}
            ]
            if incomplete:
                self.error(f"target_status.B is complete but related_tables are incomplete: {incomplete}")

        child = self.data.get("child_wiki_doc")
        verification = self.data.get("verification")
        if isinstance(child, dict) and isinstance(sync_target, dict):
            expected_parent = sync_target.get("parent_wiki_node")
            if child.get("parent_node") != expected_parent:
                self.error("child_wiki_doc.parent_node must match sync_target.parent_wiki_node")
            if child.get("parent_node_token") != expected_parent:
                self.error("child_wiki_doc.parent_node_token must match sync_target.parent_wiki_node")
        if statuses.get("C") in COMPLETE_STATUSES:
            if not isinstance(child, dict) or child.get("status") not in COMPLETE_STATUSES:
                self.error("target_status.C is complete but child_wiki_doc.status is not complete")
            child_validator = verification.get("child_validator") if isinstance(verification, dict) else None
            if (
                not isinstance(child_validator, dict)
                or child_validator.get("status") != "pass"
                or child_validator.get("violation_count") != 0
            ):
                self.error("target_status.C is complete but child_validator is not pass with violation_count 0")

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
        self.validate_sync_target()
        self.validate_target_status()
        self.validate_sections()
        self.validate_screenshots()
        self.validate_child_doc()
        self.validate_verification()
        self.validate_cross_consistency()
        return self.output()

    def output(self) -> dict[str, Any]:
        return {
            "status": "pass" if not self.errors else "fail",
            "manifest": str(self.manifest_path),
            "mode": "require-complete" if self.require_complete else "structure",
            "error_count": len(self.errors),
            "violation_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": self.errors,
            "warnings": self.warnings,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate update-manifest.json locally without external API calls")
    parser.add_argument("--manifest", required=True, help="Path to update-manifest.json")
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Apply final feishu_sync checks: real files, verified screenshots, completed readbacks, and passing validators",
    )
    args = parser.parse_args()
    result = ManifestValidator(Path(args.manifest).expanduser(), args.require_complete).run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
