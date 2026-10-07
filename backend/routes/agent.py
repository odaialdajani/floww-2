"""Owned local research. GET only observes durable work."""

import asyncio
import json
import os
import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from auth import require_api_key
from services.agent.contracts import request_spec
from services.agent.local_access import COOKIE, require_local
from services.agent.repository import TERMINAL

router = APIRouter(prefix="/api/agent", tags=["agent"])


def service(request):
    result = getattr(request.app.state, "research_service", None)
    if result is None:
        raise HTTPException(503, "Saved research storage is unavailable")
    return result


async def ready_service(request):
    """Retry failed startup once storage is ready; never replace active work."""
    if getattr(request.app.state, "research_service", None) is not None:
        return service(request)
    initialize = getattr(request.app.state, "initialize_research", None)
    if initialize is not None:
        lock = getattr(request.app.state, "research_start_lock", None)
        if lock is None:
            lock = request.app.state.research_start_lock = asyncio.Lock()
        async with lock:
            if getattr(request.app.state, "research_service", None) is None:
                try:
                    await initialize()
                except Exception:
                    raise HTTPException(503, "Saved research storage is unavailable") from None
    return service(request)


async def owner(request):
    require_local(request)
    await ready_service(request)
    try:
        result = await service(request).repository.owner(request.cookies.get(COOKIE))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Session storage is unavailable") from None
    if not result:
        raise HTTPException(401, "Research session expired")
    return result


def public_turn(doc):
    return jsonable_encoder({k: v for k, v in doc.items() if k not in {"_id", "owner", "digest", "request_id"}})


async def storage_result(operation):
    try:
        return await operation
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Saved research storage is unavailable") from None


@router.get("/budget", dependencies=[Depends(require_api_key)])
async def budget(request: Request):
    # This path is deliberately not exempt from the existing secret-key guard.
    model = (await ready_service(request)).model
    if model is None:
        raise HTTPException(503, "Model budget is unavailable")
    return await storage_result(model.spend.state())


def set_session_cookie(response, request, token):
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        max_age=30 * 86400,
        path="/api/agent",
    )


@router.post("/session/rotate")
async def rotate_session(request: Request, response: Response):
    await owner(request)
    _, token = await storage_result(service(request).repository.rotate_session(request.cookies[COOKIE]))
    set_session_cookie(response, request, token)
    return {"status": "ready"}


@router.post("/session/logout")
async def logout_session(request: Request, response: Response):
    require_local(request)
    await ready_service(request)
    await storage_result(service(request).repository.revoke_session(request.cookies.get(COOKIE)))
    response.delete_cookie(COOKIE, path="/api/agent")
    return {"status": "signed-out"}


@router.post("/session/recover", dependencies=[Depends(require_api_key)])
async def recover_session(body: dict, request: Request, response: Response):
    require_local(request)
    await ready_service(request)
    try:
        token = await service(request).repository.recover_session(body.get("owner"))
    except ValueError:
        raise HTTPException(404, "Owner history not found") from None
    except Exception:
        raise HTTPException(503, "Session recovery is unavailable") from None
    set_session_cookie(response, request, token)
    return {"status": "ready"}


@router.post("/session")
async def session(request: Request, response: Response):
    require_local(request)
    await ready_service(request)
    try:
        _, token = await service(request).repository.session(request.cookies.get(COOKIE))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Session could not be saved") from None
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        max_age=30 * 86400,
        path="/api/agent",
    )
    return {"status": "ready"}


@router.post("/ask")
async def ask(body: dict, request: Request):
    identity = await owner(request)
    # Rollback stops new work while retaining private history, observation,
    # cancellation and session revocation for work already saved.
    if os.getenv("FLOWW_AGENT_DISABLED") == "1":
        raise HTTPException(503, "New research is disabled")
    try:
        doc = await service(request).ask(identity, body.get("request_id"), request_spec(body))
        return {"turn_id": doc["turn_id"], "status": doc["status"]}
    except ValueError as exc:
        raise HTTPException(409 if "already belongs" in str(exc) else 422, str(exc)) from None
    except OverflowError:
        raise HTTPException(429, "Research queue is full") from None
    except Exception:
        raise HTTPException(503, "Request could not be saved") from None


@router.get("/turn/{turn_id}")
async def get_turn(turn_id: str, request: Request):
    identity = await owner(request)
    doc = await storage_result(service(request).repository.read(identity, turn_id))
    if doc is None:
        raise HTTPException(404, "Answer not found")
    return public_turn(doc)


@router.get("/history")
async def history(request: Request):
    identity = await owner(request)
    return {"turns": [public_turn(doc) for doc in await storage_result(service(request).repository.history(identity))]}


@router.get("/history/page")
async def history_page(request: Request, limit: int = Query(30, ge=1, le=30), cursor: str | None = None):
    identity = await owner(request)
    try:
        page = await service(request).repository.history_page(identity, limit=limit, cursor=cursor)
    except ValueError:
        raise HTTPException(422, "Invalid saved-answer page or cursor") from None
    except Exception:
        raise HTTPException(503, "Saved research storage is unavailable") from None
    return {**page, "turns": [public_turn(doc) for doc in page["turns"]]}


