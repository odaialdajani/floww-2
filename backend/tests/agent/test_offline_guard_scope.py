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


def test_only_registered_fixture_listener_is_allowed_and_permission_expires(tmp_path):
    marker = tmp_path / "scope_checked"
    probe = tmp_path / "test_owned_probe.py"
    probe.write_text(
        "import httpx, pytest, threading\n"
        "from pathlib import Path\n"
        "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
        "from tests.offline_network import permit_owned_loopback\n"
        "class Handler(BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        self.send_response(200); self.end_headers(); self.wfile.write(b'ok')\n"
        "    def log_message(self, *args): pass\n"
        "def test_scope():\n"
        "    servers=[HTTPServer(('127.0.0.1',0), Handler) for _ in range(2)]\n"
        "    threads=[threading.Thread(target=s.serve_forever, daemon=True) for s in servers]\n"
        "    for t in threads: t.start()\n"
        "    urls=[f'http://127.0.0.1:{s.server_port}' for s in servers]\n"
        "    try:\n"
        "        with permit_owned_loopback(urls[0]):\n"
        "            assert httpx.get(urls[0], trust_env=False).text == 'ok'\n"
        "            with pytest.raises(AssertionError): httpx.get(urls[1], trust_env=False)\n"
        "        with pytest.raises(AssertionError): httpx.get(urls[0], trust_env=False)\n"
        f"        Path({str(marker)!r}).write_text('registered-only; expired')\n"
        "    finally:\n"
        "        for s in servers: s.shutdown(); s.server_close()\n"
        "        for t in threads: t.join()\n",
        encoding="utf-8",
    )
    backend = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(probe), "--noconftest", "-p", "tests.offline_network", "-q"],
        cwd=backend, capture_output=True, text=True, timeout=30,
        env={**os.environ, "PYTHONPATH": str(backend)},
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert marker.read_text() == "registered-only; expired", result.stdout + result.stderr
    assert result.returncode == 1
    assert "Provider mock was missed; external requests were blocked" in result.stdout
