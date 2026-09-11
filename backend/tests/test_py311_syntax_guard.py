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

import json
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


def _sources(root=None) -> list[pathlib.Path]:
    root = root or pathlib.Path(__file__).parent.parent
    result = []
    for current, directories, files in os.walk(root):
        parent = pathlib.Path(current)
        directories[:] = [
            name for name in directories
            if name not in {".venv", "__pycache__"}
            and not (parent / name / "pyvenv.cfg").is_file()
        ]
        result.extend(parent / name for name in files if name.endswith(".py"))
    return sorted(result)


def _compile_sources(py311, sources):
    # One real 3.11 process checks every source. Compilation preserves encoding
    # cookies and syntax validation without importing code or writing bytecode.
    program = (
        "import json,pathlib,sys\n"
        "assert sys.version_info[:2] == (3,11)\n"
        "bad=[]\n"
        "for name in json.load(sys.stdin):\n"
        "    try: compile(pathlib.Path(name).read_bytes(),name,'exec')\n"
        "    except (SyntaxError,ValueError) as exc: bad.append(name+': '+str(exc))\n"
        "print(json.dumps(bad))\n"
    )
    result = subprocess.run(
        [py311, "-c", program], input=json.dumps([str(path) for path in sources]),
        capture_output=True, text=True, timeout=120,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_all_backend_sources_compile_as_py311():
    py311 = _py311()
    if py311 is None:
        pytest.skip("no python3.11 on PATH")
    bad = _compile_sources(py311, _sources())
    assert not bad, "not 3.11-compilable:\n" + "\n".join(bad)


def test_alternate_virtual_environment_is_not_application_source(tmp_path):
    app = tmp_path / "application.py"
    app.write_text("value = 1\n", encoding="utf-8")
    alternate = tmp_path / ".venv313"
    alternate.mkdir()
    (alternate / "pyvenv.cfg").write_text("version = 3.13\n", encoding="utf-8")
    (alternate / "external.py").write_text("not application code", encoding="utf-8")
    assert _sources(tmp_path) == [app]


def test_batch_compile_still_rejects_bad_source(tmp_path):
    py311 = _py311()
    if py311 is None:
        pytest.skip("no python3.11 on PATH")
    good, bad = tmp_path / "good.py", tmp_path / "bad.py"
    good.write_text("value = 1\n", encoding="utf-8")
    bad.write_text("def broken(:\n", encoding="utf-8")
    failures = _compile_sources(py311, [good, bad])
    assert len(failures) == 1 and str(bad) in failures[0]
