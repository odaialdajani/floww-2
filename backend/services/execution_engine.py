"""
backend/services/execution_engine.py

Institutional-grade trade execution engine implementing:

1. Almgren-Chriss Optimal Execution (Almgren & Chriss, 2000)
   - Minimizes expected cost + risk penalty for splitting large orders
   - Closed-form optimal trajectory: x(t) = X * sinh(κ(T-t)) / sinh(κT)
   - κ = sqrt(λσ²/η) where λ=risk aversion, σ=vol, η=temporary impact

2. Kyle's Lambda Price Impact (Kyle, 1985)
   - λ = σ_v / (2σ_u) where σ_v=private info vol, σ_u=noise trader vol
   - Price impact: Δp = λ * order_size
   - Used to estimate market impact before execution

3. Hasbrouck's Information Share (Hasbrouck, 1995)
   - Decomposes price discovery across venues
   - Used to route orders to venues with lowest information leakage

References:
- Almgren, R. & Chriss, N. (2000). "Optimal Execution of Portfolio Transactions."
  Journal of Risk, 3, 5-39.
- Kyle, A.S. (1985). "Continuous Auctions and Insider Trading." Econometrica, 53(6), 1315-1335.
- Hasbrouck, J. (1995). "One Security, Many Markets." Journal of Finance, 50(4), 1175-1199.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Order:
    """Represents a single trade order."""
    symbol: str
    side: str  # "buy" or "sell"
    quantity: int
    order_type: str = "market"  # "market", "limit", "twap", "vwap", "almgren_chriss"
    limit_price: float = 0.0
    urgency: float = 0.5  # 0=passive, 1=aggressive
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    filled_quantity: int = 0
    avg_fill_price: float = 0.0
    status: str = "pending"  # pending, partial, filled, cancelled, error
    slices: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def remaining(self) -> int:
        return self.quantity - self.filled_quantity

    @property
    def is_complete(self) -> bool:
        return self.filled_quantity >= self.quantity


@dataclass
class MarketState:
    """Current market conditions for execution decisions."""
    symbol: str
    bid: float
    ask: float
    last: float
    bid_size: int
    ask_size: int
    volume: int
    volatility: float  # annualized
    spread: float = 0.0
    kyle_lambda: float = 0.0

    def __post_init__(self):
        if self.spread == 0.0 and self.ask > 0:
            self.spread = self.ask - self.bid


@dataclass
class ExecutionResult:
    """Result of an execution."""
    order_id: str
    symbol: str
    side: str
    requested_qty: int
    filled_qty: int
    avg_price: float
    total_cost: float
    implementation_shortfall: float  # vs arrival price
    market_impact: float  # estimated Kyle Lambda impact
    timing_cost: float  # from Almgren-Chriss risk term
    slippage_bps: float
    slices_executed: int
    duration_ms: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Almgren-Chriss Optimal Execution
# ---------------------------------------------------------------------------

class AlmgrenChrissExecutor:
    """Implements the Almgren-Chriss optimal execution framework.

    Given a large order of X shares to execute over time horizon T,
    finds the optimal trading trajectory that minimizes:
        E[cost] + λ * Var[cost]

    The optimal trajectory is:
        x(t) = X * sinh(κ(T-t)) / sinh(κT)

    where κ = sqrt(λσ²/η)
    """

    def __init__(
        self,
        risk_aversion: float = 1e-6,
        temporary_impact_coeff: float = 0.1,
        permanent_impact_coeff: float = 0.05,
    ):
        self.risk_aversion = risk_aversion
        self.eta = temporary_impact_coeff  # temporary impact coefficient
        self.gamma = permanent_impact_coeff  # permanent impact coefficient

    def compute_kappa(
        self,
        volatility: float,
        risk_aversion: Optional[float] = None,
    ) -> float:
        """Compute κ = sqrt(λσ²/η).

        Args:
            volatility: Annualized volatility σ
            risk_aversion: Risk aversion parameter λ (default: self.risk_aversion)

        Returns:
            κ (kappa) — the urgency parameter
        """
        lam = risk_aversion or self.risk_aversion
        if self.eta < 1e-12 or volatility < 1e-12:
            return 0.0
        return math.sqrt(lam * volatility ** 2 / self.eta)

    def optimal_trajectory(
        self,
        total_shares: int,
        time_horizon: float,  # in seconds
        n_slices: int,
        volatility: float,
        risk_aversion: Optional[float] = None,
    ) -> List[float]:
        """Compute the optimal trading trajectory.

        Returns list of shares to trade at each time step.
        """
        kappa = self.compute_kappa(volatility, risk_aversion)
        if kappa < 1e-12 or time_horizon < 1e-12:
            # No urgency: trade evenly
            return [total_shares / n_slices] * n_slices

        T = time_horizon
        kappa_T = kappa * T
        if kappa_T > 50:  # sinh overflow protection
            # Very urgent: trade everything immediately
            return [total_shares] + [0.0] * (n_slices - 1)

        sinh_kappa_T = math.sinh(kappa_T)
        trajectory = []
        for i in range(n_slices):
            t = i * T / n_slices
            remaining = T - t
            x = total_shares * math.sinh(kappa * remaining) / sinh_kappa_T
            trajectory.append(max(x, 0.0))

        # Normalize to ensure total = total_shares
        total = sum(trajectory)
        if total > 0:
            trajectory = [x * total_shares / total for x in trajectory]

        return trajectory

    def expected_cost(
        self,
        total_shares: int,
        time_horizon: float,
        volatility: float,
        spread: float,
        risk_aversion: Optional[float] = None,
    ) -> Tuple[float, float, float]:
        """Compute expected execution cost decomposition.

        Returns: (expected_cost, permanent_impact_cost, timing_risk_cost)
        """
        kappa = self.compute_kappa(volatility, risk_aversion)
        T = time_horizon
        X = total_shares
        sigma = volatility

        if kappa < 1e-12:
            # Linear trajectory
            perm_impact = self.gamma * X ** 2 / 2
            timing_risk = 0.0
        else:
            kappa_T = kappa * T
            if kappa_T > 50:
                perm_impact = self.gamma * X ** 2 / 2
                timing_risk = 0.0
            else:
                coth = 1.0 / math.tanh(kappa_T)
                perm_impact = self.gamma * X ** 2 / 2
                timing_risk = (self.risk_aversion * sigma ** 2 * X ** 2 / (2 * kappa)) * (coth - 1.0 / kappa_T)

        spread_cost = spread * X / 2
        expected_cost = perm_impact + timing_risk + spread_cost

        return expected_cost, perm_impact, timing_risk


# ---------------------------------------------------------------------------
# Kyle's Lambda Price Impact Model
# ---------------------------------------------------------------------------

class KyleLambdaEstimator:
    """Estimates Kyle's Lambda (price impact coefficient) from market data.

    Kyle's Lambda: λ = σ_v / (2 * σ_u)
    where σ_v = private information volatility, σ_u = noise trader volatility

    In practice, estimated via OLS regression:
        Δp_t = λ * (buy_volume - sell_volume) + ε_t
    """

    def __init__(self, window: int = 50):
        self.window = window
        self._price_changes: list = []
        self._signed_volumes: list = []

    def update(self, price_change: float, signed_volume: float):
        """Add an observation."""
        self._price_changes.append(price_change)
        self._signed_volumes.append(signed_volume)
        # Keep rolling window
        if len(self._price_changes) > self.window:
            self._price_changes.pop(0)
            self._signed_volumes.pop(0)

    def estimate_lambda(self) -> float:
        """Estimate Kyle's Lambda via OLS: Δp = λ * signed_volume + ε."""
        if len(self._price_changes) < 5:
            return 0.0
        y = np.array(self._price_changes, dtype=np.float64)
        x = np.array(self._signed_volumes, dtype=np.float64)
        var_x = np.var(x)
        if var_x < 1e-15:
            return 0.0
        lambda_val = float(np.cov(y, x)[0, 1] / var_x)
        return max(lambda_val, 0.0)  # Lambda should be non-negative

    def estimate_impact(self, order_size: float) -> float:
        """Estimate price impact for a given order size: Δp = λ * Q."""
        lam = self.estimate_lambda()
        return lam * order_size

    def get_state(self) -> Dict[str, Any]:
        return {
            "lambda": self.estimate_lambda(),
            "n_obs": len(self._price_changes),
            "window": self.window,
        }


