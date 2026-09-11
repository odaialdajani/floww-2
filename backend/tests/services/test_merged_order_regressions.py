"""Incoming order regressions, using real methods and strictly local storage."""
from unittest.mock import AsyncMock

import pytest

from alpaca_client import AlpacaClient
from services.contract_validators import validate_chain_row
from services.duckdb_engine import DuckDBEngine
from services.journal_store import init_journal_tables, read_trades
from services.order_router import OrderRouter


@pytest.fixture(autouse=True)
def _reset_event_loop_and_motor(monkeypatch):
    """No provider, account, production journal, or global Mongo fixture."""
    def deny(*args, **kwargs):
        raise AssertionError("network forbidden in order regression")
    monkeypatch.setattr("aiohttp.ClientSession", deny)
    yield


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["stop", "stop_limit"])
async def test_router_retains_stop_prices_through_actual_client(kind):
    client = AlpacaClient()
    client._get = AsyncMock(return_value=None)
    client._post = AsyncMock(return_value={"id": "paper-1", "status": "accepted"})
    result = await OrderRouter(broker=client).submit_order({
        "ticker": "SPY", "qty": 2, "order_type": kind,
        "stop_loss": 440, "limit_price": 445, "signal_id": kind,
    })
    assert result["status"] == "submitted"
    url, sent = client._post.call_args.args
    assert url == "https://paper-api.alpaca.markets/v2/orders"
    assert sent["stop_price"] == "440.0"
    if kind == "stop_limit":
        assert sent["limit_price"] == "445.0"
    else:
        assert "limit_price" not in sent


@pytest.mark.asyncio
async def test_disabled_close_does_not_reserve_and_enabled_retry_can_submit(monkeypatch):
    import routes.alpaca as route
    engine = DuckDBEngine(":memory:")
    init_journal_tables(engine)
    monkeypatch.setattr("services.journal_store.get_engine", lambda: engine)
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    try:
        first = await route.close_position("SPY")
        assert "error" in first
        monkeypatch.setenv("ALPACA_API_KEY", "test-only")
        monkeypatch.setenv("ALPACA_SECRET_KEY", "test-only")
        close = AsyncMock(return_value={"id": "close-1", "symbol": "SPY", "status": "accepted"})
        monkeypatch.setattr(AlpacaClient, "close_position", close)
        second = await route.close_position("SPY")
        close.assert_awaited_once_with("SPY")
        assert second["journal_status"] == "pending_fill"
    finally:
        engine._conn.close()


@pytest.mark.asyncio
async def test_ambiguous_close_still_blocks_retry(monkeypatch):
    import routes.alpaca as route
    engine = DuckDBEngine(":memory:")
    init_journal_tables(engine)
    monkeypatch.setattr("services.journal_store.get_engine", lambda: engine)
    monkeypatch.setenv("ALPACA_API_KEY", "test-only")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-only")
    close = AsyncMock(return_value=None)
    monkeypatch.setattr(AlpacaClient, "close_position", close)
    try:
        assert "error" in await route.close_position("SPY")
        assert (await route.close_position("SPY"))["reason"] == "unresolved_close_intent"
        close.assert_awaited_once()
    finally:
        engine._conn.close()


@pytest.mark.parametrize("index", [5, 6])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_chain_counts_reject_nonfinite(index, value):
    row = ["SPY", "SPY260918C00500000", "call", 500, "2026-09-18", 0, 0, .2, .5, 501]
    assert validate_chain_row(row) == (True, None)
    row[index] = value
    assert validate_chain_row(row) == (False, "bad_volume" if index == 5 else "bad_oi")


