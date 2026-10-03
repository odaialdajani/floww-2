"""
backend/routes/solstice_price_paths.py — read-only price-path status/reads.

Mount: `app.include_router(router)` (prefix `/api/solstice/price-paths`).
No writes, no activation, no broker access. When the scheduled producer was
never registered (default), `/status` reports `worker_state: absent` — the
honest OFF receipt, not an error.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/solstice/price-paths", tags=["solstice"])


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
