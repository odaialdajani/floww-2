"""
Memory integration for Confluence Decoder using Mem0.

Provides persistent memory for:
- Trading patterns and observations
- GEX regime history
- Strategy performance tracking
- User preferences and corrections
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_memory_client = None


def get_memory_client():
    """Get the memory client singleton."""
    return _memory_client


def remember_trade(ticker: str, trade_data: Dict[str, Any]) -> Optional[str]:
    """Store a trade observation in memory."""
    client = get_memory_client()
    if not client:
        return None

    try:
        message = f"Trade: {ticker} {trade_data.get('type', 'unknown')} at {trade_data.get('entry_price', 0)}"
        result = client.add(
            message,
            user_id="nav",
            metadata={"type": "trade", "ticker": ticker, **trade_data}
        )
        logger.info(f"Stored trade memory: {ticker}")
        return str(result) if result else None
    except Exception as e:
        logger.warning(f"Failed to store trade memory: {e}")
        return None


def remember_gex_observation(ticker: str, observation: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Store a GEX observation in memory."""
    client = get_memory_client()
    if not client:
        return None

    try:
        result = client.add(
            observation,
            user_id="nav",
            metadata={"type": "gex_observation", "ticker": ticker, **(metadata or {})}
        )
        logger.info(f"Stored GEX observation: {ticker}")
        return str(result) if result else None
    except Exception as e:
        logger.warning(f"Failed to store GEX observation: {e}")
        return None


def recall_trading_context(ticker: str, query: str = "") -> List[Dict[str, Any]]:
    """Recall relevant trading memories for a ticker."""
    client = get_memory_client()
    if not client:
        return []

    try:
        search_query = f"{ticker} {query}" if query else ticker
        results = client.search(search_query, user_id="nav", limit=10)
        return results.get("results", [])
    except Exception as e:
        logger.warning(f"Failed to recall memories: {e}")
        return []


def get_trading_summary(ticker: str) -> str:
    """Get a summary of all memories for a ticker."""
    memories = recall_trading_context(ticker)
    if not memories:
        return f"No previous memories for {ticker}."

    summary = f"## Trading Memory for {ticker}\n\n"
    for i, mem in enumerate(memories[:5], 1):
        summary += f"{i}. {mem.get('memory', 'N/A')}\n"

    return summary
