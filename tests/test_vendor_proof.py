#!/usr/bin/env python3
"""Offline unit tests for vendor manifest proof checks."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_vendor_section.py"
SPEC = importlib.util.spec_from_file_location("validate_vendor_section", SCRIPT)
if SPEC is None or SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"cannot import validator: {SCRIPT}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class VendorProofTests(unittest.TestCase):
    def manifest(self, image_block: str, local_path: Path) -> dict[str, object]:
        return {
            "screenshots": [
                {
                    "kind": "social",
                    "image_block": image_block,
                    "source_url": "https://example.com/post",
                    "local_path": str(local_path),
                    "visual_check": {
                        "status": "verified",
                        "verification_method": "view_image",
                        "login_wall": False,
                        "blank": False,
                        "complete_post": True,
                    },
                }
            ]
        }

    def test_social_proof_uses_declared_visual_check_without_pillow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "social.png"
            image.write_bytes(b"x" * 100)
            violations = MODULE.social_visual_proof("social-block", self.manifest("social-block", image))
            self.assertEqual(violations, [])

    def test_social_proof_rejects_tiny_local_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "social.png"
            image.write_bytes(b"tiny")
            violations = MODULE.social_visual_proof("social-block", self.manifest("social-block", image))
            self.assertTrue(any("smaller than 100 bytes" in violation for violation in violations))

    def test_artificial_analysis_proof_requires_aa_kind_and_distinct_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "aa-1.png"
            second = root / "aa-2.png"
            first.write_bytes(b"x" * 100)
            second.write_bytes(b"x" * 100)
            base = {
                "source_class": "independent_benchmark",
                "source_url": "https://artificialanalysis.ai/models/example",
                "child_placement": "Benchmark",
                "visual_check": {
                    "status": "verified",
                    "verification_method": "view_image",
                    "blank": False,
                },
            }
            wrong_kind = {**base, "kind": "capability", "image_block": "one", "local_path": str(first), "source_section": "Overview"}
            duplicate = {**base, "kind": "artificial_analysis", "image_block": "one", "local_path": str(first), "source_section": "Breakdown"}
            self.assertTrue(any("at least two distinct" in violation for violation in MODULE.artificial_analysis_proof({"screenshots": [wrong_kind, duplicate]})))

            valid_second = {**base, "kind": "artificial_analysis", "image_block": "one", "local_path": str(second), "source_section": "Breakdown"}
            duplicate_records = MODULE.artificial_analysis_proof({"screenshots": [duplicate, valid_second]})
            self.assertTrue(any("distinct image_block" in violation for violation in duplicate_records))

    def test_artificial_analysis_proof_rejects_spoofed_hostname(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "aa-1.png"
            second = root / "aa-2.png"
            first.write_bytes(b"x" * 100)
            second.write_bytes(b"x" * 100)
            records = []
            for index, image in enumerate((first, second), start=1):
                records.append(
                    {
                        "kind": "artificial_analysis",
                        "source_class": "independent_benchmark",
                        "source_url": "https://evil.example/?source=artificialanalysis.ai",
                        "source_section": f"Section {index}",
                        "image_block": f"block-{index}",
                        "child_placement": "Benchmark",
                        "local_path": str(image),
                        "visual_check": {
                            "status": "verified",
                            "verification_method": "view_image",
                            "blank": False,
                        },
                    }
                )
            violations = MODULE.artificial_analysis_proof({"screenshots": records})
            self.assertTrue(any("at least two distinct" in violation for violation in violations))


if __name__ == "__main__":
    unittest.main()