@router.post("/cancel/{turn_id}")
async def cancel(turn_id: str, request: Request):
    identity = await owner(request)
    doc = await storage_result(service(request).cancel(identity, turn_id))
    if doc is None:
        raise HTTPException(404, "Answer not found")
    return public_turn(doc)


@router.get("/stream/{turn_id}")
async def stream(turn_id: str, request: Request):
    identity = await owner(request)
    repository = service(request).repository
    if await storage_result(repository.read(identity, turn_id)) is None:
        raise HTTPException(404, "Answer not found")
    try:
        start = max(0, int(request.headers.get("Last-Event-ID", "0")))
    except ValueError:
        raise HTTPException(422, "Invalid event cursor") from None

    async def observe():
        async def allowed():
            try:
                return await repository.owner(request.cookies.get(COOKIE)) == identity
            except Exception:
                return False

        cursor = start
        for _ in range(260):
            if await request.is_disconnected() or not await allowed():
                return
            doc = await repository.read(identity, turn_id)
            if doc is None:
                return
            for event in doc["events"]:
                if event["id"] > cursor:
                    if not await allowed():
                        return
                    yield f"id: {event['id']}\nevent: {event['type']}\ndata: {json.dumps(event)}\n\n"
                    cursor = event["id"]
            if doc["status"] in TERMINAL:
                return
            if not await allowed():
                return
            yield ": heartbeat\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        observe(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.get("/prefs")
async def prefs(request: Request):
    identity = await owner(request)
    return await storage_result(service(request).repository.get_preferences(identity))


@router.get("/models")
async def models(request: Request):
    identity = await owner(request)
    model = service(request).model
    if model is None or not hasattr(model, "catalog"):
        raise HTTPException(503, "ChatGPT login is unavailable")
    return {"models": await storage_result(model.catalog()),
            "selected": await storage_result(model.settings_for(identity)),
            "usage": await storage_result(model.spend.state())}


@router.put("/prefs")
async def save_prefs(body: dict, request: Request):
    identity = await owner(request)
    allowed = {
        "default_horizon",
        "watchlist_extra",
        "quiet_hours",
        "muted_tickers",
        "max_cards_per_day",
        "ticker_notes",
        "ai_settings",
    }
    if set(body) - allowed or len(json.dumps(body)) > 8000:
        raise HTTPException(422, "Unsupported preference")
    if "default_horizon" in body:
        from services.agent.access.horizon import normalize_horizon

        try:
            normalize_horizon(body["default_horizon"])
        except (ValueError, AttributeError):
            raise HTTPException(422, "Invalid horizon") from None
    if "ai_settings" in body:
        model = service(request).model
        if model is None or not hasattr(model, "validate_settings"):
            raise HTTPException(503, "AI choices are unavailable")
        try:
            body["ai_settings"] = await model.validate_settings(body["ai_settings"])
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        except Exception:
            raise HTTPException(503, "AI choices are unavailable") from None
    await storage_result(service(request).repository.save_preferences(identity, body))
    return {"saved": True}


@router.post("/handoffs")
async def save_native_handoff(body: dict, request: Request):
    identity = await owner(request)
    fields = {"turn_id", "context_hash", "execution_owner", "brief", "workflow_reference", "reported_status"}
    if (set(body) != fields or len(json.dumps(body)) > 12000
            or any(not isinstance(value, str) for value in body.values())
            or not re.fullmatch(r"[a-f0-9]{64}", body["context_hash"])
            or not 1 <= len(body["turn_id"]) <= 128
            or not 1 <= len(body["brief"].strip()) <= 10000
            or len(body["workflow_reference"]) > 256
            or body["execution_owner"] != "PUBLIC_NATIVE_AGENT"
            or body["reported_status"] not in {"prepared", "reviewed", "reported_active", "reported_paused"}):
        raise HTTPException(422, "Unsupported manual handoff; execution approval cannot be recorded here")
    repository = service(request).repository
    turn = await storage_result(repository.read(identity, body["turn_id"]))
    if turn is None:
        raise HTTPException(404, "Saved research not found")
    draft = (turn.get("answer") or {}).get("plan_draft") or {}
    if (turn.get("status") != "completed" or draft.get("version") != "trade-plan-draft.v1"
            or not draft.get("contract") or draft.get("context_hash") != body["context_hash"]):
        raise HTTPException(409, "Handoff requires the owning saved exact-contract draft")
    # Operator reporting is private research history, never broker verification
    # or authority to activate a native workflow or a backend executor.
    record = {**body, "version": "native-handoff.v1", "draft_id": draft["draft_id"],
              "broker_verified": False, "activation": "unverified", "approval": None}
    return public_turn(await storage_result(repository.save_native_handoff(identity, record)))


@router.get("/handoffs")
async def native_handoff_history(request: Request):
    identity = await owner(request)
    records = await storage_result(service(request).repository.native_handoff_history(identity))
    return {"handoffs": [public_turn(record) for record in records]}


@router.get("/claims")
async def claims(request: Request):
    identity = await owner(request)
    docs = (
        await service(request)
        .repository.claims.find({"owner": identity}, {"_id": 0, "owner": 0})
        .limit(100)
        .to_list(length=100)
    )
    return {"claims": jsonable_encoder(docs)}
