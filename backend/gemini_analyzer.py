"""
Gemini AI Integration for Confluence Decoder

Uses Google Gemini API for:
- Trade journal AI analysis (why did a trade work/fail?)
- Market regime interpretation
- Strategy recommendations based on GEX + flow data
- Natural language trade summaries

Free tier: Gemini 1.5 Flash via GitHub Student Pack
"""

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


class GeminiAnalyzer:
    """AI-powered trade and market analysis using Gemini."""

    def __init__(self):
        self.enabled = bool(GEMINI_API_KEY)
        self._client = None

    def _get_client(self):
        """Lazy-initialize Gemini client."""
        if self._client is None and self.enabled:
            try:
                from google import genai
                self._client = genai.Client(api_key=GEMINI_API_KEY)
            except ImportError:
                logger.warning("google-genai not installed. Run: pip install google-genai")
                self.enabled = False
        return self._client

    async def analyze_trade(self, trade: Dict[str, Any], market_context: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Analyze a trade from the journal.
        Explains why it worked or failed based on GEX regime, flow data, etc.
        """
        client = self._get_client()
        if not client:
            return None

        prompt = f"""You are an expert options trading analyst. Analyze this trade:

Trade Details:
- Ticker: {trade.get('ticker', 'Unknown')}
- Type: {trade.get('type', 'Unknown')} {trade.get('action', 'Unknown')}
- Strike: {trade.get('strike', 'N/A')}
- Expiry: {trade.get('expiry', 'N/A')}
- Quantity: {trade.get('quantity', 'N/A')}
- Entry Price: ${trade.get('entry_price', 'N/A')}
- Exit Price: ${trade.get('exit_price', 'N/A')}
- Entry Date: {trade.get('entry_date', 'N/A')}
- Exit Date: {trade.get('exit_date', 'N/A')}
- GEX Regime at Entry: {trade.get('gex_regime', 'Unknown')}
- Setup: {trade.get('setup', 'N/A')}
- Notes: {trade.get('notes', 'N/A')}

"""
        if market_context:
            prompt += f"""Market Context:
- Regime: {market_context.get('regime', 'Unknown')}
- Gamma Flip: {market_context.get('gamma_flip', 'N/A')}
- Call Wall: {market_context.get('call_wall', 'N/A')}
- Put Wall: {market_context.get('put_wall', 'N/A')}
"""

        prompt += """
Provide a concise analysis (2-3 sentences):
1. Was the trade aligned with the GEX regime?
2. What could have been done better?
3. Key takeaway for future trades.
"""

        try:
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt
            )
            if response and response.text:
                return response.text.strip()
            return None
        except Exception as e:
            logger.warning(f"Gemini API error: {e}")
            return None

    async def analyze_regime(self, regime_data: Dict[str, Any]) -> Optional[str]:
        """
        Generate a natural language summary of the current market regime.
        """
        client = self._get_client()
        if not client:
            return None

        prompt = f"""You are an expert options market analyst. Summarize the current market regime:

- GEX Regime: {regime_data.get('gex_regime', 'Unknown')}
- Net GEX: ${regime_data.get('net_gex', 0) / 1e9:.1f}B
- Gamma Flip: {regime_data.get('gamma_flip', 'N/A')}
- Call Wall: {regime_data.get('call_wall', 'N/A')}
- Put Wall: {regime_data.get('put_wall', 'N/A')}
- Max Pain: {regime_data.get('max_pain', 'N/A')}
- Spot Price: ${regime_data.get('spot', 'N/A')}
- IV Rank: {regime_data.get('iv_rank', 'N/A')}%
- VIX: {regime_data.get('vix', 'N/A')}

Provide a concise 2-3 sentence market summary and 1-2 trade ideas appropriate for this regime.
"""

        try:
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt
            )
            if response and response.text:
                return response.text.strip()
            return None
        except Exception as e:
            logger.warning(f"Gemini API error: {e}")
            return None

    async def summarize_day(self, trades: List[Dict], pnl: float, regime: str) -> Optional[str]:
        """
        Generate an end-of-day trading summary.
        """
        client = self._get_client()
        if not client:
            return None

        trade_summaries = []
        for t in trades[:10]:  # Max 10 trades
            pnl_str = ""
            if t.get('exit_price') and t.get('entry_price'):
                entry = float(t['entry_price'])
                exit_p = float(t['exit_price'])
                qty = int(t.get('quantity', 1))
                mult = 1 if t.get('action') == 'buy' else -1
                trade_pnl = (exit_p - entry) * qty * 100 * mult
                pnl_str = f" (${trade_pnl:+.0f})"
            trade_summaries.append(f"- {t.get('action', '')} {t.get('type', '')} {t.get('ticker', '')} {t.get('strike', '')}{pnl_str}")

        prompt = f"""You are an expert trading coach. Here's today's trading summary:

Regime: {regime}
Total P&L: ${pnl:+.0f}

Trades:
{chr(10).join(trade_summaries) if trade_summaries else 'No trades today'}

Provide a brief 2-3 sentence coaching summary:
1. What went well?
2. What to improve tomorrow?
3. Regime watch for tomorrow.
"""

        try:
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt
            )
            if response and response.text:
                return response.text.strip()
            return None
        except Exception as e:
            logger.warning(f"Gemini API error: {e}")
            return None

    async def explain_flow_signal(self, signal: Dict[str, Any]) -> Optional[str]:
        """
        Explain an options flow signal in plain English.
        """
        client = self._get_client()
        if not client:
            return None

        prompt = f"""You are an options flow analyst. Explain this signal:

- Ticker: {signal.get('ticker', 'Unknown')}
- Signal Type: {signal.get('signal_type', 'Unknown')}
- Strike: {signal.get('strike', 'N/A')}
- Expiry: {signal.get('expiry', 'N/A')}
- Option Type: {signal.get('option_type', 'Unknown')}
- Volume: {signal.get('volume', 'N/A')}
- Open Interest: {signal.get('open_interest', 'N/A')}
- Estimated Premium: ${signal.get('premium_usd', 0):,.0f}
- IV: {signal.get('iv', 'N/A')}%
- Spot: ${signal.get('spot_price', 'N/A')}

In 1-2 sentences, explain what this signal might indicate and whether it's bullish or bearish.
"""

        try:
            response = client.models.generate_content(
                model='gemini-1.5-flash',
                contents=prompt
            )
            if response and response.text:
                return response.text.strip()
            return None
        except Exception as e:
            logger.warning(f"Gemini API error: {e}")
            return None