# ---------------------------------------------------------------------------
# Hasbrouck Information Share
# ---------------------------------------------------------------------------

class HasbrouckInfoShare:
    """Estimates Hasbrouck's Information Share for multi-venue price discovery.

    Information Share (IS) measures the fraction of price discovery
    attributable to a particular venue/market.

    IS_i = (ψ_i * σ_i)² / Σ(ψ_j * σ_j)²

    where ψ_i is the contribution of venue i to the common efficient price.
    """

    def __init__(self, n_venues: int = 2):
        self.n_venues = n_venues
        self._returns: List[List[float]] = [[] for _ in range(n_venues)]

    def update(self, returns: List[float]):
        """Add a vector of returns from each venue."""
        for i, r in enumerate(returns):
            if i < self.n_venues:
                self._returns[i].append(r)
                if len(self._returns[i]) > 200:
                    self._returns[i] = self._returns[i][-200:]

    def information_shares(self) -> List[float]:
        """Compute information shares for each venue."""
        min_len = min(len(r) for r in self._returns)
        if min_len < 10:
            return [1.0 / self.n_venues] * self.n_venues

        data = np.array([r[-min_len:] for r in self._returns], dtype=np.float64)
        # Covariance matrix of returns
        cov = np.cov(data)
        try:
            eigenvalues, eigenvectors = np.linalg.eigh(cov)
            # The first principal component explains the most variance
            # Information share is proportional to the squared loading
            idx = np.argsort(eigenvalues)[::-1]
            pc1 = eigenvectors[:, idx[0]]
            shares = (pc1 ** 2) / np.sum(pc1 ** 2)
            return [float(s) for s in shares]
        except Exception:
            return [1.0 / self.n_venues] * self.n_venues


