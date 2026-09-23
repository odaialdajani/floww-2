"""
backend/services/solstice_strategy.py — strategy expression + cost/stress comparison (T20).

Long calls/puts first (bounded premium); debit spreads as a verified separate
phase. Whole-contract sizing from the most restrictive budget; computed zero
never rounds up to one. No automatic risky fallback.
"""

from __future__ import annotations

import math
from decimal import Decimal, ROUND_DOWN
from typing import Any


def size_contracts(premium: float | None, budgets: dict[str, float]) -> dict[str, Any]:
    """Whole-contract sizing. Returns {qty, binding_constraint}."""
    if premium is None or not math.isfinite(premium) or premium <= 0:
        return {"qty": 0, "binding_constraint": "INVALID_PREMIUM"}
    cands: dict[str, int] = {}
    for name in ("premium_budget", "stress_loss_budget", "buying_power", "portfolio_limit"):
        b = budgets.get(name)
        if b is None:
            continue
        try:
            bf = float(b)
        except (TypeError, ValueError):
            continue
        if bf <= 0:
            return {"qty": 0, "binding_constraint": name}
        cands[name] = int(Decimal(str(bf)) // Decimal(str(premium)))
    if not cands:
        return {"qty": 0, "binding_constraint": "NO_BUDGET"}
    binding = min(cands, key=lambda k: cands[k])
    return {"qty": max(0, cands[binding]), "binding_constraint": binding}


def breakeven_win_rate(win_net: float, loss_net: float) -> float | None:
    """Two-outcome illustration L/(W+L); multi-outcome needs full distribution."""
    if win_net <= 0 or loss_net <= 0:
        return None
    return loss_net / (win_net + loss_net)


def stress_candidate(candidate: dict[str, Any], spreads: list[float] | None = None,
                     fees: float = 0.0, slippage: float = 0.0) -> dict[str, Any]:
    """Stress adverse fills / wider quotes / missed fills. No double-counted spread."""
    bid = float(candidate.get("bid", 0) or 0); ask = float(candidate.get("ask", 0) or 0)
    mid = (bid + ask) / 2 if bid > 0 and ask >= bid else None
    base_spread = (ask - bid) if ask >= bid else None
    out = {"osi": candidate.get("osi"), "mid": mid, "base_spread": base_spread,
           "fee": fees, "slippage": slippage, "scenarios": []}
    for extra in (spreads or [0.0, 1.0, 2.0]):
        eff = (base_spread or 0.0) + extra * 0.01 + slippage
        out["scenarios"].append({"extra_ticks_cost": extra, "effective_cost": round(eff + fees, 4)})
    return out


def vertical_payoff(width: float, debit: float, multiplier: float = 100.0) -> dict[str, Any] | None:
    """Plain same-expiry vertical max payoff/loss (compatible deliverables only)."""
    if width <= 0 or debit < 0 or debit >= width:
        return None
    return {"max_profit": (width - debit) * multiplier, "max_loss": debit * multiplier,
            "note": "expiration payoff; pre-expiry exits/assignment still apply"}
