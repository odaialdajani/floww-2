"""
backend/tests/services/test_risk_gate.py

Unit tests for the PreTradeRiskGate.

All tests are self-contained (no external fixtures) and use only stdlib + numpy.
Total suite runtime target: < 1 second.
"""

from __future__ import annotations

import os
import tempfile
import time

from services.risk.gate import (
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
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_gate(**kwargs) -> PreTradeRiskGate:
    """Create a PreTradeRiskGate with optional overrides."""
    return PreTradeRiskGate(**kwargs)


def _make_params(**overrides) -> dict:
    """Return a dict of default passing parameters, with optional overrides."""
    base = dict(
        signal_id="test_signal_001",
        ticker="SPX",
        conviction=0.85,
        position_size=50.0,
        equity=10000.0,
        sentiment_z=-1.0,
        kyle_lambda=1e-7,
        open_positions=2,
        snapshot_age_sec=5.0,
        daily_pnl_pct=-1.0,
        kill_switch_active=False,
    )
    base.update(overrides)
    return base


# ── RiskDecision tests ───────────────────────────────────────────────────────

class TestRiskDecision:
    def test_passed_property_true(self):
        d = RiskDecision(action="PASS")
        assert d.passed is True

    def test_passed_property_false(self):
        d = RiskDecision(action="REJECT", reasons=["kill_switch_active"])
        assert d.passed is False

    def test_default_reasons_empty(self):
        d = RiskDecision(action="PASS")
        assert d.reasons == []

    def test_default_meta_empty(self):
        d = RiskDecision(action="PASS")
        assert d.meta == {}

    def test_reasons_preserved(self):
        reasons = ["daily_loss_band", "stale_market_data"]
        d = RiskDecision(action="REJECT", reasons=reasons)
        assert d.reasons == reasons


# ── Constructor defaults ─────────────────────────────────────────────────────

class TestConstructorDefaults:
    def test_default_thresholds(self):
        gate = _make_gate()
        assert gate.kyle_lambda_threshold == DEFAULT_KYLE_LAMBDA_THRESHOLD
        assert gate.min_conviction == DEFAULT_MIN_CONVICTION
        assert gate.min_account_equity == DEFAULT_MIN_ACCOUNT_EQUITY
        assert gate.max_position_pct == DEFAULT_MAX_POSITION_PCT
        assert gate.max_open_positions == DEFAULT_MAX_OPEN_POSITIONS
        assert gate.min_sentiment_z == DEFAULT_MIN_SENTIMENT_Z
        assert gate.daily_loss_pct == DEFAULT_DAILY_LOSS_PCT
        assert gate.data_staleness_sec == DEFAULT_DATA_STALENESS_SEC
        assert gate.idempotency_window_sec == DEFAULT_IDEMPOTENCY_WINDOW_SEC

    def test_custom_thresholds(self):
        gate = _make_gate(
            kyle_lambda_threshold=5e-7,
            min_conviction=0.5,
            min_account_equity=10000.0,
            max_position_pct=0.02,
            max_open_positions=10,
            min_sentiment_z=-1.5,
            daily_loss_pct=5.0,
            data_staleness_sec=60,
            idempotency_window_sec=600,
        )
        assert gate.kyle_lambda_threshold == 5e-7
        assert gate.min_conviction == 0.5
        assert gate.min_account_equity == 10000.0
        assert gate.max_position_pct == 0.02
        assert gate.max_open_positions == 10
        assert gate.min_sentiment_z == -1.5
        assert gate.daily_loss_pct == 5.0
        assert gate.data_staleness_sec == 60
        assert gate.idempotency_window_sec == 600


# ── Full pass case ───────────────────────────────────────────────────────────

class TestFullPass:
    def test_all_checks_pass(self):
        gate = _make_gate()
        decision = gate.check(**_make_params())
        assert decision.passed is True
        assert decision.action == "PASS"
        assert decision.reasons == []

    def test_meta_contains_input_values(self):
        gate = _make_gate()
        params = _make_params()
        decision = gate.check(**params)
        assert decision.meta["signal_id"] == params["signal_id"]
        assert decision.meta["ticker"] == params["ticker"]
        assert decision.meta["conviction"] == params["conviction"]


# ── Kill switch ──────────────────────────────────────────────────────────────

class TestKillSwitch:
    def test_kill_switch_active_flag(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(kill_switch_active=True))
        assert decision.passed is False
        assert "kill_switch_active" in decision.reasons

    def test_kill_switch_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            kill_path = f.name
        try:
            gate = _make_gate(kill_switch_path=kill_path)
            decision = gate.check(**_make_params())
            assert decision.passed is False
            assert "kill_switch_active" in decision.reasons
        finally:
            os.unlink(kill_path)

    def test_no_kill_switch_file_passes(self):
        gate = _make_gate(kill_switch_path="/tmp/nonexistent_kill_switch_12345")
        decision = gate.check(**_make_params())
        assert decision.passed is True

    def test_kill_switch_short_circuits(self):
        """Kill switch should return immediately without collecting other reasons."""
        gate = _make_gate()
        decision = gate.check(
            **_make_params(
                kill_switch_active=True,
                conviction=0.0,  # would also fail
                equity=0.0,  # would also fail
            )
        )
        assert decision.reasons == ["kill_switch_active"]


# ── Daily loss band ──────────────────────────────────────────────────────────

class TestDailyLossBand:
    def test_within_band(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(daily_pnl_pct=-1.0))
        assert decision.passed is True

    def test_at_boundary(self):
        """Exactly at -3% should reject (strict inequality)."""
        gate = _make_gate()
        decision = gate.check(**_make_params(daily_pnl_pct=-3.0))
        assert decision.passed is False
        assert "daily_loss_band" in decision.reasons

    def test_beyond_band(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(daily_pnl_pct=-5.0))
        assert decision.passed is False
        assert "daily_loss_band" in decision.reasons

    def test_just_inside_boundary(self):
        """-2.99% should pass."""
        gate = _make_gate()
        decision = gate.check(**_make_params(daily_pnl_pct=-2.99))
        assert decision.passed is True

    def test_positive_pnl(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(daily_pnl_pct=2.0))
        assert decision.passed is True


# ── Max open positions ───────────────────────────────────────────────────────

class TestMaxOpenPositions:
    def test_below_cap(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(open_positions=4))
        assert decision.passed is True

    def test_at_cap(self):
        """Exactly at max_open_positions should reject."""
        gate = _make_gate()
        decision = gate.check(**_make_params(open_positions=5))
        assert decision.passed is False
        assert "max_open_positions" in decision.reasons

    def test_above_cap(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(open_positions=8))
        assert decision.passed is False
        assert "max_open_positions" in decision.reasons

    def test_zero_positions(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(open_positions=0))
        assert decision.passed is True


# ── Position size ────────────────────────────────────────────────────────────

class TestPositionSize:
    def test_within_limit(self):
        gate = _make_gate()
        # 1% of 10000 = 100, so 50 is fine
        decision = gate.check(**_make_params(position_size=50.0, equity=10000.0))
        assert decision.passed is True

    def test_at_limit(self):
        """Exactly at the limit should pass (<=)."""
        gate = _make_gate()
        decision = gate.check(**_make_params(position_size=100.0, equity=10000.0))
        assert decision.passed is True

    def test_exceeds_limit(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(position_size=101.0, equity=10000.0))
        assert decision.passed is False
        assert "position_size_exceeded" in decision.reasons

    def test_zero_position_size(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(position_size=0.0))
        assert decision.passed is True


# ── Sentiment ────────────────────────────────────────────────────────────────

class TestSentiment:
    def test_above_threshold(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(sentiment_z=-1.0))
        assert decision.passed is True

    def test_at_threshold(self):
        """Exactly at -2.0 should pass (>=)."""
        gate = _make_gate()
        decision = gate.check(**_make_params(sentiment_z=-2.0))
        assert decision.passed is True

    def test_below_threshold(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(sentiment_z=-2.1))
        assert decision.passed is False
        assert "sentiment_too_negative" in decision.reasons

    def test_positive_sentiment(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(sentiment_z=1.5))
        assert decision.passed is True


# ── Liquidity (Kyle's lambda) ────────────────────────────────────────────────

class TestLiquidity:
    def test_liquid(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(kyle_lambda=1e-7))
        assert decision.passed is True

    def test_at_threshold(self):
        """Exactly at threshold should reject (strict <)."""
        gate = _make_gate()
        decision = gate.check(**_make_params(kyle_lambda=1e-6))
        assert decision.passed is False
        assert "illiquid_market" in decision.reasons

    def test_illiquid(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(kyle_lambda=1e-5))
        assert decision.passed is False
        assert "illiquid_market" in decision.reasons

    def test_zero_lambda(self):
        """Zero lambda means perfectly liquid."""
        gate = _make_gate()
        decision = gate.check(**_make_params(kyle_lambda=0.0))
        assert decision.passed is True


# ── Account equity ───────────────────────────────────────────────────────────

class TestAccountEquity:
    def test_above_floor(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(equity=10000.0))
        assert decision.passed is True

    def test_at_floor(self):
        """Exactly at min_equity should reject (strict >)."""
        gate = _make_gate()
        decision = gate.check(**_make_params(equity=5000.0))
        assert decision.passed is False
        assert "insufficient_equity" in decision.reasons

    def test_below_floor(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(equity=4999.99))
        assert decision.passed is False
        assert "insufficient_equity" in decision.reasons

    def test_zero_equity(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(equity=0.0))
        assert decision.passed is False
        assert "insufficient_equity" in decision.reasons


# ── Data freshness ───────────────────────────────────────────────────────────

class TestDataFreshness:
    def test_fresh_data(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(snapshot_age_sec=5.0))
        assert decision.passed is True

    def test_at_staleness_limit(self):
        """Exactly at 30s should reject (strict <)."""
        gate = _make_gate()
        decision = gate.check(**_make_params(snapshot_age_sec=30.0))
        assert decision.passed is False
        assert "stale_market_data" in decision.reasons

    def test_stale_data(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(snapshot_age_sec=60.0))
        assert decision.passed is False
        assert "stale_market_data" in decision.reasons

    def test_zero_age(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(snapshot_age_sec=0.0))
        assert decision.passed is True


# ── Conviction ───────────────────────────────────────────────────────────────

class TestConviction:
    def test_above_min(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(conviction=0.85))
        assert decision.passed is True

    def test_at_min(self):
        """Exactly at 0.7 should pass (>=)."""
        gate = _make_gate()
        decision = gate.check(**_make_params(conviction=0.7))
        assert decision.passed is True

    def test_below_min(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(conviction=0.69))
        assert decision.passed is False
        assert "conviction_too_low" in decision.reasons

    def test_zero_conviction(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(conviction=0.0))
        assert decision.passed is False
        assert "conviction_too_low" in decision.reasons


# ── Idempotency ──────────────────────────────────────────────────────────────

class TestIdempotency:
    def test_first_seen_passes(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(signal_id="unique_001"))
        assert decision.passed is True

    def test_duplicate_rejected(self):
        gate = _make_gate()
        params = _make_params(signal_id="dup_001")
        gate.check(**params)
        decision = gate.check(**params)
        assert decision.passed is False
        assert "duplicate_signal" in decision.reasons

    def test_different_signals_pass(self):
        gate = _make_gate()
        gate.check(**_make_params(signal_id="sig_A"))
        decision = gate.check(**_make_params(signal_id="sig_B"))
        assert decision.passed is True

    def test_cache_expiry(self):
        """After idempotency window, same signal_id should pass again."""
        gate = _make_gate(idempotency_window_sec=0.1)
        params = _make_params(signal_id="expiry_001")
        gate.check(**params)
        time.sleep(0.15)
        decision = gate.check(**params)
        assert decision.passed is True

    def test_clear_cache(self):
        gate = _make_gate()
        params = _make_params(signal_id="clear_001")
        gate.check(**params)
        gate.clear_idempotency_cache()
        decision = gate.check(**params)
        assert decision.passed is True


# ── Multiple rejections ──────────────────────────────────────────────────────

class TestMultipleRejections:
    def test_all_checks_fail(self):
        """When everything is wrong, all reasons should be collected."""
        gate = _make_gate()
        decision = gate.check(
            **_make_params(
                conviction=0.0,
                position_size=999999.0,
                equity=0.0,
                sentiment_z=-5.0,
                kyle_lambda=1.0,
                open_positions=99,
                snapshot_age_sec=999.0,
                daily_pnl_pct=-10.0,
            )
        )
        assert decision.passed is False
        assert "daily_loss_band" in decision.reasons
        assert "max_open_positions" in decision.reasons
        assert "position_size_exceeded" in decision.reasons
        assert "sentiment_too_negative" in decision.reasons
        assert "illiquid_market" in decision.reasons
        assert "insufficient_equity" in decision.reasons
        assert "stale_market_data" in decision.reasons
        assert "conviction_too_low" in decision.reasons
        # 8 reasons (kill_switch not active, idempotency passes on first call)
        assert len(decision.reasons) == 8

    def test_two_reasons(self):
        gate = _make_gate()
        decision = gate.check(
            **_make_params(
                conviction=0.5,
                equity=1000.0,
                position_size=5.0,  # small enough to pass size check (0.01 * 1000 = 10)
            )
        )
        assert decision.passed is False
        assert "conviction_too_low" in decision.reasons
        assert "insufficient_equity" in decision.reasons
        assert len(decision.reasons) == 2


# ── Edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_nan_conviction(self):
        """NaN conviction should fail the >= check."""
        gate = _make_gate()
        decision = gate.check(**_make_params(conviction=float("nan")))
        assert decision.passed is False
        assert "conviction_too_low" in decision.reasons

    def test_nan_sentiment(self):
        """NaN sentiment should fail the >= check."""
        gate = _make_gate()
        decision = gate.check(**_make_params(sentiment_z=float("nan")))
        assert decision.passed is False
        assert "sentiment_too_negative" in decision.reasons

    def test_nan_kyle_lambda(self):
        """NaN kyle_lambda should fail the < check."""
        gate = _make_gate()
        decision = gate.check(**_make_params(kyle_lambda=float("nan")))
        assert decision.passed is False
        assert "illiquid_market" in decision.reasons

    def test_negative_kyle_lambda(self):
        """Negative lambda is unusual but technically passes (< threshold)."""
        gate = _make_gate()
        decision = gate.check(**_make_params(kyle_lambda=-1e-7))
        assert decision.passed is True

    def test_very_large_equity(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(equity=1e12))
        assert decision.passed is True

    def test_very_small_position_size(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(position_size=0.01))
        assert decision.passed is True

    def test_boundary_position_pct(self):
        """Position size exactly at max_position_pct * equity should pass."""
        gate = _make_gate(max_position_pct=0.02)
        decision = gate.check(**_make_params(position_size=200.0, equity=10000.0))
        assert decision.passed is True

    def test_meta_includes_limits_on_rejection(self):
        gate = _make_gate()
        decision = gate.check(**_make_params(equity=100.0))
        assert "min_equity" in decision.meta
        assert decision.meta["min_equity"] == DEFAULT_MIN_ACCOUNT_EQUITY