# ---------------------------------------------------------------------------
# Main Execution Engine
# ---------------------------------------------------------------------------

class ExecutionEngine:
    """Main execution engine combining Almgren-Chriss, Kyle Lambda, and Hasbrouck."""

    def __init__(
        self,
        risk_aversion: float = 1e-6,
        default_urgency: float = 0.5,
        max_participation_rate: float = 0.05,  # max 5% of volume per slice
    ):
        self.almgren_chriss = AlmgrenChrissExecutor(risk_aversion=risk_aversion)
        self.kyle_lambda = KyleLambdaEstimator()
        self.hasbrouck = HasbrouckInfoShare()
        self.default_urgency = default_urgency
        self.max_participation_rate = max_participation_rate
        self._order_counter = 0

    def create_order(
        self,
        symbol: str,
        side: str,
        quantity: int,
        order_type: str = "almgren_chriss",
        urgency: Optional[float] = None,
        limit_price: float = 0.0,
    ) -> Order:
        """Create a new order."""
        self._order_counter += 1
        return Order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            urgency=urgency or self.default_urgency,
            limit_price=limit_price,
            metadata={"order_id": f"ORD-{self._order_counter:06d}"},
        )

    def plan_execution(
        self,
        order: Order,
        market: MarketState,
        time_horizon_seconds: float = 300.0,
    ) -> List[Dict[str, Any]]:
        """Plan the execution slices for an order.

        Uses Almgren-Chriss to determine optimal trajectory,
        then adjusts for Kyle Lambda impact and participation rate limits.

        Returns list of slice dicts with: time_offset_s, quantity, expected_price
        """
        urgency = order.urgency
        n_slices = max(1, min(20, int(time_horizon_seconds / 30)))  # 30s min per slice

        # Almgren-Chriss optimal trajectory
        trajectory = self.almgren_chriss.optimal_trajectory(
            total_shares=order.quantity,
            time_horizon=time_horizon_seconds,
            n_slices=n_slices,
            volatility=market.volatility / math.sqrt(252 * 6.5 * 3600),  # per-second vol
            risk_aversion=self.almgren_chriss.risk_aversion * (1 + urgency * 10),
        )

        # Kyle Lambda impact estimate
        kyle_impact_per_share = self.kyle_lambda.estimate_impact(1.0)

        slices = []
        _cumulative_cost = 0.0
        for i, shares in enumerate(trajectory):
            if shares < 0.5:
                continue
            qty = int(math.ceil(shares))
            if qty <= 0:
                continue

            # Participation rate limit
            max_qty = int(market.volume * self.max_participation_rate / n_slices)
            if max_qty > 0 and qty > max_qty:
                qty = max_qty

            # Price impact from Kyle Lambda
            impact = kyle_impact_per_share * qty
            if order.side == "buy":
                expected_price = market.ask + impact
            else:
                expected_price = market.bid - impact

            slice_info = {
                "slice_index": i,
                "time_offset_s": i * time_horizon_seconds / n_slices,
                "quantity": qty,
                "expected_price": round(expected_price, 4),
                "expected_impact": round(impact, 4),
                "participation_rate": round(qty / max(market.volume / n_slices, 1), 4),
            }
            slices.append(slice_info)

        return slices

    def estimate_execution_cost(
        self,
        order: Order,
        market: MarketState,
        time_horizon_seconds: float = 300.0,
    ) -> Dict[str, Any]:
        """Estimate the total execution cost before trading.

        Returns dict with cost breakdown.
        """
        expected, perm_impact, timing_risk = self.almgren_chriss.expected_cost(
            total_shares=order.quantity,
            time_horizon=time_horizon_seconds,
            volatility=market.volatility / math.sqrt(252 * 6.5 * 3600),
            spread=market.spread,
        )

        kyle_impact = self.kyle_lambda.estimate_impact(order.quantity)
        arrival_price = market.ask if order.side == "buy" else market.bid
        implementation_shortfall = kyle_impact * order.quantity

        return {
            "symbol": order.symbol,
            "side": order.side,
            "quantity": order.quantity,
            "arrival_price": arrival_price,
            "expected_total_cost": round(expected, 2),
            "permanent_impact_cost": round(perm_impact, 2),
            "timing_risk_cost": round(timing_risk, 2),
            "kyle_lambda_impact": round(kyle_impact, 6),
            "implementation_shortfall": round(implementation_shortfall, 2),
            "spread_cost": round(market.spread * order.quantity / 2, 2),
            "total_estimated_cost": round(expected + implementation_shortfall, 2),
            "cost_bps": round((expected + implementation_shortfall) / (arrival_price * order.quantity) * 10000, 2) if arrival_price > 0 else 0,
        }

    def get_state(self) -> Dict[str, Any]:
        return {
            "kyle_lambda": self.kyle_lambda.get_state(),
            "hasbrouck_shares": self.hasbrouck.information_shares(),
            "risk_aversion": self.almgren_chriss.risk_aversion,
            "max_participation_rate": self.max_participation_rate,
        }
