"""Render the local pricing report to publish inside the existing child Wiki.

Reads declared evidence only; never contacts Feishu, changes currency, combines
input/output prices, or assumes a workload. Does not overwrite hand-edited text.
"""
from __future__ import annotations

import argparse
import json
import sys

from sync_common import atomic_json, file_digest, invalidate, local_file, read_json
from validate_business_analysis import RATE_KEYS, per_million, validate_business


def cell(value):
    return str(value).replace("|", "／").replace("\n", " ").replace("\r", " ").strip()


def render_report(manifest):
    business = manifest["business_analysis"]
    if "pricing" not in business["topics"]:
        raise ValueError("pricing is outside this task's analysis topics")
    pricing = business["pricing"]
    claims = {c["id"]: c for c in manifest["claims"]}
    lines, chunks = [], []
    def paragraph(text):
        text = cell(text)
        lines.extend([text, ""])
        chunks.append(text)
    def heading(title, level=2):
        lines.extend(["#" * level + " " + title, ""])
        chunks.append(title)
    def table(headers, rows):
        for index, row in enumerate([headers] + rows):
            values = [cell(v) for v in row]
            lines.append("| " + " | ".join(values) + " |")
            chunks.append(" ".join(values))
            if index == 0:
                lines.append("| " + " | ".join("---" for _ in row) + " |")
        lines.append("")
    heading("商业与定价", 1)
    identity = manifest["model_identity"]
    paragraph(f"{identity['company']} · {identity['name']} · {identity['version']}")
    heading("业务摘要")
    for item in business["summary"]:
        paragraph(item["label"] + "：" + "；".join(claims[c]["statement"] for c in item["claim_ids"]) + "。适用边界：" + item["limitation"])
    heading("价格对比")
    paragraph("所有 token 单价按原币种折算为每百万 token，输入、输出、缓存及批处理分别列示。未假设业务用量；单价不能代表完成一次任务的总成本。")
    paragraph("竞品选择依据：" + pricing["peer_selection"])
    rows = []
    for quote in sorted(pricing.get("quotes", []), key=lambda q: (q["channel"] != "official", q["model_id"], q["provider"], q["id"])):
        values = []
        for key in RATE_KEYS:
            rate = quote["rates"][key]
            amount = per_million(rate)
            values.append(amount if amount is not None else ("未公开/不可用" if rate["status"] == "unavailable" else "不适用"))
        rows.append([quote["id"], "官方" if quote["channel"] == "official" else "OpenRouter", quote["model_id"], quote["provider"], quote["currency"], *values])
    table(["报价", "渠道", "模型/精确版本", "供应商", "币种/每百万token", "输入", "输出", "缓存读", "缓存写", "批处理输入", "批处理输出"], rows)
    heading("渠道核对与报价条件")
    for channel in ("official", "openrouter"):
        check = pricing[channel + "_check"]
        paragraph(f"{channel}：{check['status']}；抓取时间：{check['checked_at']}；说明：{check.get('reason', '已核对下列报价')}")
        for url in check["checked_urls"]:
            paragraph(url)
    used = set(c for item in business["summary"] for c in item["claim_ids"])
    for quote in pricing.get("quotes", []):
        paragraph(f"{quote['id']}：端点 {quote['endpoint']}；路由 {quote['routing']}；区域 {quote['region']}；档位 {quote['tier']}；上下文 {quote['context_window']}；最大输出 {quote['max_output']}；生效日期 {quote['effective_date']}；费用说明 {quote['fee_notes']}")
        for key in RATE_KEYS:
            rate = quote["rates"][key]
            if rate["status"] != "available":
                paragraph(f"{quote['id']} {key}：{rate['reason']}")
        for metric in quote.get("performance", []):
            paragraph(f"{quote['id']} {metric['name']}：{metric['value']} {metric['unit']}；{metric['percentile']}；窗口 {metric['window']}；观测 {metric['observed_at']}；供应商 {metric['provider']}；路由 {metric['routing']}。此为该服务观测，不等于模型能力或生产 SLA。")
            used.update(metric["claim_ids"])
        used.update(quote["claim_ids"])
    heading("来源与证据边界")
    for cid in sorted(used):
        claim = claims[cid]
        paragraph(cid + "：" + claim["statement"])
        for source in claim.get("sources", []):
            paragraph(f"来源 {source['url']}；抓取 {source['retrieved_at']}；定位 {source['locator']}")
        if claim.get("kind") == "inference":
            paragraph("业务解读；依据：" + "、".join(claim["basis_claim_ids"]))
    return "\n".join(lines).rstrip() + "\n", chunks


def write_report(path):
    manifest = read_json(path)
    if "business_analysis" not in manifest:
        raise ValueError("enable business-v1 before rendering")
    errors, warnings = validate_business(manifest, path, complete=True, require_report=False)
    if errors:
        raise ValueError("business evidence incomplete: " + "; ".join(errors))
    report = manifest["business_analysis"]["report"]
    destination = local_file(path, report["local_path"])
    if destination.suffix != ".md":
        raise ValueError("report path must end in .md")
    if destination.exists() and file_digest(destination) != report.get("sha256"):
        raise ValueError("report has untracked/manual edits; preserve it and choose another local_path")
    content, _ = render_report(manifest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(content, encoding="utf-8")
    report["sha256"] = file_digest(destination)
    invalidate(manifest, "pricing report regenerated; publish in existing child and revalidate")
    atomic_json(path, manifest)
    return {"status": "rendered", "path": str(destination), "sha256": report["sha256"], "warnings": warnings,
            "remote_writes": 0, "next": "when C is in scope, update 商业与定价 in the existing child, record heading block, then verify"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    try:
        result = write_report(args.manifest)
    except (KeyError, ValueError, TypeError, AttributeError, OSError) as exc:
        result = {"status": "fail", "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result["status"] == "fail"


if __name__ == "__main__":
    sys.exit(main())
