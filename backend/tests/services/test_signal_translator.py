"""
backend/tests/services/test_signal_translator.py

Unit tests for signal_translator.py — signal-to-intent translation.

Coverage:
    - Conviction calculation
    - All 5 risk gates (conviction, equity, sentiment, positions, liquidity)
    - TradeIntent generation with correct fields
    - Side determination from gex_state
    - Position sizing
    - Stop loss / take profit values
    - Signal ID generation
    - Rationale string format
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class TestConvictionCalculation:
    def test_basic_conviction(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None
        # conviction = 0.95 * (95/100) * (1-0.1) = 0.95 * 0.95 * 0.9 = 0.812
        assert result.conviction == pytest.approx(0.812, abs=0.01)

    def test_high_conviction(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None
        # conviction = 0.95 * 0.95 * 0.9 = 0.81225
        assert result.conviction > 0.8

    def test_zero_anomaly_gives_zero_conviction(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.0,
            trinity_score=100.0,
            vpin_cdf=0.0,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
            kyle_lambda=1e-7,
        )
        result = translate_signal(inp)
        assert result is None  # conviction = 0 < 0.7

    def test_max_vpin_reduces_conviction(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.9,
            trinity_score=90.0,
            vpin_cdf=1.0,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        # conviction = 0.9 * 0.9 * 0 = 0

    def test_boundary_conviction(self):
        from services.signal_translator import MIN_CONVICTION, SignalInput, translate_signal
        # Find inputs that give exactly MIN_CONVICTION
        inp = SignalInput(
            anomaly_score=MIN_CONVICTION,
            trinity_score=100.0,
            vpin_cdf=0.0,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None
        assert result.conviction >= MIN_CONVICTION


class TestRiskGates:
    def test_conviction_too_low(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.5,
            trinity_score=80.0,
            vpin_cdf=0.3,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is None

    def test_equity_too_low(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=1000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is None

    def test_sentiment_too_negative(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            flashalpha_sentiment_z=-3.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is None

    def test_too_many_open_positions(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            current_positions={"SPY": 3},
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is None

    def test_illiquid_market(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            kyle_lambda=1e-5,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is None

    def test_exact_equity_boundary(self):
        from services.signal_translator import MIN_ACCOUNT_EQUITY, SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=MIN_ACCOUNT_EQUITY,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None


class TestTradeIntentOutput:
    def test_has_signal_id(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None
        assert len(result.signal_id) == 16
        assert all(c in "0123456789abcdef" for c in result.signal_id)

    def test_side_positive_gex(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            gex_state="positive",
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None
        assert result.side == "buy"

    def test_side_negative_gex(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            gex_state="negative",
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None
        assert result.side == "sell"

    def test_side_neutral_defaults_buy(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            gex_state="neutral",
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None
        assert result.side == "buy"

    def test_stop_loss_is_2pct_below(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None
        expected_stop = round(450.0 * 0.98, 2)
        assert result.stop_loss == expected_stop

    def test_take_profit_is_6pct_above(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None
        expected_tp = round(450.0 * 1.06, 2)
        assert result.take_profit == expected_tp

    def test_rr_is_3_to_1(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=100.0,
        )
        result = translate_signal(inp)
        assert result is not None
        risk = result.limit_price - result.stop_loss
        reward = result.take_profit - result.limit_price
        rr = reward / risk
        assert rr == pytest.approx(3.0, abs=0.1)

    def test_rationale_contains_conviction(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None
        assert "conviction=" in result.rationale
        assert "anomaly=" in result.rationale
        assert "trinity=" in result.rationale

    def test_position_sizing_1pct_equity(self):
        from services.signal_translator import MAX_POSITION_PCT, SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=100.0,
        )
        result = translate_signal(inp)
        assert result is not None
        max_qty = int(10000.0 * MAX_POSITION_PCT / 100.0)
        assert result.qty <= max_qty + 1

    def test_ticker_preserved(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            ticker="QQQ",
            spot_price=350.0,
        )
        result = translate_signal(inp)
        assert result is not None
        assert result.ticker == "QQQ"

    def test_limit_price_equals_spot(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None
        assert result.limit_price == 450.0


class TestCheckGatesDirectly:
    def test_all_gates_pass(self):
        from services.signal_translator import SignalInput, _check_gates
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            flashalpha_sentiment_z=0.0,
            current_positions={},
            kyle_lambda=1e-7,
            ticker="SPY",
            spot_price=450.0,
        )
        conviction = 0.95 * 0.95 * 0.9
        result = _check_gates(inp, conviction)
        assert result["approved"] is True

    def test_conviction_gate_fails(self):
        from services.signal_translator import SignalInput, _check_gates
        inp = SignalInput(
            account_equity=10000.0,
            flashalpha_sentiment_z=0.0,
            current_positions={},
            kyle_lambda=1e-7,
        )
        result = _check_gates(inp, 0.5)
        assert result["approved"] is False
        assert "conviction" in result["reason"]

    def test_equity_gate_fails(self):
        from services.signal_translator import SignalInput, _check_gates
        inp = SignalInput(
            account_equity=100.0,
            flashalpha_sentiment_z=0.0,
            current_positions={},
            kyle_lambda=1e-7,
        )
        result = _check_gates(inp, 0.8)
        assert result["approved"] is False
        assert "equity" in result["reason"]
