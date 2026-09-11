"""Owned local research. GET only observes durable work."""

import asyncio
import json
import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from auth import require_api_key
from services.agent.contracts import request_spec
from services.agent.local_access import COOKIE, require_local
from services.agent.repository import TERMINAL

router = APIRouter(prefix="/api/agent", tags=["agent"])


def service(request):
    if os.getenv("FLOWW_AGENT_DISABLED") == "1":
        raise HTTPException(503, "Research is disabled")
    result = getattr(request.app.state, "research_service", None)
    if result is None:
        raise HTTPException(503, "Saved research storage is unavailable")
    return result


async def owner(request):
    require_local(request)
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
    model = service(request).model
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
    await storage_result(service(request).repository.revoke_session(request.cookies.get(COOKIE)))
    response.delete_cookie(COOKIE, path="/api/agent")
    return {"status": "signed-out"}


@router.post("/session/recover", dependencies=[Depends(require_api_key)])
async def recover_session(body: dict, request: Request, response: Response):
    require_local(request)
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
        cursor = start
        for _ in range(260):
            if await request.is_disconnected():
                return
            doc = await repository.read(identity, turn_id)
            if doc is None:
                return
            for event in doc["events"]:
                if event["id"] > cursor:
                    yield f"id: {event['id']}\nevent: {event['type']}\ndata: {json.dumps(event)}\n\n"
                    cursor = event["id"]
            if doc["status"] in TERMINAL:
                return
            yield ": heartbeat\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        observe(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.get("/prefs")
async def prefs(request: Request):
    return await storage_result(service(request).repository.get_preferences(await owner(request)))


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
    }
    if set(body) - allowed or len(json.dumps(body)) > 8000:
        raise HTTPException(422, "Unsupported preference")
    if "default_horizon" in body:
        from services.agent.access.horizon import normalize_horizon

        try:
            normalize_horizon(body["default_horizon"])
        except (ValueError, AttributeError):
            raise HTTPException(422, "Invalid horizon") from None
    await storage_result(service(request).repository.save_preferences(identity, body))
    return {"saved": True}


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
