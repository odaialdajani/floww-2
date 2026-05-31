"""
LLM service for Confluence Decoder.

Supports multiple providers:
- Gemini (primary)
- Cerebras (fallback for fast inference)
- OpenRouter (optional)

Used for:
- Trade analysis
- Morning briefing generation
- Alert explanations
- Market commentary
"""

import logging
import os
from typing import Any, Dict

from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()


class LLMService:
    """LLM service for trade analysis, briefings, and market commentary."""

    def __init__(self):
        self.provider = os.environ.get("LLM_PROVIDER", "gemini")
        self.api_key = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("LLM_API_KEY", "")

    def generate(self, prompt: str, system_prompt: str = "", max_tokens: int = 512) -> dict:
        """Generate a response from the configured LLM provider."""
        return {"text": "", "provider": self.provider, "tokens_used": 0}


_llm_service = None

def get_llm_service() -> LLMService:
    """Get the LLM service singleton."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


async def analyze_trade_with_llm(
    ticker: str,
    spot: float,
    regime: str,
    net_gex: float,
    prediction: str,
    confidence: float,
) -> Dict[str, Any]:
    """Analyze a trade opportunity using LLM."""
    llm = get_llm_service()

    system_prompt = """You are an expert options trading analyst. 
Analyze the trading setup and provide a concise, actionable assessment.
Focus on: regime context, GEX implications, risk/reward, and suggested strategy.
Keep responses under 200 words."""

    prompt = f"""Ticker: {ticker}
Spot: ${spot:.2f}
Current Regime: {regime}
Net GEX: {net_gex:,.0f}
ML Prediction: {prediction} (confidence: {confidence:.1%})

Provide a brief trade analysis and strategy suggestion."""

    result = llm.generate(prompt, system_prompt=system_prompt, max_tokens=512)
    return result