@pytest.mark.asyncio
@pytest.mark.parametrize("option", [False, True])
@pytest.mark.parametrize("status,filled,price,count", [
    ("accepted", "0", None, 0),
    ("partially_filled", "1", "3.25", 1),
    ("filled", "2", "3.5", 1),
    ("filled", "2", "nan", 0),
    ("filled", "nan", "3.5", 0),
])
async def test_entry_journal_uses_confirmed_fill_only(monkeypatch, option, status, filled, price, count):
    import routes.alpaca as route
    engine = DuckDBEngine(":memory:")
    init_journal_tables(engine)
    monkeypatch.setattr("services.journal_store.get_engine", lambda: engine)
    symbol = "SPY260918C00500000" if option else "SPY"
    order = {"id": "entry-1", "symbol": symbol, "side": "buy", "qty": "2",
             "status": status, "filled_qty": filled, "filled_avg_price": price}
    monkeypatch.setattr(AlpacaClient, "_post", AsyncMock(return_value=order))
    call = route.place_option_order if option else route.place_order
    try:
        result = await call(symbol, 2, "buy", "limit", 3.5)
        assert result["filled_qty"] == filled
        rows = read_trades(engine)
        assert len(rows) == count
        if count:
            assert float(rows[0]["quantity"]) == float(filled)
            assert rows[0]["entry_price"] == float(price)
            # Repeated reporting of the same broker order cannot double holdings.
            await call(symbol, 2, "buy", "limit", 3.5)
            assert len(read_trades(engine)) == 1
        else:
            assert result["journal_status"] in ("pending_fill", "unconfirmed_fill")
    finally:
        engine._conn.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("filled,price,expected", [("0", None, 0), ("1", "500", 1), ("2", "500", 2)])
async def test_router_positions_count_confirmed_quantity_only(filled, price, expected):
    client = AlpacaClient()
    client._get = AsyncMock(return_value=None)
    client._post = AsyncMock(return_value={"id": "entry-1", "symbol": "SPY", "side": "buy",
        "qty": "2", "status": "accepted" if filled == "0" else "partially_filled",
        "filled_qty": filled, "filled_avg_price": price})
    router = OrderRouter(broker=client)
    intent = {"ticker": "SPY", "qty": 2, "limit_price": 500, "signal_id": "confirmed-only"}
    await router.submit_order(intent)
    assert router.position_tracker.get("SPY") == expected
    await router.submit_order(intent)
    assert router.position_tracker.get("SPY") == expected


@pytest.mark.parametrize("filled,count", [("0", 0), ("1", 1), ("2", 1)])
def test_discord_journals_actual_fills_only(monkeypatch, filled, count):
    from services.discord_ops import _journal_approve_fill
    engine = DuckDBEngine(":memory:")
    init_journal_tables(engine)
    monkeypatch.setattr("services.journal_store.get_engine", lambda: engine)
    order = {"id": "entry-1", "symbol": "SPY", "side": "buy", "qty": "2",
             "status": "partially_filled", "filled_qty": filled, "filled_avg_price": "500"}
    result = {"broker": order}
    try:
        _journal_approve_fill({"under": "SPY"}, "buy", 2, result)
        rows = read_trades(engine)
        assert len(rows) == count
        if count:
            assert rows[0]["quantity"] == filled
            assert rows[0]["entry_price"] == 500
            _journal_approve_fill({"under": "SPY"}, "buy", 2, result)
            assert len(read_trades(engine)) == 1
    finally:
        engine._conn.close()


@pytest.mark.parametrize("field,value", [
    ("symbol", "QQQ"), ("side", "sell"), ("qty", "3"), ("id", ""),
    ("filled_qty", "3"), ("filled_avg_price", True),
])
def test_fill_attribution_and_price_must_be_real(field, value):
    from services.entry_fills import confirmed_entry_fill
    order = {"id": "entry-1", "symbol": "SPY", "side": "buy", "qty": "2",
             "filled_qty": "1", "filled_avg_price": "500"}
    order[field] = value
    assert confirmed_entry_fill(order, 2, "SPY", "buy")["quantity"] is None


