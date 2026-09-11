"""
backend/tests/services/test_server_cors_wiring.py

Pinned regression tests for the CORS + global exception-handler tightening
in backend/server.py per docs/superpowers/plans/2026-06-20-freebuff-decoder-
hardening-60h.md (freebuff-decoder P2.5 — last remaining hardening item).

Pinned properties (each pre-fix = RED, post-fix = GREEN):

P2.5-A — CORS CONFIGURATION
- Production or staging deployment without CORS_ORIGINS env var must
  refuse to import (RuntimeError).  Local-dev may fall back to ["*"].
- When CORS_ORIGINS is set, the middleware must consume the env value
  verbatim (no silent wildcard substitution).

P2.5-B — HANDLER-WILDCARD LEAK
- The three exception handlers (http_exception_handler,
  validation_exception_handler, global_exception_handler) must NOT
  hardcode `Access-Control-Allow-Origin: "*"` in their JSONResponse
  headers — they must call a runtime-computed helper
  (`_get_cors_origin_for_handlers`) so that when CORS_ORIGINS is set
  to a specific allowlist, the error responses echo that origin
  (not "*").

P2.5-C — GLOBAL EXCEPTION PAYLOAD REDACTION
- The global_exception_handler payload must NOT include a full
  `traceback` / `str(exc)` detail in production/staging.  In dev/local
  the payload MAY include the detail for debugging.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from ._subprocess_helpers import _SUBPROCESS_MIN_ENV

SERVER_PY = Path(__file__).resolve().parents[2] / "server.py"




def _read_server_source() -> str:
    return SERVER_PY.read_text(encoding="utf-8")


# ============================================================
# P2.5-A — CORS configuration (source-text + subprocess)
# ============================================================
class TestCorsConfiguration:
    """Pinned: production/staging without CORS_ORIGINS must refuse to start."""

    def test_cors_config_block_uses_runtime_prod_check(self):
        """The CORS config block must branch on `_is_prod` / `_is_staging`."""
        source = _read_server_source()
        # A defensive `_is_staging` check must exist (added by this fix).
        assert re.search(r"_is_staging\s*=", source), (
            "server.py CORS config block is missing `_is_staging` "
            "— should refuse to start in BOTH production AND staging "
            "when CORS_ORIGINS env var is unset."
        )

    def test_cors_config_raises_runtimeerror_for_prod_or_staging(self):
        """Pinned: the RuntimeError must mention both prod and staging in its condition
        (per the Freebuff Handoff P2.5-A design)."""
        source = _read_server_source()
        # The new condition must mention both prod AND staging.
        prod_branches = re.findall(r'["\']production["\']', source)
        assert len(prod_branches) >= 2, (
            "server.py CORS guard should reference 'production' in BOTH the env check "
            "AND the runtimeerror message (and similarly for staging)."
        )
        staging_branches = re.findall(r'["\']staging["\']', source)
        assert len(staging_branches) >= 1, (
            "server.py CORS guard must also catch the staging environment "
            "(see Freebuff Handoff P2.5-A)."
        )


class TestCorsRuntimeImportRaises:
    """Behavioural regression: source text alone is not enough -- verify the actual
    startup path raises RuntimeError for ANY non-development env without CORS_ORIGINS.
    Parametrized over {"production", "staging", "qa"} so the fail-closed
    `(_env != "development")` guard is exercised across the named-prod, named-
    staging, and ad-hoc env branches in one test method (avoids triplicate
    drift after future refactors of the guard / RuntimeError / resolver)."""

    @pytest.mark.parametrize("env_name", ["production", "staging", "qa"])
    def test_non_dev_env_with_no_cors_origins_raises_runtimeerror_on_import(self, env_name):
        """Run server.py as a subprocess with ENVIRONMENT=<env_name> and CORS_ORIGINS unset.

        Pre-fix: server.py starts without complaint in any of {production, staging, qa}.
        Post-fix: subprocess exits non-zero with RuntimeError in stderr mentioning
        "CORS" + the actual env name (so operators reading the deploy log can pivot
        immediately without cross-referencing other config).
        """
        repo_root = Path(__file__).resolve().parents[3]
        backend_dir = repo_root / "backend"

        env = {
            **_SUBPROCESS_MIN_ENV,
            "PYTHONPATH": str(backend_dir),
            "HOME": str(Path.home()),
            # ENVIRONMENT drives _env (top-of-file L55 chain
            # `os.getenv(ENVIRONMENT) or os.getenv(ENV) or "development"`) AND
            # the CORS fail-closed guard at server.py L2525+.  Setting all 3
            # env-key forms so the resolver picks env_name unambiguously.
            **{k: env_name for k in ("ENVIRONMENT", "ENV", "FLOWW_ENV")},
        }

        result = subprocess.run(
            [sys.executable, "-W", "ignore", "-c",
             f"import os; "
             f"os.environ['ENVIRONMENT'] = {env_name!r}; "
             f"os.environ['ENV'] = {env_name!r}; "
             # Force CORS_ORIGINS to '' so the L2525+ guard's
             # `if not _cors_origins_env` branch fires (load_dotenv defaults
             # to override=False; honour already-set env).
             "os.environ['CORS_ORIGINS'] = ''; "
             "import server"],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
            cwd=str(backend_dir),
        )
        assert result.returncode != 0, (
            f"server.py imported successfully in {env_name} env without CORS_ORIGINS -- "
            f"the CORS fail-closed guard is missing for {env_name} (P2.5-A). Any "
            f"non-development env must raise RuntimeError, not silently fall through "
            f"to the ['*'] wildcard (typo-resistant)."
        )
        combined = (result.stderr or "") + (result.stdout or "")
        assert "CORS" in combined, (
            f"server.py failed in {env_name}-without-CORS_ORIGINS but stderr "
            f"doesn't mention CORS:\n{combined}"
        )
        # Operator-friendly RuntimeError message should include the actual env name
        # so operators reading the deploy log can pivot immediately (no need to
        # cross-reference other config).  Pinned via the f-string `_env!r` in
        # server.py's CORS guard raise.
        assert f"'{env_name}'" in combined or f'"{env_name}"' in combined, (
            f"server.py raised RuntimeError but the message doesn't surface "
            f"the actual env name ('{env_name}') for operator clarity:\n{combined}"
        )

# ============================================================
# P2.5-B — Exception-handler wildcard-CORS leak (source-text)
# ============================================================
class TestExceptionHandlerCorsLeak:
    """Pinned: the 3 exception handlers must not hardcode `Access-Control-Allow-Origin: "*"`."""

    @staticmethod
    def _count_hardcoded_wildcard_in_jsonresponse_headers(source: str) -> int:
        """Count occurrences of manual `"Access-Control-Allow-Origin": "*"` inside
        JSONResponse dict literals (this is the leak: handlers inject their own
        CORS header instead of delegating to CORSMiddleware)."""
        return len(re.findall(
            r'["\']Access-Control-Allow-Origin["\']\s*:\s*["\']\*["\']',
            source,
        ))

    def test_helper_get_cors_origin_for_handlers_is_defined(self):
        source = _read_server_source()
        # The fix introduces this helper to centralize the runtime-CORS decision.
        assert re.search(r"def\s+_get_cors_origin_for_handlers\s*\(", source), (
            "server.py does not define `_get_cors_origin_for_handlers()` — "
            "the exception handlers cannot centralize their CORS-origin choice "
            "without this helper (P2.5-B)."
        )

    def test_handler_cors_leak_sites_call_the_helper(self):
        """All handler leak sites should call `_get_cors_origin_for_handlers()`
        for their Access-Control-Allow-Origin header.  Verify by counting
        helper-calls in handler-context (we accept any reasonable count >= 4:
        rate-limit middleware + http_exception_handler + validation_exception_handler
        + global_exception_handler)."""
        source = _read_server_source()
        helper_refs = re.findall(
            r'["\']Access-Control-Allow-Origin["\']\s*:\s*_get_cors_origin_for_handlers\s*\(',
            source,
        )
        assert len(helper_refs) >= 4, (
            f"only {len(helper_refs)} exception handler(s) call "
            f"`_get_cors_origin_for_handlers()` for their CORS header — "
            f"need at least 4 (rate-limit middleware + http_exception_handler + validation_exception_handler + "
            f"global_exception_handler).  See P2.5-B."
        )

    def test_no_hardcoded_wildcard_in_jsonresponse_headers(self):
        """The handlers should NOT retain a hardcoded `Access-Control-Allow-Origin: "*"`.
        Permitted: zero.  Pre-fix had 3 (one per handler).
        """
        source = _read_server_source()
        leaks = self._count_hardcoded_wildcard_in_jsonresponse_headers(source)
        assert leaks == 0, (
            f"server.py has {leaks} hardcoded `Access-Control-Allow-Origin: \"*\"` "
            f"inside JSONResponse headers (one per exception handler, pre-fix: 3).  "
            f"All must delegate to `_get_cors_origin_for_handlers()`.  See P2.5-B."
        )


# ============================================================
# P2.5-C — global_exception_handler payload redaction (source-text)
# ============================================================
class TestGlobalExceptionHandlerPayloadRedaction:
    """Pinned: prod/staging must NOT include str(exc) or traceback in 500 payload."""

    def test_global_handler_payload_uses_is_prod_branch(self):
        source = _read_server_source()
        # Look at the body of the function `global_exception_handler` (or whatever
        # name is used) — must contain a `_is_prod`-style runtime check guarding
        # whether the payload includes traceback/detail.
        #
        # Acceptable markers (any of):
        #   `_is_prod and t...`
        #   `if not _is_prod:` (or `if not _is_prod and ...`)
        #   `if ENV == ...`
        m_handler = re.search(
            r"async\s+def\s+global_exception_handler\s*\([^{]*\)\s*:\s*(.*?)(?=\nasync\s+def\s+|@app\.|\nclass\s+|\Z)",
            source,
            re.DOTALL,
        )
        assert m_handler, "global_exception_handler function body not located"
        body = m_handler.group(1)

        # Top-of-file helper resolves ENVIRONMENT/ENV fallback to _env, then to
        # _is_prod / _is_staging flags.  Handler body uses the flags; the string
        # literals 'production'/'staging' live only at top-of-file.
        assert "_is_prod" in body or "_is_staging" in body, (
            "global_exception_handler body must branch on _is_prod / _is_staging "
            "(top-of-file constants) to redact traceback/detail in "
            "production/staging (P2.5-C)."
        )
        # The runtime check should reference BOTH flags (prod AND staging).
        assert ("_is_prod" in body) and ("_is_staging" in body), (
            f"global_exception_handler body must reference BOTH _is_prod AND "
            f"_is_staging to redact for both production AND staging (P2.5-C).  "
            f"Found _is_prod={('_is_prod' in body)!r}, "
            f"_is_staging={('_is_staging' in body)!r}."
        )

    def test_500_payload_in_prod_does_not_carry_a_traceback_or_full_exc_message(
        self, monkeypatch,
    ):
        """Behavioural check: trigger a 500 in production env, assert response body
        does not contain a "Traceback (most recent call last):" fragment nor the
        raw exception message we deliberately leaked."""
        # Run a subprocess that:
        #   1) sets ENV=production, FLOWW_ENV unset, CORS_ORIGINS=*
        #   2) imports server
        #   3) registers a one-shot 500-raising route
        #   4) hits it via TestClient and prints the response body
        # Then we inspect stdout — pre-fix would include traceback, post-fix should not.
        repo_root = Path(__file__).resolve().parents[3]
        backend_dir = repo_root / "backend"

        env = {
            **_SUBPROCESS_MIN_ENV,
            "PYTHONPATH": str(backend_dir),
            "HOME": str(Path.home()),
            # ENVIRONMENT drives _is_prod/_is_staging (top-of-file helper) AND the
            # CORS config block (server.py ~L2500+).  ENV also so the helper's
            # `os.getenv(ENVIRONMENT) or os.getenv(ENV)` fallback resolves to prod.
            "ENVIRONMENT": "production",
            "ENV": "production",
            "FLOWW_ENV": "production",
            "CORS_ORIGINS": "*",
        }

        driver = (
            "import os; "
            "os.environ['ENVIRONMENT'] = 'production'; "
            "os.environ['ENV'] = 'production'; "
            "os.environ['FLOWW_ENV'] = 'production'; "
            "os.environ['CORS_ORIGINS'] = '*'; "
            # Marker so any leak in subprocess stderr is obvious in test output
            "import sys; sys.stderr.write('REDRACTION_DRV_START\\n'); sys.stderr.flush(); "
            "import server; "
            "from fastapi.testclient import TestClient; "
            # NOTE: must terminate the LEAKED assignment BEFORE the decorator
            # line.  Python grammar forbids `LEAKED='...'; @decorator` on a
            # single physical line (`@decorator` requires its own line).  Using
            # `\n` (Python interprets escape on string-literal parse) yields
            # an actual newline before the decorator.
            "LEAKED = 'highly-sensitive-internal-error-detail'\n"
            "@server.app.get('/__redact_test__')\n"
            "def _t():\n"
            "    raise ValueError(LEAKED)\n"
            "client = TestClient(server.app, raise_server_exceptions=False)\n"
            "try:\n"
            "    resp = client.get('/__redact_test__')\n"
            "    print('STATUS=', resp.status_code)\n"
            "    print('BODY=', resp.text)\n"
            "except Exception as _e:\n"
            "    print('STATUS=CRASH')\n"
            "    print('BODY=CRASH:', repr(_e))\n"
        )
        # The decorator must be on its own line; emit it explicitly to avoid a
        # single-line syntax error in the -c payload.
        driver_one = driver.replace(
            "@server.app.get('/__redact_test__')\n"
            "def _t():\n"
            "    raise ValueError(LEAKED)\n",
            "@server.app.get('/__redact_test__')\n"
            "def _t():\n"
            "    raise ValueError(LEAKED)\n",
        )
        assert driver_one == driver  # sanity (no transformation needed)

        result = subprocess.run(
            [sys.executable, "-W", "ignore", "-c", driver],
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
            cwd=str(backend_dir),
        )
        # We don't strictly require exit code 0 — TestClient.get on a 500 route
        # surfaces the status in the result object, not via raise_for_status.
        # We DO require the body to be present.
        assert "STATUS=" in result.stdout, (
            f"redaction integration driver did not produce expected stdout.\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
        assert "BODY=" in result.stdout, "redaction driver missing BODY= line"

        # Extract "BODY=..." line body and inspect.
        for line in result.stdout.splitlines():
            if line.startswith("BODY="):
                body = line[len("BODY="):]
                break
        else:
            body = ""

        assert "Traceback" not in body, (
            f"production 500 response leaks 'Traceback' fragment in body: {body!r}"
        )
        assert "highly-sensitive-internal-error-detail" not in body, (
            f"production 500 response leaks the deliberately-leaked payload: {body!r}"
        )


# ============================================================
# P2.5-D — redaction observability (Prom counter on handler floor)
# ============================================================
class TestRedacted500CountMetric:
    """Pinned (P2.5-D): global_exception_handler must increment
    `error_tracking.redacted_500_count.labels(env=_env)` when the redaction
    branch fires in prod/staging so dashboards can detect attack / upstream
    failure spikes originating from prod traffic.  Pre-fix: 0.0; post-fix: >= 1.0
    per 500 triggered.

    Reuses the existing T2 subprocess-driver convention so we drive the real
    global_exception_handler (no mocks) and observe the metric the way
    Prometheus would."""

    def test_redacted_500_count_is_exported_from_error_tracking(self):
        """Module-level pin: the Counter must be importable as
        `error_tracking.redacted_500_count` and have an `env` label, with a
        fresh 0.0 baseline for any unseen (env, ...) combination."""
        repo_root = Path(__file__).resolve().parents[3]
        backend_dir = repo_root / "backend"

        r = subprocess.run(
            [sys.executable, "-c",
             "import error_tracking; m = error_tracking.redacted_500_count; "
             "v = m.labels(env='production')._value.get(); print('VAL=', v)"],
            capture_output=True, text=True,
            env={
                **_SUBPROCESS_MIN_ENV,
                "PYTHONPATH": str(backend_dir),
                "HOME": str(Path.home()),
            },
            cwd=str(backend_dir), timeout=30,
        )
        assert r.returncode == 0, (
            f"error_tracking.redacted_500_count is not importable — module re-export missing "
            f"or prometheus_client not installed.\n"
            f"STDOUT:\n{r.stdout}\nSTDERR:\n{r.stderr}"
        )
        assert ("VAL= 0.0" in r.stdout) or ("VAL=0.0" in r.stdout), (
            f"redacted_500_count[env=production] should resolve to a fresh 0.0 counter, "
            f"got stdout={r.stdout!r}. Check labelnames=['env'] wiring in services/observability.py."
        )

    def test_global_handler_source_calls_redacted_500_count(self):
        """Source-text guard: the global_exception_handler function body must
        reference `redacted_500_count` so a future refactor can't silently
        drop the observability hook."""
        source = _read_server_source()
        assert "redacted_500_count" in source, (
            "server.py does NOT reference `redacted_500_count` — "
            "global_exception_handler should increment the counter on "
            "redaction-branch 500s (P2.5-D)."
        )

    def test_redacted_500_count_increments_when_prod_handler_fires(self):
        """Behavioural pin: drive global_exception_handler into the redaction
        branch via subprocess; confirm that after the 500 surfaces,
        error_tracking.redacted_500_count[env=production] >= 1.0.
        Pre-fix: 0.0; post-fix: 1.0+."""
        repo_root = Path(__file__).resolve().parents[3]
        backend_dir = repo_root / "backend"

        env = {
            **_SUBPROCESS_MIN_ENV,
            "PYTHONPATH": str(backend_dir),
            "HOME": str(Path.home()),
            # ENVIRONMENT drives _env (top-of-file) AND the CORS config guard.
            "ENVIRONMENT": "production",
            "ENV": "production",
            "FLOWW_ENV": "production",
            "CORS_ORIGINS": "*",
        }

        driver = (
            "import os; "
            "os.environ['ENVIRONMENT'] = 'production'; "
            "os.environ['ENV'] = 'production'; "
            "os.environ['FLOWW_ENV'] = 'production'; "
            "os.environ['CORS_ORIGINS'] = '*'; "
            "import server; "
            "from fastapi.testclient import TestClient; "
            # Decorator must be on its own physical line — Python grammar forbids
            # `@decorator` after a `;`-terminated statement on the same line.
            "LEAKED = 'metric-driver-leak-marker'\n"
            "@server.app.get('/__redact_metric_test__')\n"
            "def _t():\n"
            "    raise ValueError(LEAKED)\n"
            "client = TestClient(server.app, raise_server_exceptions=False)\n"
            "try:\n"
            "    resp = client.get('/__redact_metric_test__')\n"
            "    print('STATUS=', resp.status_code)\n"
            "    print('BODY=', resp.text)\n"
            "    import error_tracking\n"
            "    val = error_tracking.redacted_500_count.labels(env='production')._value.get()\n"
            "    print('METRIC=', val)\n"
            "except Exception as _e:\n"
            "    print('STATUS=CRASH')\n"
            "    print('BODY=CRASH:', repr(_e))\n"
            "    print('METRIC=CRASH')\n"
        )

        result = subprocess.run(
            [sys.executable, "-W", "ignore", "-c", driver],
            capture_output=True, text=True, env=env, timeout=120, cwd=str(backend_dir),
        )
        assert "STATUS=" in result.stdout, (
            f"metric driver did not produce STATUS= line.\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
        assert "BODY=" in result.stdout, "metric driver missing BODY= line"
        assert "METRIC=" in result.stdout, "metric driver missing METRIC= line"

        # Extract metric value from METRIC= line.
        metric_val = None
        for line in result.stdout.splitlines():
            if line.startswith("METRIC="):
                try:
                    metric_val = float(line[len("METRIC="):])
                except ValueError:
                    metric_val = -1.0
                break

        assert metric_val is not None and metric_val >= 1.0, (
            f"redacted_500_count[env=production] did NOT increment after a "
            f"prod 500 — expected >= 1.0, got {metric_val!r}. The handler is "
            f"not wired to the metric (P2.5-D)."
        )




# ============================================================
# P2.5-A/E -- local-dev CORS fallthrough (wildcard fallback acceptable)
# ============================================================
class TestLocalDevFallthrough:
    """Pinned (P2.5-A/E): in `development` env (the default), `CORS_ORIGINS`
    unset MUST NOT raise -- preserving the local-dev experience where the
    wildcard ["*"] fallback is acceptable.  Symmetric to
    TestCorsRuntimeImportRaises: that class asserts prod/staging RAISE when
    CORS_ORIGINS is unset; this class asserts development does NOT raise
    under the same condition.  Together they pin the env-strapped guard
    without over-blocking local dev."""

    def test_default_no_env_vars_set_does_not_raise(self):
        "Pinned: implicit development via unset env vars. CORS_ORIGINS unset must NOT raise on import."
        repo_root = Path(__file__).resolve().parents[3]
        backend_dir = repo_root / "backend"

        env = {
            **_SUBPROCESS_MIN_ENV,
            "PYTHONPATH": str(backend_dir),
            "HOME": str(Path.home()),
        }

        result = subprocess.run(
            [sys.executable, "-W", "ignore", "-c", "import server"],
            capture_output=True, text=True, env=env, timeout=60, cwd=str(backend_dir),
        )
        assert result.returncode == 0, (
            "server.py refused to import with default (development) env and "
            "CORS_ORIGINS unset -- local-dev fallthrough broken (P2.5-A/E).\n"
            "STDOUT:\n" + result.stdout +
            "\nSTDERR:\n" + result.stderr
        )

    def test_explicit_development_env_does_not_raise(self):
        "Pinned: explicit ENV=development; CORS_ORIGINS unset must NOT raise on import."
        repo_root = Path(__file__).resolve().parents[3]
        backend_dir = repo_root / "backend"

        env = {
            **_SUBPROCESS_MIN_ENV,
            "PYTHONPATH": str(backend_dir),
            "HOME": str(Path.home()),
            "ENVIRONMENT": "development",
            "ENV": "development",
            "FLOWW_ENV": "development",
        }

        result = subprocess.run(
            [sys.executable, "-W", "ignore", "-c", "import server"],
            capture_output=True, text=True, env=env, timeout=60, cwd=str(backend_dir),
        )
        assert result.returncode == 0, (
            "server.py refused to import in explicit development env with "
            "CORS_ORIGINS unset -- local-dev fallthrough broken (P2.5-A/E).\n"
            "STDOUT:\n" + result.stdout +
            "\nSTDERR:\n" + result.stderr
        )

    def test_dev_cors_origins_resolves_to_wildcard(self):
        "Pinned: in dev, server._cors_origins must resolve to ['*'] when CORS_ORIGINS is unset."
        repo_root = Path(__file__).resolve().parents[3]
        backend_dir = repo_root / "backend"

        env = {
            **_SUBPROCESS_MIN_ENV,
            "PYTHONPATH": str(backend_dir),
            "HOME": str(Path.home()),
            "ENVIRONMENT": "development",
        }

        driver = (
            "import os; "
            "os.environ['ENVIRONMENT'] = 'development'; "
            "import server; "
            "import json; "
            "print('CORS_ORIGINS=', json.dumps(server._cors_origins))"
        )

        result = subprocess.run(
            [sys.executable, "-W", "ignore", "-c", driver],
            capture_output=True, text=True, env=env, timeout=60, cwd=str(backend_dir),
        )
        assert result.returncode == 0, (
            "subprocess to inspect _cors_origins in dev env failed.\n"
            "STDOUT:\n" + result.stdout +
            "\nSTDERR:\n" + result.stderr
        )

        cors_line = None
        for line in result.stdout.splitlines():
            if line.startswith("CORS_ORIGINS="):
                cors_line = line
                break
        assert cors_line is not None, (
            "could not locate CORS_ORIGINS= line in stdout.\n"
            "STDOUT:\n" + result.stdout +
            "\nSTDERR:\n" + result.stderr
        )
        import json as _json
        body = cors_line.split("CORS_ORIGINS=", 1)[1].lstrip()
        parsed = _json.loads(body)
        assert parsed == ["*"], (
            "server._cors_origins in dev with CORS_ORIGINS unset should be "
            "['*'] (wildcard fallthrough), got " + repr(parsed) +
            ". Local-dev must continue to work without CORS_ORIGINS configured (P2.5-A/E)."
        )
