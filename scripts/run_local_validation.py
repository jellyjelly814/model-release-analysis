#!/usr/bin/env python3
"""Run the repository's offline validation suite in one command.

This runner intentionally avoids compileall/py_compile because some managed
Python installations redirect bytecode caches to a non-writable directory.
It performs AST parsing, test discovery, and validator CLI help checks only;
it never contacts Feishu or the network.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def parse_python_sources() -> int:
    paths = sorted(ROOT.glob("scripts/*.py")) + sorted(ROOT.glob("tests/*.py"))
    for path in paths:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    print(f"ast: pass ({len(paths)} files)")
    return len(paths)


def check_bash_snippets() -> int:
    """Syntax-check documented bash blocks without executing network commands."""
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```bash\n(.*?)```", text, flags=re.DOTALL)
    for block in blocks:
        # Replace documentation placeholders before parsing shell syntax.
        normalized = re.sub(r"<[^>\n]+>", "PLACEHOLDER", block)
        completed = subprocess.run(
            ["sh", "-n"],
            input=normalized,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise SystemExit(f"bash snippet syntax failed: {completed.stderr.strip()}")
    print(f"bash snippets: pass ({len(blocks)} blocks)")
    return len(blocks)


def run_command(arguments: list[str], label: str) -> None:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        arguments,
        cwd=ROOT,
        env=environment,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(f"{label} failed with exit code {completed.returncode}")
    print(f"{label}: pass")


def main() -> int:
    parse_python_sources()
    check_bash_snippets()
    run_command(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
        "unittest",
    )
    run_command([sys.executable, "scripts/validate_child_document.py", "--help"], "child validator CLI")
    run_command([sys.executable, "scripts/validate_vendor_section.py", "--help"], "vendor validator CLI")
    run_command([sys.executable, "scripts/validate_update_manifest.py", "--help"], "manifest validator CLI")
    run_command([sys.executable, "scripts/record_validator_result.py", "--help"], "result recorder CLI")
    print("local validation: pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
