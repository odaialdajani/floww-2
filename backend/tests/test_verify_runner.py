"""P3 regression: qc/verify.sh truthful exits via stub toolchains.

Builds a fake repo root (stub git -> rev-parse prints the fake root;
stub backend/.venv/bin tools; stub PATH npm/npx/pre-commit) and asserts:
all-pass prints ALL GREEN with exit 0; a failing required tool exits
nonzero WITHOUT the all-green line; a missing advisory tool is named as
a skip. Never runs the real suite.
"""

import os
import stat
import subprocess
from pathlib import Path

VERIFY = Path(__file__).resolve().parents[2] / "qc" / "verify.sh"


def make_exe(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\n" + body + "\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def fake_root(tmp: Path, *, ruff_exit=0, pytest_exit=0, with_mypy=True) -> dict:
    root = tmp / "fakerepo"
    venv = root / "backend" / ".venv" / "bin"
    venv.mkdir(parents=True)
    (root / "backend" / "tests").mkdir(parents=True)
    (root / "frontend").mkdir(parents=True)
    sbin = tmp / "stubbin"
    sbin.mkdir()
    make_exe(sbin / "git", 'if [[ "$*" == *rev-parse* ]]; then echo "$FAKE_ROOT"; else exit 0; fi')
    for name in ("pre-commit", "npm", "npx"):
        make_exe(sbin / name, "exit 0")
    make_exe(venv / "ruff", f"exit {ruff_exit}")
    make_exe(venv / "pytest", f"exit {pytest_exit}")
    for name in ("bandit", "pip-audit"):
        make_exe(venv / name, "exit 0")
    if with_mypy:
        make_exe(venv / "mypy", "exit 0")
    env = dict(os.environ)
    env["PATH"] = str(sbin) + os.pathsep + env["PATH"]
    env["FAKE_ROOT"] = str(root)
    return env


def run_verify(env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(VERIFY)], capture_output=True, text=True, env=env, timeout=120
    )


def test_all_pass_prints_all_green():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        proc = run_verify(fake_root(Path(tmp)))
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "=== ALL GREEN ===" in proc.stdout


def test_failing_required_tool_cannot_print_all_green():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        proc = run_verify(fake_root(Path(tmp), ruff_exit=1))
        assert proc.returncode != 0, proc.stdout + proc.stderr
        assert "=== ALL GREEN ===" not in proc.stdout
        assert "REQUIRED FAIL" in proc.stdout
        assert "=== QC FAILED (required) ===" in proc.stdout


def test_failing_pytest_blocks():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        proc = run_verify(fake_root(Path(tmp), pytest_exit=1))
        assert proc.returncode != 0, proc.stdout + proc.stderr
        assert "=== ALL GREEN ===" not in proc.stdout


def test_missing_advisory_tool_is_named_skip():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        proc = run_verify(fake_root(Path(tmp), with_mypy=False))
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "ADVISORY SKIP" in proc.stdout and "mypy" in proc.stdout.lower()
        assert "=== ALL GREEN ===" in proc.stdout