def test_repeated_or_changed_cumulative_fill_never_duplicates_holdings():
    from services.entry_fills import journal_confirmed_entry
    engine = DuckDBEngine(":memory:")
    init_journal_tables(engine)
    seed = {"ticker": "SPY", "type": "equity", "action": "buy", "strike": 0, "expiry": ""}
    order = {"id": "entry-1", "symbol": "SPY", "side": "buy", "qty": "2",
             "filled_qty": "1", "filled_avg_price": "500"}
    try:
        assert journal_confirmed_entry(engine, seed, order, 2, "SPY", "buy")["journal_added"] == 1
        same = journal_confirmed_entry(engine, seed, {**order, "filled_qty": "1.0"}, 2, "SPY", "buy")
        assert same["journal_status"] == "partial_fill"
        assert same["journal_added"] == 0
        changed = journal_confirmed_entry(engine, seed, {**order, "filled_qty": "2"}, 2, "SPY", "buy")
        assert changed["journal_status"] == "reconciliation_required"
        assert changed["journal_added"] == 0
        rows = read_trades(engine)
        assert len(rows) == 1 and rows[0]["quantity"] == "1"
    finally:
        engine._conn.close()


@pytest.mark.asyncio
async def test_discord_readback_cannot_use_another_order():
    from types import SimpleNamespace

    from services.discord_ops import _reconcile_fill
    other = {"id": "another-order", "symbol": "SPY", "side": "buy", "qty": "2",
             "filled_qty": "2", "filled_avg_price": "500", "status": "filled"}
    router = SimpleNamespace(fetch_venue_order=AsyncMock(return_value=other))
    result = await _reconcile_fill(router, {"broker": {"id": "entry-1"}})
    assert result["venue_status"] == "unknown"
    assert "filled_qty" not in result


@pytest.mark.asyncio
async def test_tracker_uses_canonical_sent_symbol_and_side():
    client = AlpacaClient()
    client._get = AsyncMock(return_value=None)
    client._post = AsyncMock(return_value={"id": "entry-1", "symbol": "SPY", "side": "buy",
        "qty": "2", "status": "filled", "filled_qty": "2", "filled_avg_price": "500"})
    router = OrderRouter(broker=client)
    await router.submit_order({"ticker": "spy", "side": "BUY", "qty": 2, "limit_price": 500})
    assert router.position_tracker.snapshot() == {"SPY": 2}


def test_distinct_orders_at_same_true_fill_time_remain_separate():
    from services.entry_fills import journal_confirmed_entry
    engine = DuckDBEngine(":memory:")
    init_journal_tables(engine)
    seed = {"ticker": "SPY", "type": "equity", "action": "buy", "strike": 0, "expiry": ""}
    order = {"id": "one", "symbol": "SPY", "side": "buy", "qty": "2", "status": "filled",
             "filled_qty": "2", "filled_avg_price": "500", "filled_at": "2026-09-11T10:00:00Z"}
    try:
        journal_confirmed_entry(engine, seed, order, 2, "SPY", "buy")
        journal_confirmed_entry(engine, seed, {**order, "id": "two"}, 2, "SPY", "buy")
        rows = read_trades(engine)
        assert len(rows) == 2
        assert {r["entry_date"] for r in rows} == {order["filled_at"]}
        assert len({r["broker_order_id"] for r in rows}) == 2
    finally:
        engine._conn.close()


def test_zero_snapshot_after_recorded_fill_requires_reconciliation():
    from services.entry_fills import journal_confirmed_entry
    engine = DuckDBEngine(":memory:")
    init_journal_tables(engine)
    seed = {"ticker": "SPY", "type": "equity", "action": "buy", "strike": 0, "expiry": ""}
    order = {"id": "one", "symbol": "SPY", "side": "buy", "qty": "2",
             "filled_qty": "1", "filled_avg_price": "500"}
    try:
        journal_confirmed_entry(engine, seed, order, 2, "SPY", "buy")
        result = journal_confirmed_entry(engine, seed, {**order, "filled_qty": "0",
            "filled_avg_price": None}, 2, "SPY", "buy")
        assert result["journal_status"] == "reconciliation_required"
        assert read_trades(engine)[0]["quantity"] == "1"
    finally:
        engine._conn.close()
