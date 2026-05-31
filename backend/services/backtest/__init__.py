"""
backend/services/backtest/__init__.py

Backtest engine for the Confluence Decoder trading system.
"""

from .engine import BacktestEngine, EngineConfig, run_is_oos_split, run_monte_carlo_bootstrap, run_walk_forward_cv
from .report import BacktestResult, TradeRecord
from .signals import Action, MLEnrichedSignal, Position, RuleBasedSignal, Signal

__all__ = [
    "BacktestEngine",
    "EngineConfig",
    "Action",
    "Position",
    "Signal",
    "RuleBasedSignal",
    "MLEnrichedSignal",
    "BacktestResult",
    "TradeRecord",
    "run_is_oos_split",
    "run_walk_forward_cv",
    "run_monte_carlo_bootstrap",
]
