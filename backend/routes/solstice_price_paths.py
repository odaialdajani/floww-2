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

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

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


def _prefix_day(value: Any) -> str | None:
    """Stored timestamp-prefix day — the owning manifest's attribution.

    ``session_manifest``/``compare_snapshots`` match snapshots with
    ``LIKE day%`` on the raw stored string, so the session index must use the
    same key to stay coherent with them.
    """
    if not isinstance(value, str) or len(value.strip()) < 10:
        return None
    candidate = value.strip()[:10]
    try:
        datetime.strptime(candidate, "%Y-%m-%d")
    except ValueError:
        return None
    return candidate


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
    """Stored-session enumeration: session days with snapshot counts (R17-1).

    Day attribution is the stored ``asof_ts`` timestamp prefix — the SAME
    attribution the owning ``session_manifest``/``compare_snapshots`` routes
    match with ``LIKE day%`` — so this index, the manifest and the gaps can
    never disagree about which day owns a snapshot. Each day also reports its
    ET-normalized ``ny_date`` (null when the day's snapshots do not normalize
    uniformly) and an ``overnight`` flag for exactly the case the two
    attributions differ (offset/naive stamps crossing ET midnight); the prefix
    stays canonical and the divergence is disclosed, never silently mixed.
    Read-only. Coverage gaps within a day are answered by the existing
    manifest route, not invented here; a ticker with no stored sessions
    returns an empty day list (empty state, never an error).
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
        day = _prefix_day(asof_ts)
        if day is None:
            continue
        ny = _ny_date(asof_ts)
        if day not in days:
            days[day] = {"date": day, "ny_date": ny,
                         "overnight": ny is not None and ny != day,
                         "n_snapshots": 0,
                         "first_asof": asof_ts, "last_asof": asof_ts,
                         "latest_snapshot_id": snapshot_id}
        entry = days[day]
        entry["n_snapshots"] += 1
        entry["last_asof"] = asof_ts
        entry["latest_snapshot_id"] = snapshot_id
        if ny is None:
            # ET-unparseable stamp alongside parseable ones is itself a
            # divergence: disclose it rather than silently keeping the prior day.
            if entry["ny_date"] is not None:
                entry["ny_date"] = None
                entry["overnight"] = True
        elif entry["ny_date"] is None:
            # Previously unparseable-or-mixed day meets a parseable stamp:
            # non-uniform by construction — disclose, never silently adopt.
            entry["overnight"] = True
        elif ny != entry["ny_date"]:
            # Non-uniform ET attribution inside one prefix day — disclose the
            # offset instead of silently picking a single normalized day.
            entry["ny_date"] = None
            entry["overnight"] = True
        elif ny != day:
            entry["overnight"] = True
    ordered = [days[d] for d in sorted(days)]
    return {"version": COVERAGE_VERSION, "ticker": ticker.upper(),
            "days": ordered, "n_days": len(ordered)}


@router.get("/expiries")
async def price_path_expiries(
    ticker: str = Query(..., description="Underlying symbol, e.g. SPY"),
    min_dte: int = Query(14, ge=0, le=730, description="Admitted window lower bound (DTE)"),
    max_dte: int = Query(60, ge=0, le=730, description="Admitted window upper bound (DTE)"),
    expirations: int = Query(12, ge=1, le=16, description="Listed expirations requested"),
) -> dict[str, Any]:
    """Admitted expiry-range query over listed expirations (R17-2).

    Reports each listed expiry with its DTE and an ADMITTED/excluded verdict
    for the requested lower/upper window — it never narrows the stored chain.
    Reversed bounds (``min_dte > max_dte``) refuse as 422 REVERSED_WINDOW
    before any fetch. The owning display envelope (the ``dte le=30`` filter
    ``market_data.py`` enforces) is projected per row as ``display_envelope`` —
    a DIFFERENT constraint from the admitted policy window, disclosed so the
    two never silently mix. ``coverage`` answers the listing honestly: when
    the upper window edge was not observed in the requested listings, in-range
    expiries may exist beyond the cap and the coverage says so instead of a
    silent firstN verdict. ``range_map`` projects the admitted window from the
    observed listings (sorted admitted expiries/DTEs + completeness flag).
    Expired dates refuse as EXPIRED; in-range dates
    admit; anything else names its reason. 0DTE is kept by the chain with
    exact T but falls BELOW_WINDOW here (the display envelope keeps it).
    """
    from services.public_api_adapter import fetch_chain_from_public_api

    if min_dte > max_dte:
        # Structured JSONResponse, not HTTPException: the app's global handler
        # stringifies dict details, which would bury the refusal code in a
        # repr string. A refused window must stay machine-readable.
        return JSONResponse(status_code=422, content={
            "error": "REVERSED_WINDOW",
            "message": f"min_dte {min_dte} is above max_dte {max_dte} — "
                       "no expiry can satisfy a reversed window.",
            "version": COVERAGE_VERSION,
        })
    result = await fetch_chain_from_public_api(ticker.upper(), max_expiries=expirations)
    if result is None:
        # Structured JSONResponse (same reason as the reversed refusal): the
        # global handler stringifies dict details; the 502 body stays
        # machine-readable with the refusal code at the top level.
        return JSONResponse(status_code=502, content={
            "error": "chain_unavailable",
            "message": f"Listed expirations unavailable for {ticker.upper()} — "
                       "key may be missing or the API call failed.",
            "version": COVERAGE_VERSION,
        })
    today = datetime.now(ET).date()
    rows: list[dict[str, Any]] = []
    for exp in result.get("expiries", []) or []:
        try:
            exp_date = datetime.strptime(str(exp)[:10], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            rows.append({"expiry": str(exp), "dte": None, "admitted": False,
                         "reason": "UNPARSEABLE_EXPIRY", "display_envelope": False})
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
                     "admitted": verdict, "reason": reason,
                     "display_envelope": 0 <= dte <= 30})
    admitted = sorted(
        (r for r in rows if r["admitted"] and r["dte"] is not None),
        key=lambda r: r["dte"])
    lower_observed = any(
        r["dte"] is not None and r["dte"] < min_dte for r in rows)
    upper_observed = any(
        r["dte"] is not None and r["dte"] > max_dte for r in rows)
    capped = len(rows) >= expirations
    complete = (not capped) or (lower_observed and upper_observed)
    return {"version": COVERAGE_VERSION, "ticker": ticker.upper(),
            "window": {"min_dte": min_dte, "max_dte": max_dte},
            "expiries": rows, "n_admitted": len(admitted),
            "coverage": {
                "requested_expiries": expirations,
                "n_listed": len(rows),
                "n_display_envelope": sum(1 for r in rows if r["display_envelope"]),
                "listing_capped": capped,
                "lower_edge_observed": lower_observed,
                "upper_edge_observed": upper_observed,
            },
            "range_map": {
                "version": COVERAGE_VERSION,
                "window": {"min_dte": min_dte, "max_dte": max_dte},
                "admitted_expiries": [r["expiry"] for r in admitted],
                "admitted_dtes": [r["dte"] for r in admitted],
                "min_admitted_dte": admitted[0]["dte"] if admitted else None,
                "max_admitted_dte": admitted[-1]["dte"] if admitted else None,
                "complete": complete,
                "reason": None if complete else "LISTING_CAPPED_WINDOW_MAY_EXTEND",
            },
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


# ── R18-C9: read-only owning range-record index/replay ──────────────
#
# Range-analytics.v1 records (rga1-*) live in their OWN namespace
# (range_analytics_envelopes_v1). These routes only READ that namespace —
# identity-bound filters, bounded pagination, typed refusals. They never
# write, never fetch a current chain for historical playback, and the legacy
# snapshot replay namespace above is untouched.

@router.get("/range-records")
async def range_record_index(
    ticker: str | None = Query(None, description="Owning symbol filter"),
    min_dte: int | None = Query(None, ge=0, le=365),
    max_dte: int | None = Query(None, ge=0, le=365),
    as_of: str | None = Query(None, description="Owning NY date YYYY-MM-DD"),
    status: str | None = Query(None, pattern="^(ok|partial)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Record index with per-row integrity verdicts (range-records.v1)."""
    from services.heatmap_history import list_range_envelopes

    conn = _store_conn()
    if conn is None:
        return {"version": "range-records.v1", "status": "refused",
                "reason": "recorder_unavailable", "rows": [], "n_returned": 0}
    return list_range_envelopes(conn, ticker=ticker, min_dte=min_dte,
                                max_dte=max_dte, as_of=as_of, status=status,
                                limit=limit, offset=offset)


@router.get("/range-records/{record_id}")
async def range_record_replay(record_id: str) -> Any:
    """Replay one owning rga1 envelope by identity — validated, never refetched.

    Unknown identity → 404; integrity refusals (tamper/schema/header) stay
    machine-readable with 422; a healthy record restores the stored display
    exactly (no recomputation of present-day chains).
    """
    from services.heatmap_history import replay_range_envelope

    conn = _store_conn()
    if conn is None:
        return JSONResponse(status_code=503, content={
            "version": "range-records.v1",
            "status": "refused", "reason": "recorder_unavailable",
        })
    rep = replay_range_envelope(conn, record_id)
    if rep is None:
        return JSONResponse(status_code=404, content={
            "version": "range-records.v1", "status": "refused",
            "reason": "NO_RECORD", "record_id": record_id})
    if rep.get("error"):
        code = 503 if rep["error"] == "STORE_READ_FAILED" else 422
        return JSONResponse(status_code=code, content={
            "version": "range-records.v1", "status": "refused",
            "reason": rep["error"], "record_id": rep.get("record_id"),
            "detail": rep.get("detail")})
    return {"version": "range-records.v1", "status": "ok", **rep}
