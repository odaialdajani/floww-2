"""
backend/tests/services/test_trading_signals.py

Tests for the VPIN_HFT trading signal generator.
12+ tests covering all IF/ELSE branches, death count logic, and state management.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.trading_signals import Signal, SignalState, TradingSignalGenerator


class TestTradingSignalBuyBranch:
    """Test the BUY signal branch: toxic + qi_zscore > 1.5."""

    def test_buy_signal_all_conditions_met(self):
        """vpin_cdf_z > 0.5, corr_sum > 4, qi_z > 1.5 => BUY."""
        gen = TradingSignalGenerator()
        signal = gen.evaluate(
            vpin_cdf_zscore=0.8,
            exchange_corr_zscore=2.5,
            asset_corr_zscore=2.0,
            qi_zscore=1.8,
        )
        assert signal == Signal.BUY

    def test_buy_resets_long_death_count(self):
        """BUY signal resets long death count to 10."""
        gen = TradingSignalGenerator()
        gen.evaluate(
            vpin_cdf_zscore=0.8,
            exchange_corr_zscore=2.5,
            asset_corr_zscore=2.0,
            qi_zscore=1.8,
        )
        assert gen.state.long_death_count == 10
        assert gen.state.short_death_count == 0
        assert gen.state.current_position == "LONG"

    def test_buy_covers_shorts(self):
        """BUY signal when short resets short death count to 0."""
        gen = TradingSignalGenerator()
        # First go short
        gen.evaluate(0.8, 2.5, 2.0, -1.8)
        assert gen.state.current_position == "SHORT"
        # Then buy
        gen.evaluate(0.8, 2.5, 2.0, 1.8)
        assert gen.state.current_position == "LONG"
        assert gen.state.short_death_count == 0


class TestTradingSignalSellBranch:
    """Test the SELL signal branch: toxic + qi_zscore < -1.5."""

    def test_sell_signal_all_conditions_met(self):
        """vpin_cdf_z > 0.5, corr_sum > 4, qi_z < -1.5 => SELL."""
        gen = TradingSignalGenerator()
        signal = gen.evaluate(
            vpin_cdf_zscore=0.8,
            exchange_corr_zscore=2.5,
            asset_corr_zscore=2.0,
            qi_zscore=-1.8,
        )
        assert signal == Signal.SELL

    def test_sell_resets_short_death_count(self):
        """SELL signal resets short death count to 10."""
        gen = TradingSignalGenerator()
        gen.evaluate(0.8, 2.5, 2.0, -1.8)
        assert gen.state.short_death_count == 10
        assert gen.state.long_death_count == 0
        assert gen.state.current_position == "SHORT"

    def test_sell_covers_longs(self):
        """SELL signal when long resets long death count to 0."""
        gen = TradingSignalGenerator()
        gen.evaluate(0.8, 2.5, 2.0, 1.8)
        assert gen.state.current_position == "LONG"
        gen.evaluate(0.8, 2.5, 2.0, -1.8)
        assert gen.state.current_position == "SHORT"
        assert gen.state.long_death_count == 0


class TestTradingSignalHoldBranch:
    """Test HOLD conditions."""

    def test_hold_low_vpin(self):
        """vpin_cdf_zscore <= 0.5 => HOLD even if other conditions met."""
        gen = TradingSignalGenerator()
        signal = gen.evaluate(
            vpin_cdf_zscore=0.3,
            exchange_corr_zscore=3.0,
            asset_corr_zscore=2.0,
            qi_zscore=2.0,
        )
        assert signal == Signal.HOLD

    def test_hold_low_correlation(self):
        """corr_sum <= 4 => HOLD even if VPIN is high."""
        gen = TradingSignalGenerator()
        signal = gen.evaluate(
            vpin_cdf_zscore=0.8,
            exchange_corr_zscore=1.0,
            asset_corr_zscore=1.0,
            qi_zscore=2.0,
        )
        assert signal == Signal.HOLD

    def test_hold_qi_in_middle(self):
        """Toxic but -1.5 <= qi_zscore <= 1.5 => HOLD."""
        gen = TradingSignalGenerator()
        signal = gen.evaluate(
            vpin_cdf_zscore=0.8,
            exchange_corr_zscore=2.5,
            asset_corr_zscore=2.0,
            qi_zscore=0.5,
        )
        assert signal == Signal.HOLD

    def test_hold_qi_exactly_at_threshold(self):
        """qi_zscore exactly at 1.5 => not > 1.5 => HOLD."""
        gen = TradingSignalGenerator()
        signal = gen.evaluate(
            vpin_cdf_zscore=0.8,
            exchange_corr_zscore=2.5,
            asset_corr_zscore=2.0,
            qi_zscore=1.5,
        )
        assert signal == Signal.HOLD

    def test_hold_qi_exactly_at_sell_threshold(self):
        """qi_zscore exactly at -1.5 => not < -1.5 => HOLD."""
        gen = TradingSignalGenerator()
        signal = gen.evaluate(
            vpin_cdf_zscore=0.8,
            exchange_corr_zscore=2.5,
            asset_corr_zscore=2.0,
            qi_zscore=-1.5,
        )
        assert signal == Signal.HOLD


class TestTradingSignalDeathCount:
    """Test death count decrement and position expiry."""

    def test_death_count_decrements_each_period(self):
        """Death count decrements by 1 each evaluate() call."""
        gen = TradingSignalGenerator()
        gen.evaluate(0.8, 2.5, 2.0, 1.8)  # BUY -> long_death_count = 10
        gen.evaluate(0.1, 0.1, 0.1, 0.0)  # HOLD -> decrements
        assert gen.state.long_death_count == 9

    def test_death_count_reaches_zero_exits_position(self):
        """After 10 HOLD periods following BUY, position is None."""
        gen = TradingSignalGenerator()
        gen.evaluate(0.8, 2.5, 2.0, 1.8)  # BUY -> long = 10
        for _ in range(10):
            gen.evaluate(0.1, 0.1, 0.1, 0.0)  # HOLD -> decrement
        assert gen.state.long_death_count == 0
        assert gen.state.current_position is None

    def test_short_death_count_expires(self):
        """Short position expires after 10 HOLD periods."""
        gen = TradingSignalGenerator()
        gen.evaluate(0.8, 2.5, 2.0, -1.8)  # SELL -> short = 10
        for _ in range(10):
            gen.evaluate(0.1, 0.1, 0.1, 0.0)
        assert gen.state.short_death_count == 0
        assert gen.state.current_position is None

    def test_new_buy_resets_death_count(self):
        """A new BUY signal during long resets death count to 10."""
        gen = TradingSignalGenerator()
        gen.evaluate(0.8, 2.5, 2.0, 1.8)  # BUY -> 10
        for _ in range(5):
            gen.evaluate(0.1, 0.1, 0.1, 0.0)  # -> 5
        assert gen.state.long_death_count == 5
        gen.evaluate(0.8, 2.5, 2.0, 1.8)  # BUY again -> 10
        assert gen.state.long_death_count == 10

    def test_death_count_never_negative(self):
        """Death count should never go below 0."""
        gen = TradingSignalGenerator()
        gen.evaluate(0.1, 0.1, 0.1, 0.0)  # No position
        assert gen.state.long_death_count == 0
        assert gen.state.short_death_count == 0


class TestTradingSignalState:
    """Test state management and serialization."""

    def test_initial_state(self):
        gen = TradingSignalGenerator()
        assert gen.state.long_death_count == 0
        assert gen.state.short_death_count == 0
        assert gen.state.current_position is None
        assert gen.state.last_signal == Signal.HOLD

    def test_custom_thresholds(self):
        state = SignalState(
            vpin_cdf_zscore_threshold=0.3,
            corr_zscore_sum_threshold=3.0,
            death_count_max=5,
        )
        gen = TradingSignalGenerator(state=state)
        signal = gen.evaluate(0.4, 2.0, 2.0, 1.8)
        assert signal == Signal.BUY
        assert gen.state.long_death_count == 5

    def test_get_state(self):
        gen = TradingSignalGenerator()
        gen.evaluate(0.8, 2.5, 2.0, 1.8)
        state = gen.get_state()
        assert state["current_position"] == "LONG"
        assert state["last_signal"] == "BUY"
        assert state["long_death_count"] == 10
        assert "thresholds" in state
        assert state["signal_count"] == 1

    def test_signal_history_recorded(self):
        gen = TradingSignalGenerator()
        gen.evaluate(0.8, 2.5, 2.0, 1.8)
        gen.evaluate(0.1, 0.1, 0.1, 0.0)
        assert len(gen.state.signal_history) == 2
        assert gen.state.signal_history[0]["signal"] == "BUY"
        assert gen.state.signal_history[1]["signal"] == "HOLD"
