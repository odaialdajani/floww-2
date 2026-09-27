"""
backend/routes/solstice.py — versioned Solstice analytics endpoints.

Reads are typed data with NO broker write credentials. The single write
endpoint (POST /outcomes/close) appends idempotent research outcome rows
only — never orders, positions, or snapshots. AI reads the same snapshot
store as the UI. Execution stays disarmed elsewhere.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

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
                   mode: str = Query("day", pattern="^(day|swing|scalp)$"),
                   dte: int | None = Query(None, ge=0, le=30),
                   scalp: bool = Query(False),
                   snapshot_id: str | None = Query(None)) -> dict[str, Any]:
    """Read-only evidence packet for the selected wall (T21, P02/R4-03).

    Two coherent modes, never a rebuilt different scope:
    - snapshot_id given: packet is built from the RECORDED snapshot
      (available-at replay — the exact scope the UI displayed).
    - otherwise: rebuilds with the FULL scope (dte/scalp included) and the
      identical query-key format as /snapshot, so IDs stay comparable.
    """
    from server import build_heatmap
    from services.heatmap_snapshot import build_snapshot_v2
    from services.solstice_evidence import build_evidence_packet
    t = ticker.strip().upper()
    if snapshot_id:
        from services.duckdb_engine import db as eng
        from services.heatmap_history import replay_snapshot
        conn = eng.conn if hasattr(eng, "conn") else None
        if conn is None:
            return {"packet": None, "error": "recorder_unavailable"}
        rep = replay_snapshot(conn, snapshot_id)
        if rep is None:
            return {"packet": None, "error": "snapshot_not_found"}
        snap_row = rep.get("snapshot", {}) or {}
        # R5-E: the requested ticker must match the stored snapshot ticker —
        # never explain SPY evidence under a QQQ heading.
        if snap_row.get("ticker") and snap_row.get("ticker") != t:
            return {"packet": None, "error": "ticker_mismatch"}
        # R5-E: the requested wall must be a member of the stored walls.
        stored_walls = rep.get("walls", []) or []
        if wall_id and not any(isinstance(w, dict) and w.get("wall_id") == wall_id
                               for w in stored_walls):
            return {"packet": None, "error": "unknown_wall"}
        import json as _json

        def _parse(v: Any) -> Any:
            try:
                return _json.loads(v) if isinstance(v, str) else v
            except (TypeError, ValueError):
                return None

        snap = build_snapshot_v2({
            "ticker": snap_row.get("ticker", t),
            "spot": snap_row.get("spot"),
            "expiries_used": _parse(snap_row.get("expiries")) or [],
            "data_source": snap_row.get("data_source") or "recorded",
            "exposure_basis": snap_row.get("exposure_basis") or "OI",
            "formula_version": snap_row.get("formula_version") or "gex.v2",
            "asof": snap_row.get("asof_ts"),
            "source_received_at": snap_row.get("received_at"),
            "strikes": rep.get("strikes", []),
            "grid": ((rep.get("grids") or {}).get("grid")) or {},
            "metrics": {"walls": stored_walls, "grids": rep.get("grids") or {}},
            "quality": rep.get("quality") or {"state": "unknown", "reasonCodes": [],
                                              "setupEligible": False,
                                              "executionEligible": False,
                                              "tradeSideCapability": "none"},
            "scenarios": rep.get("scenarios", []),
            "interactions": rep.get("interactions", []),
        }, query_key=f"replay|{snapshot_id}")
        pkt = build_evidence_packet(snap, wall_id=wall_id, mode="replay")
        pkt["replay_of"] = snapshot_id  # requested record; packet binds replayed content
        return {"packet": pkt, "replay": True, "replay_note": rep.get("replay_note")}
    payload = await build_heatmap(t, expiries, True, mode, dte, scalp)
    snap = build_snapshot_v2(payload, query_key=f"{t}|{expiries}|{mode}|{dte}|{scalp}")
    return {"packet": build_evidence_packet(snap, wall_id=wall_id)}


@router.get("/walls/{ticker}")
async def walls(ticker: str, expiries: int = Query(4, ge=1, le=12),
                mode: str = Query("day", pattern="^(day|swing|scalp)$"),
                dte: int | None = Query(None, ge=0, le=30),
                scalp: bool = Query(False)) -> dict[str, Any]:
    """Wall registry for the current snapshot (T05, P08/R4-03).

    Same full scope (expiries/mode/dte/scalp) and identical query-key format
    as /snapshot; scoped wall IDs (symbol+formula) so grid/inspector/AI/
    recorder resolve one wall.
    """
    from server import build_heatmap
    from services.wall_structure import discover_walls, nearest_by_side, nearest_walls
    t = ticker.strip().upper()
    payload = await build_heatmap(t, expiries, True, mode, dte, scalp)
    spot = payload.get("spot", 0)
    scope = {"symbol": t, "formula": "gex.v2"}
    w = discover_walls(payload.get("strikes", []), spot, scope=scope)
    return {"walls": w, "nearest": nearest_walls(w, spot),
            "nearest_by_side": nearest_by_side(w, spot),
            "spot": spot, "asof": payload.get("asof"),
            "scope": scope, "queryKey": f"{t}|{expiries}|{mode}|{dte}|{scalp}"}


@router.get("/regime/{ticker}")
async def regime(ticker: str, expiries: int = Query(4, ge=1, le=12)) -> dict[str, Any]:
    """Corrected gamma regime + roots (T15). Sign never permits direction."""
    from server import fetch_spot_and_chains_merged
    from services.solstice_regime import regime_at_spot
    raw = await fetch_spot_and_chains_merged(ticker.strip().upper(), expiries)
    return regime_at_spot(float(raw.get("spot", 0)), raw.get("contracts", []), ticker)


@router.get("/patterns/{ticker}")
async def patterns(ticker: str, expiries: int = Query(4, ge=1, le=12),
                   mode: str = Query("day", pattern="^(day|swing|scalp)$"),
                   dte: int | None = Query(None, ge=0, le=30),
                   scalp: bool = Query(False)) -> dict[str, Any]:
    """Numeric pattern records (T16, P08/R4-03: same scope + queryKey)."""
    from server import build_heatmap
    from services.solstice_patterns import detect_patterns_v1
    from services.wall_structure import discover_walls
    t = ticker.strip().upper()
    payload = await build_heatmap(t, expiries, True, mode, dte, scalp)
    spot = payload.get("spot", 0)
    scope = {"symbol": t, "formula": "gex.v2"}
    w = discover_walls(payload.get("strikes", []), spot, scope=scope)
    return {"patterns": detect_patterns_v1(payload.get("strikes", []), spot, w),
            "asof": payload.get("asof"),
            "scope": scope, "queryKey": f"{t}|{expiries}|{mode}|{dte}|{scalp}"}


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
    """Read-only 0DTE scout with rejection reasons (T10, R5-D strict context)."""
    from datetime import UTC, datetime

    from server import fetch_spot_and_chains_merged
    from services.contract_scout import scout_candidates
    raw = await fetch_spot_and_chains_merged(ticker.strip().upper(), expiries)
    _now = datetime.now(UTC)
    return scout_candidates(raw.get("contracts", []), side, float(raw.get("spot", 0) or 0),
                            now_s=_now.timestamp(), session_date=_now.date().isoformat())


@router.get("/capability")
async def capability() -> dict[str, Any]:
    """27-operation registry + measured manifest (T18/T26, R5-F unified).

    Registry (documented), in-memory measured manifest, and persisted
    capability observations are returned together so documented support can
    be reconciled against observed behavior in one place.
    """
    from services.capability_manifest import get_manifest
    from services.public_capability import registry
    observed: list[dict[str, Any]] = []
    try:
        from services.duckdb_engine import db as eng
        conn = eng.conn if hasattr(eng, "conn") else None
        if conn is not None:
            from services.connection_guard import query_rows
            rows = query_rows(conn,
                "SELECT at_ts, ticker, operation, requested, returned, usable, truncated "
                "FROM capability_observations_v1 ORDER BY at_ts DESC LIMIT 50")
            for r in rows or []:
                observed.append({"at": r[0], "ticker": r[1], "operation": r[2],
                                 "requested": r[3], "returned": r[4],
                                 "usable": r[5], "truncated": bool(r[6])})
    except Exception as e:
        log.debug("capability observations unavailable: %s", e)
    from services.public_capability import symbol_matrix
    return {"registry": registry(), "measured": get_manifest(),
            "observed": observed, "n_observed": len(observed),
            "symbols": symbol_matrix(observed)}


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
async def manifest(ticker: str, day: str = Query(""),
                   cadence_s: float = Query(300.0, gt=0)) -> dict[str, Any]:
    """Session completeness manifest for ticker/day (T09/T23 guided replay).

    R5-F: the expected capture cadence is explicit so gap detection runs;
    without it every manifest would report snapshots without gaps.
    """
    from datetime import UTC, datetime

    from services.duckdb_engine import db as eng
    from services.heatmap_history import session_manifest
    conn = eng.conn if hasattr(eng, "conn") else None
    day = day or datetime.now(UTC).date().isoformat()
    if conn is None:
        return {"ticker": ticker.upper(), "day": day, "error": "recorder_unavailable"}
    return session_manifest(conn, ticker, day, expected_cadence_s=cadence_s)


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


@router.get("/recorder_health")
async def recorder_health() -> dict[str, Any]:
    """Truthful recorder health (R5-F): durable mode, tables, latest write.

    Memory fallback keeps analytics running but never claims durable capture.
    Commissioning remains a separate final authorization.
    """
    import os as _os
    from datetime import UTC, datetime

    from services.duckdb_engine import db as eng
    from services.heatmap_history import recorder_status

    conn = eng.conn if hasattr(eng, "conn") else None
    path = _os.environ.get("DUCKDB_PATH", ":memory:")
    status = recorder_status(conn, path)
    latest: dict[str, Any] = {}
    try:
        if conn is not None:
            from services.connection_guard import query_rows
            rows = query_rows(conn,
                "SELECT snapshot_id, ticker, asof_ts FROM heatmap_snapshots_v2 "
                "ORDER BY asof_ts DESC LIMIT 1")
            if rows:
                latest = {"snapshot_id": rows[0][0], "ticker": rows[0][1],
                          "asof": rows[0][2]}
    except Exception as e:
        log.debug("recorder health latest failed: %s", e)
    status["latest_snapshot"] = latest
    status["checked_at"] = datetime.now(UTC).isoformat()
    return status


class _OutcomesCloseBody(BaseModel):
    paths: dict[str, list] = {}


@router.post("/outcomes/close")
async def outcomes_close(body: _OutcomesCloseBody) -> dict[str, Any]:
    """Run the deterministic outcome job over open decisions (R6-5/B11).

    Research-write endpoint: appends idempotent outcome rows only — never
    orders, positions, or snapshots. The caller supplies price paths per
    open decision id (the scheduled price-path recorder is a commissioning
    item; see COMMISSIONING_PACKAGE.md). Decisions without a complete
    episode stay pending (NEED_EPISODE) and are never labeled.
    """
    from services.duckdb_engine import db as eng
    from services.solstice_labels import close_episodes

    conn = eng.conn if hasattr(eng, "conn") else None
    if conn is None:
        return {"closed": [], "skipped_idempotent": [], "skipped_pending": [],
                "pending_reasons": {}, "results": {},
                "error": "recorder_unavailable"}
    paths: dict[str, list] = {}
    for did, pts in (body.paths or {}).items():
        clean: list = []
        for pt in pts or []:
            try:
                t = float(pt[0])
                p = None if pt[1] is None else float(pt[1])
                if p is not None and not (p == p and abs(p) != float("inf")):
                    p = None  # non-finite censors via data_gap, never a price
                clean.append((t, p))
            except (TypeError, ValueError, IndexError):
                clean.append((0.0, None))  # corrupt point censors, never labels
        paths[did] = clean

    out = close_episodes(conn, paths)

    # R8-05: after closure, attach outcome labels to the decision features
    # so the review journal shows the final outcome alongside the frozen
    # episode layout. Terminal outcomes are idempotent; censored/indeterminate
    # are overwritten on re-processing.
    if out.get("closed"):
        try:
            from services.heatmap_history import attach_outcomes_to_decisions
            attach_outcomes_to_decisions(conn, out["results"])
        except Exception as _ae:
            log.debug("attach outcomes to decisions: %s", _ae)

    out["recorder"] = "ok"
    return out
