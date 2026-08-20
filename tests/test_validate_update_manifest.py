#!/usr/bin/env python3
"""Regression tests for the local update-manifest validator.

These tests use only the Python standard library and temporary files.  They do
not contact Feishu, open a browser, or make network requests.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_update_manifest.py"
SPEC = importlib.util.spec_from_file_location("validate_update_manifest", SCRIPT)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import failure is fatal
    raise RuntimeError(f"cannot import validator: {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def screenshot(
    root: Path,
    screenshot_id: str,
    kind: str,
    source_url: str,
    source_section: str,
    filename: str,
    visual_check: dict[str, Any],
) -> dict[str, Any]:
    path = root / filename
    path.write_bytes(b"local test image")
    return {
        "id": screenshot_id,
        "kind": kind,
        "source_class": "official_social" if kind == "social" else "independent_benchmark",
        "source_url": source_url,
        "source_section": source_section,
        "source_original": source_url,
        "method": "view_image",
        "local_path": str(path),
        "image_block": f"block-{screenshot_id}",
        "caption": f"Caption {screenshot_id}",
        "caption_block": f"caption-{screenshot_id}",
        "caption_before_image": True,
        "display_width": 600,
        "display_height": 300,
        "size_policy": "test policy",
        "template_reference": "CHILD-DOC-TEMPLATE.md",
        "parent_placement": "parent section",
        "child_placement": "child section",
        "visual_check": visual_check,
        "status": "verified",
    }


def complete_manifest(root: Path) -> dict[str, Any]:
    return {
        "sync_target": {
            "parent_doc": "parent-doc-token",
            "parent_wiki_node": "parent-wiki-node",
            "vendor_heading": "Vendor",
            "scope": ["A", "B", "C"],
            "permission_preflight": {
                "identity": "user_access_token",
                "docx_read_write": True,
                "media_read_write": True,
                "sheets_read_write": True,
                "wiki_node_manage": True,
                "status": "complete",
            },
        },
        "target_status": {"A": "updated", "B": "checked_no_change", "C": "pass"},
        "parent_section": {
            "wiki_node": "parent-wiki-node",
            "vendor": "Vendor",
            "model_entry": "Model",
            "status": "updated",
        },
        "related_tables": [
            {
                "block_id": "sheet-block",
                "header": ["模型", "发布时间"],
                "reason": "No table changes",
                "status": "checked_no_change",
                "checked_rows": 2,
                "remaining_mismatches": 0,
            }
        ],
        "screenshots": [
            screenshot(
                root,
                "social-1",
                "social",
                "https://example.com/post",
                "Official launch post",
                "social.png",
                {
                    "status": "verified",
                    "verification_method": "view_image",
                    "login_wall": False,
                    "blank": False,
                    "complete_post": True,
                },
            ),
            screenshot(
                root,
                "aa-1",
                "artificial_analysis",
                "https://artificialanalysis.ai/models/example",
                "Intelligence overview",
                "aa-overview.png",
                {"status": "verified", "verification_method": "view_image", "blank": False},
            ),
            screenshot(
                root,
                "aa-2",
                "artificial_analysis",
                "https://artificialanalysis.ai/models/example",
                "Benchmark breakdown",
                "aa-breakdown.png",
                {"status": "verified", "verification_method": "view_image", "blank": False},
            ),
        ],
        "screenshot_candidates": [],
        "child_wiki_doc": {
            "parent_node": "parent-wiki-node",
            "node_token": "child-node-token",
            "obj_token": "child-doc-token",
            "parent_node_token": "parent-wiki-node",
            "title": "Model",
            "status": "pass",
        },
        "verification": {
            "parent_readback": True,
            "tables_checked": True,
            "screenshots_checked": True,
            "child_readback": True,
            "child_validator": {"status": "pass", "violation_count": 0},
            "vendor_validator": {"status": "pass", "violation_count": 0},
        },
    }


class ValidateUpdateManifestTests(unittest.TestCase):
    def run_validator(self, manifest: dict[str, Any], require_complete: bool = True) -> dict[str, Any]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "update-manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            return MODULE.ManifestValidator(path, require_complete).run()

    def test_complete_manifest_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = complete_manifest(root)
            path = root / "update-manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            result = MODULE.ManifestValidator(path, True).run()
            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["error_count"], 0)
            self.assertEqual(result["violation_count"], 0)

    def test_cli_returns_nonzero_for_missing_target_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = complete_manifest(root)
            del manifest["target_status"]
            path = root / "update-manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--manifest", str(path), "--require-complete"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 1)
            output = json.loads(completed.stdout)
            self.assertEqual(output["status"], "fail")
            self.assertTrue(any("target_status" in error for error in output["errors"]))

    def test_each_target_status_is_required_in_structure_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for target in ("A", "B", "C"):
                with self.subTest(target=target):
                    manifest = complete_manifest(root)
                    del manifest["target_status"][target]
                    result = self.run_validator(manifest, require_complete=False)
                    self.assertEqual(result["status"], "fail")
                    self.assertTrue(any(f"target_status.{target}" in error for error in result["errors"]))

    def test_invalid_target_status_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = complete_manifest(root)
            manifest["target_status"]["B"] = "done"
            result = self.run_validator(manifest, require_complete=False)
            self.assertEqual(result["status"], "fail")
            self.assertTrue(any("target_status.B is invalid" in error for error in result["errors"]))

    def test_validator_result_schema_cannot_be_bypassed_by_manual_edit(self) -> None:
        invalid_results = (
            {"status": "pass", "violation_count": True},
            {"status": "fail", "violation_count": 0},
            {"status": "pass", "violation_count": 0, "operational_error": True},
            {
                "status": "fail",
                "violation_count": 1,
                "operational_error": True,
                "error_type": "PermissionError",
            },
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for validator_result in invalid_results:
                with self.subTest(validator_result=validator_result):
                    manifest = complete_manifest(root)
                    manifest["verification"]["child_validator"] = validator_result
                    result = self.run_validator(manifest, require_complete=False)
                    self.assertEqual(result["status"], "fail")

    def test_cross_target_tokens_must_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fields = (
                ("parent_section", "wiki_node"),
                ("child_wiki_doc", "parent_node"),
                ("child_wiki_doc", "parent_node_token"),
            )
            for section, field in fields:
                with self.subTest(section=section, field=field):
                    manifest = complete_manifest(root)
                    manifest[section][field] = "different-parent"
                    result = self.run_validator(manifest, require_complete=False)
                    self.assertEqual(result["status"], "fail")
                    self.assertTrue(any(f"{section}.{field}" in error for error in result["errors"]))

    def test_complete_manifest_rejects_screenshot_outside_research_folder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = complete_manifest(root)
            outside = root.parent / "outside-image.png"
            outside.write_bytes(b"outside")
            manifest["screenshots"][0]["local_path"] = str(outside)
            result = self.run_validator(manifest, require_complete=True)
            self.assertEqual(result["status"], "fail")
            self.assertTrue(any("inside the research folder" in error for error in result["errors"]))

    def test_invalid_permission_preflight_status_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = complete_manifest(root)
            manifest["sync_target"]["permission_preflight"]["status"] = "updated"
            result = self.run_validator(manifest, require_complete=False)
            self.assertEqual(result["status"], "fail")
            self.assertTrue(any("permission_preflight.status" in error for error in result["errors"]))

    def test_artificial_analysis_source_must_use_real_hostname(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = complete_manifest(root)
            manifest["screenshots"][1]["source_url"] = "https://evil.example/?source=artificialanalysis.ai"
            result = self.run_validator(manifest, require_complete=True)
            self.assertEqual(result["status"], "fail")
            self.assertTrue(any("source_url must point to artificialanalysis.ai" in error for error in result["errors"]))

    def test_complete_manifest_requires_canonical_wiki_parent_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = complete_manifest(root)
            manifest["sync_target"]["parent_wiki_node"] = "https://feishu.example/wiki/parent"
            result = self.run_validator(manifest, require_complete=True)
            self.assertEqual(result["status"], "fail")
            self.assertTrue(any("canonical parent node token" in error for error in result["errors"]))

    def test_completed_c_requires_passing_child_validator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = complete_manifest(root)
            manifest["verification"]["child_validator"] = {"status": "pending", "violation_count": None}
            result = MODULE.ManifestValidator(root / "update-manifest.json", True)
            result.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            output = result.run()
            self.assertEqual(output["status"], "fail")
            self.assertTrue(any("target_status.C is complete" in error for error in output["errors"]))

    def test_placeholder_is_rejected_only_in_complete_mode(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = complete_manifest(root)
            manifest["sync_target"]["parent_doc"] = "<verified_parent_doc_token>"
            structure_result = self.run_validator(manifest, require_complete=False)
            self.assertEqual(structure_result["status"], "pass")
            result = self.run_validator(manifest, require_complete=True)
            self.assertEqual(result["status"], "fail")
            self.assertTrue(any("sync_target.parent_doc" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
