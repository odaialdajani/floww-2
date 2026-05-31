"""
Tests for Kelly Criterion position sizing engine (services/position_sizing.py)
and REST API route (routes/position_sizing_api.py).

Covers:
  - Formula correctness: f* = (bp - q) / b
  - Fractional Kelly scaling
  - Hard clamp at 25%
  - Edge cases: win_rate=0, win_rate=1, payoff=1, zero/negative inputs
  - NaN/Inf guards (I-8)
  - API validation and response shape
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

from services.position_sizing import (
    MAX_RISK_PCT,
    compute_kelly,
    get_kelly_pct,
    size_position,
)

# ── 1. Formula correctness ────────────────────────────────────────────────

class TestKellyFormula:
    """Validate the Kelly formula f* = (bp - q) / b."""

    def test_basic_kelly(self):
        """win_rate=0.55, payoff=1.8 → f* = (1.8*0.55 - 0.45) / 1.8 ≈ 0.2944."""
        p, b = 0.55, 1.8
        expected_raw = (b * p - (1 - p)) / b  # ≈ 0.29444...
        result = compute_kelly(p, b, kelly_fraction=1.0)
        assert abs(result - expected_raw) < 1e-10

    def test_half_kelly_scaling(self):
        """Half-Kelly should halve the raw fraction."""
        full = compute_kelly(0.6, 2.0, kelly_fraction=1.0)
        half = compute_kelly(0.6, 2.0, kelly_fraction=0.5)
        assert abs(half - full * 0.5) < 1e-10

    def test_fair_game_zero_kelly(self):
        """win_rate=0.5, payoff=1 → edge=0, Kelly=0."""
        result = compute_kelly(0.5, 1.0)
        assert abs(result) < 1e-10

    def test_negative_edge(self):
        """win_rate=0.4, payoff=1 → negative Kelly (no edge)."""
        result = compute_kelly(0.4, 1.0, kelly_fraction=1.0)
        assert result < 0

    def test_perfect_win_rate(self):
        """win_rate=1.0 → Kelly = 1.0 (with full Kelly)."""
        result = compute_kelly(1.0, 2.0, kelly_fraction=1.0)
        assert abs(result - 1.0) < 1e-10

    def test_zero_win_rate(self):
        """win_rate=0.0 → Kelly = -1/b (negative, should be floored to 0)."""
        result = compute_kelly(0.0, 2.0, kelly_fraction=1.0)
        assert result < 0


# ── 2. Position sizing & risk caps ────────────────────────────────────────

class TestPositionSizing:

    def test_dollar_allocation(self):
        """$100K account, 10% Kelly → $10K allocation."""
        result = size_position(
            account_size=100_000,
            win_rate=0.55,
            payoff_ratio=1.8,
            kelly_fraction=0.5,
        )
        # raw ≈ 0.2944, half ≈ 0.1472, dollar ≈ $14,722
        assert result.dollar_allocation > 0
        assert result.dollar_allocation <= 100_000 * MAX_RISK_PCT

    def test_hard_cap_25pct(self):
        """Even with win_rate=1.0, allocation must not exceed 25%."""
        result = size_position(
            account_size=100_000,
            win_rate=1.0,
            payoff_ratio=10.0,
            kelly_fraction=1.0,
        )
        assert result.kelly_pct <= MAX_RISK_PCT
        assert result.dollar_allocation <= 100_000 * MAX_RISK_PCT
        assert result.capped is True

    def test_max_contracts(self):
        """With $100K account and $10K contract value."""
        result = size_position(
            account_size=100_000,
            win_rate=0.55,
            payoff_ratio=1.8,
            kelly_fraction=0.5,
            contract_value=10_000,
        )
        assert result.max_contracts >= 0
        assert isinstance(result.max_contracts, int)

    def test_zero_allocation_for_no_edge(self):
        """Fair game (p=0.5, b=1) → zero allocation."""
        result = size_position(
            account_size=50_000,
            win_rate=0.5,
            payoff_ratio=1.0,
        )
        assert result.kelly_pct == 0.0
        assert result.dollar_allocation == 0.0


# ── 3. Input validation ───────────────────────────────────────────────────

class TestInputValidation:

    def test_invalid_win_rate_raises(self):
        with pytest.raises(ValueError, match="win_rate"):
            compute_kelly(1.5, 2.0)

    def test_invalid_payoff_raises(self):
        with pytest.raises(ValueError, match="payoff_ratio"):
            compute_kelly(0.5, 0.0)

    def test_invalid_kelly_fraction_raises(self):
        with pytest.raises(ValueError, match="kelly_fraction"):
            compute_kelly(0.5, 2.0, kelly_fraction=0.0)

    def test_invalid_account_size_raises(self):
        with pytest.raises(ValueError, match="account_size"):
            size_position(account_size=0, win_rate=0.5, payoff_ratio=1.0)

    def test_negative_win_rate_raises(self):
        with pytest.raises(ValueError, match="win_rate"):
            compute_kelly(-0.1, 2.0)


# ── 4. NaN / Inf guards (I-8) ─────────────────────────────────────────────

class TestNaNInfGuards:

    def test_nan_win_rate_returns_zero(self):
        result = compute_kelly(float("nan"), 2.0)
        assert result == 0.0

    def test_nan_payoff_returns_zero(self):
        result = compute_kelly(0.5, float("nan"))
        assert result == 0.0

    def test_inf_payoff_returns_zero(self):
        result = compute_kelly(0.5, float("inf"))
        assert result == 0.0


# ── 5. Convenience function ───────────────────────────────────────────────

class TestGetKellyPct:

    def test_returns_float(self):
        result = get_kelly_pct(0.55, 1.8)
        assert isinstance(result, float)

    def test_clamped_to_max(self):
        result = get_kelly_pct(1.0, 10.0, kelly_fraction=1.0)
        assert result <= MAX_RISK_PCT


# ── 6. REST API endpoint ──────────────────────────────────────────────────

class TestPositionSizingAPI:

    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from routes.position_sizing_api import router
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_api_returns_valid_json(self, client):
        resp = client.get(
            "/api/position-sizing",
            params={"account": 100000, "win_rate": 0.55, "payoff": 1.8},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "kelly_fraction" in data
        assert "dollar_allocation" in data
        assert "max_contracts" in data
        assert "capped" in data

    def test_api_kelly_value(self, client):
        resp = client.get(
            "/api/position-sizing",
            params={"account": 100000, "win_rate": 0.55, "payoff": 1.8},
        )
        data = resp.json()
        # raw ≈ 0.2944, half ≈ 0.1472
        assert data["kelly_pct"] > 0.14
        assert data["kelly_pct"] <= 0.15

    def test_api_fair_game(self, client):
        resp = client.get(
            "/api/position-sizing",
            params={"account": 100000, "win_rate": 0.5, "payoff": 1.0},
        )
        data = resp.json()
        assert data["kelly_pct"] == 0.0
        assert data["dollar_allocation"] == 0.0

    def test_api_capped(self, client):
        resp = client.get(
            "/api/position-sizing",
            params={"account": 100000, "win_rate": 1.0, "payoff": 10.0},
        )
        data = resp.json()
        assert data["kelly_pct"] <= MAX_RISK_PCT
        assert data["capped"] is True

    def test_api_invalid_win_rate(self, client):
        resp = client.get(
            "/api/position-sizing",
            params={"account": 100000, "win_rate": 1.5, "payoff": 1.8},
        )
        assert resp.status_code == 422

    def test_api_invalid_account(self, client):
        resp = client.get(
            "/api/position-sizing",
            params={"account": 0, "win_rate": 0.55, "payoff": 1.8},
        )
        assert resp.status_code == 422

    def test_api_invalid_payoff(self, client):
        resp = client.get(
            "/api/position-sizing",
            params={"account": 100000, "win_rate": 0.55, "payoff": -1.0},
        )
        assert resp.status_code == 422
