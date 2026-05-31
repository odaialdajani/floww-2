"""
backend/services/risk/__init__.py — Risk management package.

Exports:
  PreTradeRiskGate — New API with check(**kwargs) -> RiskDecision
  RiskDecision — Result with action, reasons, meta
  RiskGate — Original API with before_trade(intent, account) -> RiskResult
  KillSwitch — Daily loss kill switch
  KellySizer — Kelly criterion position sizer with daily lock
  DEFAULT_* — Default threshold constants
"""

from .gate import (
    DEFAULT_DAILY_LOSS_PCT,
    DEFAULT_DATA_STALENESS_SEC,
    DEFAULT_IDEMPOTENCY_WINDOW_SEC,
    DEFAULT_KYLE_LAMBDA_THRESHOLD,
    DEFAULT_MAX_OPEN_POSITIONS,
    DEFAULT_MAX_POSITION_PCT,
    DEFAULT_MIN_ACCOUNT_EQUITY,
    DEFAULT_MIN_CONVICTION,
    DEFAULT_MIN_SENTIMENT_Z,
    PreTradeRiskGate,
    RiskDecision,
    RiskGate,
    RiskResult,
)
from .killswitch import KillSwitch
from .sizer import KellySizer

__all__ = [
    "PreTradeRiskGate",
    "RiskDecision",
    "RiskGate",
    "RiskResult",
    "KillSwitch",
    "KellySizer",
    "DEFAULT_DAILY_LOSS_PCT",
    "DEFAULT_DATA_STALENESS_SEC",
    "DEFAULT_IDEMPOTENCY_WINDOW_SEC",
    "DEFAULT_KYLE_LAMBDA_THRESHOLD",
    "DEFAULT_MAX_OPEN_POSITIONS",
    "DEFAULT_MAX_POSITION_PCT",
    "DEFAULT_MIN_ACCOUNT_EQUITY",
    "DEFAULT_MIN_CONVICTION",
    "DEFAULT_MIN_SENTIMENT_Z",
]
