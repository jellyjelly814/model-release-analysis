#!/usr/bin/env python3
"""Validate an independent model-release Wiki document against the child template."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from sync_common import (document_snapshot, assert_document_unchanged, provenance, linked_target,
                         SOURCE_CLASSES, load_helper as shared_load_helper)


TEXT_KEYS = {
    2: "text", 3: "heading1", 4: "heading2", 5: "heading3", 6: "heading4",
    7: "heading5", 8: "heading6", 9: "heading7", 10: "heading8", 11: "heading9",
    12: "bullet", 13: "ordered", 14: "code", 15: "quote", 17: "todo",
}
HEADING_TYPES = set(range(3, 12))
FORBIDDEN_READER_TEXT = (
    ("internal normalization label", re.compile(r"规范化摘要")),
    ("template name exposed", re.compile(r"按\s*GPT-[^，。；\n]{0,24}(?:模板|子文档)")),
    ("community classification instruction exposed", re.compile(r"社区反馈按.{0,40}(?:分开记录|分类记录)")),
    ("asset-selection instruction exposed", re.compile(r"优先保留(?:官网|官方|客户|截图|证据)")),
    ("future agent task exposed", re.compile(r"(?:每个\s*Demo|后续).{0,24}(?:继续补|补充)(?:来源|截图|URL|证据)?")),
    ("agent-facing rule exposed", re.compile(r"(?:模板名称|执行步骤|执行要求|验收规则|验收提醒|截图合同|面向\s*Agent|给\s*Agent)")),
    ("layout instruction exposed", re.compile(r"每列(?:只)?保留一张图")),
    ("KOL classification instruction exposed", re.compile(r"避免把普通转发写成\s*KOL\s*背书", re.I)),
    ("screenshot workflow instruction exposed", re.compile(
        r"(?:下面使用|不再使用|下面截取|不再保留).{0,24}(?:发布页|截图|逻辑区块|半截|截断)"
    )),
    ("benchmark placement instruction exposed", re.compile(
        r"(?:具体榜单|榜单).{0,24}(?:放到|放在).{0,24}(?:Benchmark|逐项拆解)", re.I
    )),
    ("summary substitution instruction exposed", re.compile(
        r"避免(?:只)?用一张(?:总览图|总榜图|截图).{0,24}(?:代替|替代|冒充)"
    )),
    ("writing directive exposed", re.compile(
        r"(?:应写成|不能写成|不能把.{0,48}(?:写成|包装成))[“\"].{0,48}[”\"]?"
    )),
    ("evidence admission instruction exposed", re.compile(
        r"普通截图.{0,20}(?:不纳入|不进入).{0,20}(?:证据|Demo)", re.I
    )),
    ("placement instruction exposed", re.compile(
        r"(?:把|将).{0,24}(?:榜单|截图|图片|图表).{0,24}(?:放到|放在|插入).{0,24}(?:小节|Benchmark|正文|右列|下方)", re.I
    )),
    ("generic normalized subsection exposed", re.compile(r"^(?:核心能力|展示 Case|外部复现与可复用任务|Case：完整任务结果)$")),
    ("generic release-table fallback exposed", re.compile(
        r"^(?:上一代按原有产品线迭代|本次围绕新的能力重点集中发布|以常规产品更新为主|"
        r"单点能力或常规升级|按既有生态扩散|合作伙伴、客户与社区反馈分开验证|"
        r"沿用已有入口|跑分或产品文案|完整 Benchmark \+ Case \+ 社媒原帖三类证据)$"
    )),
)


def load_helper(path):
    helper = shared_load_helper(path)
    if not callable(getattr(helper, "download_media", None)):
        raise ValueError("helper must provide download_media without exposing raw credentials")
    return helper


def block_text(block):
    key = TEXT_KEYS.get(block.get("block_type"))
    if not key:
        return ""
    return "".join(
        element.get("text_run", {}).get("content", "")
        or element.get("mention_doc", {}).get("title", "")
        for element in block.get(key, {}).get("elements", [])
    ).strip()


def block_urls(block):
    key = TEXT_KEYS.get(block.get("block_type"))
    if not key:
        return []
    urls = []
    for element in block.get(key, {}).get("elements", []):
        text_run = element.get("text_run", {})
        url = text_run.get("text_element_style", {}).get("link", {}).get("url")
        if url:
            urls.append(url)
        urls.extend(re.findall(r"https?://[^\s]+", text_run.get("content", "")))
        mention = element.get("mention_doc", {})
        if mention.get("url"):
            urls.append(mention["url"])
    return urls


def clickable_urls(block):
    """Return URLs carried by actual links, not URLs that merely appear as text."""
    key = TEXT_KEYS.get(block.get("block_type"))
    if not key:
        return []
    urls = []
    for element in block.get(key, {}).get("elements", []):
        text_run = element.get("text_run", {})
        link = text_run.get("text_element_style", {}).get("link", {})
        if link.get("url"):
            urls.append(link["url"])
        mention = element.get("mention_doc", {})
        if mention.get("url"):
            urls.append(mention["url"])
    return urls


def descendant_ids(block_id, blocks):
    result = []
    stack = list(blocks[block_id].get("children") or [])
    while stack:
        child_id = stack.pop(0)
        result.append(child_id)
        stack[0:0] = list(blocks.get(child_id, {}).get("children") or [])
    return result


def resolve_document(fd, token):
    for suffix in ("", "&obj_type=docx"):
        _, response = fd.api("GET", f"/open-apis/wiki/v2/spaces/get_node?token={token}{suffix}")
        if response.get("code") == 0:
            return response["data"]["node"]["obj_token"], response["data"]["node"]
    _, response = fd.api("GET", f"/open-apis/docx/v1/documents/{token}")
    if response.get("code") == 0:
        _, node_response = fd.api(
            "GET",
            f"/open-apis/wiki/v2/spaces/get_node?token={token}&obj_type=docx",
        )
        node = node_response.get("data", {}).get("node") if node_response.get("code") == 0 else None
        return token, node
    raise RuntimeError(f"cannot resolve document or Wiki node: {token}")


def find_heading(root_ids, blocks, predicate):
    for index, block_id in enumerate(root_ids):
        block = blocks[block_id]
        if block.get("block_type") in HEADING_TYPES and predicate(block_text(block).lower()):
            return index
    return None


def has_table_ancestor(block_id, blocks):
    current = blocks.get(block_id, {})
    while current.get("parent_id"):
        current = blocks.get(current["parent_id"], {})
        if current.get("block_type") == 31:
            return True
    return False


def image_digest(fd, token):
    return hashlib.sha256(fd.download_media(token)).hexdigest()


def load_manifest(path):
    manifest_path = Path(path).expanduser()
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest does not exist: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest root must be a JSON object")
    if manifest.get("schema_version") != 3:
        raise ValueError("child validation requires manifest schema_version 3")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc", required=True, help="Child docx token or Wiki node token")
    parser.add_argument(
        "--parent-node",
        required=True,
        help="Actual parent Wiki node token returned by the API; never infer a default target",
    )
    parser.add_argument(
        "--helper",
        required=True,
        help="Path to an existing compatible Feishu helper; no private-directory default is assumed",
    )
    parser.add_argument(
        "--manifest",
        required=True,
        help="Path to the v3 manifest used to bind model, images, and target tokens",
    )
    args = parser.parse_args()

    manifest = load_manifest(args.manifest) if args.manifest else None
    fd = load_helper(args.helper)
    document_id, wiki_node = resolve_document(fd, args.doc)
    snapshot = document_snapshot(fd, document_id)
    title = snapshot["metadata"].get("title", "")
    items = snapshot["blocks"]
    blocks = {block["block_id"]: block for block in items}
    root = blocks.get(document_id) or next((block for block in items if block.get("block_type") == 1), None)
    if not root:
        raise RuntimeError("document root block not found")
    root_ids = root.get("children") or []
    violations = []
    reader_text_hits = []
    heading_audit = []

    for block in items:
        block_type = block.get("block_type")
        if block_type not in HEADING_TYPES:
            continue
        level = block_type - 2
        parent_id = block.get("parent_id")
        heading_audit.append({
            "block_id": block.get("block_id"),
            "level": level,
            "parent_id": parent_id,
            "text": block_text(block)[:160],
        })
        if parent_id == document_id and level >= 3:
            violations.append(
                f"root-level heading{level} is not allowed; use a true H1 section, H2 subsection, or body label: {block.get('block_id')}"
            )

    if not root_ids or blocks[root_ids[0]].get("block_type") != 19:
        violations.append("document must start with a reader-facing summary callout")
    else:
        callout_ids = descendant_ids(root_ids[0], blocks)
        callout_text_blocks = [block_id for block_id in callout_ids if block_text(blocks[block_id])]
        callout_urls = [url for block_id in callout_ids for url in clickable_urls(blocks[block_id])]
        if len(callout_text_blocks) < 3:
            violations.append("opening callout must contain a core judgment, positioning, and source links")
        if len(callout_urls) < 2:
            violations.append("opening callout must contain at least two clickable official source links")

    for block in items:
        text = block_text(block)
        if not text:
            continue
        for label, pattern in FORBIDDEN_READER_TEXT:
            if pattern.search(text):
                reader_text_hits.append({
                    "block_id": block["block_id"],
                    "rule": label,
                    "text": text[:240],
                })
                violations.append(f"agent-facing text is visible in {block['block_id']}: {label}")

    if not re.match(r"^【\d{4}/\d{2}/\d{2}】.{4,}", title):
        violations.append("title must start with 【YYYY/MM/DD】 and include model plus release theme")
    if not wiki_node:
        violations.append("document is not resolved as a Wiki node")
    elif wiki_node.get("parent_node_token") != args.parent_node:
        violations.append(
            f"Wiki parent mismatch: expected {args.parent_node}, found {wiki_node.get('parent_node_token') or '(root)'}"
        )

    section_rules = [
        ("基本信息", lambda text: text.startswith("基本信息")),
        ("模型特点 + 展示 Case", lambda text: "模型特点" in text and ("case" in text or "展示" in text)),
        ("Benchmark", lambda text: "benchmark" in text or text.startswith("测评")),
        ("发布过程", lambda text: text == "发布过程" or text.startswith("发布过程：")),
        ("发布过程与社区声势", lambda text: "社区声势" in text or "宣发对比" in text),
        ("社区 Demo", lambda text: "社区" in text and ("demo" in text or "案例" in text)),
        ("MiniMax 可以借鉴的", lambda text: "minimax" in text and "借鉴" in text),
    ]
    indexes = {}
    for label, predicate in section_rules:
        indexes[label] = find_heading(root_ids, blocks, predicate)
        if indexes[label] is None:
            violations.append(f"missing required section heading: {label}")

    ordered_labels = [label for label, _ in section_rules if indexes.get(label) is not None]
    ordered_indexes = [indexes[label] for label in ordered_labels]
    if ordered_indexes != sorted(ordered_indexes):
        violations.append("required sections are not in the template order")

    grids = [block for block in items if block.get("block_type") == 24]
    if len(grids) < 3:
        violations.append(f"child document must contain at least three visual grids, found {len(grids)}")
    column_counts = [len(grid.get("children") or []) for grid in grids]
    for required_columns, label in ((4, "opening evidence wall"), (2, "capability / benchmark"), (3, "release / community")):
        if required_columns not in column_counts:
            violations.append(f"missing required {required_columns}-column {label} grid")
    opening_four_column = (
        blocks.get(root_ids[1])
        if len(root_ids) > 1
        and blocks.get(root_ids[1], {}).get("block_type") == 24
        and len(blocks.get(root_ids[1], {}).get("children") or []) == 4
        else None
    )
    if opening_four_column is None:
        violations.append("four-column evidence wall must immediately follow the opening callout")
    for grid in grids:
        columns = grid.get("children") or []
        if len(columns) not in (2, 3, 4):
            violations.append(f"grid {grid['block_id']} must have 2, 3, or 4 columns, found {len(columns)}")
            continue
        grid_texts = []
        grid_images = []
        for column_id in columns:
            column_descendants = descendant_ids(column_id, blocks)
            heading_descendants = [
                child_id for child_id in column_descendants
                if blocks.get(child_id, {}).get("block_type") in HEADING_TYPES
            ]
            if heading_descendants:
                violations.append(
                    f"grid {grid['block_id']} contains heading blocks; use bold body labels inside grids: "
                    + ", ".join(heading_descendants)
                )
            image_ids = [child_id for child_id in column_descendants if blocks.get(child_id, {}).get("block_type") == 27]
            column_text = "\n".join(
                block_text(blocks[child_id]) for child_id in column_descendants
                if block_text(blocks[child_id])
            )
            if column_text:
                grid_texts.append(column_text)
            grid_images.extend(image_ids)
        if grid_images and len(columns) != 4 and not grid_texts:
            root_index = root_ids.index(grid["block_id"]) if grid["block_id"] in root_ids else -1
            nearby = []
            if root_index > 0:
                nearby.append(block_text(blocks.get(root_ids[root_index - 1], {})))
            if root_index >= 0 and root_index + 1 < len(root_ids):
                nearby.append(block_text(blocks.get(root_ids[root_index + 1], {})))
            if not any(nearby):
                violations.append(f"grid {grid['block_id']} contains images without nearby explanatory text")
        if len(columns) == 4:
            image_counts = [
                len([
                    child_id for child_id in descendant_ids(column_id, blocks)
                    if blocks.get(child_id, {}).get("block_type") == 27
                ])
                for column_id in columns
            ]
            if image_counts != [1, 1, 1, 1]:
                violations.append(f"four-column evidence wall must contain one image per column, found {image_counts}")

    images = [block for block in items if block.get("block_type") == 27]
    if len(images) < 2:
        violations.append(f"child document must contain at least two evidence images, found {len(images)}")
    image_hashes = {}
    image_hash_by_block = {}
    image_hash_errors = []
    for image_block in images:
        image_id = image_block["block_id"]
        image = image_block.get("image") or {}
        width = image.get("width") or 0
        height = image.get("height") or 0
        if width <= 200 or height <= 200:
            violations.append(f"image {image_id} is an unreadable thumbnail at {width}x{height}")
        token = image.get("token")
        if not token:
            message = "image block is missing its Feishu media token"
            image_hash_errors.append({"block_id": image_id, "error": message})
            violations.append(f"image {image_id} {message}")
        else:
            try:
                digest = image_digest(fd, token)
                image_hashes.setdefault(digest, []).append(image_id)
                image_hash_by_block[image_id] = digest
            except Exception as exc:
                raise RuntimeError(
                    f"cannot read image media for duplicate-content validation: "
                    f"{image_id}: {type(exc).__name__}: {exc}"
                ) from exc
        if has_table_ancestor(image_id, blocks):
            violations.append(f"image {image_id} is inside a table")
        if image_id in root_ids:
            index = root_ids.index(image_id)
            previous_text = block_text(blocks.get(root_ids[index - 1], {})) if index > 0 else ""
            if not previous_text:
                violations.append(f"root-level image {image_id} has no preceding explanatory text")

    duplicate_image_groups = [block_ids for block_ids in image_hashes.values() if len(block_ids) > 1]
    for block_ids in duplicate_image_groups:
        violations.append(f"same image content is repeated across blocks: {', '.join(block_ids)}")

    model_entry = None
    screenshot_by_child_block = {}
    if manifest is not None:
        parent_section = manifest.get("parent_section")
        child_target = manifest.get("child_wiki_doc")
        screenshots = manifest.get("screenshots")
        model_entry = parent_section.get("model_entry") if isinstance(parent_section, dict) else None
        if not isinstance(model_entry, str) or not model_entry.strip():
            violations.append("manifest parent_section.model_entry is missing")
        if not isinstance(child_target, dict):
            violations.append("manifest child_wiki_doc must be an object")
        else:
            expected_child = {
                "obj_token": document_id,
                "node_token": wiki_node.get("node_token") if wiki_node else None,
                "parent_node_token": args.parent_node,
                "title": title,
            }
            for key, value in expected_child.items():
                if child_target.get(key) != value:
                    violations.append(f"manifest child_wiki_doc.{key} does not match the live child document")

        if not isinstance(screenshots, list):
            violations.append("manifest screenshots must be an array")
            screenshots = []
        for index, record in enumerate(screenshots):
            if not isinstance(record, dict):
                violations.append(f"manifest screenshots[{index}] must be an object")
                continue
            if record.get("model_entry") != model_entry:
                violations.append(f"manifest screenshots[{index}].model_entry does not match parent_section.model_entry")
            child_block = record.get("child_image_block")
            if not child_block:
                continue
            if child_block in screenshot_by_child_block:
                violations.append(f"manifest child_image_block is duplicated: {child_block}")
                continue
            screenshot_by_child_block[child_block] = record
            if child_block not in blocks or blocks[child_block].get("block_type") != 27:
                violations.append(f"manifest child_image_block is missing from the live child document: {child_block}")
                continue
            if record.get("content_sha256") != image_hash_by_block.get(child_block):
                violations.append(f"manifest content_sha256 does not match live child image block: {child_block}")

    unbound = sorted(set(image_hash_by_block) - set(screenshot_by_child_block))
    if unbound:
        violations.append("live child images missing manifest binding: " + ", ".join(unbound))

    if opening_four_column is not None and manifest is not None:
        opening_image_ids = [
            block_id
            for column_id in opening_four_column.get("children") or []
            for block_id in descendant_ids(column_id, blocks)
            if blocks.get(block_id, {}).get("block_type") == 27
        ]
        missing_records = [block_id for block_id in opening_image_ids if block_id not in screenshot_by_child_block]
        if missing_records:
            violations.append(
                "opening evidence images are missing manifest screenshot records: " + ", ".join(missing_records)
            )
        source_classes = {
            screenshot_by_child_block[block_id].get("source_class")
            for block_id in opening_image_ids
            if block_id in screenshot_by_child_block
            and screenshot_by_child_block[block_id].get("source_class")
        }
        originals = [screenshot_by_child_block[bid].get("source_original") for bid in opening_image_ids if bid in screenshot_by_child_block]
        if len(set(originals)) != len(originals):
            violations.append("opening evidence wall repeats one original source through crops")
        if not source_classes <= SOURCE_CLASSES:
            violations.append("opening evidence wall uses an unknown source_class")
        if len(source_classes) < 3:
            violations.append(
                f"opening evidence wall must cover at least three manifest source classes, found {len(source_classes)}"
            )

    benchmark_index = indexes.get("Benchmark")
    release_index = indexes.get("发布过程")
    feature_index = indexes.get("模型特点 + 展示 Case")
    if feature_index is not None and benchmark_index is not None and feature_index < benchmark_index:
        capability_subheadings = [
            block_id for block_id in root_ids[feature_index + 1:benchmark_index]
            if blocks[block_id].get("block_type") == 4 and block_text(blocks[block_id])
        ]
        if len(capability_subheadings) < 2:
            violations.append(
                "模型特点 + 展示 Case must contain at least two model-specific capability subsections"
            )
    if benchmark_index is not None and release_index is not None and benchmark_index < release_index:
        benchmark_grids = [
            blocks[block_id] for block_id in root_ids[benchmark_index + 1:release_index]
            if blocks[block_id].get("block_type") == 24
        ]
        valid_benchmark_grid = False
        for grid in benchmark_grids:
            columns = grid.get("children") or []
            if len(columns) != 2:
                continue
            left_text = "\n".join(
                block_text(blocks[child_id]) for child_id in descendant_ids(columns[0], blocks)
                if block_text(blocks[child_id])
            )
            right_images = [
                child_id for child_id in descendant_ids(columns[1], blocks)
                if blocks[child_id].get("block_type") == 27
            ]
            if left_text and len(right_images) == 1:
                valid_benchmark_grid = True
                break
        if not valid_benchmark_grid:
            violations.append("Benchmark section must contain a two-column grid with text left and one image right")

    takeaways_index = indexes.get("MiniMax 可以借鉴的")
    if release_index is not None:
        stop = takeaways_index if takeaways_index is not None and takeaways_index > release_index else len(root_ids)
        release_tables = [
            block_id for block_id in root_ids[release_index + 1:stop]
            if blocks[block_id].get("block_type") == 31
        ]
        if not release_tables:
            violations.append("发布过程 section must contain a comparison table")

    urls = sorted({url for block in items for url in block_urls(block)})
    clickable = sorted({url for block in items for url in clickable_urls(block)})
    if len(urls) < 3:
        violations.append(f"child document must contain at least three source URLs, found {len(urls)}")
    target = manifest["sync_target"]
    if not any(linked_target(element, target["parent_doc"], args.parent_node, target["allowed_link_hosts"])
               for block in items for element in block.get(TEXT_KEYS.get(block.get("block_type")), {}).get("elements", [])):
        violations.append("child document is missing a clickable return link to the parent summary Wiki")

    assert_document_unchanged(fd, snapshot)
    output = {
        **provenance(manifest, snapshot),
        "snapshot": snapshot,
        "image_hash_by_block": image_hash_by_block,
        "status": "pass" if not violations else "fail",
        "document": document_id,
        "wiki_node": wiki_node.get("node_token") if wiki_node else None,
        "title": title,
        "parent_node": wiki_node.get("parent_node_token") if wiki_node else None,
        "model_entry": model_entry,
        "manifest": str(Path(args.manifest).expanduser()),
        "sections": indexes,
        "grid_count": len(grids),
        "grid_column_counts": column_counts,
        "opening_callout": root_ids[0] if root_ids and blocks[root_ids[0]].get("block_type") == 19 else None,
        "image_count": len(images),
        "table_count": len([block for block in items if block.get("block_type") == 31]),
        "url_count": len(urls),
        "clickable_url_count": len(clickable),
        "heading_audit": heading_audit,
        "reader_text_hits": reader_text_hits,
        "duplicate_image_groups": duplicate_image_groups,
        "image_hash_errors": image_hash_errors,
        "violations": violations,
        "violation_count": len(violations),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    sys.exit(0 if not violations else 1)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "fail",
                    "violation_count": 1,
                    "operational_error": True,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        sys.exit(1)
