"""
Simple API key authentication for mutating routes.

Usage: Add X-API-Key header to requests.
The API key is stored in the .env file as API_SECRET_KEY.
"""

import hmac
import logging
import os

from fastapi import HTTPException, Request, WebSocket

logger = logging.getLogger(__name__)

# Routes that require authentication
PROTECTED_METHODS = {"POST", "PUT", "DELETE", "PATCH"}

# Routes that are always public (no auth needed)
PUBLIC_PATHS = {
    "/health",
    "/api/preferences",
    "/api/spot/",
    "/api/data/",
    "/api/chain/",
    "/api/advanced/",
    "/api/movers",
    "/api/history/",
    "/api/gamma-flip/",
    "/api/daily-checklist/",
    "/api/gex/",
    "/api/alerts/check",
    "/api/memory/recall/",
    "/api/memory/summary/",
    "/api/auth/",
    "/api/ml/predict/",       # ML predictions — safe GET, no auth needed
    "/api/ml/briefing/",      # ML briefing — safe GET, no auth needed
    "/api/ml/models",         # Model listing — safe GET
    "/api/ml/features/",      # Feature inspection — safe GET
    "/api/ml/dashboard",       # Dashboard — safe GET
    "/api/ml/drift/",         # Drift report — safe GET
    "/dashboard/_dash-update-component",
    "/dashboard/_dash-layout",
    "/dashboard/_dash-dependencies",
    "/favicon.ico",

}


def get_api_key() -> str:
    """Get the API secret key from environment."""
    return os.environ.get("API_SECRET_KEY", "")


def get_ws_token() -> str:
    """Get the WebSocket auth token from environment.

    Empty string means no token is configured → verify_ws_token allows the
    connection (development mode). Mirrors get_api_key for HTTP routes.
    """
    return os.environ.get("WS_API_TOKEN", "")


def is_public_path(path: str) -> bool:
    """Check if a path is public (no auth required)."""
    return any(path.startswith(public_path) for public_path in PUBLIC_PATHS)


async def require_api_key(request: Request):
    """Verify API key for ALL HTTP methods (use on sensitive GET routes).

    Unlike verify_api_key, this does NOT skip non-mutating methods.
    Add as Depends(require_api_key) on GET routes that expose sensitive data.
    """
    api_key = request.headers.get("X-API-Key", "")
    expected_key = get_api_key()
    if not expected_key:
        logger.critical(
            "API_SECRET_KEY not set — sensitive route is DISABLED. "
            "Set API_SECRET_KEY in environment to enable."
        )
        raise HTTPException(
            status_code=503,
            detail="Authentication not configured. Set API_SECRET_KEY.",
        )
    # Constant-time compare — plain != leaks length/prefix via timing.
    if not hmac.compare_digest(api_key, expected_key):
        client_host = request.client.host if request.client else "unknown"
        logger.warning(f"Invalid API key from {client_host} for {request.url.path}")
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return True


async def verify_api_key(request: Request):
    """Verify the API key for protected routes."""
    # Only protect mutating methods
    if request.method not in PROTECTED_METHODS:
        return True

    from services.agent.local_access import research_path
    if research_path(request.method, request.url.path):
        return True  # Routes independently enforce local session ownership.

    # Public paths don't need auth
    if is_public_path(request.url.path):
        return True

    # Check for API key in header
    api_key = request.headers.get("X-API-Key", "")
    expected_key = get_api_key()

    # FAIL CLOSED: if no API key is configured, reject all mutating requests.
    # This prevents accidental exposure when .env is missing or misconfigured.
    if not expected_key:
        logger.critical(
            "API_SECRET_KEY not set — mutating routes are DISABLED. "
            "Set API_SECRET_KEY in environment to enable."
        )
        raise HTTPException(
            status_code=503,
            detail="Authentication not configured. Set API_SECRET_KEY."
        )

    # Constant-time compare — plain != leaks length/prefix via timing.
    if not hmac.compare_digest(api_key, expected_key):
        client_host = request.client.host if request.client else "unknown"
        logger.warning(f"Invalid API key from {client_host} for {request.url.path}")
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    return True


async def verify_ws_token(websocket: WebSocket) -> bool:
    """Verify the WebSocket connection token.

    Token can be passed as a query parameter: /ws/{topic}?token=<token>
    If WS_API_TOKEN is not set, connections are allowed (development mode).
    """
    expected = get_ws_token()
    if not expected:
        # No token configured — allow (dev mode)
        return True

    token = websocket.query_params.get("token", "")
    # Constant-time compare — plain != leaks length/prefix via timing.
    if not hmac.compare_digest(token, expected):
        logger.warning(f"Invalid WS token from {websocket.client.host if websocket.client else 'unknown'}")
        return False
    return True
