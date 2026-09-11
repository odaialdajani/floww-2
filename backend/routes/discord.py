"""
backend/routes/discord.py — Discord ops wiring status (no secrets, ever).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from auth import require_api_key

router = APIRouter(prefix="/api/discord", tags=["discord"])


@router.get("/status")
async def discord_status(_: bool = Depends(require_api_key)):
    """Show Discord wiring state. Booleans only — tokens never leave env."""
    try:
        from services import discord_ops as ops

        return {
            "webhook_configured": bool(ops.webhook_url()),
            "bot_token_configured": bool(ops._env("DISCORD_BOT_TOKEN", "").strip()),
            "min_tier": ops.min_tier(),
            "rules": sorted(ops.watched_rules()),
            "trading_allowlist_size": len(ops.allowed_user_ids()),
            "dropped_empty_total": ops.DROPPED_EMPTY["count"],
            "venue": "alpaca-paper",
        }
    except Exception as e:
        return {"error": str(e)}


@router.post("/test")
async def discord_test(_: bool = Depends(require_api_key)):
    """Post a test ping to the webhook (proves wiring end-to-end)."""
    try:
        from services import discord_ops as ops

        if not ops.webhook_url():
            return {"posted": False, "reason": "DISCORD_WEBHOOK_URL unset"}
        n = await ops.post_alerts([{
            "key": "test|ping", "ckey": "ping", "rule": "SCORE", "tier": "GOLD",
            "side": "BUY", "bias": "BULLISH", "under": "SPY", "type": "call",
            "strike": 700, "exp": "2099-01-01", "dte": 5, "score": 99,
            "premium": 1000000, "vol_oi": 9.9, "why": "wiring test — ignore",
        }])
        return {"posted": n > 0}
    except Exception as e:
        return {"posted": False, "reason": str(e)}
