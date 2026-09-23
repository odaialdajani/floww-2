"""
backend/routes/solstice.py — versioned Solstice analytics endpoints (read-only).

All tools return typed data with NO broker write credentials. AI reads the
same snapshot store as the UI. Execution stays disarmed elsewhere.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/solstice", tags=["solstice"])


@router.get("/snapshot/{ticker}")
async def snapshot(ticker: str, expiries: int = Query(4, ge=1, le=12),
                   mode: str = Query("day", pattern="^(day|swing|scalp)$"),
                   dte: int | None = Query(None, ge=0, le=30),
                   scalp: bool = Query(False)) -> dict[str, Any]:
    """Canonical immutable snapshot (HeatmapSnapshotV2) + legacy payload."""
    from server import build_heatmap
    from services.heatmap_snapshot import build_snapshot_v2, to_legacy_payload
    payload = await build_heatmap(ticker.strip().upper(), expiries, True, mode, dte, scalp)
    snap = build_snapshot_v2(payload, query_key=f"{ticker}|{expiries}|{mode}|{dte}|{scalp}")
    return {"snapshot": snap, "data": to_legacy_payload(snap)}


@router.get("/evidence/{ticker}")
async def evidence(ticker: str, wall_id: str | None = None,
                   expiries: int = Query(4, ge=1, le=12),
                   mode: str = Query("day", pattern="^(day|swing|scalp)$")) -> dict[str, Any]:
    """Read-only evidence packet for the selected wall (T21)."""
    from server import build_heatmap
    from services.heatmap_snapshot import build_snapshot_v2
    from services.solstice_evidence import build_evidence_packet
    payload = await build_heatmap(ticker.strip().upper(), expiries, True, mode, None, False)
    snap = build_snapshot_v2(payload)
    return {"packet": build_evidence_packet(snap, wall_id=wall_id)}


@router.get("/walls/{ticker}")
async def walls(ticker: str, expiries: int = Query(4, ge=1, le=12)) -> dict[str, Any]:
    """Wall registry for the current snapshot (T05)."""
    from server import build_heatmap
    from services.wall_structure import discover_walls, nearest_walls
    payload = await build_heatmap(ticker.strip().upper(), expiries)
    spot = payload.get("spot", 0)
    w = discover_walls(payload.get("strikes", []), spot)
    return {"walls": w, "nearest": nearest_walls(w, spot),
            "spot": spot, "asof": payload.get("asof")}


@router.get("/regime/{ticker}")
async def regime(ticker: str, expiries: int = Query(4, ge=1, le=12)) -> dict[str, Any]:
    """Corrected gamma regime + roots (T15). Sign never permits direction."""
    from server import fetch_spot_and_chains_merged
    from services.solstice_regime import regime_at_spot
    raw = await fetch_spot_and_chains_merged(ticker.strip().upper(), expiries)
    return regime_at_spot(float(raw.get("spot", 0)), raw.get("contracts", []), ticker)


@router.get("/patterns/{ticker}")
async def patterns(ticker: str, expiries: int = Query(4, ge=1, le=12)) -> dict[str, Any]:
    """Numeric pattern records (T16)."""
    from server import build_heatmap
    from services.solstice_patterns import detect_patterns_v1
    from services.wall_structure import discover_walls
    payload = await build_heatmap(ticker.strip().upper(), expiries)
    spot = payload.get("spot", 0)
    w = discover_walls(payload.get("strikes", []), spot)
    return {"patterns": detect_patterns_v1(payload.get("strikes", []), spot, w),
            "asof": payload.get("asof")}


@router.get("/vanna/{ticker}")
async def vanna(ticker: str, expiries: int = Query(4, ge=1, le=12)) -> dict[str, Any]:
    """Vanna/Vomma views + expiry-removal scenario (T17)."""
    from server import fetch_spot_and_chains_merged
    from services.solstice_vanna import expiry_removal_view, vanna_by_expiry
    raw = await fetch_spot_and_chains_merged(ticker.strip().upper(), expiries)
    spot = float(raw.get("spot", 0))
    return {"vanna": vanna_by_expiry(raw.get("contracts", []), spot, ticker),
            "removal": expiry_removal_view(raw.get("contracts", []), spot,
                                           raw.get("expiries", [])[:1], ticker)}


@router.get("/scout/{ticker}")
async def scout(ticker: str, side: str = Query("CALLS"),
                expiries: int = Query(4, ge=1, le=12)) -> dict[str, Any]:
    """Read-only 0DTE scout with rejection reasons (T10)."""
    from server import fetch_spot_and_chains_merged
    from services.contract_scout import scout_candidates
    raw = await fetch_spot_and_chains_merged(ticker.strip().upper(), expiries)
    return scout_candidates(raw.get("contracts", []), side, float(raw.get("spot", 0) or 0))


@router.get("/capability")
async def capability() -> dict[str, Any]:
    """27-operation registry + measured manifest (T18/T26)."""
    from services.capability_manifest import get_manifest
    from services.public_capability import registry
    return {"registry": registry(), "measured": get_manifest()}


@router.get("/replay/{snapshot_id}")
async def replay(snapshot_id: str) -> dict[str, Any]:
    """Available-at replay of a recorded snapshot (T09)."""
    from services.duckdb_engine import db as eng
    from services.heatmap_history import replay_snapshot
    conn = eng.conn if hasattr(eng, "conn") else None
    if conn is None:
        return {"snapshot_id": snapshot_id, "error": "recorder_unavailable"}
    return replay_snapshot(conn, snapshot_id) or {"snapshot_id": snapshot_id, "error": "not_found"}


@router.get("/manifest/{ticker}")
async def manifest(ticker: str, day: str = Query("")) -> dict[str, Any]:
    """Session completeness manifest for ticker/day (T09/T23 guided replay)."""
    from datetime import UTC, datetime

    from services.duckdb_engine import db as eng
    from services.heatmap_history import session_manifest
    conn = eng.conn if hasattr(eng, "conn") else None
    day = day or datetime.now(UTC).date().isoformat()
    if conn is None:
        return {"ticker": ticker.upper(), "day": day, "error": "recorder_unavailable"}
    return session_manifest(conn, ticker, day)


@router.get("/attribute/{ticker}")
async def attribute(ticker: str, day: str = Query("")) -> dict[str, Any]:
    """Coarse wall-level change between the last two snapshots (T09).

    Descriptive comparison only — not the spot/IV/time/OI counterfactual.
    """
    from datetime import UTC, datetime

    from services.duckdb_engine import db as eng
    from services.heatmap_history import compare_snapshots
    conn = eng.conn if hasattr(eng, "conn") else None
    day = day or datetime.now(UTC).date().isoformat()
    if conn is None:
        return {"ticker": ticker.upper(), "day": day, "status": "error",
                "error": "recorder_unavailable"}
    return compare_snapshots(conn, ticker, day)
