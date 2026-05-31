"""
backend/services/position_sizing.py

Fractional Kelly Criterion position sizing engine.

Formula: f* = (bp - q) / b
  b = payoff_ratio (avg_win / avg_loss)
  p = win_rate
  q = 1 - p

Fractional Kelly: f = f* * kelly_fraction  (default 0.5 = half-Kelly)
Hard clamp: f clamped to [0.0, 0.25] — never risk more than 25% per trade.

All math is pure; no external dependencies beyond math/std typing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ── Constants ──────────────────────────────────────────────────────────────

MAX_RISK_PCT = 0.25        # hard cap: never allocate > 25% of account
DEFAULT_KELLY_FRACTION = 0.5  # half-Kelly by default


# ── Data class ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class KellyResult:
    """Result of a fractional Kelly position sizing calculation."""
    kelly_fraction: float
    adjusted_fraction: float
    kelly_pct: float
    dollar_allocation: float
    max_contracts: int
    win_rate: float
    payoff_ratio: float
    kelly_multiplier: float
    account_size: float
    capped: bool


def compute_kelly(
    win_rate: float,
    payoff_ratio: float,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
) -> float:
    """Compute the fractional Kelly fraction.

    Args:
        win_rate: Probability of winning, in [0, 1].
        payoff_ratio: Average win / average loss, must be > 0.
        kelly_fraction: Fractional Kelly multiplier (0, 1], default 0.5.

    Returns:
        Raw Kelly fraction (before clamping). May be negative if edge is
        insufficient; caller should clamp to 0.

    Raises:
        ValueError: If inputs are out of valid range.
    """
    # I-8: NaN / Inf guards — must come before range checks since NaN
    # comparisons are always False and would incorrectly pass validation.
    if math.isnan(win_rate) or math.isinf(win_rate):
        return 0.0
    if math.isnan(payoff_ratio) or math.isinf(payoff_ratio):
        return 0.0

    if not 0.0 <= win_rate <= 1.0:
        raise ValueError(f"win_rate must be in [0, 1], got {win_rate}")
    if payoff_ratio <= 0.0:
        raise ValueError(f"payoff_ratio must be > 0, got {payoff_ratio}")
    if not 0.0 < kelly_fraction <= 1.0:
        raise ValueError(f"kelly_fraction must be in (0, 1], got {kelly_fraction}")

    q = 1.0 - win_rate

    raw_kelly = (payoff_ratio * win_rate - q) / payoff_ratio

    # Guard against NaN/Inf from floating-point edge cases
    if math.isnan(raw_kelly) or math.isinf(raw_kelly):
        return 0.0

    return raw_kelly * kelly_fraction


def size_position(
    account_size: float,
    win_rate: float,
    payoff_ratio: float,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
    contract_value: float = 1.0,
) -> KellyResult:
    """Full position sizing: Kelly fraction + dollar allocation + contract count.

    Args:
        account_size: Total account equity, must be > 0.
        win_rate: Probability of winning, in [0, 1].
        payoff_ratio: Average win / average loss, must be > 0.
        kelly_fraction: Fractional Kelly multiplier, default 0.5.
        contract_value: Notional value per contract (for max_contracts calc).

    Returns:
        KellyResult with all sizing fields populated.

    Raises:
        ValueError: If account_size <= 0 or other inputs invalid.
    """
    if account_size <= 0.0:
        raise ValueError(f"account_size must be > 0, got {account_size}")

    raw_kelly = compute_kelly(win_rate, payoff_ratio, kelly_fraction)

    # Floor at 0 — never go negative (no anti-Kelly)
    adjusted = max(0.0, raw_kelly)

    # Hard clamp at MAX_RISK_PCT
    capped = adjusted > MAX_RISK_PCT
    final_pct = min(adjusted, MAX_RISK_PCT)

    dollar_allocation = account_size * final_pct

    # Max whole contracts we can afford
    if contract_value > 0:
        max_contracts = int(dollar_allocation // contract_value)
    else:
        max_contracts = 0

    return KellyResult(
        kelly_fraction=raw_kelly / kelly_fraction if kelly_fraction != 0 else 0.0,
        adjusted_fraction=adjusted,
        kelly_pct=final_pct,
        dollar_allocation=round(dollar_allocation, 2),
        max_contracts=max_contracts,
        win_rate=win_rate,
        payoff_ratio=payoff_ratio,
        kelly_multiplier=kelly_fraction,
        account_size=account_size,
        capped=capped,
    )


def get_kelly_pct(
    win_rate: float,
    payoff_ratio: float,
    kelly_fraction: float = DEFAULT_KELLY_FRACTION,
) -> float:
    """Convenience: return just the final Kelly percentage (clamped)."""
    result = size_position(
        account_size=1.0,  # dummy — we only want the percentage
        win_rate=win_rate,
        payoff_ratio=payoff_ratio,
        kelly_fraction=kelly_fraction,
    )
    return result.kelly_pct
