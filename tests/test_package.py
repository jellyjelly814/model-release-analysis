"""Check archive reproducibility independently of the system clock."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import package_skill_clean as packager


class PackageTests(unittest.TestCase):
    def test_identical_sources_produce_identical_archives_at_different_times(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            (root / "tests").mkdir(parents=True)
            (root / "SKILL.md").write_text("test skill\n", encoding="utf-8")
            (root / "tests/test_example.py").write_text("# fixture\n", encoding="utf-8")
            first = Path(directory) / "first.skill"
            second = Path(directory) / "second.skill"
            # This test exercises ZIP bytes, CRC, and extraction hashes. Stub the
            # nested self-test to avoid recursively running the packaging suite.
            with patch.object(packager, "ROOT", root), patch.object(
                packager.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)
            ), patch("zipfile.time.localtime", return_value=(2026, 9, 11, 1, 0, 0, 4, 254, 0)):
                first_result = packager.package(first)
            with patch.object(packager, "ROOT", root), patch.object(
                packager.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)
            ), patch("zipfile.time.localtime", return_value=(2026, 9, 12, 8, 30, 0, 5, 255, 0)):
                second_result = packager.package(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(first_result["sha256"], second_result["sha256"])


if __name__ == "__main__":
    unittest.main()
