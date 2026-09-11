"""
backend/routes/health.py

Health check endpoint that verifies all backend dependencies are operational.

PUBLIC-API-ONLY POLICY (2026-09-03): the live market-data check is Public.com
(PUBLIC_API_KEY). Alpha Vantage is retired — its check entry is kept as a
deprecated disabled stub so old monitors/dashboards don't KeyError.
"""
from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

import httpx  # noqa: F401 — re-exported for tests that patch routes.health.httpx
from fastapi import APIRouter

from services.alpha_vantage_client import circuit as av_circuit
from services.duckdb_engine import db as duckdb_engine
from services.websocket_streamer import manager as ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()

_STARTED_AT = datetime.now(UTC).isoformat()


def _git_sha() -> str:
    """Running commit, best-effort (source checkout may be absent in prod)."""
    try:
        import subprocess
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        sha = (out.stdout or "").strip()
        return sha or "unknown"
    except Exception:
        return "unknown"


@router.get("/api/version")
async def version():
    """Build-vs-backend freshness stamp for the UI stale banner."""
    return {"sha": _git_sha(), "started_at": _STARTED_AT}


def _institutional_section(feed_status: str) -> dict:
    """C11 payload: feed x budget x sweep-age x alerts x calibration.

    Every source is fail-open: unwired or erroring sources report None +
    note (unknown), never fabricated values.
    """
    try:
        from services.public_budget import budget

        budget_snapshot: dict = {"status": "ok", **budget.status()}
    except Exception as e:
        budget_snapshot = {"status": "unknown", "note": f"budget unreadable: {e}"}

    try:
        from services.sweep_watch import sweep_age_s

        age = sweep_age_s()
        sweep: dict = {"age_s": age}
        if age is None:
            sweep["note"] = "pending B hook: note_sweep() in sweep loop"
    except Exception as e:
        sweep = {"age_s": None, "note": f"sweep watch unreadable: {e}"}

    try:
        with duckdb_engine._conn_lock:
            row = duckdb_engine._conn.execute(
                "SELECT COUNT(*) FROM flow_alerts_daily"
            ).fetchone()
        alerts: dict = {"stored": int(row[0]) if row else 0}
    except Exception as e:
        alerts = {"stored": None, "note": f"alert store unreadable: {e}"}

    try:
        from routes.flowseeker import get_calibration_status

        status = get_calibration_status() or {}
        stage = status.get("stage")
        calibration = {
            "stage": stage,
            "n": status.get("n"),
            "method": status.get("method_note") or status.get("model_kind"),
            "age_s": status.get("age_s"),
        }
        if stage in (None, 0):
            calibration["note"] = "uncalibrated until stage >= 1 (min-n gates)"
    except Exception as e:
        calibration = {"stage": None, "note": f"calibration unreadable: {e}"}

    return {
        "feed": {"public_api": feed_status},
        "budget": budget_snapshot,
        "sweep": sweep,
        "alerts": alerts,
        "calibration": calibration,
    }


@router.get("/api/health")
async def health_check():
    """Check status of all dependencies.

    Returns:
        {
            "status": "healthy" | "degraded",
            "timestamp": "<ISO8601 UTC>",
            "checks": {
                "duckdb": {"status": "healthy"},
                "public_api": {"status": "healthy"} | {"status": "unhealthy", "error": "..."},
                "alpha_vantage": {"status": "disabled", "deprecated": True, ...},
                "websocket": {"status": "healthy", "active_connections": 0}
            }
        }
    """
    checks: dict = {}

    # DuckDB check
    try:
        # Take the conn lock — touching _conn directly races the ingestion
        # writer thread (duckdb connections are not thread-safe) and can
        # deadlock the event loop.
        with duckdb_engine._conn_lock:
            duckdb_engine._conn.execute("SELECT 1").fetchone()
        checks["duckdb"] = {"status": "healthy"}
    except Exception as e:
        logger.warning(f"Health check: DuckDB unhealthy: {e}")
        checks["duckdb"] = {"status": "unhealthy", "error": str(e)}

    # Public API check (primary market-data source). Key-presence probe only —
    # the broker auths lazily on first real fetch, so a live auth here would
    # add latency/flakiness to every health poll.
    try:
        api_key = os.environ.get("PUBLIC_API_KEY", "")
        if not api_key:
            checks["public_api"] = {
                "status": "unhealthy",
                "error": "PUBLIC_API_KEY not configured",
            }
        else:
            checks["public_api"] = {"status": "healthy", "key_configured": True}
    except Exception as e:
        logger.warning(f"Health check: Public API unhealthy: {e}")
        checks["public_api"] = {"status": "unhealthy", "error": str(e)}

    # Alpha Vantage — RETIRED 2026-09-03. Deprecated stub: always disabled,
    # excluded from the overall verdict (see below).
    checks["alpha_vantage"] = {
        "status": "disabled",
        "deprecated": True,
        "error": "Alpha Vantage retired 2026-09-03 — use /api/public/* (Public.com API)",
    }

    # WebSocket check
    ws_count = len(ws_manager._all)
    checks["websocket"] = {"status": "healthy", "active_connections": ws_count}

    # Alpha Vantage Circuit Breaker check (retired with the provider;
    # kept for dashboard compat, always closed/disabled).
    checks["circuit_breaker"] = {
        "status": "healthy",
        "state": av_circuit.state.value,
        "failure_count": av_circuit.failure_count,
        "success_count": av_circuit.success_count,
        "note": "alpha_vantage retired 2026-09-03 — breaker retained for compat",
    }

    # Overall verdict counts only live checks — deprecated/disabled entries
    # (alpha_vantage) never flip the service to degraded.
    live_checks = {
        name: c for name, c in checks.items() if not c.get("deprecated")
    }
    overall = (
        "healthy"
        if all(c.get("status") == "healthy" for c in live_checks.values())
        else "degraded"
    )

    return {
        "status": overall,
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": checks,
        "institutional": _institutional_section(
            str(checks.get("public_api", {}).get("status"))
        ),
    }


@router.get("/health")
async def health_alias():
    """Lightweight liveness alias at the root level.

    Load balancers / Caddy probes hit /health (no /api prefix). This returns
    a minimal 200 without running dependency checks — deep diagnostics live
    at /api/health. Mounted without prefix via server.py include_router.
    """
    return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}
