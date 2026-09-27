"""Preserve legacy journal rows while giving venue fills durable identities."""
import json

import duckdb
import pytest

from services.close_intents import apply_close_fill, bind_close_order, prepare_close
from services.duckdb_engine import DuckDBEngine
from services.entry_fills import journal_confirmed_entry
from services.journal_store import (
    _JOURNAL_DDL,
    close_trade,
    init_journal_tables,
    journal_seed_key,
    read_trades,
    save_seeds,
)


@pytest.fixture(autouse=True)
def _reset_event_loop_and_motor():
    """Only an in-memory journal is used by these migration tests."""
    yield


@pytest.fixture
def engine():
    eng = DuckDBEngine(":memory:")
    yield eng
    eng._conn.close()


def seed():
    return {"ticker": "SPY", "type": "equity", "action": "buy", "strike": 0,
            "expiry": "", "quantity": "2", "entry_price": 500,
            "entry_date": "2026-09-11T10:00:00Z", "source": "legacy-test"}


def broker_fill(engine, identity):
    row = seed()
    order = {"id": identity, "symbol": "SPY", "side": "buy", "qty": "2",
             "filled_qty": "2", "filled_avg_price": "500", "filled_at": row["entry_date"]}
    return journal_confirmed_entry(engine, row, order, 2, "SPY", "buy")


def legacy_table(engine):
    # Exactly the previous table key: no broker identity column.
    old = _JOURNAL_DDL.replace("        broker_order_id TEXT NOT NULL DEFAULT '',\n", "")
    old = old.replace("entry_date, broker_order_id)", "entry_date)")
    engine.execute_write(old)
    engine.execute_write("INSERT INTO flow_journal_trades "
        "(ckey,ticker,type,action,strike,expiry,quantity,entry_price,entry_date,notes,source) "
        "VALUES ('legacy-key','SPY','equity','buy',0,'','2',500,'2026-09-11T10:00:00Z','keep me','legacy-test')")


def test_migration_preserves_all_legacy_values_and_six_part_key(engine):
    legacy_table(engine)
    columns = [r[1] for r in engine._conn.execute("PRAGMA table_info('flow_journal_trades')").fetchall()]
    before = engine._conn.execute("SELECT * FROM flow_journal_trades").fetchall()
    init_journal_tables(engine)
    init_journal_tables(engine)
    after = engine._conn.execute(f"SELECT {','.join(columns)} FROM flow_journal_trades").fetchall()
    assert after == before
    legacy = read_trades(engine)[0]
    assert legacy["broker_order_id"] == ""
    assert len(journal_seed_key(legacy).split("|")) == 6
    broker_fill(engine, "one")
    assert len(read_trades(engine)) == 2
    assert close_trade(engine, journal_seed_key(legacy), exit_price=501, exit_date="2026-09-11")
    rows = read_trades(engine)
    assert [r["source"] for r in rows if r["exit_date"]] == ["legacy-test"]
    assert next(r for r in rows if r["broker_order_id"])["exit_date"] == ""


def test_failed_migration_rolls_back_without_changing_old_table(engine):
    legacy_table(engine)
    engine.execute_write("ALTER TABLE flow_journal_trades ADD COLUMN custom_legacy_note TEXT DEFAULT 'keep extra'")
    before = engine._conn.execute("SELECT * FROM flow_journal_trades").fetchall()
    with pytest.raises(duckdb.BinderException, match="custom_legacy_note"):
        init_journal_tables(engine)
    assert engine._conn.execute("SELECT * FROM flow_journal_trades").fetchall() == before
    assert "broker_order_id" not in [r[1] for r in engine._conn.execute("PRAGMA table_info('flow_journal_trades')").fetchall()]


def test_broker_key_closes_exactly_one_same_time_fill(engine):
    init_journal_tables(engine)
    broker_fill(engine, "one")
    broker_fill(engine, "two")
    first = next(r for r in read_trades(engine) if r["broker_order_id"].endswith("one"))
    assert len(journal_seed_key(first).split("|")) == 7
    assert close_trade(engine, journal_seed_key(first), exit_price=501, exit_date="2026-09-11")
    closed = [r for r in read_trades(engine) if r["exit_date"]]
    assert len(closed) == 1 and closed[0]["broker_order_id"] == first["broker_order_id"]


def test_reserved_close_keeps_both_same_time_fills_and_closes_each_once(engine):
    init_journal_tables(engine)
    broker_fill(engine, "one")
    broker_fill(engine, "two")
    intent = prepare_close(engine, "SPY")
    bind_close_order(engine, intent["intent_id"], "close-1")
    fill = {"id": "close-1", "symbol": "SPY", "side": "sell", "qty": "4",
            "filled_qty": "4", "filled_avg_price": "501", "status": "filled"}
    assert apply_close_fill(engine, "SPY", "close-1", fill)["journal_closed"] == 2
    assert apply_close_fill(engine, "SPY", "close-1", fill)["journal_closed"] == 0


def test_old_reservation_cannot_acquire_a_new_same_time_broker_fill(engine):
    init_journal_tables(engine)
    save_seeds(engine, [seed()])
    intent = prepare_close(engine, "SPY")
    targets = json.loads(engine._conn.execute("SELECT targets FROM paper_close_intents").fetchone()[0])
    for row in targets:
        del row["broker_order_id"]
    engine._conn.execute("UPDATE paper_close_intents SET targets=?", [json.dumps(targets)])
    bind_close_order(engine, intent["intent_id"], "close-1")
    broker_fill(engine, "new")
    fill = {"id": "close-1", "symbol": "SPY", "side": "sell", "qty": "2",
            "filled_qty": "2", "filled_avg_price": "501", "status": "filled"}
    assert apply_close_fill(engine, "SPY", "close-1", fill)["journal_closed"] == 1
    assert next(r for r in read_trades(engine) if r["broker_order_id"])["exit_date"] == ""


def test_migrated_identity_survives_file_reopen(tmp_path):
    path = str(tmp_path / "isolated-journal.duckdb")
    first = DuckDBEngine(path)
    try:
        legacy_table(first)
        init_journal_tables(first)
        broker_fill(first, "one")
        broker_fill(first, "two")
        before = read_trades(first)
    finally:
        first._conn.close()
    reopened = DuckDBEngine(path)
    try:
        init_journal_tables(reopened)
        after = read_trades(reopened)
        assert after == before
        assert len(after) == 3
        assert {r["entry_date"] for r in after} == {"2026-09-11T10:00:00Z"}
        assert {r["broker_order_id"] for r in after} == {"", "alpaca-order:one", "alpaca-order:two"}
    finally:
        reopened._conn.close()


def test_unknown_broker_fill_time_stays_unknown(engine):
    init_journal_tables(engine)
    order = {"id": "known-fill-unknown-time", "symbol": "SPY", "side": "buy", "qty": "2",
             "filled_qty": "1", "filled_avg_price": "500", "filled_at": None}
    journal_confirmed_entry(engine, seed(), order, 2, "SPY", "buy")
    row = read_trades(engine)[0]
    assert row["quantity"] == "1" and row["entry_price"] == 500
    assert row["entry_date"] == ""
