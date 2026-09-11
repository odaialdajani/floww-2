"""P1 regression: AST silent-except gate behavior on fixture trees.

Runs qc/audit/check_silent_except.py in a temp dir with known positive
and negative cases; asserts exit codes. Never plants failures in
production code.
"""

import subprocess
import sys
from pathlib import Path

GATE = Path(__file__).resolve().parents[2] / "qc" / "audit" / "check_silent_except.py"
PY = sys.executable


def run_gate(root: Path, *targets: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PY, str(GATE), "--root", str(root), *targets],
        capture_output=True,
        text=True,
    )


def write(root: Path, name: str, content: str) -> None:
    (root / name).write_text(content)


def test_unjustified_typed_handler_fails():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "a.py", "try:\n    x = 1\nexcept ValueError:\n    pass\n")
        proc = run_gate(root, ".")
        assert proc.returncode == 1, proc.stdout + proc.stderr


def test_justified_marker_passes():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root,
            "a.py",
            "try:\n    x = 1\nexcept ValueError:\n    pass  # silent by design: probe, caller retries\n",
        )
        proc = run_gate(root, ".")
        assert proc.returncode == 0, proc.stdout + proc.stderr


def test_alias_multiline_nested_fail():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root,
            "a.py",
            "def f():\n    try:\n        x = 1\n"
            "    except (ValueError, KeyError) as e:\n"
            "        # a plain comment, no marker\n"
            "        pass\n",
        )
        write(
            root,
            "b.py",
            "class C:\n    def m(self):\n        try:\n            x = 1\n"
            "        except Exception: pass\n",
        )
        proc = run_gate(root, ".")
        assert proc.returncode == 1, proc.stdout + proc.stderr
        assert "a.py" in proc.stdout and "b.py" in proc.stdout


def test_strings_and_comments_are_not_code():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(
            root,
            "a.py",
            'S = "except Exception: pass"\n# except Exception\n#     pass\n'
            "try:\n    x = 1\nexcept ValueError:\n    raise\n",
        )
        proc = run_gate(root, ".")
        assert proc.returncode == 0, proc.stdout + proc.stderr


def test_syntax_error_is_malformed_not_green():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "a.py", "def f(:\n    pass\n")
        proc = run_gate(root, ".")
        assert proc.returncode == 2, proc.stdout + proc.stderr


def test_baseline_ratchet_freeze_then_new_fails():
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        write(root, "a.py", "try:\n    x = 1\nexcept ValueError:\n    pass\n")
        base = root / "baseline.txt"
        freeze = subprocess.run(
            [PY, str(GATE), "--root", str(root), "--freeze-baseline", str(base), "."],
            capture_output=True,
            text=True,
        )
        assert freeze.returncode == 0, freeze.stdout + freeze.stderr
        ok = subprocess.run(
            [PY, str(GATE), "--root", str(root), "--baseline", str(base), "."],
            capture_output=True,
            text=True,
        )
        assert ok.returncode == 0, ok.stdout + ok.stderr
        write(root, "b.py", "try:\n    y = 2\nexcept KeyError:\n    pass\n")
        new = subprocess.run(
            [PY, str(GATE), "--root", str(root), "--baseline", str(base), "."],
            capture_output=True,
            text=True,
        )
        assert new.returncode == 1, new.stdout + new.stderr
        assert "b.py" in new.stdout
