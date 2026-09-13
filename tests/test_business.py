"""Regression tests for market-facing price and leaderboard contracts."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from sync_common import file_digest, utc_now
from validate_business_analysis import new_business_analysis, per_million, validate_business
from render_pricing_report import write_report


def pricing_manifest(root: Path) -> dict:
    source = root / "html" / "pricing.html"
    source.parent.mkdir(parents=True)
    source.write_text("official price for Fixture v1; input 0.30 USD/M tokens", encoding="utf-8")
    now = utc_now()
    claim = {
        "id": "price-fixture", "kind": "fact", "statement": "Fixture v1 input price is 0.30 USD/M tokens",
        "model_version": "v1", "subject_model": "Fixture v1", "review_status": "verified",
        "sources": [{"url": "https://official.example/pricing", "retrieved_at": now, "locator": "pricing table",
                     "local_path": "html/pricing.html", "content_sha256": file_digest(source)}],
        "placements": [{"target": "C", "block_id": "pricing-block"}],
    }
    business = new_business_analysis(["pricing"])
    business["summary"] = [{"label": "成本敏感", "claim_ids": ["price-fixture"], "limitation": "只覆盖公布的 token 价格"}]
    business["pricing"].update({
        "peer_selection": "同一输入/输出模态的公开 API 版本",
        "official_check": {"status": "checked", "checked_at": now, "checked_urls": ["https://official.example/pricing"]},
        "openrouter_check": {"status": "unavailable", "checked_at": now, "checked_urls": ["https://openrouter.ai/compare/"], "reason": "fixture has no OpenRouter record"},
        "quotes": [{
            "id": "official-fixture", "channel": "official", "model_id": "Fixture v1", "provider": "Fixture Labs",
            "endpoint": "https://api.official.example/v1", "routing": "direct", "currency": "USD",
            "effective_date": "2026-09-01", "region": "global", "tier": "standard", "context_window": "unknown",
            "max_output": "unknown", "fee_notes": "token billing", "claim_ids": ["price-fixture"],
            "rates": {key: ({"status": "available", "amount": "0.00000030", "per_tokens": 1} if key == "input" else {"status": "unavailable", "reason": "not disclosed"})
                      for key in ("input", "output", "cache_read", "cache_write", "batch_input", "batch_output")},
        }],
    })
    return {"schema_version": 3, "mode": "feishu_sync", "model_identity": {"company": "Fixture Labs", "name": "Fixture", "version": "v1", "release_date": "2026-09-01"},
            "claims": [claim], "business_analysis": business, "sync_target": {"scope": ["C"]},
            "target_status": {"C": "pending"}, "parent_section": {"status": "pending"},
            "child_wiki_doc": {"status": "pending"}, "verification": {}}


class BusinessAnalysisTests(unittest.TestCase):
    def test_price_is_normalized_from_token_unit(self):
        self.assertEqual(per_million({"status": "available", "amount": "0.00000030", "per_tokens": 1}), "0.30000000")

    def test_unavailable_price_is_not_silently_zero(self):
        with self.assertRaises(ValueError):
            per_million({"status": "available", "amount": "0", "per_tokens": 0})

    def test_pricing_ledger_requires_peer_selection_and_passes_complete_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = pricing_manifest(root)
            path = root / "update-manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            errors, warnings = validate_business(manifest, path, complete=True, require_report=False)
            self.assertEqual(errors, [], warnings)

    def test_pricing_report_is_written_and_bound_to_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = pricing_manifest(root)
            path = root / "update-manifest.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            result = write_report(path)
            self.assertEqual(result["status"], "rendered")
            saved = json.loads(path.read_text())
            report = root / saved["business_analysis"]["report"]["local_path"]
            self.assertIn("商业与定价", report.read_text())
            self.assertEqual(saved["business_analysis"]["report"]["sha256"], file_digest(report))

    def test_leaderboard_unknown_conditions_cannot_be_comparable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = pricing_manifest(root)
            manifest["business_analysis"] = new_business_analysis(["leaderboards"])
            now = utc_now()
            manifest["business_analysis"]["leaderboards"]["checks"] = [
                {"name": name, "status": "unavailable", "checked_at": now, "checked_urls": ["https://example.com"], "reason": "not found"}
                for name in ("Artificial Analysis", "DeepSWE", "Terminal-Bench", "CyberGym")
            ]
            manifest["business_analysis"]["leaderboards"]["aa_methodology"] = {"status": "unknown", "current_version": "unknown", "previous_version": "unknown", "reason": "method page unavailable", "checked_urls": ["https://artificialanalysis.ai/methodology/intelligence-benchmarking"], "evaluation_changes": [], "weight_change": "unknown", "impact_explanation": "unknown"}
            benchmark_claim = copy.deepcopy(manifest["claims"][0])
            benchmark_claim.update(id="terminal-bench", kind="independent_benchmark", statement="Fixture Terminal-Bench score is 80", subject_model="Fixture v1", conditions={"dataset_version": "unknown", "harness": "unknown", "tools": "unknown", "sampling": "unknown", "measured_at": now})
            manifest["claims"].append(benchmark_claim)
            manifest["business_analysis"]["leaderboards"]["entries"] = [{"id": "x", "board": "Terminal-Bench", "board_version": "unknown", "model_id": "Fixture v1", "effort": "unknown", "provider": "unknown", "task_type": "terminal", "metric": "pass@1", "score_unit": "%", "population": "unknown", "cluster": "coding_agent", "conditions": {"dataset_version": "unknown", "harness": "unknown", "tools": "unknown", "sampling": "unknown", "measured_at": now}, "score": "80", "rank": 1, "comparable": True, "claim_ids": ["terminal-bench"], "observed_at": now}]
            errors, _ = validate_business(manifest, root / "update-manifest.json", complete=True, require_report=False)
            self.assertTrue(any("precise comparison" in error for error in errors))

    def test_init_cli_enables_business_profile(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            targets = root / "targets.json"
            targets.write_text(json.dumps({"parent_doc": "doc", "parent_wiki_node": "wiki", "vendor_heading": "Vendor", "allowed_link_hosts": ["tenant.feishu.cn"]}), encoding="utf-8")
            output = subprocess.run(["python3", "scripts/sync_run.py", "init", "--directory", str(root / "run"), "--targets", str(targets), "--company", "Fixture", "--model", "Fixture", "--version", "v1", "--release-date", "2026-09-01", "--model-entry", "【2026/09/01】Fixture v1", "--analysis-topics", "pricing"], capture_output=True, text=True, check=False)
            self.assertEqual(output.returncode, 0, output.stderr)
            saved = json.loads((root / "run/update-manifest.json").read_text())
            self.assertEqual(saved["business_analysis"]["profile"], "business-v1")
            self.assertEqual(saved["business_analysis"]["topics"], ["pricing"])


if __name__ == "__main__":
    unittest.main()
