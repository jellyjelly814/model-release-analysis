"""Validate business evidence, normalized prices and leaderboard methodology.

Offline structural checks only. Source interpretation and causal explanations
still require human/agent review; no API calls or invented business scores.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from sync_common import file_digest, local_file, parse_time, read_json, utc_now

PROFILE = "business-v1"
TOPICS = {"pricing", "leaderboards"}
RATE_KEYS = ("input", "output", "cache_read", "cache_write", "batch_input", "batch_output")
CHECK_NAMES = ("Artificial Analysis", "DeepSWE", "Terminal-Bench", "CyberGym")
CLUSTERS = {"coding_agent", "general", "knowledge_work", "scientific_reasoning", "multimodal", "other"}


def new_business_analysis(topics=None):
    topics = list(topics if topics is not None else ("pricing", "leaderboards"))
    if not topics or len(topics) != len(set(topics)) or not set(topics) <= TOPICS:
        raise ValueError("analysis topics must be pricing, leaderboards, or both")
    return {"profile": PROFILE, "topics": topics, "summary": [],
            "pricing": {"official_check": {"status": "pending"},
                        "openrouter_check": {"status": "pending"}, "quotes": []},
            "leaderboards": {"checks": [{"name": name, "status": "pending"} for name in CHECK_NAMES],
                             "entries": [], "aa_methodology": {"status": "pending"}},
            "report": {"local_path": "pricing-report.md", "section_heading_block": None}}


def number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("expected a finite non-negative decimal")
    try:
        value = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("expected a decimal") from exc
    if not value.is_finite() or value < 0:
        raise ValueError("expected a finite non-negative decimal")
    return value


def per_million(rate):
    """Normalize a token rate, preserving zero vs unavailable and its currency."""
    if rate.get("status") != "available":
        return None
    units = rate.get("per_tokens")
    if isinstance(units, bool) or not isinstance(units, int) or units <= 0:
        raise ValueError("per_tokens must be a positive token count; request/image rates are separate")
    return format(number(rate.get("amount")) * Decimal(1000000) / Decimal(units), "f")


def normalize_text(text):
    # Match Markdown table cells/headings to native Docx text without depending
    # on layout whitespace. Content, numbers, currency and URLs remain intact.
    lines = [line for line in text.splitlines() if not re.fullmatch(r"[\s|:\-]+", line)]
    return re.sub(r"[\s|*`#]+", "", "\n".join(lines))


def block_text(block):
    parts = []
    for value in block.values():
        if isinstance(value, dict):
            for element in value.get("elements", []):
                if "text_run" in element:
                    parts.append(element["text_run"].get("content", ""))
                elif "mention_doc" in element:
                    parts.append(element["mention_doc"].get("title", ""))
    return "".join(parts)


def section_text(snapshot, heading_id):
    blocks = {b["block_id"]: b for b in snapshot["blocks"]}
    roots = blocks[snapshot["document"]].get("children", [])
    if heading_id not in roots or blocks[heading_id].get("block_type") != 3:
        raise ValueError("commercial section must be a root Heading 1 in the current child")
    if block_text(blocks[heading_id]).strip() != "商业与定价":
        raise ValueError("commercial heading must be 商业与定价")
    start = roots.index(heading_id)
    stop = next((i for i in range(start + 1, len(roots)) if blocks[roots[i]].get("block_type") == 3), len(roots))
    seen = set()
    def visit(bid):
        if bid in seen:
            raise ValueError("cyclic or repeated commercial section block")
        seen.add(bid)
        block = blocks[bid]
        return "\n".join([block_text(block)] + [visit(child) for child in block.get("children", [])])
    return "\n".join(visit(bid) for bid in roots[start:stop])


def validate_business(manifest, path, complete=False, artifacts=None, require_report=True):
    business = manifest.get("business_analysis")
    if business is None:
        return [], ["legacy v3 manifest: business profile not enabled; cannot claim business-v1 acceptance"]
    errors, warnings = [], []
    def require(condition, message):
        if not condition:
            errors.append(message)
    def text_fields(obj, fields, context):
        for field in fields:
            require(isinstance(obj.get(field), str) and bool(obj[field].strip()), f"{context}: {field} required; use unknown if undisclosed")
    def timestamp(value, context):
        try:
            require(parse_time(value) <= parse_time(utc_now()), f"{context}: future observation")
        except (AttributeError, TypeError, ValueError):
            errors.append(f"{context}: timezone-aware timestamp required")
    claims = {c["id"]: c for c in manifest.get("claims", []) if isinstance(c, dict) and c.get("id")}
    def bindings(obj, context, model_id=None, benchmark=False):
        ids = obj.get("claim_ids")
        if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or i not in claims for i in ids):
            errors.append(f"{context}: bind existing claim_ids"); return []
        found = [claims[i] for i in ids]
        for claim in found:
            if model_id:
                require(claim.get("subject_model") == model_id, f"{context}: claim subject_model differs from exact compared model")
            if benchmark:
                require(claim.get("kind") in {"official_benchmark", "independent_benchmark"}, f"{context}: benchmark evidence type required")
            if complete:
                require(claim.get("review_status") == "verified", f"{context}: unreviewed claim")
                for source in claim.get("sources", []):
                    try:
                        timestamp(source.get("retrieved_at"), context)
                        require(bool(source.get("locator")), context + ": source locator required")
                        require(file_digest(local_file(path, source["local_path"])) == source.get("content_sha256"), context + ": source cache hash mismatch")
                    except (KeyError, ValueError, TypeError, OSError) as exc:
                        errors.append(context + ": missing source cache: " + str(exc))
        return found
    def check(obj, context):
        if not complete and obj.get("status") == "pending":
            return
        require(obj.get("status") in {"checked", "unavailable", "not_applicable"}, f"{context}: check status required")
        urls = obj.get("checked_urls")
        require(isinstance(urls, list) and bool(urls) and all(isinstance(u, str) and urlparse(u).scheme in {"http", "https"} and urlparse(u).hostname for u in urls), f"{context}: actual checked_urls required")
        timestamp(obj.get("checked_at"), context)
        if obj.get("status") != "checked":
            text_fields(obj, ("reason",), context)
            warnings.append(f"{context}: {obj.get('status')} - {obj.get('reason', '')}")

    require(isinstance(business, dict), "business_analysis must be an object")
    if not isinstance(business, dict):
        return errors, warnings
    require(business.get("profile") == PROFILE, "unsupported business profile")
    topics = business.get("topics")
    if not isinstance(topics, list) or not topics or any(t not in TOPICS for t in topics) or len(set(topics)) != len(topics):
        return errors + ["business topics must contain pricing and/or leaderboards"], warnings
    require(not business.get("scenario_costs"), "default business profile excludes assumed scenario costs")
    require(business.get("overall_business_score") is None, "do not combine benchmarks into one business score")
    summary = business.get("summary", [])
    require(isinstance(summary, list) and (bool(summary) or not complete), "business summary labels are required")
    for item in summary:
        text_fields(item, ("label", "limitation"), "business summary")
        bindings(item, "business summary")

    if "pricing" in topics:
        pricing = business.get("pricing", {})
        if complete:
            text_fields(pricing, ("peer_selection",), "pricing comparison")
        for channel in ("official", "openrouter"):
            check(pricing.get(channel + "_check", {}), channel + " pricing")
        quotes = pricing.get("quotes", [])
        require(isinstance(quotes, list), "pricing.quotes must be an array")
        ids = set()
        for quote in quotes:
            context = "quote " + str(quote.get("id", "?"))
            text_fields(quote, ("id", "model_id", "provider", "endpoint", "routing", "currency", "effective_date", "region", "tier", "context_window", "max_output", "fee_notes"), context)
            require(quote.get("id") not in ids, "duplicate quote ID"); ids.add(quote.get("id"))
            channel = quote.get("channel")
            require(channel in {"official", "openrouter"}, context + ": invalid channel")
            require(bool(re.fullmatch(r"[A-Z]{3}", quote.get("currency", ""))), context + ": ISO currency required")
            if quote.get("effective_date") == "unknown":
                warnings.append(context + ": effective date undisclosed; observation date is not effective date")
            else:
                from datetime import date
                try: date.fromisoformat(quote.get("effective_date", ""))
                except (TypeError, ValueError): errors.append(context + ": effective_date must be ISO date or unknown")
            found = bindings(quote, context, quote.get("model_id"))
            for claim in found:
                require(claim.get("kind") == "fact" and bool(claim.get("sources")), context + ": sourced price fact required")
            if channel == "openrouter":
                require(any(urlparse(s.get("url", "")).hostname == "openrouter.ai" for c in found for s in c.get("sources", [])), context + ": OpenRouter price requires an OpenRouter source")
            for key in RATE_KEYS:
                rate = quote.get("rates", {}).get(key, {})
                require(rate.get("status") in {"available", "unavailable", "not_applicable"}, f"{context}: explicit {key} rate status required")
                if rate.get("status") == "available":
                    try: per_million(rate)
                    except ValueError as exc: errors.append(f"{context}: {key}: {exc}")
                else:
                    require(bool(rate.get("reason")), f"{context}: {key} missing-rate reason required")
                    require(rate.get("amount") is None, f"{context}: {key} unavailable is not a zero price")
            for metric in quote.get("performance", []):
                text_fields(metric, ("name", "unit", "percentile", "window", "provider", "routing"), context + " performance")
                timestamp(metric.get("observed_at"), context + " performance")
                bindings(metric, context + " performance", quote.get("model_id"))
                try: number(metric.get("value"))
                except ValueError as exc: errors.append(str(exc))
        if complete:
            for channel in ("official", "openrouter"):
                present = any(q.get("channel") == channel for q in quotes)
                require((pricing.get(channel + "_check", {}).get("status") == "checked") == present,
                        channel + ": checked status must match actual quotes; explain unavailable data")

    if "leaderboards" in topics:
        boards = business.get("leaderboards", {})
        checks = boards.get("checks", [])
        by_name = {c.get("name"): c for c in checks}
        require(len(by_name) == len(checks), "duplicate leaderboard checks")
        for name in CHECK_NAMES:
            require(name in by_name, name + ": missing coverage check")
        for item in checks:
            check(item, str(item.get("name")))
        entries = boards.get("entries", [])
        seen = set()
        for entry in entries:
            context = "leaderboard " + str(entry.get("id", "?"))
            text_fields(entry, ("id", "board", "board_version", "model_id", "effort", "provider", "task_type", "metric", "score_unit", "population"), context)
            require(entry.get("id") not in seen, "duplicate leaderboard entry ID"); seen.add(entry.get("id"))
            require(entry.get("cluster") in CLUSTERS, context + ": capability cluster required")
            found = bindings(entry, context, entry.get("model_id"), benchmark=True)
            require(isinstance(entry.get("comparable"), bool), context + ": comparable must be explicit")
            if any(c.get("comparable") is False or "unknown" in c.get("conditions", {}).values() for c in found) or any(entry.get(k) == "unknown" for k in ("board_version", "effort", "provider")):
                require(entry.get("comparable") is False, context + ": unknown/mismatched conditions cannot support precise comparison")
            try: number(entry.get("score"))
            except ValueError as exc: errors.append(context + ": " + str(exc))
            rank = entry.get("rank")
            require(rank is None or (isinstance(rank, int) and not isinstance(rank, bool) and rank > 0), context + ": rank must be positive or null")
            if rank is not None:
                require(entry.get("population") != "unknown", context + ": rank needs its filtered population")
            timestamp(entry.get("observed_at"), context)
        method = boards.get("aa_methodology", {})
        if complete or method.get("status") != "pending":
            require(method.get("status") in {"verified", "unknown"}, "AA methodology must be verified or explicitly unknown")
            text_fields(method, ("current_version", "previous_version", "impact_explanation"), "AA methodology")
            if method.get("status") == "verified":
                found = bindings(method, "AA methodology")
                require(any(urlparse(s.get("url", "")).hostname == "artificialanalysis.ai" for c in found for s in c.get("sources", [])), "AA methodology requires the original methodology/changelog source")
            else:
                require(bool(method.get("reason")) and bool(method.get("checked_urls")), "unknown AA methodology needs reason and checked_urls")
                require(method.get("weight_change") == "unknown", "unknown AA methodology cannot assert a weight change")
            require(isinstance(method.get("evaluation_changes"), list), "AA evaluation changes must be recorded separately from weights")
            change = method.get("weight_change")
            require(change in {"changed", "unchanged", "unknown"}, "AA weight_change required")
            weights = []
            for key in ("current_weights", "previous_weights"):
                value = method.get(key)
                if value is not None:
                    try:
                        require(isinstance(value, dict) and bool(value), key + ": expected category weight object")
                        parsed = {k: number(v) for k, v in value.items()}
                        require(sum(parsed.values()) == 100, key + ": category weights must total 100")
                        weights.append(parsed)
                    except (ValueError, AttributeError) as exc: errors.append(key + ": " + str(exc))
            if change != "unknown":
                require(method.get("status") == "verified" and method.get("previous_version") not in {None, "unknown"} and method.get("current_version") not in {None, "unknown"} and len(weights) == 2, "weight comparison needs both named versions and sourced weight maps")
                if len(weights) == 2:
                    require((weights[0] == weights[1]) == (change == "unchanged"), "claimed weight change contradicts category weights")
            require(method.get("causal_share") is None, "category weights alone cannot quantify a model's rank-loss cause")

    if complete and require_report and "pricing" in topics:
        from render_pricing_report import render_report
        report = business.get("report", {})
        try:
            expected, chunks = render_report(manifest)
            report_path = local_file(path, report["local_path"])
            require(report_path.suffix == ".md", "pricing report must be Markdown")
            require(report_path.read_text(encoding="utf-8") == expected, "pricing report differs from current business evidence; render it again")
            require(file_digest(report_path) == report.get("sha256"), "pricing report hash missing or stale")
            scope = manifest.get("sync_target", {}).get("scope", [])
            if artifacts is not None and manifest.get("mode") == "feishu_sync" and "C" in scope:
                snapshot = artifacts["C"]["snapshot"]
                require(snapshot["document"] == manifest["child_wiki_doc"]["obj_token"], "pricing report points to a different child")
                actual = normalize_text(section_text(snapshot, report.get("section_heading_block")))
                position = 0
                for chunk in chunks:
                    wanted = normalize_text(chunk)
                    found = actual.find(wanted, position)
                    require(found >= 0, "commercial section readback missing/out of order: " + chunk[:80])
                    if found >= 0: position = found + len(wanted)
        except (KeyError, ValueError, TypeError, OSError) as exc:
            errors.append("pricing report/readback: " + str(exc))
    return errors, warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--require-complete", action="store_true", help="Check local research/report completeness; remote delivery uses sync_run.py verify")
    args = parser.parse_args()
    try:
        errors, warnings = validate_business(read_json(args.manifest), args.manifest, args.require_complete)
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        errors, warnings = ["invalid business analysis: " + str(exc)], []
    print(json.dumps({"status": "fail" if errors else "pass", "errors": errors, "warnings": warnings,
                      "violation_count": len(errors), "remote_delivery_verified": False,
                      "semantic_accuracy": "requires source review"}, ensure_ascii=False, indent=2))
    return bool(errors)


if __name__ == "__main__":
    sys.exit(main())
