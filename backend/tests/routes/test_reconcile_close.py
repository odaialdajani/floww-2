"""Eventual reconciliation for pending paper-close orders.

RED contract: close_position() leaves journal_status=pending_fill when the
venue fill is unconfirmed, and nothing ever re-polls the venue — the journal
card stays open forever. reconcile_pending_close() must re-fetch the venue
order by id and close cards only on a confirmed fill with a positive average
price. Canceled / open / missing / zero-price states stay honest; failures
never raise into the caller.
"""
from __future__ import annotations

import contextlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.duckdb_engine import DuckDBEngine  # noqa: E402
from services.journal_store import (  # noqa: E402
    init_journal_tables,
    read_trades,
    save_seeds,
)


@pytest.fixture
def jeng():
    eng = DuckDBEngine(":memory:")
    init_journal_tables(eng)
    yield eng
    with contextlib.suppress(Exception):
        eng._conn.close()


def _seed(ticker, **over):
    base = {
        "ticker": ticker, "type": "equity", "action": "buy", "strike": 0.0,
        "expiry": "", "quantity": "2", "entry_price": 1.25,
        "exit_price": "", "entry_date": "2026-08-22", "exit_date": "",
        "notes": "", "gex_regime": "", "setup": "recon", "tags": "auto",
        "ckey": f"{ticker}|call|500|2026-09-18",
    }
    base.update(over)
    return base


def _open_cards(jeng, ticker):
    return [t for t in read_trades(jeng) if t["ticker"] == ticker and not t.get("exit_date")]


class _FakeClient:
    """Venue stub: order lookup by id, programmable per test."""

    def __init__(self, orders=None, fail=False):
        self.orders = orders or {}
        self.fail = fail
        self.looked_up = []

    async def get_order(self, order_id):
        self.looked_up.append(order_id)
        if self.fail:
            raise RuntimeError("venue down")
        return self.orders.get(order_id)


def _filled(order_id="ord-1", px=12.5, status="filled", symbol="RCN_FILL"):
    return {"id": order_id, "status": status, "filled_avg_price": px,
            "symbol": symbol, "side": "sell", "qty": "2", "filled_qty": "2"}


def _reserve(jeng, symbol, order_id):
    from services.close_intents import bind_close_order, prepare_close
    intent = prepare_close(jeng, symbol)
    bind_close_order(jeng, intent["intent_id"], order_id)


class TestReconcilePendingClose:
    async def test_filled_order_closes_card(self, jeng):
        from routes.alpaca import reconcile_pending_close

        save_seeds(jeng, [_seed("RCN_FILL")])
        _reserve(jeng, "RCN_FILL", "ord-1")
        client = _FakeClient({"ord-1": _filled()})
        out = await reconcile_pending_close("RCN_FILL", "ord-1",
                                            client=client, engine=jeng)
        assert out["reconciled"] is True
        assert out["journal_closed"] == 1
        assert client.looked_up == ["ord-1"]
        assert _open_cards(jeng, "RCN_FILL") == []
        closed = [t for t in read_trades(jeng) if t["ticker"] == "RCN_FILL"][0]
        assert float(closed["exit_price"]) == 12.5

    async def test_open_order_stays_pending(self, jeng):
        from routes.alpaca import reconcile_pending_close

        save_seeds(jeng, [_seed("RCN_OPEN")])
        _reserve(jeng, "RCN_OPEN", "ord-2")
        client = _FakeClient({"ord-2": _filled("ord-2", px=0, status="new", symbol="RCN_OPEN")})
        out = await reconcile_pending_close("RCN_OPEN", "ord-2",
                                            client=client, engine=jeng)
        assert out["reconciled"] is False
        assert out["journal_closed"] == 0
        assert len(_open_cards(jeng, "RCN_OPEN")) == 1

    async def test_canceled_order_never_closes(self, jeng):
        from routes.alpaca import reconcile_pending_close

        save_seeds(jeng, [_seed("RCN_CXL")])
        _reserve(jeng, "RCN_CXL", "ord-3")
        client = _FakeClient({"ord-3": _filled("ord-3", px=9.0, status="canceled", symbol="RCN_CXL")})
        out = await reconcile_pending_close("RCN_CXL", "ord-3",
                                            client=client, engine=jeng)
        assert out["reconciled"] is False
        assert out["journal_closed"] == 0
        assert len(_open_cards(jeng, "RCN_CXL")) == 1

    async def test_filled_without_price_is_not_a_fill(self, jeng):
        from routes.alpaca import reconcile_pending_close

        save_seeds(jeng, [_seed("RCN_NOPX")])
        _reserve(jeng, "RCN_NOPX", "ord-4")
        client = _FakeClient({"ord-4": {"id": "ord-4", "status": "filled",
                                        "symbol": "RCN_NOPX", "side": "sell", "qty": "2", "filled_qty": "2",
                                        "filled_avg_price": None}})
        out = await reconcile_pending_close("RCN_NOPX", "ord-4",
                                            client=client, engine=jeng)
        assert out["reconciled"] is False
        assert len(_open_cards(jeng, "RCN_NOPX")) == 1

    async def test_missing_order_is_honest(self, jeng):
        from routes.alpaca import reconcile_pending_close

        client = _FakeClient({})
        out = await reconcile_pending_close("RCN_GONE", "ord-9",
                                            client=client, engine=jeng)
        assert out["reconciled"] is False
        assert out["status"] == "reconciliation_exception"
        assert out["reason"] == "unmatched_close_intent"

    async def test_venue_failure_never_raises(self, jeng):
        from routes.alpaca import reconcile_pending_close

        save_seeds(jeng, [_seed("RCN_DOWN")])
        _reserve(jeng, "RCN_DOWN", "ord-1")
        client = _FakeClient(fail=True)
        out = await reconcile_pending_close("RCN_DOWN", "ord-1",
                                            client=client, engine=jeng)
        assert out["reconciled"] is False
        assert "error" in out
        assert len(_open_cards(jeng, "RCN_DOWN")) == 1

    async def test_partial_fill_stays_pending(self, jeng):
        """A partially filled close is not a confirmed fill: card stays open."""
        from routes.alpaca import reconcile_pending_close

        save_seeds(jeng, [_seed("RCN_PART")])
        _reserve(jeng, "RCN_PART", "ord-5")
        client = _FakeClient({"ord-5": {"id": "ord-5", "status": "partially_filled",
                                        "symbol": "RCN_PART", "side": "sell",
                                        "filled_avg_price": 8.0,
                                        "filled_qty": 1, "qty": 2}})
        out = await reconcile_pending_close("RCN_PART", "ord-5",
                                            client=client, engine=jeng)
        assert out["reconciled"] is False
        assert out["journal_closed"] == 0
        assert len(_open_cards(jeng, "RCN_PART")) == 1
