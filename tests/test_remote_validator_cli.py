#!/usr/bin/env python3
"""CLI contract tests for remote validators without contacting Feishu."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHILD = ROOT / "scripts" / "validate_child_document.py"
VENDOR = ROOT / "scripts" / "validate_vendor_section.py"


class RemoteValidatorCliTests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, *arguments],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_child_validator_requires_explicit_helper(self) -> None:
        completed = self.run_cli(str(CHILD), "--doc", "doc", "--parent-node", "parent")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("--helper", completed.stderr)
        self.assertIn("required", completed.stderr)

    def test_vendor_validator_requires_explicit_helper(self) -> None:
        completed = self.run_cli(str(VENDOR), "--doc", "doc", "--vendor", "Vendor")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("--helper", completed.stderr)
        self.assertIn("required", completed.stderr)

    def test_help_does_not_expose_private_default_path(self) -> None:
        for script in (CHILD, VENDOR):
            with self.subTest(script=script.name):
                completed = self.run_cli(str(script), "--help")
                self.assertEqual(completed.returncode, 0)
                self.assertIn("--helper", completed.stdout)
                self.assertNotIn(".claude/skills", completed.stdout)

    def test_missing_helper_returns_machine_readable_operational_failure(self) -> None:
        cases = (
            (CHILD, "--doc", "doc", "--parent-node", "parent"),
            (VENDOR, "--doc", "doc", "--vendor", "Vendor"),
        )
        for script, *arguments in cases:
            with self.subTest(script=script.name):
                completed = self.run_cli(
                    str(script),
                    *arguments,
                    "--helper",
                    "/definitely/missing/feishu_helper.py",
                )
                self.assertEqual(completed.returncode, 1)
                output = json.loads(completed.stdout)
                self.assertEqual(output["status"], "fail")
                self.assertEqual(output["violation_count"], 1)
                self.assertIs(output["operational_error"], True)
                self.assertEqual(output["error_type"], "FileNotFoundError")
                self.assertNotIn("Traceback", completed.stdout + completed.stderr)

    def test_child_media_read_failure_is_an_operational_failure(self) -> None:
        helper_source = '''
BASE = "invalid://feishu"

def _uat():
    return "test-token"

def api(method, path):
    if path.startswith("/open-apis/wiki/"):
        return None, {
            "code": 0,
            "data": {"node": {
                "obj_token": "doc",
                "node_token": "child",
                "parent_node_token": "parent",
            }},
        }
    return None, {"code": 0, "data": {"document": {"title": "【2026/08/19】Model：Release"}}}

def _all_blocks(document_id):
    return [
        {"block_id": "doc", "block_type": 1, "children": ["image"]},
        {
            "block_id": "image",
            "block_type": 27,
            "parent_id": "doc",
            "image": {"token": "media-token", "width": 600, "height": 300},
        },
    ]
'''
        with tempfile.TemporaryDirectory() as directory:
            helper = Path(directory) / "feishu_helper.py"
            helper.write_text(helper_source, encoding="utf-8")
            completed = self.run_cli(
                str(CHILD),
                "--doc",
                "child",
                "--parent-node",
                "parent",
                "--helper",
                str(helper),
            )
        self.assertEqual(completed.returncode, 1)
        output = json.loads(completed.stdout)
        self.assertEqual(output["status"], "fail")
        self.assertEqual(output["violation_count"], 1)
        self.assertIs(output["operational_error"], True)
        self.assertIn("cannot read image media", output["error"])
        self.assertNotIn("Traceback", completed.stdout + completed.stderr)

    def test_vendor_section_without_model_entries_fails_content_validation(self) -> None:
        helper_source = '''
def api(method, path):
    return None, {"code": 0}

def _all_blocks(document_id):
    return [
        {"block_id": document_id, "block_type": 1, "children": ["vendor"]},
        {
            "block_id": "vendor",
            "block_type": 4,
            "parent_id": document_id,
            "heading2": {"elements": [{"text_run": {"content": "Vendor"}}]},
        },
    ]
'''
        with tempfile.TemporaryDirectory() as directory:
            helper = Path(directory) / "feishu_helper.py"
            helper.write_text(helper_source, encoding="utf-8")
            completed = self.run_cli(
                str(VENDOR),
                "--doc",
                "parent-doc",
                "--vendor",
                "Vendor",
                "--helper",
                str(helper),
            )
        self.assertEqual(completed.returncode, 1)
        output = json.loads(completed.stdout)
        self.assertEqual(output["status"], "fail")
        self.assertEqual(output["violation_count"], 1)
        self.assertIn("no dated model entries", output["global_violations"][0])
        self.assertNotIn("operational_error", output)

    def test_child_validator_rejects_image_without_media_token(self) -> None:
        helper_source = '''
BASE = "invalid://feishu"

def _uat():
    return "test-token"

def api(method, path):
    if path.startswith("/open-apis/wiki/"):
        return None, {
            "code": 0,
            "data": {"node": {
                "obj_token": "doc",
                "node_token": "child",
                "parent_node_token": "parent",
            }},
        }
    return None, {"code": 0, "data": {"document": {"title": "【2026/08/19】Model：Release"}}}

def _all_blocks(document_id):
    return [
        {"block_id": "doc", "block_type": 1, "children": ["image"]},
        {
            "block_id": "image",
            "block_type": 27,
            "parent_id": "doc",
            "image": {"width": 600, "height": 300},
        },
    ]
'''
        with tempfile.TemporaryDirectory() as directory:
            helper = Path(directory) / "feishu_helper.py"
            helper.write_text(helper_source, encoding="utf-8")
            completed = self.run_cli(
                str(CHILD),
                "--doc",
                "child",
                "--parent-node",
                "parent",
                "--helper",
                str(helper),
            )
        self.assertEqual(completed.returncode, 1)
        output = json.loads(completed.stdout)
        self.assertEqual(output["status"], "fail")
        self.assertNotIn("operational_error", output)
        self.assertTrue(any("missing its Feishu media token" in violation for violation in output["violations"]))


if __name__ == "__main__":
    unittest.main()
