"""
backend/routes/__init__.py

Route module exports.
"""
from .admin import router as admin_router
from .analytics import router as analytics_router
from .briefing import router as briefing_router
from .live_trading import router as live_trading_router

# ml_training_router removed 2026-05-25 (10 dead routes, see commit history)
from .llm import router as llm_router
from .market_data import router as market_data_router
from .memory import router as memory_router
from .paper_trading import router as paper_trading_router
from .portfolio import router as portfolio_router
from .schwab import router as schwab_router

__all__ = [
    "market_data_router",
    "analytics_router",
    "portfolio_router",
    "paper_trading_router",
    "briefing_router",
    "admin_router",
    "llm_router",
    "schwab_router",
    "live_trading_router",
    "memory_router",
]
