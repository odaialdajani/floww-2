"""Focused regression — ledger cash reconciliation invariants (paper-recovery B13).

The recovered Oct-18 plan requires complete fill/cost/cash-change
reconciliation before any paper performance is trusted. These tests pin the
identities the three in-repo simulation books must satisfy for ANY sequence of
fills — seeded-random for PaperBroker, scripted journeys for the engine and
the VPIN adapter:

  I1  cash book == replay of the fill/order journal (no off-journal money)
  I2  when every position is flat: cash change == total realized PnL
      (PaperTrader: minus total commissions — its realized field excludes fees)
  I3  position quantity == signed sum of fills
  I4  portfolio summary values == cash + marked-at-cost holdings

These are invariant pins, not fixes: they must pass on the current tree, and
any future ledger regression that breaks one of these identities fails here.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.execution_engine import MarketState  # noqa: E402
from services.paper_broker import PaperBroker, PaperBrokerConfig  # noqa: E402
from services.paper_trader import PaperTrader  # noqa: E402
from services.paper_trading import PaperTradingEngine  # noqa: E402
from services.trading_signals import Signal  # noqa: E402


class TestPaperBrokerRandomReconciliation:
    def test_random_fill_sequence_reconciles(self):
        rng = random.Random(20261027)
        broker = PaperBroker(config=PaperBrokerConfig(initial_capital=1_000_000.0))
        for _step in range(200):
            symbol = rng.choice(["SPY", "QQQ", "DIA"])
            side = rng.choice(["buy", "sell"])
            qty = rng.randint(1, 10)
            price = round(rng.uniform(90, 110), 2)
            order_id = broker.submit_order(symbol, side, qty)
            fill = broker.execute_fill(order_id, price)
            # D1 pin: a replayed fill is refused and moves nothing.
            assert broker.execute_fill(order_id, price) is None
            assert fill is not None
        # Close everything, so the flat identity can be checked.
        for _ in range(200):
            open_positions = broker.get_all_positions()
            if not open_positions:
                break
            for pos in open_positions:
                broker.close_position(pos.symbol, round(rng.uniform(90, 110), 2))
        assert broker.get_all_positions() == []

        # I1: cash book == journal replay (fills in recorded order).
        expected_cash = 1_000_000.0
        signed_by_symbol = {}
        for f in broker.fills:
            value = f.fill_price * f.quantity
            expected_cash += value if f.side == "sell" else -value
            signed_by_symbol[f.symbol] = signed_by_symbol.get(f.symbol, 0) + (
                f.quantity if f.side == "buy" else -f.quantity)
        assert broker.cash == pytest.approx(expected_cash, abs=1e-6)

        # I2: flat book — cash change == realized PnL (no fee model here).
        assert broker.total_realized_pnl == pytest.approx(broker.cash - 1_000_000.0, abs=1e-6)
        # get_pnl reports the same realized total rounded to cents (its format).
        assert broker.get_pnl()["realized_pnl"] == pytest.approx(
            broker.total_realized_pnl, abs=0.0051)

        # I3: position quantities == signed fills (all flat now).
        for pos in broker.positions.values():
            assert signed_by_symbol.get(pos.symbol, 0) == pytest.approx(pos.quantity, abs=0)

    def test_long_short_reversal_reconciles(self):
        broker = PaperBroker(config=PaperBrokerConfig(initial_capital=100_000.0))
        o1 = broker.submit_order("SPY", "buy", 5)
        broker.execute_fill(o1, 500.0)
        o2 = broker.submit_order("SPY", "sell", 12)  # closes 5, opens short 7
        broker.execute_fill(o2, 510.0)
        o3 = broker.submit_order("SPY", "buy", 7)  # cover the short
        broker.execute_fill(o3, 495.0)
        assert broker.get_position("SPY").quantity == 0

        expected_cash = 100_000.0
        for f in broker.fills:
            expected_cash += f.fill_price * f.quantity * (1 if f.side == "sell" else -1)
        assert broker.cash == pytest.approx(expected_cash, abs=1e-6)
        assert broker.total_realized_pnl == pytest.approx(broker.cash - 100_000.0, abs=1e-6)


class TestEngineJournalReconcilesCash:
    def _market(self, bid=100.0, ask=100.1):
        return MarketState(symbol="SPY", bid=bid, ask=ask, last=(bid + ask) / 2,
                           bid_size=100, ask_size=100, volume=1_000_000, volatility=0.2)

    def test_trade_history_replays_to_exact_cash(self):
        engine = PaperTradingEngine(initial_capital=100_000, commission_per_contract=0.65)
        m = self._market()
        b1 = engine.submit_order(symbol="SPY", side="buy", quantity=5, market=m)["order_id"]
        engine.execute_order(b1, m)
        b2 = engine.submit_order(symbol="SPY", side="buy", quantity=3, market=m)["order_id"]
        engine.execute_order(b2, self._market(101, 101.2))
        s1 = engine.submit_order(symbol="SPY", side="sell", quantity=4, market=m)["order_id"]
        engine.execute_order(s1, self._market(102, 102.2))
        s2 = engine.submit_order(symbol="SPY", side="sell", quantity=4, market=m)["order_id"]
        engine.execute_order(s2, self._market(99, 99.2))
        # B1 pin: replays are refused and move nothing.
        with pytest.raises(ValueError):
            engine.execute_order(s2, m)

        expected_cash = 100_000.0
        for t in engine.trade_history:
            gross = t["fill_price"] * t["quantity"]
            expected_cash += (-gross - t["commission"]) if t["side"] == "buy" else (gross - t["commission"])
        assert engine.cash == pytest.approx(expected_cash, abs=1e-6)
        assert len(engine.trade_history) == 4

        # I4: portfolio summary values net positions at cost (summary rounds
        # its outputs to cents — compare within the cent).
        summary = engine.get_portfolio_summary()
        held = sum(p["avg_cost"] * p["quantity"] for p in summary["positions"])
        assert summary["total_value"] == pytest.approx(engine.cash + held, abs=0.0051)
        assert summary["open_positions"] == 0  # bought 8, sold 8 -> flat


class TestVPINTraderReconciles:
    def test_closed_pairs_reconcile_with_open_entry_adjustment(self):
        # Design fact: every BUY opens a long and every SELL opens a short —
        # there is no close-only signal path — so after an odd cover the book
        # necessarily holds one open LONG. The identity must hold anyway:
        #   cash change == realized - commissions - open entry outflow
        trader = PaperTrader(initial_capital=50_000, commission_per_share=0.01)
        trader.execute_signal(Signal.BUY, "SPY", 500.0)      # long entry
        trader.execute_signal(Signal.SELL, "SPY", 505.0)     # closes long, opens short
        trader.execute_signal(Signal.BUY, "SPY", 498.0)      # closes short, opens long
        trader.execute_signal(Signal.SELL, "SPY", 502.0)     # closes long, opens short
        trader.execute_signal(Signal.BUY, "SPY", 495.0)      # closes short -> one open LONG

        open_positions = [p for p in trader.positions.values() if p.status == "open"]
        assert len(open_positions) == 1 and open_positions[0].side == "LONG"

        total_realized = sum(t.realized_pnl for t in trader.trade_history)
        # B15: closes now record the commission actually charged on the cover.
        close_commissions = sum(t.commission for t in trader.trade_history)
        open_commissions = sum(o["commission"] for o in trader.order_log)
        open_entry_outflow = open_positions[0].entry_price * open_positions[0].quantity
        open_order_commission = trader.commission_per_share * open_positions[0].quantity
        closed_open_commissions = open_commissions - open_order_commission
        # I2 (fee-carrying book, one open long remains):
        #   cash change == realized
        #     − close commissions
        #     − open commissions of the CLOSED pairs
        #     − the remaining open long's full entry cost (incl. its fee)
        assert trader.cash - 50_000 == pytest.approx(
            total_realized - close_commissions - closed_open_commissions
            - (open_entry_outflow + open_order_commission),
            abs=0.01)

        # I1: FULL journal replay — open orders from order_log (cent-rounded
        # cost/proceeds) plus every cover's exit value minus its recorded
        # close commission must reconstruct the cash book.
        expected_cash = 50_000.0
        for o in trader.order_log:
            expected_cash += -o["cost"] if o["side"] == "BUY" else o["proceeds"]
        for t in trader.trade_history:
            exit_value = t.exit_price * t.quantity
            expected_cash += (exit_value - t.commission) if t.side == "LONG" \
                else -(exit_value + t.commission)
        assert trader.cash == pytest.approx(expected_cash, abs=0.01)
        # The journal must now carry every commission: 5 opens + 4 covers.
        assert len(trader.order_log) == 5 and len(trader.trade_history) == 4
        assert close_commissions + open_commissions > 0
