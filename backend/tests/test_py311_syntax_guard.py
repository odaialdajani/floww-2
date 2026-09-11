"""
backend/tests/test_py311_syntax_guard.py — CI runs Python 3.11 while the
local venv is 3.12. 3.12 accepts nested same-type quotes in f-strings;
3.11 raises SyntaxError at import, which broke conftest collection and
failed the entire backend-tests job (routes/quant.py:187, 2026-09-05).

Compiles every backend source with a real 3.11 interpreter when one is
available (CI provides python3.11; dev macs carry ~/.local/bin/python3.11).
Skips only when no 3.11 exists anywhere on PATH.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

import pytest


def _py311() -> str | None:
    if sys.version_info[:2] == (3, 11):
        return sys.executable
    for cand in ("python3.11", os.path.expanduser("~/.local/bin/python3.11")):
        path = shutil.which(cand) or (cand if pathlib.Path(cand).exists() else None)
        if path:
            return path
    return None


def _sources() -> list[pathlib.Path]:
    root = pathlib.Path(__file__).parent.parent
    return sorted(
        p for p in root.rglob("*.py")
        if ".venv" not in p.parts and "__pycache__" not in p.parts
    )


def test_all_backend_sources_compile_as_py311():
    py311 = _py311()
    if py311 is None:
        pytest.skip("no python3.11 on PATH")
    bad = []
    for p in _sources():
        r = subprocess.run([py311, "-m", "py_compile", str(p)],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            tail = (r.stderr.strip().splitlines() or ["compile failed"])[-1]
            bad.append(f"{p}: {tail}")
    assert not bad, "not 3.11-compilable:\n" + "\n".join(bad)
