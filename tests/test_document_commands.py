#!/usr/bin/env python3
"""Smoke tests for shell commands shown as copyable Skill instructions."""

from __future__ import annotations

import re
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "SKILL.md"


class DocumentCommandTests(unittest.TestCase):
    def test_manifest_example_is_valid_preparation_manifest(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        match = re.search(r"### 更新 manifest 最低格式.*?```json\n(.*?)\n```", text, flags=re.DOTALL)
        self.assertIsNotNone(match, "Skill must contain the manifest contract example")
        example = json.loads(match.group(1))
        self.assertEqual(example["screenshots"], [])
        self.assertTrue(example["screenshot_candidates"])
        self.assertTrue(
            all(candidate["status"] in {"pending", "manual_screenshot_required"} for candidate in example["screenshot_candidates"])
        )

    def test_skill_color_and_gate_wording_is_consistent(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        self.assertNotIn("使用加粗 + 颜色标注", text)
        self.assertNotIn("三个 validator 中任一", text)
        self.assertIn("所有文字必须为黑色", text)

    def test_default_mode_contract_remains_explicit(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("默认自动进入 `feishu_sync`", text)
        self.assertIn("只有用户明确说“只做 Word / 只做研究底稿 / 只做研究 / 不更新飞书”", text)

    def test_research_folder_command_creates_three_subdirectories(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        match = re.search(
            r'mkdir -p "<研究文件夹>/images" "<研究文件夹>/html" "<研究文件夹>/pdf"',
            text,
        )
        self.assertIsNotNone(match, "Skill must contain the portable mkdir command")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "research folder"
            command = (
                f'mkdir -p "{root}/images" "{root}/html" "{root}/pdf"'
            )
            completed = subprocess.run(
                ["sh", "-c", command],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((root / "images").is_dir())
            self.assertTrue((root / "html").is_dir())
            self.assertTrue((root / "pdf").is_dir())

    def test_skill_does_not_keep_quoted_brace_directory_command(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        self.assertNotIn('mkdir -p "<研究文件夹>/{images,html,pdf}"', text)

    def test_feishu_validator_order_is_executable(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        child = text.index("scripts/validate_child_document.py")
        vendor = text.index("scripts/validate_vendor_section.py", child)
        manifest_gate = text.index(
            "scripts/validate_update_manifest.py --manifest <研究文件夹>/update-manifest.json --require-complete",
            vendor,
        )
        self.assertLess(child, vendor)
        self.assertLess(vendor, manifest_gate)
        self.assertIn("把两个 validator 的实际 `status` 与 `violation_count` 写回 manifest", text)


if __name__ == "__main__":
    unittest.main()
