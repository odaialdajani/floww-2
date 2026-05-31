"""
backend/tests/services/test_execution_engine.py

Tests for the Almgren-Chriss execution engine, Kyle Lambda estimator,
and Hasbrouck information share.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.execution_engine import (
    AlmgrenChrissExecutor,
    ExecutionEngine,
    HasbrouckInfoShare,
    KyleLambdaEstimator,
    MarketState,
)


class TestAlmgrenChriss:
    """Test Almgren-Chriss optimal execution."""

    def test_kappa_computation(self):
        """κ = sqrt(λσ²/η)."""
        ac = AlmgrenChrissExecutor(risk_aversion=1e-6, temporary_impact_coeff=0.1)
        kappa = ac.compute_kappa(volatility=0.15)
        expected = math.sqrt(1e-6 * 0.15**2 / 0.1)
        assert abs(kappa - expected) < 1e-10

    def test_kappa_zero_vol(self):
        """κ should be 0 when volatility is 0."""
        ac = AlmgrenChrissExecutor()
        assert ac.compute_kappa(volatility=0.0) == 0.0

    def test_optimal_trajectory_sums_to_total(self):
        """Trajectory should sum to total shares."""
        ac = AlmgrenChrissExecutor(risk_aversion=1e-6)
        traj = ac.optimal_trajectory(
            total_shares=1000,
            time_horizon=300.0,
            n_slices=10,
            volatility=0.15 / math.sqrt(252 * 6.5 * 3600),
        )
        assert abs(sum(traj) - 1000.0) < 1.0

    def test_optimal_trajectory_front_loaded(self):
        """With high urgency, more should be traded early."""
        ac = AlmgrenChrissExecutor(risk_aversion=1e-4)  # high urgency
        traj = ac.optimal_trajectory(
            total_shares=1000,
            time_horizon=300.0,
            n_slices=10,
            volatility=0.15 / math.sqrt(252 * 6.5 * 3600),
        )
        # First slice should have more than last
        assert traj[0] > traj[-1]

    def test_optimal_trajectory_low_urgency_monotone(self):
        """With low urgency, trajectory should be monotonically decreasing."""
        ac = AlmgrenChrissExecutor(risk_aversion=1e-10)
        traj = ac.optimal_trajectory(
            total_shares=1000,
            time_horizon=300.0,
            n_slices=10,
            volatility=0.15 / math.sqrt(252 * 6.5 * 3600),
        )
        # Should be monotonically decreasing (trade more early)
        for i in range(len(traj) - 1):
            assert traj[i] >= traj[i + 1], f"Not monotone: {traj[i]} < {traj[i+1]}"

    def test_expected_cost_positive(self):
        """Expected cost should be positive."""
        ac = AlmgrenChrissExecutor()
        cost, perm, timing = ac.expected_cost(
            total_shares=1000,
            time_horizon=300.0,
            volatility=0.15 / math.sqrt(252 * 6.5 * 3600),
            spread=0.1,
        )
        assert cost > 0
        assert perm > 0
        assert timing >= 0


class TestKyleLambda:
    """Test Kyle's Lambda estimation."""

    def test_lambda_zero_with_no_data(self):
        """Lambda should be 0 with insufficient data."""
        kyle = KyleLambdaEstimator()
        assert kyle.estimate_lambda() == 0.0

    def test_lambda_recovers_true_value(self):
        """Lambda should recover the true value from synthetic data."""
        kyle = KyleLambdaEstimator(window=200)
        true_lambda = 0.001
        np.random.seed(42)
        for i in range(200):
            signed_vol = np.random.normal(0, 1000)
            price_change = true_lambda * signed_vol + np.random.normal(0, 0.01)
            kyle.update(price_change, signed_vol)

        estimated = kyle.estimate_lambda()
        # Should be within 50% of true value with 200 samples
        assert abs(estimated - true_lambda) / true_lambda < 0.5

    def test_impact_proportional_to_size(self):
        """Impact should be proportional to order size."""
        kyle = KyleLambdaEstimator()
        kyle._price_changes = [0.01, 0.02, -0.01]
        kyle._signed_volumes = [100, 200, -100]

        impact_100 = kyle.estimate_impact(100)
        impact_200 = kyle.estimate_impact(200)
        assert abs(impact_200 - 2 * impact_100) < 0.001

    def test_impact_non_negative(self):
        """Impact should always be non-negative."""
        kyle = KyleLambdaEstimator()
        kyle._price_changes = [-0.01, -0.02, 0.01]
        kyle._signed_volumes = [100, 200, -100]

        impact = kyle.estimate_impact(100)
        assert impact >= 0


