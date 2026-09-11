"""Local ownership boundary, separate from privileged actions."""

import os
import re
from urllib.parse import urlsplit

from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

COOKIE = "floww_research"
_EXACT = {
    "POST": {"/api/agent/session", "/api/agent/ask", "/api/agent/session/rotate", "/api/agent/session/logout"},
    "GET": {"/api/agent/history", "/api/agent/claims", "/api/agent/prefs"},
    "PUT": {"/api/agent/prefs"},
}


def research_path(method, path):
    if path in _EXACT.get(method, set()):
        return True
    return bool(
        re.fullmatch(r"/api/agent/(?:turn|stream)/[a-f0-9-]{36}", path)
        if method == "GET"
        else re.fullmatch(r"/api/agent/cancel/[a-f0-9-]{36}", path)
        if method == "POST"
        else False
    )


def trusted_origins():
    return {
        v.strip()
        for v in os.getenv(
            "FLOWW_AGENT_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8000,http://127.0.0.1:8000",
        ).split(",")
        if v.strip() and v.strip() != "*"
    }


def require_local(request):
    if os.getenv("FLOWW_AGENT_DEPLOYMENT") != "local":
        raise HTTPException(503, "Local research mode must be explicitly configured")
    if request.client is None or request.client.host not in {"127.0.0.1", "::1"}:
        raise HTTPException(403, "Direct local access required")
    if any(h in request.headers for h in ("forwarded", "x-forwarded-for", "x-forwarded-host", "x-real-ip")):
        raise HTTPException(403, "Proxied anonymous access is disabled")
    host = urlsplit("//" + request.headers.get("host", "")).hostname
    if host not in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(403, "Untrusted host")
    origin = request.headers.get("origin")
    if origin and origin not in trusted_origins():
        raise HTTPException(403, "Untrusted origin")
    if request.method in {"POST", "PUT", "DELETE", "PATCH"} and origin not in trusted_origins():
        raise HTTPException(403, "A trusted browser origin is required")


class AgentCORSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not request.url.path.startswith("/api/agent/"):
            return await call_next(request)
        origin = request.headers.get("origin")
        if request.method == "OPTIONS":
            method = request.headers.get("access-control-request-method", "")
            # CORS permission does not grant anonymous access: these exact
            # administrative routes retain their server-key dependency.
            administrative = (method, request.url.path) in {
                ("POST", "/api/agent/session/recover"),
                ("GET", "/api/agent/budget"),
            }
            response = Response(
                status_code=204
                if origin in trusted_origins() and (research_path(method, request.url.path) or administrative)
                else 403
            )
        else:
            response = await call_next(request)
        for name in ("access-control-allow-origin", "access-control-allow-credentials"):
            if name in response.headers:
                del response.headers[name]
        if origin in trusted_origins():
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Last-Event-ID, X-API-Key"
            response.headers["Vary"] = "Origin"
        return response
