"""Gate test: silent-except scanner must fire on violations, pass on clean tree."""
import subprocess
import sys
from pathlib import Path

GATE = Path(__file__).resolve().parents[2] / "scripts" / "silent_except_gate.py"


def _run_gate(root: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE), "--root", str(root), *extra],
        capture_output=True,
        text=True,
    )


def test_gate_fires_on_silent_except(tmp_path: Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text("try:\n    x = 1\nexcept Exception:\n    pass\n")
    proc = _run_gate(tmp_path)
    assert proc.returncode == 1, f"expected gate to fire, got: {proc.stdout}{proc.stderr}"
    assert "bad.py" in proc.stdout + proc.stderr


def test_gate_passes_on_clean_tree(tmp_path: Path) -> None:
    good = tmp_path / "good.py"
    good.write_text(
        "try:\n    x = 1\nexcept ValueError as e:\n    raise RuntimeError('ctx') from e\n"
    )
    proc = _run_gate(tmp_path)
    assert proc.returncode == 0, f"expected clean pass, got: {proc.stdout}{proc.stderr}"
