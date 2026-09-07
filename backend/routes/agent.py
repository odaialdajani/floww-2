"""Lodestar transport (plan v3 L8).

POST /api/agent/ask -> {turn_id} (key-free on local app via PUBLIC_PATHS).
GET  /api/agent/stream/{turn_id} SSE: step -> sentence -> done, id: on every
event, Last-Event-ID resume, max_seconds=120, heartbeat.
GET  /api/agent/turn/{id} replay. POST /api/agent/cancel/{id}.
GET  /api/agent/budget, GET /api/agent/claims, GET/PUT /api/agent/prefs.

Contract mirrors tests/routes/test_llm_endpoints.py: 200 or clean 503,
never 500. Errors after the stream opens are event: error frames.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from services.agent.budget import budget_state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent"])

_TURNS: dict[str, dict[str, Any]] = {}
_CANCEL: set[str] = set()
_INFLIGHT: dict[str, str] = {}
_PREFS: dict[str, Any] = {
    "risk_pct": 1.0,
    "default_horizon": "all",
    "watchlist_extra": [],
    "venue_default": "paper",
    "quiet_hours": [],
    "conviction_floor": 60,
    "max_cards_per_day": 24,
    "muted_tickers": [],
}
_CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization, X-API-Key",
}

MAX_SECONDS = 120


def _disabled() -> bool:
    if os.environ.get("FLOWW_AGENT_DISABLED", "") == "1":
        return True
    try:
        return bool(_PREFS.get("agent_enabled") is False)
    except Exception:
        return False


def _db(request: Request):  # Mongo or None
    try:
        return request.app.state.mongo_db if hasattr(request.app.state, "mongo_db") else None
    except Exception:
        return None


def _frame(event: str, payload: Any, eid: str) -> str:
    try:
        data = json.dumps(payload, default=str)
    except Exception:
        data = "{}"
    return f"id: {eid}\nevent: {event}\ndata: {data}\n\n"


@router.post("/ask")
async def ask(body: dict[str, Any], request: Request):
    try:
        if _disabled():
            return JSONResponse(status_code=503, content={"error": "agent-disabled", "message": "Agent is disabled."}, headers=_CORS)
        q = str((body or {}).get("question", "") or "")[:2000]
        ticker = str((body or {}).get("ticker", "SPY") or "SPY")[:12]
        horizon = str((body or {}).get("horizon", "all") or "all")[:12]
        qclass = str((body or {}).get("question_class", "full-research") or "full-research")[:32]
        screen = (body or {}).get("screen") if isinstance(body, dict) else None
        if not q:
            return JSONResponse(status_code=422, content={"error": "empty-question"}, headers=_CORS)
        key = f"{ticker.upper()}:{(horizon or 'all').lower()}"
        if key in _INFLIGHT:
            return JSONResponse(status_code=200, content={"turn_id": _INFLIGHT[key], "deduped": True}, headers=_CORS)
        turn_id = str(uuid.uuid4())
        _INFLIGHT[key] = turn_id
        _TURNS[turn_id] = {"status": "queued", "body": {"question": q, "ticker": ticker, "horizon": horizon, "question_class": qclass, "screen": screen}, "events": [], "key": key}
        return JSONResponse(status_code=200, content={"turn_id": turn_id}, headers=_CORS)
    except Exception as e:
        logger.warning("agent ask failed: %s", e)
        return JSONResponse(status_code=503, content={"error": "agent-unavailable", "message": str(e)[:200]}, headers=_CORS)


async def _run_and_store(turn_id: str, db: Any) -> None:
    spec = _TURNS.get(turn_id, {})
    body = spec.get("body", {})
    try:
        from services.agent.loop import run_turn

        turn = await run_turn(question=body.get("question", ""), ticker=body.get("ticker", "SPY"), horizon=body.get("horizon", "all"), question_class=body.get("question_class", "full-research"), screen=body.get("screen"), db=db)
        turn["turn_id"] = turn_id
        _TURNS[turn_id] = turn
    except Exception as e:
        _TURNS[turn_id] = {"turn_id": turn_id, "status": "error", "error": str(e)[:300], "events": [], "text": "", "verdict": {}}
    finally:
        key = spec.get("key", "")
        if key and _INFLIGHT.get(key) == turn_id:
            _INFLIGHT.pop(key, None)


@router.get("/stream/{turn_id}")
async def stream(turn_id: str, request: Request):
    try:
        if _disabled():
            async def _off():
                yield _frame("error", {"error": "agent-disabled"}, "0")

            return StreamingResponse(_off(), media_type="text/event-stream", headers=_CORS)
        spec = _TURNS.get(turn_id)
        if spec is None:
            try:
                db = _db(request)
                if db is not None:
                    doc = db["agent_turns"].find_one({"turn_id": turn_id})
                    if doc:
                        _TURNS[turn_id] = {"turn_id": turn_id, "status": "done", "events": doc.get("events", []), "text": "", "verdict": doc.get("verdict", {})}
                        spec = _TURNS[turn_id]
            except Exception:
                pass
        if spec is None:
            async def _nf():
                yield _frame("error", {"error": "unknown-turn"}, "0")

            return StreamingResponse(_nf(), media_type="text/event-stream", headers=_CORS)

        last_id = request.headers.get("Last-Event-ID", "")
        db = _db(request)

        async def _gen():
            eid = 0
            yield _frame("heartbeat", {"turn_id": turn_id}, str(eid))
            if spec.get("status") == "queued":
                task = asyncio.create_task(_run_and_store(turn_id, db))
                t0 = time.time()
                while _TURNS.get(turn_id, {}).get("status") == "queued" and (time.time() - t0) < MAX_SECONDS:
                    if turn_id in _CANCEL:
                        task.cancel()
                        yield _frame("error", {"error": "cancelled"}, str(eid + 1))
                        return
                    await asyncio.sleep(0.25)
                with contextlib.suppress(Exception):
                    await asyncio.wait_for(task, timeout=5)
            turn = _TURNS.get(turn_id, {})
            if turn.get("status") == "error":
                yield _frame("error", {"error": turn.get("error", "failed")}, "1")
                return
            events = turn.get("events", []) or []
            start = 0
            try:
                start = int(last_id) if str(last_id).isdigit() else 0
            except Exception:
                start = 0
            eid = start
            for ev in events[start:]:
                eid += 1
                yield _frame("step", ev, str(eid))
            text = turn.get("text", "") or ""
            # Sentence-level streaming (token streaming is incompatible
            # with cite substitution + regeneration).
            sents = [s.strip() for s in text.replace("\n", " ").split(". ") if s.strip()][:40]
            if not sents and text:
                sents = [text[:800]]
            for s in sents:
                eid += 1
                if turn_id in _CANCEL:
                    yield _frame("error", {"error": "cancelled"}, str(eid))
                    return
                yield _frame("sentence", {"text": s[:800]}, str(eid))
            eid += 1
            cost = {}
            with contextlib.suppress(Exception):
                cost = budget_state(db)
            yield _frame("done", {"turn_id": turn_id, "verdict": turn.get("verdict", {}), "flagged": turn.get("flagged", []), "cost": cost, "prep_mode": turn.get("prep_mode", False)}, str(eid))

        return StreamingResponse(_gen(), media_type="text/event-stream", headers={**_CORS, "Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    except Exception as e:
        logger.warning("agent stream failed: %s", e)

        async def _err():
            yield _frame("error", {"error": "agent-unavailable"}, "0")

        return StreamingResponse(_err(), media_type="text/event-stream", headers=_CORS)


@router.get("/turn/{turn_id}")
async def get_turn(turn_id: str, request: Request):
    try:
        turn = _TURNS.get(turn_id)
        if turn is None and _db(request) is not None:
            try:
                doc = _db(request)["agent_turns"].find_one({"turn_id": turn_id})
                if doc:
                    doc.pop("_id", None)
                    return JSONResponse(status_code=200, content=doc, headers=_CORS)
            except Exception:
                pass
        if turn is None:
            return JSONResponse(status_code=404, content={"error": "unknown-turn"}, headers=_CORS)
        safe = {k: v for k, v in turn.items() if k != "ledger"}
        return JSONResponse(status_code=200, content=safe, headers=_CORS)
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": "agent-unavailable", "message": str(e)[:200]}, headers=_CORS)


@router.post("/cancel/{turn_id}")
async def cancel(turn_id: str):
    _CANCEL.add(turn_id)
    return JSONResponse(status_code=200, content={"cancelled": turn_id}, headers=_CORS)


@router.get("/budget")
async def budget(request: Request):
    try:
        return JSONResponse(status_code=200, content=budget_state(_db(request)), headers=_CORS)
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": "agent-unavailable", "message": str(e)[:200]}, headers=_CORS)


@router.get("/claims")
async def claims(request: Request, ticker: str = "", limit: int = 50):
    try:
        db = _db(request)
        if db is None:
            return JSONResponse(status_code=200, content={"claims": [], "note": "no db"}, headers=_CORS)
        q: dict[str, Any] = {}
        if ticker:
            q["ticker"] = ticker.upper()
        cur = db["agent_claims"].find(q).sort("made_at", -1).limit(max(1, min(int(limit), 200)))
        out = []
        for d in cur:
            d.pop("_id", None)
            out.append(d)
        return JSONResponse(status_code=200, content={"claims": out}, headers=_CORS)
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": "agent-unavailable", "message": str(e)[:200]}, headers=_CORS)


@router.get("/prefs")
async def get_prefs():
    return JSONResponse(status_code=200, content=_PREFS, headers=_CORS)


@router.put("/prefs")
async def put_prefs(body: dict[str, Any]):
    try:
        for k in ("risk_pct", "default_horizon", "watchlist_extra", "venue_default", "quiet_hours", "conviction_floor", "max_cards_per_day", "muted_tickers"):
            if k in (body or {}):
                _PREFS[k] = body[k]
        return JSONResponse(status_code=200, content=_PREFS, headers=_CORS)
    except Exception as e:
        return JSONResponse(status_code=503, content={"error": "agent-unavailable", "message": str(e)[:200]}, headers=_CORS)