class TestHasbrouckInfoShare:
    """Test Hasbrouck information share."""

    def test_equal_shares_with_uncorrelated_returns(self):
        """With uncorrelated returns, shares should sum to 1 and be non-negative."""
        hasbrouck = HasbrouckInfoShare(n_venues=2)
        np.random.seed(42)
        for _ in range(500):
            r1 = np.random.normal(0, 0.01)
            r2 = np.random.normal(0, 0.01)
            hasbrouck.update([r1, r2])

        shares = hasbrouck.information_shares()
        assert len(shares) == 2
        # Shares should sum to 1
        assert abs(sum(shares) - 1.0) < 0.01
        # Both shares should be non-negative
        assert all(s >= 0 for s in shares)
        # With equal-variance uncorrelated returns, neither should dominate
        assert all(0.1 < s < 0.9 for s in shares)

    def test_dominant_venue_gets_higher_share(self):
        """A venue with more variance should get higher information share."""
        hasbrouck = HasbrouckInfoShare(n_venues=2)
        np.random.seed(42)
        for _ in range(200):
            r1 = np.random.normal(0, 0.02)  # higher vol = more info
            r2 = np.random.normal(0, 0.005)  # lower vol = less info
            hasbrouck.update([r1, r2])

        shares = hasbrouck.information_shares()
        assert shares[0] > shares[1]

    def test_insufficient_data_returns_equal(self):
        """With insufficient data, should return equal shares."""
        hasbrouck = HasbrouckInfoShare(n_venues=3)
        shares = hasbrouck.information_shares()
        assert len(shares) == 3
        for s in shares:
            assert abs(s - 1/3) < 0.01


class TestExecutionEngine:
    """Test the main execution engine."""

    def test_create_order(self):
        engine = ExecutionEngine()
        order = engine.create_order("SPY", "buy", 100)
        assert order.symbol == "SPY"
        assert order.side == "buy"
        assert order.quantity == 100
        assert order.status == "pending"

    def test_plan_execution(self):
        engine = ExecutionEngine()
        order = engine.create_order("SPY", "buy", 100)
        market = MarketState(
            symbol="SPY", bid=500.0, ask=500.1, last=500.05,
            bid_size=1000, ask_size=1000, volume=100000, volatility=0.15,
        )
        slices = engine.plan_execution(order, market)
        assert len(slices) > 0
        total_qty = sum(s["quantity"] for s in slices)
        # Should be close to requested quantity (within 10% for ceiling/rounding)
        assert abs(total_qty - 100) <= 10

    def test_estimate_cost(self):
        engine = ExecutionEngine()
        # Feed some Kyle Lambda data
        for i in range(20):
            engine.kyle_lambda.update(0.01 * i, 1000 * i)
        order = engine.create_order("SPY", "buy", 1000)
        market = MarketState(
            symbol="SPY", bid=500.0, ask=500.1, last=500.05,
            bid_size=1000, ask_size=1000, volume=100000, volatility=0.15,
            spread=0.1,
        )
        estimate = engine.estimate_execution_cost(order, market)
        assert estimate["expected_total_cost"] > 0
        assert estimate["cost_bps"] > 0

    def test_state(self):
        engine = ExecutionEngine()
        state = engine.get_state()
        assert "kyle_lambda" in state
        assert "hasbrouck_shares" in state
