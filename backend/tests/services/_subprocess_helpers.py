"""Shared helpers for subprocess-driven test suites.

Exports `_SUBPROCESS_MIN_ENV`, the standard 3-key baseline Python env every
subprocess test in this tree should spread into its `subprocess.run(env=...)`
call.  Hoisted from `test_server_cors_wiring.py` (commit `b0d1053`) and
shared with `test_server_p1_wiring.py` so a single source of truth governs
every subprocess-driven test in `tests/services/`.

PYTHONPATH and HOME intentionally stay per-call-site-computed because they
depend on per-test `backend_dir` (resolved from `repo_root / "backend"`) and
per-process `Path.home()`.  Spread them in alongside `_SUBPROCESS_MIN_ENV`
at the call site:

    env = {
        **_SUBPROCESS_MIN_ENV,
        "PYTHONPATH": str(backend_dir),
        "HOME": str(Path.home()),
        ...test-specific keys (ENVIRONMENT/ENV/FLOWW_ENV/CORS_ORIGINS/...)...
    }

Adding a new test file?  Just `from _subprocess_helpers import _SUBPROCESS_MIN_ENV`
(relative-style sibling import works because `tests/services/__init__.py`
makes this directory a package) and spread per-call-site keys as above.

SINGLE SOURCE OF TRUTH for the subprocess-test baseline env — new static keys go HERE, not at per-test sites.
"""

import os

# Baseline Python env for subprocess-driven test suites.
# (PATH / API_SECRET_KEY / FLOWW_ENABLE_LIVE_SCHWAB are truly-static and
# can be baked at import time; PYTHONPATH and HOME are per-call-site-computed.)
# FLOWW_ENABLE_LIVE_SCHWAB=0 guards live-Schwab — harmless when spread
# into dev/paper-only tests (Schwab branch never fires without creds).
_SUBPROCESS_MIN_ENV: dict[str, str] = {
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/usr/local/bin:/opt/homebrew/bin",
    "API_SECRET_KEY": "test-secret-key",
    "FLOWW_ENABLE_LIVE_SCHWAB": "0",
}
if os.name == "nt":
    # Winsock provider loading requires OS directory metadata even with an
    # absolute interpreter path. Keep credentials and app settings excluded.
    _SUBPROCESS_MIN_ENV.update({key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ})
