"""
backend/routes/solstice_price_paths.py — read-only coverage/status/reads.

Mount: `app.include_router(router)` (prefix `/api/solstice/price-paths`).
No writes, no activation, no broker access. When the scheduled producer was
never registered (default), `/status` reports `worker_state: absent` — the
honest OFF receipt, not an error.

Contract `coverage-read.v1` on the admission/coverage answers below.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/solstice/price-paths", tags=["solstice"])

COVERAGE_VERSION = "coverage-read.v1"
ET = ZoneInfo("America/New_York")


def _store_conn() -> Any | None:
    try:
        from services.duckdb_engine import db as eng

        return eng.conn if hasattr(eng, "conn") else None
    except Exception:
        return None


def _ny_date(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(ET).strftime("%Y-%m-%d")


@router.get("/status")
async def price_paths_status() -> dict[str, Any]:
    """Producer health + store durability, reported separately (R15-2)."""
    from services import solstice_price_producer as prod
    from services.heatmap_history import recorder_status

    try:
        from services.duckdb_engine import db as eng

        conn = eng.conn if hasattr(eng, "conn") else None
    except Exception:
        conn = None
    store = recorder_status(conn) if conn is not None else {"durable": False, "mode": "no_connection"}
    # Module singleton state when a worker was registered; otherwise OFF receipt.
    capture_registered = False
    worker_state = "absent"
    worker_enabled = False
    cadence_s: float | None = None
    symbols: list[str] = []
    try:
        import services.solstice_price_producer as _p

        capture = getattr(_p, "_CAPTURE", None)
        thread = getattr(_p, "_THREAD", None)
        alive = bool(thread is not None and thread.is_alive())
        capture_registered = capture is not None
        worker_state = "active" if alive else ("wired_off" if capture_registered else "absent")
        worker_enabled = bool(_p.worker_enabled())
        cadence_s = float((capture or {}).get("cadence_s", prod.WORKER_INTERVAL_S)) if capture else None
        symbols = list((capture or {}).get("symbols", [])) if capture else []
    except Exception:  # silent by design: status must answer OFF even if introspection fails
        pass
    return {
        "version": "price-path-producer.v1",
        "durable": bool(store.get("durable")),
        "store": store,
        "capture_registered": capture_registered,
        "worker_state": worker_state,
        "worker_enabled": worker_enabled,
        "cadence_s": cadence_s,
        "symbols": symbols,
        "policy": prod.POLICY_NOTE,
        "resolution": prod.RESOLUTION_CLAIM,
        "resolution_limit": prod.RESOLUTION_LIMIT,
    }


@router.get("/points")
async def price_path_points(
    ticker: str = Query(..., description="Underlying symbol, e.g. SPY"),
    since: float = Query(0.0, description="Epoch seconds lower bound (vendor time)"),
    limit: int = Query(1000, ge=1, le=100000),
) -> dict[str, Any]:
    """Read-only ordered (t, price) observations for a ticker (no writes)."""
    from services.heatmap_history import price_paths_since

    try:
        from services.duckdb_engine import db as eng

        conn = eng.conn if hasattr(eng, "conn") else None
    except Exception:
        conn = None
    if conn is None:
        return {"ticker": ticker.upper(), "points": [], "error": "recorder_unavailable"}
    pts = price_paths_since(conn, ticker, since_ts=float(since), limit=int(limit))
    return {"ticker": ticker.upper(), "since": float(since), "limit": int(limit),
            "n_points": len(pts), "points": [[t, p] for t, p in pts]}


@router.get("/sessions")
async def price_path_sessions(
    ticker: str = Query(..., description="Underlying symbol, e.g. SPY"),
) -> dict[str, Any]:
    """Stored-session enumeration: NY session days with snapshot counts (R17-1).

    Read-only index over recorded snapshots. Coverage gaps within a day are
    answered by the existing manifest route, not invented here; a ticker with
    no stored sessions returns an empty day list (empty state, never an error).
    """
    conn = _store_conn()
    if conn is None:
        return {"ticker": ticker.upper(), "days": [], "n_days": 0,
                "error": "recorder_unavailable"}
    try:
        from services.connection_guard import query_rows

        rows = query_rows(
            conn,
            "SELECT asof_ts, snapshot_id FROM heatmap_snapshots_v2 WHERE ticker = ? "
            "ORDER BY asof_ts ASC",
            [ticker.upper()],
        )
    except Exception:
        return {"ticker": ticker.upper(), "days": [], "n_days": 0,
                "error": "recorder_unavailable"}
    days: dict[str, dict[str, Any]] = {}
    for asof_ts, snapshot_id in rows or []:
        day = _ny_date(asof_ts)
        if day is None:
            continue
        entry = days.setdefault(day, {"date": day, "n_snapshots": 0,
                                      "first_asof": asof_ts, "last_asof": asof_ts,
                                      "latest_snapshot_id": snapshot_id})
        entry["n_snapshots"] += 1
        entry["last_asof"] = asof_ts
        entry["latest_snapshot_id"] = snapshot_id
    ordered = [days[d] for d in sorted(days)]
    return {"version": COVERAGE_VERSION, "ticker": ticker.upper(),
            "days": ordered, "n_days": len(ordered)}


@router.get("/expiries")
async def price_path_expiries(
    ticker: str = Query(..., description="Underlying symbol, e.g. SPY"),
    min_dte: int = Query(14, ge=0, le=730, description="Admitted window lower bound (DTE)"),
    max_dte: int = Query(60, ge=0, le=730, description="Admitted window upper bound (DTE)"),
    expirations: int = Query(6, ge=1, le=12, description="Listed expirations requested"),
) -> dict[str, Any]:
    """Admitted expiry-range query over listed expirations (R17-2).

    Reports each listed expiry with its DTE and an ADMITTED/excluded verdict
    for the requested window — it never narrows the stored chain. The existing
    `dte≤30` display filter in `market_data.py` is untouched. Expired dates
    refuse as EXPIRED; in-range dates admit; anything else names its reason.
    0DTE is kept by the chain with exact T but falls BELOW_WINDOW here.
    """
    from services.public_api_adapter import fetch_chain_from_public_api

    result = await fetch_chain_from_public_api(ticker.upper(), max_expiries=expirations)
    if result is None:
        raise HTTPException(status_code=502, detail={
            "error": "chain_unavailable",
            "message": f"Listed expirations unavailable for {ticker.upper()} — "
                       "key may be missing or the API call failed.",
        })
    today = datetime.now(ET).date()
    rows: list[dict[str, Any]] = []
    for exp in result.get("expiries", []) or []:
        try:
            exp_date = datetime.strptime(str(exp)[:10], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            rows.append({"expiry": str(exp), "dte": None,
                         "admitted": False, "reason": "UNPARSEABLE_EXPIRY"})
            continue
        dte = (exp_date - today).days
        if dte < 0:
            verdict, reason = False, "EXPIRED"
        elif dte < min_dte:
            verdict, reason = False, "BELOW_WINDOW"
        elif dte > max_dte:
            verdict, reason = False, "ABOVE_WINDOW"
        else:
            verdict, reason = True, "ADMITTED"
        rows.append({"expiry": exp_date.isoformat(), "dte": dte,
                     "admitted": verdict, "reason": reason})
    return {"version": COVERAGE_VERSION, "ticker": ticker.upper(),
            "window": {"min_dte": min_dte, "max_dte": max_dte},
            "expiries": rows, "n_admitted": sum(1 for r in rows if r["admitted"]),
            "spot": result.get("spot"), "fetched_at": result.get("fetched_at"),
            "stale": bool(result.get("stale", False)), "data_source": "public_api"}


@router.get("/comparable")
async def price_path_comparable(
    baseline_id: str = Query(..., description="Owning baseline snapshot ID"),
    snapshot_id: str = Query(..., description="Current snapshot ID"),
) -> dict[str, Any]:
    """Comparable-pair admission verdict over two stored snapshots (R17-3).

    Runs the exact `check_window_comparability` gate on the replayed records'
    declared identity (ticker/data_source/scope_key/formula_version/session_date
    + asof ordering). A missing record refuses as NO_BASELINE; undeclared
    fields refuse as IDENTITY_UNDECLARED — never a silent comparable number.
    """
    from services.heatmap_history import replay_snapshot
    from services.solstice_window import check_window_comparability

    conn = _store_conn()
    if conn is None:
        return {"admitted": False, "reason": "recorder_unavailable",
                "version": COVERAGE_VERSION}

    def _meta(rep: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(rep, dict):
            return None
        snap = rep.get("snapshot") or {}
        return {
            "ticker": snap.get("ticker"),
            "data_source": snap.get("data_source"),
            "scope_key": snap.get("query_key"),
            "formula_version": snap.get("formula_version"),
            "session_date": _ny_date(snap.get("asof_ts")),
            "asof": snap.get("asof_ts"),
        }

    base = _meta(replay_snapshot(conn, baseline_id))
    cur = _meta(replay_snapshot(conn, snapshot_id))
    if base is None:
        return {"admitted": False, "reason": "NO_BASELINE",
                "detail": f"baseline {baseline_id} not stored",
                "version": COVERAGE_VERSION}
    if cur is None:
        return {"admitted": False, "reason": "NO_BASELINE",
                "detail": f"snapshot {snapshot_id} not stored",
                "version": COVERAGE_VERSION}
    reason, detail = check_window_comparability(base, cur)
    if reason is None:
        return {"admitted": True, "reason": None, "detail": None,
                "baseline_id": baseline_id, "snapshot_id": snapshot_id,
                "version": COVERAGE_VERSION}
    return {"admitted": False, "reason": reason, "detail": detail,
            "baseline_id": baseline_id, "snapshot_id": snapshot_id,
            "version": COVERAGE_VERSION}
