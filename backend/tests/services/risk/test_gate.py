"""
backend/tests/services/risk/test_gate.py — Tests for risk gate.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from services.risk.gate import AccountState, RiskGate, RiskResult, TradeIntent


def make_intent(ticker="SPY", side="BUY", qty=2, price=400.0, conviction=0.8, kyle=0.01):
    return TradeIntent(
        ticker=ticker, side=side, qty=qty, limit_price=price,
        conviction=conviction, kyle_lambda=kyle,
    )


def make_account(equity=50000.0, daily_pnl=0.0, consecutive_losses=0, open_positions=None):
    return AccountState(
        equity=equity,
        cash=equity * 0.5,
        daily_pnl_pct=daily_pnl,
        consecutive_losses=consecutive_losses,
        open_positions=open_positions or {},
    )


class TestRiskGateApprove:
    def test_normal_trade_approved(self):
        gate = RiskGate()
        intent = make_intent()
        account = make_account()
        result = gate.before_trade(intent, account)
        assert result.approved
        assert result.rule == ""

    def test_small_position_approved(self):
        gate = RiskGate()
        intent = make_intent(qty=1, price=100.0)
        account = make_account(equity=10000.0)
        result = gate.before_trade(intent, account)
        assert result.approved


class TestRiskGateReject:
    def test_daily_loss_limit(self):
        gate = RiskGate()
        intent = make_intent()
        account = make_account(daily_pnl=-0.03)  # -3%
        result = gate.before_trade(intent, account)
        assert not result.approved
        assert result.rule == "daily_loss_limit"

    def test_consecutive_losses(self):
        gate = RiskGate()
        intent = make_intent()
        account = make_account(consecutive_losses=3)
        result = gate.before_trade(intent, account)
        assert not result.approved
        assert result.rule == "consecutive_losses"

    def test_position_concentration(self):
        gate = RiskGate()
        intent = make_intent(qty=100, price=400.0)  # $40k position on $10k equity
        account = make_account(equity=10000.0)
        result = gate.before_trade(intent, account)
        assert not result.approved
        assert result.rule == "position_concentration"

    def test_max_position_value(self):
        gate = RiskGate()
        intent = make_intent(qty=100, price=100.0)  # $10k > $5k max
        account = make_account(equity=100000.0)
        result = gate.before_trade(intent, account)
        assert not result.approved
        assert result.rule == "max_position_value"

    def test_max_open_positions(self):
        gate = RiskGate()
        intent = make_intent(ticker="NEW")
        positions = {f"T{i}": None for i in range(5)}
        account = make_account(equity=100000.0, open_positions=positions)
        result = gate.before_trade(intent, account)
        assert not result.approved
        assert result.rule == "max_open_positions"

    def test_liquidity_gate(self):
        gate = RiskGate()
        intent = make_intent(kyle=0.1)  # > 0.05 threshold
        account = make_account()
        result = gate.before_trade(intent, account)
        assert not result.approved
        assert result.rule == "liquidity_gate"

    def test_min_equity(self):
        gate = RiskGate()
        intent = make_intent()
        account = make_account(equity=500.0)  # < $1000 min
        result = gate.before_trade(intent, account)
        assert not result.approved
        assert result.rule == "min_equity"

    def test_low_conviction(self):
        gate = RiskGate()
        intent = make_intent(conviction=0.3)  # < 0.5
        account = make_account()
        result = gate.before_trade(intent, account)
        assert not result.approved
        assert result.rule == "conviction_threshold"


class TestCircuitBreaker:
    def test_circuit_breaker_blocks_after_trip(self):
        gate = RiskGate()
        gate._trip_circuit_breaker("test")
        intent = make_intent()
        account = make_account()
        result = gate.before_trade(intent, account)
        assert not result.approved
        assert result.rule == "circuit_breaker"

    def test_circuit_breaker_reset(self):
        gate = RiskGate()
        gate._trip_circuit_breaker("test")
        gate.reset_circuit_breaker()
        assert not gate.circuit_breaker_active
        intent = make_intent()
        account = make_account()
        result = gate.before_trade(intent, account)
        assert result.approved

    def test_daily_loss_trips_circuit_breaker(self):
        gate = RiskGate()
        intent = make_intent()
        account = make_account(daily_pnl=-0.03)
        result = gate.before_trade(intent, account)
        assert not result.approved
        assert gate.circuit_breaker_active


class TestAfterTrade:
    def test_records_trade(self):
        gate = RiskGate()
        intent = make_intent()
        gate.after_trade(intent, pnl=100.0)
        history = gate.get_trade_history()
        assert len(history) == 1
        assert history[0]["pnl"] == 100.0

    def test_records_loss(self):
        gate = RiskGate()
        intent = make_intent()
        gate.after_trade(intent, pnl=-50.0)
        history = gate.get_trade_history()
        assert history[0]["pnl"] == -50.0


class TestRiskResult:
    def test_bool_approved(self):
        r = RiskResult(approved=True, reason="", rule="")
        assert bool(r) is True

    def test_bool_rejected(self):
        r = RiskResult(approved=False, reason="test", rule="test")
        assert bool(r) is False
