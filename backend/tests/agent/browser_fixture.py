"""Explicit OFFLINE browser fixture; never imported by the production server."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from mongomock_motor import AsyncMongoMockClient

from routes.agent import router
from services.agent.local_access import AgentCORSMiddleware
from services.agent.reads import ResearchReads
from services.agent.repository import AgentRepository
from services.agent.research import ResearchService

os.environ["FLOWW_AGENT_DEPLOYMENT"] = "local"
os.environ["FLOWW_AGENT_ORIGINS"] = "http://localhost:3101,http://127.0.0.1:3101,http://localhost:3102"
app = FastAPI()
app.include_router(router)
app.add_middleware(AgentCORSMiddleware)
STAMP = datetime.now(UTC).isoformat()
EXPIRY = (datetime.now(UTC) + timedelta(days=7)).date().isoformat()


def chain(ticker="SPY", *args):
    return {
        "ok": True,
        "spot": 500,
        "event_time": STAMP,
        "data_source": "OFFLINE BROWSER FIXTURE",
        "contracts": [
            {
                "strike": strike,
                "type": "call" if strike > 499 else "put",
                "expiry": EXPIRY,
                "gamma": 0.01,
                "open_interest": 1000,
                "oi": 1000,
                "volume": 2000,
                "iv": 0.2,
                "bid": 2,
                "ask": 2.1,
            }
            for strike in (485, 490, 495, 500, 505, 510, 515)
        ],
    }


def heat(ticker="SPY"):
    strikes = [485, 490, 495, 500, 505, 510, 515]
    return {
        "ticker": ticker,
        "spot": 500,
        "event_time": STAMP,
        "source": "OFFLINE BROWSER FIXTURE",
        "grid": {
            "expiries": [EXPIRY],
            "strikes": strikes,
            "grid": {EXPIRY: {str(s): (i - 3) * 2000000 for i, s in enumerate(strikes)}},
        },
    }


@app.on_event("startup")
async def startup():
    repository = AgentRepository(AsyncMongoMockClient().offline_browser)
    await repository.initialize()
    app.state.research_service = ResearchService(repository, ResearchReads(chain, heat, lambda *a: []))


@app.get("/api/heatmap/{ticker}")
async def map_data(ticker):
    return heat(ticker)


@app.get("/api/flowseeker/regime/{ticker}")
async def regime(ticker):
    return {
        "current_state": "OFFLINE TEST",
        "gamma_flip": 498,
        "total_gex": 2000000,
        "vol_env": "Fixture",
        "event_time": STAMP,
    }


@app.get("/api/flowseeker/scan")
async def scan():
    return {
        "rows": [["SPY", "SPY260918C00500000", "call", 500, EXPIRY, 2000, 1000, 0.2, 0.5, 500]],
        "source": "OFFLINE BROWSER FIXTURE",
        "cache_age_seconds": 0,
        "stale": False,
    }


@app.get("/api/public/chain/{ticker}")
async def public_chain(ticker):
    return chain(ticker)


@app.get("/api/flowseeker/alerts/feed")
async def alerts():
    return {
        "alerts": [
            {
                "key": "fixture-alert",
                "under": "SPY",
                "type": "call",
                "strike": 500,
                "exp": EXPIRY,
                "bias": "BULLISH",
                "conviction": 88,
                "rule": "WHALE",
                "asof_ts": STAMP,
                "why": "OFFLINE BROWSER FIXTURE",
                "tier": "GOLD",
            }
        ]
    }


@app.get("/api/flowseeker/alerts/stream")
async def alert_stream():
    async def heartbeats():
        for _ in range(300):
            yield ": offline fixture\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(heartbeats(), media_type="text/event-stream")


@app.websocket("/ws/signals")
async def signals(socket: WebSocket):
    await socket.accept()
    try:
        while True:
            await socket.receive_text()
    except WebSocketDisconnect:
        pass


@app.get("/api/{path:path}")
async def unavailable(path):
    return {}


app.mount(
    "/", StaticFiles(directory=Path(__file__).resolve().parents[3] / "frontend" / "build", html=True), name="offline-ui"
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=3101, proxy_headers=False)
