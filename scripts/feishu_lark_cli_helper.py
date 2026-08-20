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
    )
    return completed.returncode, completed.stdout, completed.stderr


def api(method: str, path: str):
    """Call a Feishu API path through lark-cli and return helper-style data."""

    parsed = urlsplit(path)
    args = ["api", method.upper(), parsed.path, "--as", IDENTITY, "--json"]
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
    if payload.get("ok") is True:
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
        if not page_token:
            raise RuntimeError("block API reported has_more without a page_token")


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
