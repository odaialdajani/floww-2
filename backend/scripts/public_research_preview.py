"""Local acceptance view: production routes, real Public reads and real Mongo.

Run from backend: python -m scripts.public_research_preview
This starts a separate local instance, never a sample-data fixture. Background
trading, messaging and optional integrations are not started. Only Public market
read requests are allowed through httpx. Research uses the managed ChatGPT login.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from dotenv import dotenv_values
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
values = dotenv_values(ROOT / ".env")
public_key = values.get("PUBLIC_API_KEY") or os.getenv("PUBLIC_API_KEY", "")
for key in values:
    if key:
        os.environ[key] = ""
os.environ.update(
    PUBLIC_API_KEY=public_key,
    MONGO_URL="mongodb://127.0.0.1:27017",
    DB_NAME="floww_public_research_acceptance",
    FLOWW_AGENT_DEPLOYMENT="local",
    FLOWW_AGENT_ORIGINS="http://localhost:3101,http://127.0.0.1:3101,http://localhost:3102",
    FLOWW_MARKET_DATA_PROVIDER="public",
    FLOWW_ENABLE_LIVE_PUBLIC="0",
    FLOWW_PUBLIC_UNIVERSE="SPY,QQQ",
    CORS_ORIGINS="http://localhost:3101,http://127.0.0.1:3101,http://localhost:3102",
    ENVIRONMENT="development",
    DISCORD_WEBHOOK_URL="",
    TELEGRAM_BOT_TOKEN="",
)

# Request allowlist covers the actual auth/accounts metadata needed by Public's
# market-data client, but no order or position mutation and no messaging host.
original_transport = httpx.AsyncHTTPTransport.handle_async_request


async def market_reads_only(self, request):
    allowed = request.url.host == "api.public.com" and (
        request.url.path == "/userapiauthservice/personal/access-tokens"
        or "/marketdata/" in request.url.path
        or "/historicdata/" in request.url.path
        or (request.method == "GET" and request.url.path.endswith("/trading/account"))
    )
    if not allowed:
        raise httpx.RequestError("This local acceptance view only permits Public market reads", request=request)
    return await original_transport(self, request)


httpx.AsyncHTTPTransport.handle_async_request = market_reads_only

import server  # noqa: E402
from services import journal_store  # noqa: E402

# Scanner reads can update the app's journal/whale projections. Keep those
# incidental writes in this acceptance instance's separate store too.
if journal_store._engine is not None:
    raise RuntimeError("Journal was opened before acceptance isolation; refusing to start")
journal_store._DB_PATH = Path(os.environ["LOCALAPPDATA"]) / "FLOWW" / "acceptance" / "public-journal.duckdb"

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
app = server.app


@asynccontextmanager
async def lifespan(_app):
    from services.flow_alerts import init_flow_alert_tables
    from services.public_api_adapter import close_broker, fetch_chain_from_public_api
    await server.startup_duckdb()
    init_flow_alert_tables(server.duckdb_engine)
    await server.startup_research()
    if app.state.research_service is None:
        raise RuntimeError("Real saved research storage is unavailable")
    data = await fetch_chain_from_public_api("SPY", max_expiries=6)
    if not data or not data.get("contracts"):
        raise RuntimeError("Real Public option data is unavailable")
    print(f"REAL_PUBLIC_READY ticker=SPY contracts={len(data['contracts'])} source={data['data_source']}", flush=True)
    try:
        yield
    finally:
        await server.shutdown_research()
        await close_broker()
        await server.shutdown_duckdb()
        server.client.close()


app.router.lifespan_context = lifespan


@app.middleware("http")
async def research_mutations_only(request, call_next):
    if request.method not in {"GET", "HEAD", "OPTIONS"} and not (
        request.url.path.startswith("/api/agent/")
        or request.url.path == "/api/preferences/theme"
    ):
        return JSONResponse({"detail": "Trading and external messages are disabled in this local view"}, status_code=403)
    return await call_next(request)


# This acceptance instance serves the actual frontend at its root. Preserve all
# production API routes; the server's separate root health response would win
# route matching before the static mount and hide the application.
app.router.routes[:] = [route for route in app.router.routes if getattr(route, "path", None) != "/"]
app.mount("/", StaticFiles(directory=ROOT.parent / "frontend" / "build", html=True), name="public-research-ui")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=3101, proxy_headers=False)
