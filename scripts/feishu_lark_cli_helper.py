#!/usr/bin/env python3
"""Small Feishu helper backed by the installed ``lark-cli`` binary.

The remote validators were originally written for a Python helper that owns
the HTTP token.  This adapter deliberately delegates authentication to
``lark-cli --as user`` instead of reading or storing an access token in the
project.  It exposes the minimal functions required by both validators.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit


BASE = "https://open.feishu.cn"
CLI = os.environ.get("LARK_CLI_BIN", "lark-cli")
IDENTITY = os.environ.get("LARK_CLI_AS", "user")


def _decode_json(stdout: str) -> Any:
    """Decode JSON even if a CLI notice precedes the JSON payload."""

    decoder = json.JSONDecoder()
    for index, char in enumerate(stdout):
        if char not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(stdout[index:])
            return value
        except json.JSONDecodeError:
            continue
    raise RuntimeError(f"lark-cli returned no JSON payload: {stdout[:400]}")


def _run_cli(args: list[str], *, cwd: str | None = None) -> tuple[int, str, str]:
    completed = subprocess.run(
        [CLI, *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    return completed.returncode, completed.stdout, completed.stderr


def api(method: str, path: str):
    """Call a Feishu API path through lark-cli and return helper-style data."""

    if method.upper() not in {"GET", "HEAD"}:
        raise ValueError("validation helper permits read-only requests")
    parsed = urlsplit(path)
    # The installed lark-cli exposes the generic API formatter as
    # ``--format json``; unlike shortcut commands it does not accept the
    # ``--json`` shorthand here.
    args = ["api", method.upper(), parsed.path, "--as", IDENTITY, "--format", "json"]
    if parsed.query:
        args.extend(
            [
                "--params",
                json.dumps(dict(parse_qsl(parsed.query, keep_blank_values=True)), ensure_ascii=False),
            ]
        )
    returncode, stdout, stderr = _run_cli(args)
    if returncode != 0:
        detail = (stdout or stderr).strip()
        return None, {"code": returncode, "msg": detail}
    payload = _decode_json(stdout)
    # lark-cli 1.0.13 returns the raw API envelope (``code: 0``), while
    # newer builds may wrap it as ``ok: true``. Support both shapes.
    if payload.get("ok") is True or payload.get("code") == 0:
        return None, {"code": 0, "data": payload.get("data", {})}
    error = payload.get("error") or {}
    return None, {
        "code": error.get("code") or returncode or 1,
        "msg": error.get("message") or "lark-cli API call failed",
        "data": payload.get("data", {}),
    }


def _all_blocks(document_id: str) -> list[dict[str, Any]]:
    """Read all document blocks, following the Docx API page token."""

    blocks: list[dict[str, Any]] = []
    page_token = ""
    seen_tokens = set()
    while True:
        params = {"page_size": "500", "document_revision_id": "-1"}
        if page_token:
            params["page_token"] = page_token
        path = f"/open-apis/docx/v1/documents/{document_id}/blocks?{urlencode(params)}"
        _, response = api("GET", path)
        if response.get("code") != 0:
            raise RuntimeError(response.get("msg") or "cannot fetch document blocks")
        data = response.get("data") or {}
        blocks.extend(data.get("items") or [])
        if not data.get("has_more"):
            return blocks
        page_token = data.get("page_token") or ""
        if not page_token or page_token in seen_tokens:
            raise RuntimeError("block API returned a missing or repeated page_token")
        seen_tokens.add(page_token)


def download_media(token: str) -> bytes:
    """Download media through lark-cli without exposing a bearer token."""

    with tempfile.TemporaryDirectory(prefix="feishu-media-") as directory:
        output_name = "media.bin"
        path = f"/open-apis/drive/v1/medias/{token}/download"
        returncode, stdout, stderr = _run_cli(
            ["api", "GET", path, "--as", IDENTITY, "--output", output_name],
            cwd=directory,
        )
        output_path = Path(directory) / output_name
        if returncode != 0 or not output_path.is_file():
            detail = (stdout or stderr).strip()
            raise RuntimeError(detail or f"cannot download Feishu media {token}")
        return output_path.read_bytes()


def _uat() -> str:
    """Optional raw UAT hook required by the legacy validator contract.

    The adapter intentionally does not read credentials from disk.  Media
    validation uses ``download_media`` above, which lets lark-cli manage the
    current user token.  Set FEISHU_USER_ACCESS_TOKEN only if another caller
    explicitly needs the legacy raw-HTTP hook.
    """

    token = os.environ.get("FEISHU_USER_ACCESS_TOKEN")
    if not token:
        raise RuntimeError(
            "raw UAT is not exposed by this adapter; use download_media() "
            "or provide FEISHU_USER_ACCESS_TOKEN explicitly"
        )
    return token


def _shortcut(args):
    code, stdout, _ = _run_cli(["sheets", *args, "--as", IDENTITY, "--format", "json"])
    if code:
        raise RuntimeError(f"sheets read command failed (exit {code})")
    result = _decode_json(stdout)
    if result.get("ok") is not True or not isinstance(result.get("data"), dict):
        raise RuntimeError("sheets shortcut did not return a successful data object")
    return result["data"]


def sheet_metadata(token, sheet_id):
    data = _shortcut(["+workbook-info", "--spreadsheet-token", token])
    sheets = data.get("sheets")
    if not isinstance(sheets, list):
        raise RuntimeError("workbook-info missing sheets; update the adapter for the observed CLI schema")
    matches = [s for s in sheets if s.get("sheet_id", s.get("reference_id")) == sheet_id]
    if len(matches) != 1:
        raise RuntimeError("cannot uniquely resolve requested sheet")
    sheet = matches[0]
    grid = sheet.get("grid_properties", sheet)
    rows, cols = grid.get("row_count"), grid.get("column_count")
    if not isinstance(rows, int) or not isinstance(cols, int) or rows < 1 or cols < 1:
        raise RuntimeError("sheet physical dimensions unavailable")
    return {"row_count": rows, "column_count": cols, "sheet_id": sheet_id}


def read_sheet_range(token, sheet_id, a1_range):
    """Typed CLI read with original row/column coordinates and formula preservation.

    Fail closed on truncation or an unfamiliar envelope; never infer cell addresses
    from a clipped matrix. Validation compares the normalized snapshot twice.
    """
    data = _shortcut(["+cells-get", "--spreadsheet-token", token, "--sheet-id", sheet_id,
                      "--range", a1_range, "--include", "value,formula", "--skip-hidden=false"])
    if data.get("has_more") or data.get("truncated") or data.get("warning_message"):
        raise RuntimeError("sheet read truncated or warned; split the requested range")
    ranges = data.get("ranges")
    if not isinstance(ranges, list) or len(ranges) != 1:
        raise RuntimeError("cells-get missing one explicit range; unsupported CLI schema")
    item = ranges[0]
    if item.get("has_more") or item.get("truncated") or item.get("warning_message"):
        raise RuntimeError("sheet range incomplete")
    actual = item.get("actual_range", "").split("!")[-1].replace("$", "")
    if actual != a1_range:
        raise RuntimeError("requested sheet range was clipped or changed")
    rows, cols, cells = item.get("row_indices"), item.get("col_indices"), item.get("cells")
    if not isinstance(rows, list) or not isinstance(cols, list) or not isinstance(cells, list):
        raise RuntimeError("cells-get missing original coordinates")
    if len(cells) != len(rows) or any(not isinstance(row, list) or len(row) != len(cols) for row in cells):
        raise RuntimeError("cells-get matrix incomplete")
    values, formulas = [], []
    for row in cells:
        value_row, formula_row = [], []
        for cell in row:
            if cell is None:
                cell = {}
            if not isinstance(cell, dict):
                raise RuntimeError("cells-get returned an unsupported cell representation")
            value_row.append(cell.get("value"))
            formula_row.append(cell.get("formula") or None)
        values.append(value_row)
        formulas.append(formula_row)
    return {"range": actual, "row_indices": rows, "col_indices": cols,
            "values": values, "formulas": formulas}
