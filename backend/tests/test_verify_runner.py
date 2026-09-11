"""Exercise the real verification script against a fully fake toolchain.

No project tests, provider reads or real tool installations run here.
Missing tools must produce an incomplete result, never an all-green claim.
"""
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

VERIFY = Path(__file__).resolve().parents[2] / "qc" / "verify.sh"


def make_exe(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\n" + body + "\n", newline="\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def fake_root(tmp: Path, *, ruff_exit=0, pytest_exit=0, with_mypy=True) -> dict:
    root = tmp / "fakerepo"
    venv = root / "backend" / ".venv" / "bin"
    venv.mkdir(parents=True)
    (root / "backend" / "tests").mkdir()
    (root / "frontend" / "node_modules").mkdir(parents=True)
    (root / ".pre-commit-config.yaml").write_text("repos: []\n")
    sbin = tmp / "stubbin"
    sbin.mkdir()
    make_exe(sbin / "git", 'if [[ "$*" == *rev-parse* ]]; then echo "$FAKE_ROOT"; else exit 0; fi')
    for name in ("pre-commit", "npm", "npx"):
        make_exe(sbin / name, "exit 0")
    make_exe(venv / "python", '''
if [[ "$1" == "--version" ]]; then echo "Fixture Python"; exit 0; fi
if [[ "$1" == "-c" ]]; then
    if [[ "$2" == "import mypy" && "$FAKE_MYPY" == "0" ]]; then exit 1; fi
    exit 0
fi
if [[ "$1" == "-m" && "$2" == "ruff" ]]; then exit "$FAKE_RUFF_EXIT"; fi
if [[ "$1" == "-m" && "$2" == "pytest" ]]; then exit "$FAKE_PYTEST_EXIT"; fi
exit 0
''')
    env = dict(os.environ)
    env["PATH"] = str(sbin) + os.pathsep + env["PATH"]
    env["FAKE_ROOT"] = root.as_posix()
    env["FLOWW_TEST_STUB_BIN"] = str(sbin)
    env.update(FAKE_RUFF_EXIT=str(ruff_exit), FAKE_PYTEST_EXIT=str(pytest_exit), FAKE_MYPY=str(int(with_mypy)))
    return env


def run_verify(env: dict) -> subprocess.CompletedProcess:
    shell = shutil.which("bash")
    if os.name == "nt":
        shell = str(Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Git" / "bin" / "bash.exe")
        assert Path(shell).is_file(), "Git Bash is required for shell-script tests"
        env = dict(env)
        # Preserve the stub commands first; add native Bash utilities after them.
        first, rest = env["PATH"].split(os.pathsep, 1)
        env["PATH"] = os.pathsep.join([first, str(Path(shell).parent.parent / "usr" / "bin"), rest])
    # Set PATH inside Bash after its Windows startup conversion. Otherwise a
    # real Git executable can precede the fake one and select the real repo.
    setup = 'export PATH="$FLOWW_TEST_STUB_BIN:/usr/bin:/bin"; '
    if os.name == "nt":
        setup = 'stub=$(cygpath -u "$FLOWW_TEST_STUB_BIN"); export PATH="$stub:/usr/bin:/bin"; '
    setup += (
        'for tool in git pre-commit npm npx; do '
        '[ "$(command -v "$tool")" = "${PATH%%:*}/$tool" ] || exit 90; done; '
        '[ "$(git rev-parse --show-toplevel)" = "$FAKE_ROOT" ] || exit 91; '
        'exec bash "$1"'
    )
    return subprocess.run([shell, "--noprofile", "--norc", "-c", setup, "fixture", VERIFY.as_posix()],
                          capture_output=True, text=True, env=env,
                          cwd=env["FAKE_ROOT"], timeout=120)


def test_all_pass_prints_all_green():
    with tempfile.TemporaryDirectory() as tmp:
        proc = run_verify(fake_root(Path(tmp)))
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "=== ALL GREEN:" in proc.stdout


def test_failing_required_tool_cannot_print_all_green():
    with tempfile.TemporaryDirectory() as tmp:
        proc = run_verify(fake_root(Path(tmp), ruff_exit=1))
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "=== ALL GREEN:" not in proc.stdout
        assert "FAIL: ruff lint" in proc.stdout
        assert "=== VERIFY FAILED:" in proc.stdout


def test_failing_pytest_blocks():
    with tempfile.TemporaryDirectory() as tmp:
        proc = run_verify(fake_root(Path(tmp), pytest_exit=1))
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "=== ALL GREEN:" not in proc.stdout
        assert "FAIL: backend pytest" in proc.stdout


def test_missing_advisory_tool_is_named_skip():
    with tempfile.TemporaryDirectory() as tmp:
        proc = run_verify(fake_root(Path(tmp), with_mypy=False))
        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert "SKIP: mypy" in proc.stdout
        assert "=== VERIFY INCOMPLETE:" in proc.stdout
        assert "=== ALL GREEN:" not in proc.stdout
