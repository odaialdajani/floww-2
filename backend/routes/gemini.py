"""API routes for Gemini AI analysis."""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/analyze-trade")
async def analyze_trade(trade: Dict[str, Any], market_context: Optional[Dict[str, Any]] = None):
    """AI analysis of a trade from the journal."""
    try:
        from gemini_analyzer import GeminiAnalyzer
        analyzer = GeminiAnalyzer()
        result = await analyzer.analyze_trade(trade, market_context)
        if result:
            return {"analysis": result, "source": "gemini"}
        return {"error": "Gemini not available. Check API key and quota."}
    except Exception as e:
        return {"error": str(e)}


@router.post("/analyze-regime")
async def analyze_regime(regime_data: Dict[str, Any]):
    """AI analysis of current market regime."""
    try:
        from gemini_analyzer import GeminiAnalyzer
        analyzer = GeminiAnalyzer()
        result = await analyzer.analyze_regime(regime_data)
        if result:
            return {"analysis": result, "source": "gemini"}
        return {"error": "Gemini not available. Check API key and quota."}
    except Exception as e:
        return {"error": str(e)}


@router.post("/summarize-day")
async def summarize_day(
    trades: List[Dict[str, Any]],
    pnl: float = 0,
    regime: str = "unknown",
):
    """AI end-of-day trading summary."""
    try:
        from gemini_analyzer import GeminiAnalyzer
        analyzer = GeminiAnalyzer()
        result = await analyzer.summarize_day(trades, pnl, regime)
        if result:
            return {"summary": result, "source": "gemini"}
        return {"error": "Gemini not available. Check API key and quota."}
    except Exception as e:
        return {"error": str(e)}


@router.post("/explain-signal")
async def explain_signal(signal: Dict[str, Any]):
    """AI explanation of an options flow signal."""
    try:
        from gemini_analyzer import GeminiAnalyzer
        analyzer = GeminiAnalyzer()
        result = await analyzer.explain_flow_signal(signal)
        if result:
            return {"explanation": result, "source": "gemini"}
        return {"error": "Gemini not available. Check API key and quota."}
    except Exception as e:
        return {"error": str(e)}


@router.get("/status")
async def get_ai_status():
    """Get AI service status."""
    try:
        from gemini_analyzer import GEMINI_API_KEY
        return {
            "gemini": {
                "enabled": bool(GEMINI_API_KEY),
                "key_set": bool(GEMINI_API_KEY),
                "model": "gemini-1.5-flash",
                "note": "Free tier via GitHub Student Pack. Quota may be limited.",
            }
        }
    except Exception as e:
        return {"error": str(e)}
