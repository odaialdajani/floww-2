"""Exercise the real verification script against a fully fake toolchain.

No project tests, provider reads or real tool installations run here.
Missing tools must produce an incomplete result, never an all-green claim.
"""
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

VERIFY = Path(__file__).resolve().parents[2] / "qc" / "verify.sh"


def make_exe(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\n" + body + "\n", newline="\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def fake_root(
    tmp: Path, *, ruff_exit=0, pytest_exit=0, with_mypy=True, pip_audit_exit=0
) -> dict:
    root = tmp / "fakerepo"
    venv = root / "backend" / ".venv" / "bin"
    venv.mkdir(parents=True)
    (root / "backend" / "tests").mkdir(parents=True)
    (root / "backend" / "requirements.txt").write_text("# stub\n")
    (root / "frontend").mkdir(parents=True)
    # The fake root must satisfy EVERY probe verify.sh makes, or the script
    # correctly reports "VERIFY INCOMPLETE" (exit 2) and the all-green tests
    # can never pass. That means:
    #   - a pre-commit config, so the hook is a PASS rather than a SKIP
    #   - frontend/node_modules, or the build is a SKIP
    #   - backend/requirements.txt, which pip-audit is invoked against
    # The importability probes are answered by the `python -c` shim below.
    (root / ".pre-commit-config.yaml").write_text("repos: []\n")
    (root / "frontend" / "node_modules").mkdir(parents=True, exist_ok=True)
    sbin = tmp / "stubbin"
    sbin.mkdir()
    make_exe(sbin / "git", 'if [[ "$*" == *rev-parse* ]]; then echo "$FAKE_ROOT"; else exit 0; fi')
    for name in ("pre-commit", "npm", "npx"):
        make_exe(sbin / name, "exit 0")
    # qc/verify.sh resolves the backend INTERPRETER first and aborts
    # ("FATAL: no backend virtualenv interpreter found") before it ever looks
    # at a tool. The fake root must therefore provide a `python` executable in
    # the same bin/ directory, or the script correctly refuses to check
    # anything and every test below fails for the wrong reason.
    #
    # The shim must also DISPATCH, not merely exist — and it has to satisfy
    # two DIFFERENT probes verify.sh uses:
    #   1. has_module()  ->  "$BACKEND_PY" -c "import ruff"   (importability)
    #   2. the check body ->  "$BACKEND_PY" -m ruff check .    (execution)
    # A shim that merely execs a real interpreter would run the developer's
    # actual ruff/pytest, so ruff_exit/pytest_exit/with_mypy would stop
    # controlling anything and the suite would report on the real repo.
    # A shim that only handles "-m" fails probe (1) and every tool SKIPs.
    # Handle both: answer the import probe from a sibling stub, execute the
    # -m form, and fall through to the real interpreter for anything else
    # (e.g. the `python -m pip install` hint text).
    make_exe(
        venv / "python",
        'd="$(dirname "$0")"\n'
        'if [ "$1" = "-c" ]; then\n'
        '  case "$2" in\n'
        '    "import "*) for pair in ruff:ruff pytest:pytest mypy:mypy bandit:bandit '
        'pip_audit:pip-audit; do\n'
        '                   want="${pair%%:*}"; stub="${pair##*:}"\n'
        '                   if [ "$2" = "import $want" ] && [ -x "$d/$stub" ]; then exit 0; fi\n'
        '                 done ;;\n'
        '    *socket*27017*)\n'
        '      # verify.sh probes for a real mongod on 127.0.0.1:27017 before it\n'
        '      # will run the full backend suite. Without mongod (e.g. a laptop,\n'
        '      # or this test) that probe fails and the script SKIPs the suite, so\n'
        '      # it can never reach ALL GREEN. CI runs a mongo:7 service container\n'
        '      # and does reach it. Answering the probe from the stub keeps these\n'
        '      # tests hermetic: they assert the script\'s verdict logic, not\n'
        '      # whether the developer happens to have a database running.\n'
        '      exit 0 ;;\n'
        '  esac\n'
        '  exit 1\n'
        'fi\n'
        'if [ "$1" = "-m" ] && [ -x "$d/$2" ]; then exec "$d/$2"; fi\n'
        # `-m pip_audit` names a MODULE (underscore) but the console stub on
        # disk is `pip-audit` (hyphen), so the plain -x test above misses it and
        # the call falls through to the real interpreter, which has no
        # pip_audit installed -> the check reports an ADVISORY instead of a
        # PASS. Map the one known module/stub name mismatch.
        'if [ "$1" = "-m" ] && [ "$2" = "pip_audit" ] && [ -x "$d/pip-audit" ]; then\n'
        '  exec "$d/pip-audit"\n'
        'fi\n'
        f'exec "{sys.executable}" "$@"',
    )
    make_exe(venv / "ruff", f"exit {ruff_exit}")
    make_exe(venv / "pytest", f"exit {pytest_exit}")
    make_exe(venv / "bandit", "exit 0")
    make_exe(venv / "pip-audit", f"exit {pip_audit_exit}")
    if with_mypy:
        make_exe(venv / "mypy", "exit 0")
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
        # With every stub clean, no check SKIPs and none ADVISORies, so the
        # strict verdict is ALL GREEN. The forbidden verdicts are the ones
        # that would mean the script lied.
        assert "ALL GREEN" in proc.stdout
        assert "NOT GREEN" not in proc.stdout
        assert "VERIFY INCOMPLETE" not in proc.stdout


def test_advisory_still_exits_zero_but_is_not_all_green():
    """An advisory is non-gating, but it must NOT be dressed up as ALL GREEN.

    verify.sh has two exit-0 verdicts: ALL GREEN (zero advisories) and
    VERIFY GREEN (>=1 advisory). A check that ran and reported findings is
    still a passing run, but calling it "all green" would overstate it.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        proc = run_verify(fake_root(Path(tmp), pip_audit_exit=1))
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "VERIFY GREEN" in proc.stdout
        assert "=== ALL GREEN: all" not in proc.stdout


def test_failing_required_tool_cannot_print_all_green():
    with tempfile.TemporaryDirectory() as tmp:
        proc = run_verify(fake_root(Path(tmp), ruff_exit=1))
        assert proc.returncode != 0, proc.stdout + proc.stderr
        assert "ALL GREEN" not in proc.stdout
        # A failed gating check must be reported as a FAIL and must block the
        # all-green verdict, whatever the exact wording is.
        assert "FAIL: ruff lint" in proc.stdout
        assert "NOT GREEN" in proc.stdout


def test_failing_pytest_blocks():
    with tempfile.TemporaryDirectory() as tmp:
        proc = run_verify(fake_root(Path(tmp), pytest_exit=1))
        assert proc.returncode != 0, proc.stdout + proc.stderr
        assert "ALL GREEN" not in proc.stdout


def test_missing_advisory_tool_is_named_skip():
    """An absent tool is SKIPPED BY NAME and downgrades the verdict to exit 2.

    This is the honesty contract that matters most: a check that did not run
    must never be allowed to look like a pass. `with_mypy=False` removes the
    mypy stub, so verify.sh SKIPs mypy, reports 1 of 8 checks as unverified,
    and exits 2 ("unknown", not "good"). The N/A verdict is different — it is
    reserved for checks that do not exist in this repo by design.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        proc = run_verify(fake_root(Path(tmp), with_mypy=False))
        assert proc.returncode == 2, proc.stdout + proc.stderr
        assert "SKIP: mypy" in proc.stdout
        assert "SKIPPED checks" in proc.stdout  # listed as NOT verified
        assert "VERIFY INCOMPLETE" in proc.stdout
        assert "ALL GREEN" not in proc.stdout
