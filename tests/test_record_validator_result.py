#!/usr/bin/env python3
"""Smoke tests for recording captured validator output locally."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "record_validator_result.py"
MANIFEST_SCRIPT = ROOT / "scripts" / "validate_update_manifest.py"
FIXTURE_SPEC = importlib.util.spec_from_file_location(
    "manifest_fixtures", ROOT / "tests" / "test_validate_update_manifest.py"
)
if FIXTURE_SPEC is None or FIXTURE_SPEC.loader is None:  # pragma: no cover
    raise RuntimeError("cannot load manifest fixtures")
FIXTURES = importlib.util.module_from_spec(FIXTURE_SPEC)
FIXTURE_SPEC.loader.exec_module(FIXTURES)


class RecordValidatorResultTests(unittest.TestCase):
    def write_manifest(self, root: Path) -> Path:
        path = root / "update-manifest.json"
        path.write_text(
            json.dumps(
                {
                    "verification": {
                        "child_validator": {"status": "pending", "violation_count": None},
                        "vendor_validator": {"status": "pending", "violation_count": None},
                    }
                }
            ),
            encoding="utf-8",
        )
        return path

    def run_recorder(self, manifest: Path, validator: str, result: dict[str, object]) -> subprocess.CompletedProcess[str]:
        result_path = manifest.parent / f"{validator}-result.json"
        result_path.write_text(json.dumps(result), encoding="utf-8")
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--manifest",
                str(manifest),
                "--validator",
                validator,
                "--result-file",
                str(result_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_records_actual_child_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_manifest(Path(directory))
            completed = self.run_recorder(manifest, "child", {"status": "pass", "violation_count": 0})
            self.assertEqual(completed.returncode, 0, completed.stderr)
            data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(data["verification"]["child_validator"], {"status": "pass", "violation_count": 0})

    def test_rejects_inconsistent_result_without_changing_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_manifest(Path(directory))
            before = manifest.read_text(encoding="utf-8")
            completed = self.run_recorder(manifest, "vendor", {"status": "pass", "violation_count": 2})
            self.assertEqual(completed.returncode, 1)
            self.assertEqual(manifest.read_text(encoding="utf-8"), before)

    def test_records_operational_failure_details(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_manifest(Path(directory))
            result = {
                "status": "fail",
                "violation_count": 1,
                "operational_error": True,
                "error_type": "PermissionError",
                "error": "Feishu read permission denied",
            }
            completed = self.run_recorder(manifest, "child", result)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(data["verification"]["child_validator"], result)

    def test_rejects_operational_error_on_pass_without_changing_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifest = self.write_manifest(Path(directory))
            before = manifest.read_text(encoding="utf-8")
            completed = self.run_recorder(
                manifest,
                "vendor",
                {"status": "pass", "violation_count": 0, "operational_error": True},
            )
            self.assertEqual(completed.returncode, 1)
            self.assertIn("only be true when status is fail", completed.stderr)
            self.assertEqual(manifest.read_text(encoding="utf-8"), before)

    def test_rejects_incomplete_operational_error_without_changing_manifest(self) -> None:
        invalid_results = (
            {
                "status": "fail",
                "violation_count": 1,
                "operational_error": True,
                "error": "helper unavailable",
            },
            {
                "status": "fail",
                "violation_count": 1,
                "operational_error": True,
                "error_type": "FileNotFoundError",
            },
        )
        for result in invalid_results:
            with self.subTest(result=result), tempfile.TemporaryDirectory() as directory:
                manifest = self.write_manifest(Path(directory))
                before = manifest.read_text(encoding="utf-8")
                completed = self.run_recorder(manifest, "child", result)
                self.assertEqual(completed.returncode, 1)
                self.assertIn("required for an operational error", completed.stderr)
                self.assertEqual(manifest.read_text(encoding="utf-8"), before)

    def test_rejects_non_json_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = self.write_manifest(root)
            result_path = root / "bad.json"
            result_path.write_text("not-json", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--manifest",
                    str(manifest),
                    "--validator",
                    "child",
                    "--result-file",
                    str(result_path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 1)
            self.assertIn("valid JSON", completed.stderr)

    def test_record_both_results_then_final_manifest_gate_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_data = FIXTURES.complete_manifest(root)
            manifest_data["verification"]["child_validator"] = {
                "status": "pending",
                "violation_count": None,
            }
            manifest_data["verification"]["vendor_validator"] = {
                "status": "pending",
                "violation_count": None,
            }
            manifest = root / "update-manifest.json"
            manifest.write_text(json.dumps(manifest_data), encoding="utf-8")

            child = self.run_recorder(manifest, "child", {"status": "pass", "violation_count": 0})
            vendor = self.run_recorder(manifest, "vendor", {"status": "pass", "violation_count": 0})
            self.assertEqual(child.returncode, 0, child.stderr)
            self.assertEqual(vendor.returncode, 0, vendor.stderr)

            gate = subprocess.run(
                [
                    sys.executable,
                    str(MANIFEST_SCRIPT),
                    "--manifest",
                    str(manifest),
                    "--require-complete",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(gate.returncode, 0, gate.stdout + gate.stderr)
            self.assertEqual(json.loads(gate.stdout)["status"], "pass")


if __name__ == "__main__":
    unittest.main()
