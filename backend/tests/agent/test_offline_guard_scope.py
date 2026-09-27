"""The offline guard must precede module-scoped application startup."""

import os
import subprocess
import sys
from pathlib import Path


def test_module_startup_cannot_escape_network_guard(tmp_path):
    probe = tmp_path / "test_startup_probe.py"
    probe.write_text(
        "import httpx, pytest\n"
        "@pytest.fixture(scope='module')\n"
        "def startup():\n"
        "    try:\n"
        "        httpx.get('https://guard-probe.invalid', timeout=0.01)\n"
        "    except Exception:\n"
        "        pass\n"
        "def test_probe(startup):\n"
        "    assert True\n",
        encoding="utf-8",
    )
    backend = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(probe), "--noconftest", "-p", "tests.offline_network", "-q"],
        cwd=backend, capture_output=True, text=True, timeout=30,
        env={**os.environ, "PYTHONPATH": str(backend)},
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Provider mock was missed; external requests were blocked" in result.stdout
    assert "guard-probe.invalid" in result.stdout and "test_probe" in result.stdout
