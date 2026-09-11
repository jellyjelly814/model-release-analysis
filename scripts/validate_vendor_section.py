#!/usr/bin/env python3
"""Validate a vendor section against the parent-page model-entry contract."""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
from sync_common import (document_snapshot, assert_document_unchanged, provenance, linked_target, local_file)


TEXT_KEYS = {
    2: "text",
    3: "heading1",
    4: "heading2",
    5: "heading3",
    6: "heading4",
    7: "heading5",
    8: "heading6",
    9: "heading7",
    10: "heading8",
    11: "heading9",
    12: "bullet",
    13: "ordered",
    14: "code",
    15: "quote",
    17: "todo",
}


def load_helper(path):
    helper_path = os.path.expanduser(path)
    if not os.path.isfile(helper_path):
        raise FileNotFoundError(f"Feishu helper does not exist: {helper_path}")
    spec = importlib.util.spec_from_file_location("feishudoc", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load Feishu helper module: {helper_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    missing = [name for name in ("api", "_all_blocks") if not hasattr(module, name)]
    if missing:
        raise RuntimeError(f"Feishu helper is incompatible; missing: {', '.join(missing)}")
    return module


def block_text(block):
    key = TEXT_KEYS.get(block.get("block_type"))
    if not key:
        return ""
    parts = []
    for element in block.get(key, {}).get("elements", []):
        if "text_run" in element:
            parts.append(element["text_run"].get("content", ""))
        elif "mention_doc" in element:
            parts.append(element["mention_doc"].get("title", ""))
    return "".join(parts).strip()


def has_doc_mention(block):
    return any("mention_doc" in element for element in block.get("text", {}).get("elements", []))


def block_urls(block):
    key = TEXT_KEYS.get(block.get("block_type"))
    if not key:
        return []
    urls = []
    for element in block.get(key, {}).get("elements", []):
        text_run = element.get("text_run", {})
        content = text_run.get("content", "")
        style = text_run.get("text_element_style", {})
        link = style.get("link", {})
        if link.get("url"):
            urls.append(link["url"])
        urls.extend(re.findall(r"https?://[^\s]+", content))
    return urls


def clickable_urls(block):
    key = TEXT_KEYS.get(block.get("block_type"))
    if not key:
        return []
    urls = []
    for element in block.get(key, {}).get("elements", []):
        text_run = element.get("text_run", {})
        url = text_run.get("text_element_style", {}).get("link", {}).get("url")
        if url:
            urls.append(url)
        mention = element.get("mention_doc", {})
        if mention.get("url"):
            urls.append(mention["url"])
    return urls


def is_artificial_analysis_url(value):
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    return parsed.scheme in {"http", "https"} and (
        host == "artificialanalysis.ai" or host.endswith(".artificialanalysis.ai")
    )


def image_signature(path):
    head = Path(path).read_bytes()[:16]
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def verify_local_image(record, label):
    violations = []
    local_path = record.get("local_path")
    if not local_path or not os.path.isfile(local_path):
        return [f"{label} local_path is missing or unreadable"]
    if os.path.getsize(local_path) < 100:
        violations.append(f"{label} local file is smaller than 100 bytes")
    if image_signature(local_path) is None:
        violations.append(f"{label} local file is not a supported image by file signature")
    declared = record.get("content_sha256")
    actual = hashlib.sha256(Path(local_path).read_bytes()).hexdigest()
    if not isinstance(declared, str) or declared.lower() != actual:
        violations.append(f"{label} content_sha256 does not match local_path")
    return violations


def descendant_ids(block_id, blocks):
    result = []
    stack = list(blocks[block_id].get("children") or [])
    while stack:
        child_id = stack.pop(0)
        result.append(child_id)
        stack[0:0] = list(blocks.get(child_id, {}).get("children") or [])
    return result


def allowed_trailing_root_block(block):
    return block.get("block_type") == 22 or (
        block.get("block_type") == 2 and not block_text(block)
    )


def social_visual_proof(image_id, manifest, model_entry=None):
    if not manifest:
        return ["social visual proof manifest is required"]
    record = next(
        (
            item
            for item in manifest.get("screenshots", [])
            if item.get("kind") == "social" and item.get("parent_image_block") == image_id
        ),
        None,
    )
    if not record:
        return [f"social image {image_id} has no matching manifest screenshot record"]

    violations = []
    visual = record.get("visual_check", {})
    if visual.get("status") != "verified":
        violations.append("social screenshot visual_check.status must be verified")
    if visual.get("verification_method") != "view_image":
        violations.append("social screenshot must be visually checked with view_image")
    if visual.get("login_wall") is not False:
        violations.append("social screenshot login_wall must be explicitly false")
    if visual.get("blank") is not False:
        violations.append("social screenshot blank must be explicitly false")
    if visual.get("complete_post") is not True:
        violations.append("social screenshot complete_post must be explicitly true")
    if not record.get("source_url", "").startswith("http"):
        violations.append("social screenshot is missing its source URL")
    if model_entry and record.get("model_entry") != model_entry:
        violations.append("social screenshot model_entry does not match the validated entry")
    if "C" in manifest.get("sync_target", {}).get("scope", []) and not record.get("child_image_block"):
        violations.append("social screenshot is missing its child_image_block")
    violations.extend(verify_local_image(record, "social screenshot"))
    return violations


def artificial_analysis_proof(manifest, model_entry=None):
    """Apply the manifest's conditional Artificial Analysis evidence policy."""
    if not manifest:
        return ["Artificial Analysis screenshot manifest is required"]
    if "C" not in manifest.get("sync_target", {}).get("scope", []):
        return []
    policy = manifest.get("evidence_policy", {}).get("artificial_analysis", {})
    status = policy.get("status")
    if status in {"checked_unavailable", "not_applicable"}:
        violations = []
        checked_urls = policy.get("checked_urls")
        if not isinstance(checked_urls, list) or not checked_urls:
            violations.append(f"Artificial Analysis {status} policy requires checked_urls")
        if not isinstance(policy.get("reason"), str) or not policy["reason"].strip():
            violations.append(f"Artificial Analysis {status} policy requires a reason")
        alternatives = policy.get("alternatives")
        if not isinstance(alternatives, list) or not alternatives:
            violations.append(f"Artificial Analysis {status} policy requires alternatives")
        return violations
    if status != "available":
        return ["Artificial Analysis evidence policy status is missing or invalid"]
    records = [
        item
        for item in manifest.get("screenshots", [])
        if item.get("kind") == "artificial_analysis"
        if item.get("source_class") == "independent_benchmark"
        and is_artificial_analysis_url(item.get("source_url"))
        and (model_entry is None or item.get("model_entry") == model_entry)
    ]
    violations = []
    if len(records) < 2:
        violations.append(
            f"at least two distinct Artificial Analysis screenshots are required, found {len(records)}"
        )
    sections = {item.get("source_section") for item in records if item.get("source_section")}
    if len(sections) < 2:
        violations.append("Artificial Analysis screenshots must cover at least two distinct page sections")
    for record in records:
        if "C" in manifest.get("sync_target", {}).get("scope", []) and not record.get("child_image_block"):
            violations.append("Artificial Analysis screenshot is missing its actual child_image_block")
        if not record.get("child_placement"):
            violations.append("Artificial Analysis screenshot is missing its child_placement")
        visual = record.get("visual_check", {})
        if visual.get("status") != "verified":
            violations.append("Artificial Analysis screenshot visual_check.status must be verified")
        if visual.get("verification_method") != "view_image":
            violations.append("Artificial Analysis screenshot must be visually checked with view_image")
        if visual.get("blank") is not False:
            violations.append("Artificial Analysis screenshot blank must be explicitly false")
        violations.extend(verify_local_image(record, "Artificial Analysis screenshot"))
    image_blocks = [record.get("child_image_block") for record in records if record.get("child_image_block")]
    if len(image_blocks) != len(set(image_blocks)):
        violations.append("Artificial Analysis screenshots must use distinct child_image_block values")
    hashes = [record.get("content_sha256") for record in records if record.get("content_sha256")]
    if len(hashes) != len(set(hashes)):
        violations.append("Artificial Analysis screenshots must use distinct content_sha256 values")
    return violations


def validate_entry(root_ids, start, end, blocks, manifest, require_social_visual_proof):
    heading_id = root_ids[start]
    heading = blocks[heading_id]
    title = block_text(heading)
    violations = []
    entry_ids = root_ids[start:end]

    if len(entry_ids) < 5:
        violations.append(
            "entry must contain heading, detail link, main grid, 宣发/社媒 heading, and social grid"
        )
        return {"model": title, "heading": heading_id, "violations": violations}

    detail_id = entry_ids[1]
    detail = blocks[detail_id]
    if detail.get("block_type") != 2 or not block_text(detail).startswith("详细追踪"):
        violations.append("second root block must be the detail-tracking text block")
    elif manifest:
        child = manifest.get("child_wiki_doc", {})
        hosts = manifest.get("sync_target", {}).get("allowed_link_hosts", [])
        if not any(linked_target(element, child.get("obj_token"), child.get("node_token"), hosts)
                   for element in detail.get("text", {}).get("elements", [])):
            violations.append("detail-tracking link does not target the manifest child document")
    elif not clickable_urls(detail) and not has_doc_mention(detail):
        violations.append("detail-tracking block has no clickable document link")

    grid_id = entry_ids[2]
    grid = blocks[grid_id]
    if grid.get("block_type") != 24:
        violations.append("third root block must be the main two-column grid")
        grid_id = None

    social_heading_id = entry_ids[3]
    social_heading = blocks[social_heading_id]
    if social_heading.get("block_type") != 2 or block_text(social_heading) != "宣发/社媒":
        violations.append("fourth root block must be the exact text heading 宣发/社媒")

    social_grid_id = entry_ids[4]
    social_grid = blocks[social_grid_id]
    if social_grid.get("block_type") != 24:
        violations.append("fifth root block must be the social two-column grid")
        social_grid_id = None

    extras = [x for x in entry_ids[5:] if not allowed_trailing_root_block(blocks[x])]
    if extras:
        labels = [f"{blocks[x].get('block_type')}:{block_text(blocks[x])[:30]}" for x in extras]
        violations.append("unexpected root blocks after social grid: " + " | ".join(labels))

    if grid_id:
        columns = grid.get("children") or []
        if len(columns) != 2:
            violations.append(f"grid must have exactly two columns, found {len(columns)}")
        else:
            left_id, right_id = columns
            left_desc = descendant_ids(left_id, blocks)
            right_desc = descendant_ids(right_id, blocks)
            left_text = "\n".join(block_text(blocks[x]) for x in left_desc)
            right_text = "\n".join(block_text(blocks[x]) for x in right_desc)

            if "核心能力" not in left_text:
                violations.append("left column is missing 核心能力")
            if "展示的 Case" not in left_text:
                violations.append("left column is missing 展示的 Case")
            if "宣发" in left_text or "网页" in left_text:
                violations.append("main grid must not contain 宣发/社媒 or 网页 content")
            if "关键参数" not in right_text:
                violations.append("right column is missing 关键参数")
            if "测评" not in right_text:
                violations.append("right column is missing 测评")

            image_ids = [x for x in right_desc if blocks[x].get("block_type") == 27]
            if len(image_ids) != 1:
                violations.append(f"right column must contain exactly one benchmark image, found {len(image_ids)}")
            for image_id in image_ids:
                image = blocks[image_id].get("image", {})
                width, height = image.get("width") or 0, image.get("height") or 0
                if width > 600 or height > 300:
                    violations.append(f"benchmark image exceeds 600x300: {width}x{height}")
                parent_id = blocks[image_id].get("parent_id")
                siblings = blocks.get(parent_id, {}).get("children") or []
                index = siblings.index(image_id) if image_id in siblings else -1
                if index <= 0 or blocks[siblings[index - 1]].get("block_type") != 2 or not block_text(blocks[siblings[index - 1]]):
                    violations.append("benchmark image has no immediately preceding text caption")

    if social_grid_id:
        columns = social_grid.get("children") or []
        if len(columns) != 2:
            violations.append(f"social grid must have exactly two columns, found {len(columns)}")
        else:
            left_id, right_id = columns
            left_desc = descendant_ids(left_id, blocks)
            right_desc = descendant_ids(right_id, blocks)
            left_text_blocks = [block_text(blocks[x]) for x in left_desc if block_text(blocks[x])]
            left_text = "\n".join(left_text_blocks)
            urls = sorted({url for x in left_desc for url in clickable_urls(blocks[x])})

            if not left_text_blocks or left_text_blocks[0] in {"网页", "网页："}:
                violations.append("social left column is missing a propagation analysis paragraph")
            if "网页" not in left_text:
                violations.append("social left column is missing 网页")
            if len(urls) < 2:
                violations.append(f"social left column must contain at least two clickable URLs, found {len(urls)}")

            image_ids = [x for x in right_desc if blocks[x].get("block_type") == 27]
            if len(image_ids) > 1:
                violations.append(f"social right column may contain at most one image, found {len(image_ids)}")
            for image_id in image_ids:
                image = blocks[image_id].get("image", {})
                width, height = image.get("width") or 0, image.get("height") or 0
                if width > 720 or height > 1000:
                    violations.append(f"social image exceeds 720x1000: {width}x{height}")
                if require_social_visual_proof:
                    violations.extend(social_visual_proof(image_id, manifest, title))

    root_images = [x for x in entry_ids if blocks[x].get("block_type") == 27]
    if root_images:
        violations.append("entry contains root-level image blocks outside the grid")

    return {
        "model": title,
        "heading": heading_id,
        "detail": detail_id,
        "grid": grid_id,
        "social_heading": social_heading_id,
        "social_grid": social_grid_id,
        "violations": violations,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc", required=True)
    parser.add_argument("--vendor", required=True, help="Substring of the vendor heading")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--model-entry", help="Exact dated model heading to validate for this delivery")
    scope.add_argument(
        "--all-entries",
        action="store_true",
        help="Validate every dated entry in the vendor section for an explicit migration audit",
    )
    parser.add_argument(
        "--helper",
        required=True,
        help="Path to an existing compatible Feishu helper; no private-directory default is assumed",
    )
    parser.add_argument("--manifest", help="Update manifest containing social screenshot proof")
    parser.add_argument(
        "--require-social-visual-proof",
        action="store_true",
        help="Fail unless every social image has verified, nonblank, non-login-wall manifest proof",
    )
    parser.add_argument(
        "--require-artificial-analysis",
        action="store_true",
        help="Apply the manifest's conditional Artificial Analysis evidence policy",
    )
    args = parser.parse_args()

    if args.require_social_visual_proof and not args.manifest:
        parser.error("--require-social-visual-proof requires --manifest")
    if args.require_artificial_analysis and not args.manifest:
        parser.error("--require-artificial-analysis requires --manifest")
    manifest = None
    if args.manifest:
        with open(args.manifest, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        if not isinstance(manifest, dict) or manifest.get("schema_version") != 3:
            raise ValueError("vendor validation requires manifest schema_version 3")

    if manifest:
        for record in manifest.get("screenshots", []):
            record["local_path"] = str(local_file(args.manifest, record["local_path"]))
    fd = load_helper(args.helper)
    snapshot = document_snapshot(fd, args.doc)
    items = snapshot["blocks"]
    blocks = {block.get("block_id"): block for block in items}
    root = blocks.get(args.doc) or next((b for b in items if b.get("block_type") == 1), None)
    if not root:
        raise RuntimeError("document root block not found")
    root_ids = root.get("children") or []

    vendor_index = next(
        (i for i, block_id in enumerate(root_ids) if blocks[block_id].get("block_type") == 4 and args.vendor == block_text(blocks[block_id])),
        None,
    )
    if vendor_index is None:
        raise RuntimeError(f"vendor heading not found: {args.vendor}")

    section_end = next(
        (i for i in range(vendor_index + 1, len(root_ids)) if blocks[root_ids[i]].get("block_type") == 4),
        len(root_ids),
    )
    heading_indexes = [
        i
        for i in range(vendor_index + 1, section_end)
        if blocks[root_ids[i]].get("block_type") == 5 and block_text(blocks[root_ids[i]]).startswith("【")
    ]
    all_entry_ranges = []
    for position, start in enumerate(heading_indexes):
        end = heading_indexes[position + 1] if position + 1 < len(heading_indexes) else section_end
        all_entry_ranges.append((start, end))

    global_violations = []
    if not heading_indexes:
        global_violations.append("vendor section contains no dated model entries")
    if args.all_entries:
        selected_ranges = all_entry_ranges
        selected_model = None
        validation_scope = "all_entries"
    else:
        selected_ranges = [
            (start, end)
            for start, end in all_entry_ranges
            if block_text(blocks[root_ids[start]]) == args.model_entry
        ]
        selected_model = args.model_entry
        validation_scope = "current_entry"
        if len(selected_ranges) > 1:
            global_violations.append("duplicate current model headings; resolve before completion")
        if heading_indexes and not selected_ranges:
            global_violations.append(f"current model entry not found: {args.model_entry}")

    entries = []
    for start, end in selected_ranges:
        entries.append(
            validate_entry(
                root_ids,
                start,
                end,
                blocks,
                manifest,
                args.require_social_visual_proof,
            )
        )

    if manifest and not args.all_entries:
        manifest_model = manifest.get("parent_section", {}).get("model_entry")
        if manifest_model != args.model_entry:
            global_violations.append("--model-entry must match manifest parent_section.model_entry")
    if args.require_artificial_analysis:
        global_violations.extend(artificial_analysis_proof(manifest, selected_model))
    image_hash_by_block = {}
    if manifest and not args.all_entries:
        selected_ids = {bid for start, end in selected_ranges for rid in root_ids[start:end]
                        for bid in [rid, *descendant_ids(rid, blocks)]}
        records = {r.get("parent_image_block"): r for r in manifest.get("screenshots", []) if r.get("parent_image_block")}
        actual_images = {bid for bid in selected_ids if blocks[bid].get("block_type") == 27}
        if set(records) != actual_images:
            global_violations.append("parent image manifest bindings differ from live current-entry images")
        for bid in actual_images:
            token = blocks[bid].get("image", {}).get("token")
            if not token or not callable(getattr(fd, "download_media", None)):
                raise RuntimeError("parent media cannot be downloaded for hash verification")
            actual = hashlib.sha256(fd.download_media(token)).hexdigest()
            image_hash_by_block[bid] = actual
            if records.get(bid, {}).get("content_sha256") != actual:
                global_violations.append(f"parent image content hash differs from manifest: {bid}")
    assert_document_unchanged(fd, snapshot)
    violation_count = len(global_violations) + sum(len(entry["violations"]) for entry in entries)
    vendor_title = block_text(blocks[root_ids[vendor_index]])
    historical_entries = [
        block_text(blocks[root_ids[index]])
        for index in heading_indexes
        if args.all_entries or block_text(blocks[root_ids[index]]) != args.model_entry
    ]
    output = {
        **(provenance(json.loads(Path(args.manifest).read_text()), snapshot) if manifest else {}),
        "snapshot": snapshot,
        "image_hash_by_block": image_hash_by_block,
        "audit_only": bool(args.all_entries or not manifest),
        "status": "pass" if violation_count == 0 else "fail",
        "vendor": vendor_title,
        "document": args.doc,
        "model_entry": selected_model,
        "validation_scope": validation_scope,
        "historical_entries": historical_entries,
        "manifest": args.manifest,
        "require_social_visual_proof": args.require_social_visual_proof,
        "require_artificial_analysis": args.require_artificial_analysis,
        "global_violations": global_violations,
        "entries": entries,
        "violation_count": violation_count,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    sys.exit(0 if violation_count == 0 else 1)


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
