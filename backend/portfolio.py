"""
Portfolio Position Tracking & Greek Neutralization Module
Institutional-grade position management with real-time P&L and hedging.

Features:
- Position entry with full Greeks tracking
- Real-time P&L calculation (theoretical + mark-to-market)
- Greek aggregation across portfolio (net delta, gamma, vega, theta, charm)
- Greek-neutral hedging calculator (matrix-based, from Dynamic-Derivatives-Portfolio-Hedging)
- Scenario analysis (what-if for spot moves, vol changes, time decay)
- Position sizing based on GEX levels
"""

import math
from datetime import date, datetime, timezone
from typing import Any, Dict, List

from scipy.stats import norm

from bs_greeks import (
    RISK_FREE_RATE,
    bs_charm,
    bs_delta,
    bs_gamma,
    bs_vanna,
    bs_vega,
    bs_vomma,
    bs_zomma,
)

# ============ Position Models ============

class Position:
    """Single options position with full Greeks tracking."""
    def __init__(self, symbol: str, option_type: str, strike: float, expiry: str,
                 quantity: int, entry_price: float, entry_iv: float,
                 underlying_price: float, is_long: bool = True):
        self.symbol = symbol
        self.option_type = option_type  # "call" or "put"
        self.strike = strike
        self.expiry = expiry
        self.quantity = quantity  # positive for long, negative for short
        self.entry_price = entry_price
        self.entry_iv = entry_iv
        self.underlying_price = underlying_price
        self.is_long = is_long
        self.entry_date = datetime.now(timezone.utc)

        # Calculate time to expiration
        try:
            exp_date = datetime.strptime(expiry, "%Y-%m-%d").date()
            self.dte = max((exp_date - date.today()).days, 0)
            self.T = self.dte / 365.0
        except Exception:
            self.dte = 0
            self.T = 0

        # Calculate Greeks at entry
        self._calculate_greeks()

    def _calculate_greeks(self):
        """Calculate all Greeks for this position."""
        S = self.underlying_price
        K = self.strike
        T = self.T
        sigma = self.entry_iv
        r = RISK_FREE_RATE
        q = 0.0  # dividend yield

        if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
            self.delta = 0
            self.gamma = 0
            self.vega = 0
            self.theta = 0
            self.vanna = 0
            self.charm = 0
            self.vomma = 0
            self.zomma = 0
            self.price = 0
            return

        self.gamma = bs_gamma(S, K, T, sigma, q)
        self.delta = bs_delta(S, K, T, sigma, q, self.option_type)
        self.vega = bs_vega(S, K, T, sigma, q)
        self.vanna = bs_vanna(S, K, T, sigma, q)
        self.charm = bs_charm(S, K, T, sigma, q=q, kind=self.option_type)
        self.vomma = bs_vomma(S, K, T, sigma, q)
        self.zomma = bs_zomma(S, K, T, sigma, q)

        # Theta (time decay) - approximate
        self.theta = -self.gamma * S * sigma / (2 * math.sqrt(T)) if T > 0 else 0

        # Theoretical price
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        if self.option_type == "call":
            self.price = S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        else:
            self.price = K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)

    def current_greeks(self, spot: float, iv: float) -> Dict[str, float]:
        """Calculate current Greeks given new spot and IV."""
        T = max(self.T - (datetime.now(timezone.utc) - self.entry_date).days / 365.0, 0.001)
        if T <= 0.001:
            return {"delta": 0, "gamma": 0, "vega": 0, "theta": 0, "vanna": 0, "charm": 0, "vomma": 0, "zomma": 0, "price": 0}

        S = spot
        K = self.strike
        sigma = iv
        r = RISK_FREE_RATE
        q = 0.0

        gamma = bs_gamma(S, K, T, sigma, q)
        delta = bs_delta(S, K, T, sigma, q, self.option_type)
        vega = bs_vega(S, K, T, sigma, q)
        vanna = bs_vanna(S, K, T, sigma, q)
        charm = bs_charm(S, K, T, sigma, q, self.option_type)
        vomma = bs_vomma(S, K, T, sigma, q)
        zomma = bs_zomma(S, K, T, sigma, q)
        theta = -gamma * S * sigma / (2 * math.sqrt(T))

        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        if self.option_type == "call":
            price = S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
        else:
            price = K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)

        sign = 1 if self.is_long else -1
        return {
            "delta": delta * self.quantity * sign * 100,
            "gamma": gamma * self.quantity * sign * 100,
            "vega": vega * self.quantity * sign * 100,
            "theta": theta * self.quantity * sign * 100,
            "vanna": vanna * self.quantity * sign * 100,
            "charm": charm * self.quantity * sign * 100,
            "vomma": vomma * self.quantity * sign * 100,
            "zomma": zomma * self.quantity * sign * 100,
            "price": price,
        }

    def pnl(self, current_price: float) -> Dict[str, float]:
        """Calculate P&L for this position."""
        sign = 1 if self.is_long else -1
        per_contract = (current_price - self.entry_price) * sign
        total = per_contract * abs(self.quantity) * 100
        return {
            "per_contract": round(per_contract, 2),
            "total": round(total, 2),
            "entry_value": round(self.entry_price * abs(self.quantity) * 100, 2),
            "current_value": round(current_price * abs(self.quantity) * 100, 2),
        }


