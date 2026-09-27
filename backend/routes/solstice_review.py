"""
R8-04: review/journal endpoints for saved scenario decisions.

Adds:
- GET /{ticker}/decisions — list saved scenario decisions (review journal)
- POST /{ticker}/decisions/{decision_id}/review — save a review state
"""

from __future__ import annotations

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


# Imported by server.py to attach these routes to the main router.
__all__ = ["register_review_routes"]
