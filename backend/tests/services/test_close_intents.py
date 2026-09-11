"""A broker close may mutate only the exact, durably reserved journal rows."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from services.duckdb_engine import DuckDBEngine
from services.journal_store import init_journal_tables, read_trades, save_seeds


@pytest.fixture(autouse=True)
def _reset_event_loop_and_motor():
    """These isolated storage tests do not use the global HTTP/Mongo fixture."""
    yield


def seed(engine, day="2026-09-01", **values):
    row = dict(ticker="SPY", type="equity", action="buy", strike=0.0,
               expiry="", quantity="2", entry_price=500, entry_date=day,
               exit_date="", exit_price="", source="api-alpaca")
    row.update(values)
    assert save_seeds(engine, [row]) == 1


def filled(**values):
    order = dict(id="close-1", symbol="SPY", side="sell", qty="2",
                 filled_qty="2", filled_avg_price="501", status="filled")
    order.update(values)
    return order


@pytest.fixture
def engine():
    eng = DuckDBEngine(":memory:")
    init_journal_tables(eng)
    yield eng
    eng._conn.close()


def reserve(engine):
    from services.close_intents import bind_close_order, prepare_close
    intent = prepare_close(engine, "SPY")
    bind_close_order(engine, intent["intent_id"], "close-1")
    return intent


@pytest.mark.asyncio
async def test_unmatched_order_cannot_close_any_card(engine):
    from routes.alpaca import reconcile_pending_close
    seed(engine, type="call", strike=500, expiry="2026-09-18")
    client = SimpleNamespace(get_order=AsyncMock(return_value=filled(symbol="QQQ")))
    result = await reconcile_pending_close("SPY", "close-1", client=client, engine=engine)
    assert result["journal_closed"] == 0
    assert result["status"] == "reconciliation_exception"
    assert all(not row["exit_date"] for row in read_trades(engine))


def test_fill_closes_zero_strike_equity_once_not_new_rows(engine):
    from services.close_intents import apply_close_fill
    seed(engine)
    reserve(engine)
    first = apply_close_fill(engine, "SPY", "close-1", filled())
    assert first["journal_closed"] == 1
    seed(engine, day="2026-09-02")
    second = apply_close_fill(engine, "SPY", "close-1", filled())
    assert second["journal_closed"] == 0
    assert second["status"] == "reconciled"
    assert len(read_trades(engine, status="open")) == 1


@pytest.mark.parametrize("change", [
    {"symbol": "QQQ"}, {"side": "buy"}, {"id": "entry-order"},
    {"filled_qty": "1"}, {"qty": "3"}, {"filled_avg_price": "nan"},
    {"filled_avg_price": "inf"}, {"filled_avg_price": "0"},
])
def test_mismatched_fill_never_mutates(engine, change):
    from services.close_intents import apply_close_fill
    seed(engine)
    reserve(engine)
    result = apply_close_fill(engine, "SPY", "close-1", filled(**change))
    assert result["status"] == "reconciliation_exception"
    assert len(read_trades(engine, status="open")) == 1


def test_equity_close_does_not_close_options(engine):
    from services.close_intents import apply_close_fill
    seed(engine)
    seed(engine, type="call", strike=500, expiry="2026-09-18")
    reserve(engine)
    assert apply_close_fill(engine, "SPY", "close-1", filled())["journal_closed"] == 1
    assert read_trades(engine, status="open")[0]["type"] == "call"


def test_changed_reserved_row_is_exception_without_partial_write(engine):
    from services.close_intents import apply_close_fill
    seed(engine)
    reserve(engine)
    engine.execute_write("UPDATE flow_journal_trades SET quantity='3'")
    assert apply_close_fill(engine, "SPY", "close-1", filled())["status"] == "reconciliation_exception"
    assert len(read_trades(engine, status="open")) == 1


def test_intent_survives_database_reopen(tmp_path):
    from services.close_intents import apply_close_fill
    filename = str(tmp_path / "journal.duckdb")
    one = DuckDBEngine(filename)
    init_journal_tables(one)
    seed(one)
    reserve(one)
    one._conn.close()
    two = DuckDBEngine(filename)
    try:
        assert apply_close_fill(two, "SPY", "close-1", filled())["journal_closed"] == 1
    finally:
        two._conn.close()


def test_prepared_intent_blocks_duplicate_submission(engine):
    from services.close_intents import prepare_close
    seed(engine)
    first = prepare_close(engine, "SPY")
    second = prepare_close(engine, "SPY")
    assert first["new"] is True
    assert second["new"] is False
    assert second["intent_id"] == first["intent_id"]


def test_pending_order_can_later_reconcile_same_targets(engine):
    from services.close_intents import apply_close_fill
    seed(engine)
    reserve(engine)
    assert apply_close_fill(engine, "SPY", "close-1", filled(status="accepted"))["status"] == "pending_fill"
    assert apply_close_fill(engine, "SPY", "close-1", filled())["journal_closed"] == 1


def test_exact_option_contract_is_resolved(engine):
    from services.close_intents import apply_close_fill, bind_close_order, prepare_close
    seed(engine, type="call", strike=500, expiry="2026-09-18")
    symbol = "SPY260918C00500000"
    intent = prepare_close(engine, symbol)
    bind_close_order(engine, intent["intent_id"], "close-1")
    assert apply_close_fill(engine, symbol, "close-1", filled(symbol=symbol))["journal_closed"] == 1


@pytest.mark.parametrize("status", ["canceled", "expired", "rejected"])
@pytest.mark.parametrize("executed", ["1", None, "nan", "-1", "inf"])
def test_terminal_order_with_nonzero_or_unknown_fill_keeps_reservation(engine, status, executed):
    from services.close_intents import apply_close_fill, prepare_close
    seed(engine)
    original = reserve(engine)
    result = apply_close_fill(engine, "SPY", "close-1", filled(status=status, filled_qty=executed))
    assert result["status"] == "reconciliation_exception"
    assert len(read_trades(engine, status="open")) == 1
    retry = prepare_close(engine, "SPY")
    assert retry["new"] is False
    assert retry["intent_id"] == original["intent_id"]


@pytest.mark.parametrize("status", ["canceled", "expired", "rejected"])
def test_terminal_order_with_verified_zero_fill_releases_reservation(engine, status):
    from services.close_intents import apply_close_fill, prepare_close
    seed(engine)
    original = reserve(engine)
    result = apply_close_fill(engine, "SPY", "close-1", filled(status=status, filled_qty="0"))
    assert result["status"] == "canceled"
    assert len(read_trades(engine, status="open")) == 1
    retry = prepare_close(engine, "SPY")
    assert retry["new"] is True
    assert retry["intent_id"] != original["intent_id"]
