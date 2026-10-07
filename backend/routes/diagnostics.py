"""Local-only bounded problem reports, separate from research and broker actions."""
import json

from fastapi import APIRouter, HTTPException, Request

from services.agent.local_access import require_local
from services.problem_journal import KINDS, journal, record_problem

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])
FIELDS = {"kind", "route", "method", "status", "duration_ms", "name", "result", "event_id"}
CLIENT_KINDS = KINDS - {"server_log", "failed_request", "slow_request"}


@router.post("/events")
async def events(request: Request):
    require_local(request)
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 12000:
            raise HTTPException(413, "Problem report is too large")
    try:
        payload = json.loads(body)
    except ValueError:
        raise HTTPException(422, "Invalid problem report") from None
    rows = payload.get("events") if isinstance(payload, dict) and set(payload) == {"events"} else None
    if not isinstance(rows, list) or not 1 <= len(rows) <= 30:
        raise HTTPException(422, "Use a small list of problem reports")
    for row in rows:
        if not isinstance(row, dict) or set(row) - FIELDS or row.get("kind") not in CLIENT_KINDS:
            raise HTTPException(422, "Unsupported problem report")
    saved = sum(record_problem(row) for row in rows)
    if saved != len(rows):
        raise HTTPException(503, "Problem log could not save every report")
    return {"saved": saved}


@router.get("/summary")
async def summary(request: Request):
    require_local(request)
    try:
        return journal().summary()
    except Exception:
        raise HTTPException(503, "Problem log is unavailable") from None
