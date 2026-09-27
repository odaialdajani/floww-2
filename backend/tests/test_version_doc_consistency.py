"""Docs must state the versions that actually ship.

CLAUDE.md claimed Python 3.13.15 at `backend/.venv313/Scripts/python.exe`
(a Windows path, on a POSIX repo, in a directory that does not exist) and
told you never to use `backend/.venv` — which is the venv that actually has
pytest and ruff. It also claimed React 18 (the app is React 19) and
`target-version = "py313"` (the real value is `py311`, and it must track
`requires-python`).

The failure mode is worse than a stale number: an agent or new dev following
those instructions runs a binary that isn't there, or skips the only working
interpreter. So these are pinned against the real sources of truth.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
README = REPO_ROOT / "README.md"
DOCKERFILE = REPO_ROOT / "Dockerfile.backend"
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT = REPO_ROOT / "backend" / "pyproject.toml"
PACKAGE_JSON = REPO_ROOT / "frontend" / "package.json"


def _shipped_python() -> str:
    """The Python that actually runs in production, from the Dockerfile."""
    m = re.search(r"^FROM python:(\d+\.\d+)", DOCKERFILE.read_text(), re.M)
    assert m, "could not determine the shipped Python from Dockerfile.backend"
    return m.group(1)


def _ci_python() -> str:
    text = CI_YML.read_text()
    m = re.search(r'python-version:\s*"(\d+\.\d+)"', text)
    assert m, "ci.yml has no python-version pin"
    return m.group(1)


def _react_major() -> str:
    pkg = json.loads(PACKAGE_JSON.read_text())
    m = re.search(r"\d+", pkg["dependencies"]["react"])
    return m.group(0)


def test_shipped_python_is_consistent_across_docker_ci_and_pyproject():
    shipped = _shipped_python()
    assert _ci_python() == shipped, (
        f"Dockerfile.backend ships {shipped} but ci.yml pins {_ci_python()}"
    )
    pyproject = PYPROJECT.read_text()
    # The floor is deliberately <= shipped (it is the minimum supported local
    # dev version, not the deploy version), so assert the relationship rather
    # than an exact string.
    floor = re.search(r'requires-python = ">=(\d+\.\d+)"', pyproject)
    assert floor, "pyproject has no requires-python floor"
    assert tuple(map(int, floor.group(1).split("."))) <= tuple(
        map(int, shipped.split("."))
    ), f"requires-python floor {floor.group(1)} is above the shipped {shipped}"


def test_ruff_target_version_tracks_requires_python():
    """A target above the runtime makes ruff propose unparseable syntax."""
    text = PYPROJECT.read_text()
    # ruff writes target-version as "py311" (no dot), unlike every other
    # version string in the file. Parse it as major+minor digits.
    target = re.search(r'target-version = "py(\d+)"', text)
    assert target, "no ruff target-version set"
    digits = target.group(1)
    assert len(digits) >= 2, f"unparseable ruff target-version: py{digits}"
    target_v = (int(digits[0]), int(digits[1:]))
    floor = re.search(r'requires-python = ">=(\d+)\.(\d+)"', text)
    assert floor, "no requires-python floor set"
    floor_v = (int(floor.group(1)), int(floor.group(2)))
    assert target_v <= floor_v, (
        f"ruff target-version py{digits} is above the "
        f"requires-python floor {floor_v[0]}.{floor_v[1]}"
    )


def test_claude_md_does_not_point_at_a_nonexistent_windows_venv():
    """No RUNNABLE command may reference a path that does not exist here.

    Checks command lines only (`$ ...` / backticked invocations), so prose
    explaining that the old path was wrong does not trip the gate.
    """
    text = CLAUDE_MD.read_text()
    commands = [
        ln for ln in text.splitlines()
        if ln.strip().startswith("$") or " -m pytest" in ln or " -m ruff" in ln
    ]
    bad = [ln.strip() for ln in commands if "Scripts/python.exe" in ln or ".venv313" in ln]
    assert not bad, f"runnable commands reference a nonexistent Windows venv: {bad}"

    # And it must not forbid the venv that actually has the toolchain.
    assert not re.search(r"never `?backend/\.venv`?", text), (
        "CLAUDE.md forbids backend/.venv, which is the working interpreter"
    )


def test_claude_md_states_the_shipped_python_and_react_major():
    text = CLAUDE_MD.read_text()
    shipped = _shipped_python()
    assert f"Python {shipped}" in text, f"CLAUDE.md never states Python {shipped}"
    react = _react_major()
    assert f"React {react}" in text, f"CLAUDE.md never states React {react}"
    # No other React major may be asserted as current.
    stale = {m for m in re.findall(r"React (\d+)", text)} - {react}
    assert not stale, f"CLAUDE.md still claims React {sorted(stale)}; the app is {react}"


def test_readme_states_the_shipped_python():
    text = README.read_text()
    shipped = _shipped_python()
    assert f"Python {shipped}" in text, f"README does not state the shipped {shipped}"
