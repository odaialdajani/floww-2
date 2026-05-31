"""
backend/tests/services/test_paper_trader.py

Tests for the VPIN_HFT paper trading execution adapter.
8+ tests covering signal execution, position management, and trade lifecycle.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.paper_trader import PaperPosition, PaperTrader
from services.trading_signals import Signal


class TestPaperPosition:
    """Test the PaperPosition dataclass."""

    def test_long_position_close(self):
        pos = PaperPosition(
            symbol="SPY", side="LONG", quantity=10,
            entry_price=500.0, entry_time="2024-01-01T00:00:00Z"
        )
        pnl = pos.close(510.0)
        assert pnl == 100.0  # (510 - 500) * 10
        assert pos.status == "closed"

    def test_short_position_close(self):
        pos = PaperPosition(
            symbol="SPY", side="SHORT", quantity=10,
            entry_price=500.0, entry_time="2024-01-01T00:00:00Z"
        )
        pnl = pos.close(490.0)
        assert pnl == 100.0  # (500 - 490) * 10
        assert pos.status == "closed"

    def test_to_dict(self):
        pos = PaperPosition(
            symbol="SPY", side="LONG", quantity=5,
            entry_price=500.0, entry_time="2024-01-01T00:00:00Z"
        )
        d = pos.to_dict()
        assert d["symbol"] == "SPY"
        assert d["side"] == "LONG"
        assert d["status"] == "open"


class TestPaperTraderInit:
    """Test paper trader initialization."""

    def test_default_init(self):
        pt = PaperTrader()
        assert pt.initial_capital == 100_000.0
        assert pt.cash == 100_000.0
        assert pt.position_size_pct == 0.05
        assert pt.max_positions == 5

    def test_custom_init(self):
        pt = PaperTrader(initial_capital=50_000.0, max_positions=3)
        assert pt.initial_capital == 50_000.0
        assert pt.max_positions == 3


class TestPaperTraderSignalExecution:
    """Test signal-driven order execution."""

    def test_buy_signal_creates_long_position(self):
        pt = PaperTrader(initial_capital=100_000.0)
        result = pt.execute_signal(Signal.BUY, "SPY", 500.0)
        assert result["status"] == "filled"
        assert result["action"] == "BUY"
        assert result["quantity"] > 0

    def test_sell_signal_creates_short_position(self):
        pt = PaperTrader(initial_capital=100_000.0)
        result = pt.execute_signal(Signal.SELL, "SPY", 500.0)
        assert result["status"] == "filled"
        assert result["action"] == "SELL"
        assert result["quantity"] > 0

    def test_hold_signal_no_action(self):
        pt = PaperTrader()
        result = pt.execute_signal(Signal.HOLD, "SPY", 500.0)
        assert result["status"] == "no_action"

    def test_buy_covers_existing_short(self):
        """BUY signal when short should cover the short first."""
        pt = PaperTrader(initial_capital=100_000.0)
        pt.execute_signal(Signal.SELL, "SPY", 500.0)
        # Now buy to cover
        result = pt.execute_signal(Signal.BUY, "SPY", 505.0)
        assert result["status"] == "filled"
        assert "cover" in result

    def test_sell_covers_existing_long(self):
        """SELL signal when long should cover the long first."""
        pt = PaperTrader(initial_capital=100_000.0)
        pt.execute_signal(Signal.BUY, "SPY", 500.0)
        result = pt.execute_signal(Signal.SELL, "SPY", 505.0)
        assert result["status"] == "filled"
        assert "cover" in result

    def test_position_limit_rejects(self):
        """Should reject when max positions reached."""
        pt = PaperTrader(initial_capital=100_000.0, max_positions=1)
        pt.execute_signal(Signal.BUY, "SPY", 500.0)
        result = pt.execute_signal(Signal.SELL, "QQQ", 400.0)
        assert result["status"] == "rejected"
        assert "Max positions" in result["reason"]

    def test_insufficient_cash_rejects(self):
        """Should reject buy when not enough cash."""
        pt = PaperTrader(initial_capital=10.0)
        result = pt.execute_signal(Signal.BUY, "SPY", 500.0)
        assert result["status"] == "rejected"


class TestPaperTraderPortfolio:
    """Test portfolio summary and state."""

    def test_portfolio_summary_empty(self):
        pt = PaperTrader()
        summary = pt.get_portfolio_summary()
        assert summary["cash"] == 100_000.0
        assert summary["open_positions"] == 0
        assert summary["total_trades"] == 0

    def test_portfolio_after_buy(self):
        pt = PaperTrader(initial_capital=100_000.0)
        pt.execute_signal(Signal.BUY, "SPY", 500.0)
        summary = pt.get_portfolio_summary({"SPY": 510.0})
        assert summary["open_positions"] == 1
        assert summary["unrealized_pnl"] > 0  # Price went up

    def test_trade_history_recorded(self):
        pt = PaperTrader(initial_capital=100_000.0)
        pt.execute_signal(Signal.BUY, "SPY", 500.0)
        pt.execute_signal(Signal.SELL, "SPY", 510.0)  # Close
        assert len(pt.trade_history) >= 1

    def test_get_state(self):
        pt = PaperTrader()
        state = pt.get_state()
        assert state["cash"] == 100_000.0
        assert state["initial_capital"] == 100_000.0
        assert "position_size_pct" in state