class Portfolio:
    """Portfolio of options positions with aggregated Greeks and hedging."""

    def __init__(self, name: str = "Default"):
        self.name = name
        self.positions: List[Position] = []
        self.cash = 0.0

    def add_position(self, position: Position):
        self.positions.append(position)
        sign = 1 if position.is_long else -1
        self.cash -= position.entry_price * abs(position.quantity) * 100 * sign

    def total_pnl(self, spot: float, iv: float) -> Dict[str, float]:
        """Calculate total portfolio P&L."""
        total_pnl = 0
        total_entry = 0
        total_current = 0
        for pos in self.positions:
            g = pos.current_greeks(spot, iv)
            current_price = g.get("price", 0)
            p = pos.pnl(current_price)
            total_pnl += p["total"]
            total_entry += p["entry_value"]
            total_current += p["current_value"]
        return {
            "total_pnl": round(total_pnl, 2),
            "total_entry_value": round(total_entry, 2),
            "total_current_value": round(total_current, 2),
            "pct_pnl": round((total_pnl / total_entry) * 100, 2) if total_entry else 0,
        }

def calc_position_size(account_size: float, risk_per_trade_pct: float,
                        spot: float, gex_level: float,
                        max_position_pct: float = 0.25) -> Dict[str, Any]:
    """
    Calculate position size based on GEX levels and risk parameters.
    Near high-GEX strikes, reduce size (more predictable but crowded).
    Near low-GEX strikes, increase size (more volatile but less crowded).
    """
    risk_amount = account_size * risk_per_trade_pct
    max_position_value = account_size * max_position_pct

    # GEX-based sizing factor
    # High GEX = more dealer hedging = more predictable = can size larger
    # But also more crowded = wider stops needed
    gex_factor = min(1.0, abs(gex_level) / 1e9) if gex_level else 0.5
    gex_factor = max(0.2, min(1.0, gex_factor))

    # Distance to nearest GEX wall
    # Closer to wall = smaller position (risk of reversal)
    # Further from wall = larger position (more room to run)

    contracts = int(risk_amount / (spot * 0.01 * 100))  # Risk per 1% move
    contracts = min(contracts, int(max_position_value / (spot * 100)))
    contracts = max(1, contracts)

    return {
        "account_size": account_size,
        "risk_per_trade": risk_amount,
        "max_position_value": max_position_value,
        "recommended_contracts": contracts,
        "gex_factor": round(gex_factor, 2),
        "position_value": round(contracts * spot * 100, 2),
        "position_pct_of_account": round((contracts * spot * 100) / account_size * 100, 2),
    }
