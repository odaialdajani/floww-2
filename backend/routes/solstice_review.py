"""
R8-04: review/journal endpoints for saved scenario decisions.

Adds:
- GET /{ticker}/decisions — list saved scenario decisions (review journal)
- POST /{ticker}/decisions/{decision_id}/review — save a review state
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/solstice", tags=["solstice"])

# ---------------------------------------------------------------------------
# Re-export existing router (snapshot, evidence, manifest, attribute,
# outcomes/close, recorder_health) — this file is imported alongside
# the original routes/solstice.py router in server.py.
# ---------------------------------------------------------------------------


class _ReviewBody(BaseModel):
    state: str = Query("pending")  # pending | reviewed | waiting | skipped
    reason: str | None = None
    note: str | None = None


def register_review_routes(router: APIRouter) -> None:
    """Register review/journal routes on the given router.

    Called from server.py after the main solstice router is created.
    """

    @router.get("/{ticker}/decisions")
    async def decisions_list(ticker: str,
                             limit: int = Query(50, ge=1, le=200),
                             state: str | None = Query(None)) -> dict[str, Any]:
        """List saved scenario decisions for a ticker (R8-04 review journal).

        Returns decision rows with frozen features, candidate quotes, and
        any attached outcome labels. Read-only — never mutates storage.
        """
        from services.duckdb_engine import db as eng
        from services.heatmap_history import list_decisions

        conn = eng.conn if hasattr(eng, "conn") else None
        if conn is None:
            return {"ticker": ticker.upper(), "decisions": [],
                    "error": "recorder_unavailable"}

        try:
            rows = list_decisions(conn, ticker, limit=limit, state_filter=state)
            return {"ticker": ticker.upper(), "decisions": rows,
                    "count": len(rows), "checked_at": __import__("datetime").datetime.now(
                        __import__("datetime").timezone.utc).isoformat()}
        except Exception as e:
            log.warning("decisions list failed for %s: %s", ticker, e)
            return {"ticker": ticker.upper(), "decisions": [],
                    "error": str(e)}

    @router.post("/{ticker}/decisions/{decision_id}/review")
    async def save_review(ticker: str, decision_id: str,
                          body: _ReviewBody) -> dict[str, Any]:
        """Save a review state on a decision (R8-04).

        States: pending | reviewed | waiting | skipped.
        Persists through the real route/store; never falls back to
        transient memory and claims durability.
        """
        from fastapi import HTTPException

        from services.duckdb_engine import db as eng
        from services.heatmap_history import save_decision_review

        allowed = ("pending", "reviewed", "waiting", "skipped")
        if body.state not in allowed:
            raise HTTPException(status_code=422, detail={
                "error": "unknown review state",
                "allowed": list(allowed)})
        conn = eng.conn if hasattr(eng, "conn") else None
        if conn is None:
            return {"decision_id": decision_id, "state": body.state,
                    "error": "recorder_unavailable",
                    "durability": "transient_memory_fallback_not_allowed"}

        try:
            saved = save_decision_review(
                conn, decision_id, body.state,
                reason=body.reason, note=body.note, ticker=ticker)
            if not saved:
                raise HTTPException(status_code=503, detail={
                    "error": "Review could not be saved", "durability": "failed"})
            return {"decision_id": decision_id, "state": body.state,
                    "saved_at": saved, "durability": "durable"}
        except HTTPException:
            raise
        except Exception as e:
            log.warning("review save failed for %s/%s: %s",
                        ticker, decision_id, e)
            return {"decision_id": decision_id, "state": body.state,
                    "error": str(e),
                    "durability": "failed"}


    @router.get("/{ticker}/contract")
    async def contract_detail(
        ticker: str,
        osi: str | None = Query(None),
        strike: str | None = Query(None),
        expiry: str | None = Query(None),
        type: str | None = Query(None),
        snapshot_id: str | None = Query(None),
    ) -> dict[str, Any]:
        """Resolve ONE exact contract identity from a recorded snapshot (S5).

        The backend half of the R10-13 migration. It requires an explicit
        identity: OSI, or strike+expiry+type. It never substitutes the wall
        midpoint or the first expiry, and a miss is a miss. Quote age and
        spread are reported per leg with unknown preserved as unknown.

        Read-only. No broker call, no side inference, no aggressor identity.
        """
        from services.contract_identity import (
            REASON_IDENTITY_INCOMPLETE,
            resolve_contract,
            triad_request_scope,
        )
        from services.duckdb_engine import db as eng
        from services.heatmap_history import replay_snapshot

        conn = eng.conn if hasattr(eng, "conn") else None
        scope = triad_request_scope()
        if conn is None:
            return {"ticker": ticker.upper(), "status": "unavailable",
                    "reason": "recorder_unavailable", "scope": scope,
                    "snapshot_id": snapshot_id, "quote": None}
        if not osi and (strike is None or not expiry or not type):
            return {"ticker": ticker.upper(), "status": "unavailable",
                    "reason": REASON_IDENTITY_INCOMPLETE, "scope": scope,
                    "snapshot_id": snapshot_id, "quote": None,
                    "note": "supply osi, or strike+expiry+type; the wall midpoint and "
                            "first expiry are never substituted"}

        sid = snapshot_id
        if not sid:
            try:
                from services.connection_guard import query_rows

                rows = query_rows(
                    conn,
                    "SELECT snapshot_id FROM heatmap_snapshots_v2 WHERE ticker = '"
                    + str(ticker).upper().replace("'", "''")
                    + "' ORDER BY asof_ts DESC LIMIT 1")
                sid = str(rows[0][0]) if rows else None
            except Exception as e:  # non-fatal: no recorded snapshot to resolve against
                log.debug("contract detail: no recorded snapshot for %s (%s)", ticker, e)
                sid = None
        if not sid:
            return {"ticker": ticker.upper(), "status": "unavailable",
                    "reason": "NO_RECORDED_SNAPSHOT", "scope": scope,
                    "snapshot_id": None, "quote": None}
        try:
            replayed = replay_snapshot(conn, sid) or {}
        except Exception as e:
            log.warning("contract detail replay failed for %s/%s: %s", ticker, sid, e)
            return {"ticker": ticker.upper(), "status": "unavailable",
                    "reason": "REPLAY_FAILED", "scope": scope,
                    "snapshot_id": sid, "quote": None}
        snapshot = replayed.get("snapshot") or {}
        if not snapshot:
            return {"ticker": ticker.upper(), "status": "unavailable",
                    "reason": "NO_RECORDED_SNAPSHOT", "snapshot_id": sid,
                    "scope": None, "quote": None}
        if str(snapshot.get("ticker", "")).upper() != ticker.upper():
            return {"ticker": ticker.upper(), "status": "unavailable",
                    "reason": "SNAPSHOT_TICKER_MISMATCH", "snapshot_id": sid,
                    "scope": None, "quote": None}
        try:
            expiries_used = json.loads(snapshot.get("expiries") or "[]")
        except (TypeError, ValueError):
            expiries_used = []
        scope = {**scope, "source": "recorded_snapshot",
                 "expiries_requested": None, "is_true_zero_dte": None,
                 "zero_dte_note": "use the recorded expiry dates and session; not inferred",
                 "expiries_used": expiries_used,
                 "query_key": snapshot.get("query_key"),
                 "provider": snapshot.get("data_source"),
                 "formula_version": snapshot.get("formula_version"),
                 "basis": snapshot.get("exposure_basis"),
                 "observed_at": snapshot.get("asof_ts"),
                 "received_at": snapshot.get("received_at")}
        resolved = resolve_contract(
            replayed.get("contracts") or [],
            {"osi": osi, "strike": strike, "expiry": expiry, "type": type},
        )
        return {"ticker": ticker.upper(), "snapshot_id": sid, "scope": scope, **resolved}


# Imported by server.py to attach these routes to the main router.
__all__ = ["register_review_routes"]
