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

# Steal-list top-3 (Dual-GEX #1, Wheel income #3, IV-from-mid #5).
# Mounted by backend/server.py so the routes live on canonical :8000;
# the dev sidecar at :8001 also includes the same router via
# services/steal_three_server.py so :8000 and :8001 stay API-identical.
from .steal_three import router as steal_three_router

__all__ = [
    "market_data_router",
    "analytics_router",
    "portfolio_router",
    "paper_trading_router",
    "briefing_router",
    "admin_router",
    "llm_router",
    "live_trading_router",
    "memory_router",
    "steal_three_router",
]
