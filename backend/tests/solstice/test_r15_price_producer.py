"""R15-2: default-off scheduled price-path producer — focused contract tests.

No live calls, no activation, no worker start on import. All transport/session/
budget seams are injected fakes. Storage uses the REAL heatmap_history seam
(record_price_path / price_paths_since / outcome_close_tick / replay_snapshot)
on throwaway DuckDB handles (memory + temp files for reopen proof).

Source of truth: docs/solstice/MUSE_STATE.md R15-2 (contract price-path-producer.v1).
"""

import sys

sys.path.insert(0, "backend")

import os
import tempfile
from datetime import UTC, datetime

import duckdb
import pytest

from services.heatmap_history import (
    ensure_tables,
    outcome_close_tick,
    price_paths_since,
    record_decision,
    record_price_path,
    record_snapshot,
    replay_snapshot,
)


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat()


def _obs(ticker: str, at_epoch: float, price: float, source: str = "public-mid"):
    fetched = _iso(at_epoch + 0.4)
    return {
        "ticker": ticker,
        "price": price,
        "event_time": _iso(at_epoch),
        "fetched_at": fetched,
        "source": source,
    }


def test_producer_is_default_off_without_flag():
    import services.solstice_price_producer as prod

    assert os.environ.get("FLOWW_PRICE_PATH_PRODUCER", "") != "1"
    receipt = prod.start_worker()
    assert receipt["started"] is False
    assert receipt["worker_state"] in ("absent", "wired_off")
    assert "FLOWW_PRICE_PATH_PRODUCER" in receipt["reason"]
    prod.stop_worker()


def test_producer_refuses_without_capture_or_store():
    import services.solstice_price_producer as prod

    prod.stop_worker()
    # Even with flag, no fetch + no conn is a clear refusal, never a silent no-op.
    os.environ["FLOWW_PRICE_PATH_PRODUCER"] = "1"
    try:
        receipt = prod.start_worker()
        assert receipt["started"] is False
        assert receipt["reason"] in ("no capture registered", "no store registered")
    finally:
        os.environ.pop("FLOWW_PRICE_PATH_PRODUCER", None)
        prod.stop_worker()


def test_tick_writes_one_point_per_symbol_with_vendor_time():
    import services.solstice_price_producer as prod

    conn = duckdb.connect(":memory:")
    ensure_tables(conn)
    seen = [_obs("SPY", 1_700_000_000.0, 500.25), _obs("QQQ", 1_700_000_000.0, 410.10)]

    def fetch(symbol):
        for o in seen:
            if o["ticker"] == symbol:
                return dict(o)
        return None

    p = prod.PricePathProducer(
        conn=conn,
        symbols=["SPY", "QQQ"],
        cadence_s=300,
        fetch_one=fetch,
        session_gate=lambda sym, now: (True, "open"),
    )
    out = p.tick(now_epoch=1_700_000_000.5)
    assert out["written"] == 2
    assert out["gaps"] == 0
    spy = price_paths_since(conn, "SPY")
    assert spy == [(1_700_000_000.0, 500.25)]
    # Vendor observation time (at_ts) differs from fetch time (received_at).
    rows = conn.execute(
        "SELECT at_ts, received_at, source FROM price_paths_v1 WHERE ticker='SPY'"
    ).fetchall()
    assert float(rows[0][0]) == 1_700_000_000.0
    assert rows[0][1] == _iso(1_700_000_000.0 + 0.4)
    assert rows[0][2] == "public-mid"


def test_duplicate_observation_is_idempotent():
    import services.solstice_price_producer as prod

    conn = duckdb.connect(":memory:")
    ensure_tables(conn)
    o = _obs("SPY", 1_700_000_100.0, 501.0)
    p = prod.PricePathProducer(
        conn=conn,
        symbols=["SPY"],
        fetch_one=lambda sym: dict(o),
        session_gate=lambda sym, now: (True, "open"),
    )
    first = p.tick(now_epoch=1_700_000_100.5)
    second = p.tick(now_epoch=1_700_000_101.5)
    assert first["written"] == 1
    assert second["written"] == 0
    assert second["duplicates"] == 1
    assert price_paths_since(conn, "SPY") == [(1_700_000_100.0, 501.0)]


def test_stale_out_of_order_points_are_stored_ordered_and_counted():
    import services.solstice_price_producer as prod

    conn = duckdb.connect(":memory:")
    ensure_tables(conn)
    points = [_obs("SPY", 200.0, 500.0), _obs("SPY", 100.0, 499.0)]

    def fetch(sym):
        return dict(points.pop(0)) if points else None

    p = prod.PricePathProducer(
        conn=conn, symbols=["SPY"], fetch_one=fetch,
        session_gate=lambda sym, now: (True, "open"),
    )
    p.tick(now_epoch=201.0)
    out = p.tick(now_epoch=202.0)
    assert out["written"] == 1
    assert out["out_of_order"] == 1
    # Storage never drops: ordered read returns both, sorted by at_ts.
    assert price_paths_since(conn, "SPY") == [(100.0, 499.0), (200.0, 500.0)]


def test_partial_write_counts_gaps_without_losing_successes():
    import services.solstice_price_producer as prod

    conn = duckdb.connect(":memory:")
    ensure_tables(conn)

    def fetch(sym):
        if sym == "SPY":
            return _obs("SPY", 300.0, 502.0)
        return None  # QQQ gap: no observation this tick

    p = prod.PricePathProducer(
        conn=conn, symbols=["SPY", "QQQ"], fetch_one=fetch,
        session_gate=lambda sym, now: (True, "open"),
    )
    out = p.tick(now_epoch=301.0)
    assert out["written"] == 1 and out["gaps"] == 1
    assert price_paths_since(conn, "SPY") == [(300.0, 502.0)]
    assert price_paths_since(conn, "QQQ") == []


def test_closed_session_skips_without_fabrication():
    import services.solstice_price_producer as prod

    conn = duckdb.connect(":memory:")
    ensure_tables(conn)
    calls = []

    def fetch(sym):
        calls.append(sym)
        return _obs(sym, 400.0, 503.0)

    p = prod.PricePathProducer(
        conn=conn, symbols=["SPY"], fetch_one=fetch,
        session_gate=lambda sym, now: (False, "EXCHANGE_HOLIDAY"),
    )
    out = p.tick(now_epoch=401.0)
    assert out["written"] == 0
    assert out["closed_skips"] == 1
    assert calls == []  # no provider call when the session is closed
    assert price_paths_since(conn, "SPY") == []


def test_nonfinite_and_missing_prices_become_gaps():
    import services.solstice_price_producer as prod

    conn = duckdb.connect(":memory:")
    ensure_tables(conn)
    bad = [
        _obs("SPY", 500.0, float("nan")),
        _obs("SPY", 501.0, float("inf")),
        {"ticker": "SPY", "price": None, "event_time": _iso(502.0),
         "fetched_at": _iso(502.4), "source": "public-mid"},
    ]

    def fetch(sym):
        return dict(bad.pop(0)) if bad else None

    p = prod.PricePathProducer(
        conn=conn, symbols=["SPY"], fetch_one=fetch,
        session_gate=lambda sym, now: (True, "open"),
    )
    assert p.tick(now_epoch=503.0)["gaps"] == 1
    assert p.tick(now_epoch=504.0)["gaps"] == 1
    assert p.tick(now_epoch=505.0)["gaps"] == 1
    assert price_paths_since(conn, "SPY") == []


def test_writer_contention_four_threads_no_loss():
    import threading

    import services.solstice_price_producer as prod

    conn = duckdb.connect(":memory:")
    ensure_tables(conn)
    p = prod.PricePathProducer(
        conn=conn, symbols=["SPY"],
        fetch_one=lambda sym: None,
        session_gate=lambda sym, now: (True, "open"),
    )
    errors = []

    def write_batch(base):
        try:
            for i in range(5):
                ok = record_price_path(conn, "SPY", float(base + i), 500.0 + i, "test")
                assert ok is True
        except Exception as exc:  # noqa: BLE001 — collected, asserted below
            errors.append(exc)

    threads = [threading.Thread(target=write_batch, args=(1000 + 100 * k,)) for k in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(price_paths_since(conn, "SPY")) == 20
    # Producer tick serializes on the same single-writer lock.
    p.tick(now_epoch=5000.0)
    assert p.health()["errors"] == 0


def test_restart_creates_new_generation_without_duplicating_history():
    import services.solstice_price_producer as prod

    conn = duckdb.connect(":memory:")
    ensure_tables(conn)
    p = prod.PricePathProducer(
        conn=conn, symbols=["SPY"],
        fetch_one=lambda sym: _obs("SPY", 600.0, 504.0),
        session_gate=lambda sym, now: (True, "open"),
    )
    gen1 = p.generation
    p.tick(now_epoch=601.0)
    p2 = prod.PricePathProducer(
        conn=conn, symbols=["SPY"],
        fetch_one=lambda sym: _obs("SPY", 600.0, 504.0),  # same observation
        session_gate=lambda sym, now: (True, "open"),
    )
    assert p2.generation != gen1
    out = p2.tick(now_epoch=602.0)
    assert out["duplicates"] == 1  # history survives restart, no rewrite
    assert price_paths_since(conn, "SPY") == [(600.0, 504.0)]


def test_duplicate_startup_returns_already_running_once():
    import services.solstice_price_producer as prod

    prod.stop_worker()
    conn = duckdb.connect(":memory:")
    ensure_tables(conn)
    os.environ["FLOWW_PRICE_PATH_PRODUCER"] = "1"
    try:
        prod.register_store(conn)
        prod.register_capture(
            symbols=["SPY"],
            fetch_one=lambda sym: None,
            session_gate=lambda sym, now: (True, "open"),
        )
        first = prod.start_worker()
        second = prod.start_worker()
        assert first["started"] is True
        assert second["started"] is False
        assert second["reason"] == "already running"
    finally:
        os.environ.pop("FLOWW_PRICE_PATH_PRODUCER", None)
        prod.stop_worker()
        prod._reset_for_tests()


def test_second_process_reopens_file_db_with_identical_paths_and_replay():
    import services.solstice_price_producer as prod

    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/price_paths.duckdb"
        conn1 = duckdb.connect(path)
        ensure_tables(conn1)
        sid = record_snapshot(conn1, {
            "ticker": "SPY", "snapshot_id": "s-reopen", "asof": _iso(700.0),
            "spot": 500.0, "contracts": [], "strikes": [], "walls": [],
            "metrics": {}, "quality": {}, "scenarios": [], "interactions": [],
            "coverage": {}, "expiries_used": [], "data_source": "t",
            "exposure_basis": "OI", "formula_version": "gex.v2"}, "q", "s-reopen")
        did = record_decision(conn1, {
            "ticker": "SPY", "snapshot_id": "s-reopen", "scenario": "CALLS",
            "side": "CALLS", "eligible": True, "reason_codes": [],
            "features": {"spot": 500.0, "zone": [498, 502], "target": 505.0,
                         "stop": 495.0, "horizon_s": 60,
                         "policy_version": "research_barriers.v1"}})
        p = prod.PricePathProducer(
            conn=conn1, symbols=["SPY"],
            fetch_one=lambda sym: _obs("SPY", 700.0, 500.0),
            session_gate=lambda sym, now: (True, "open"),
        )
        assert p.tick(now_epoch=701.0)["written"] == 1
        before_paths = price_paths_since(conn1, "SPY")
        assert replay_snapshot(conn1, "s-reopen") is not None
        conn1.close()  # producer exits; file persists

        # Second process (new connection) reopens the same file.
        conn2 = duckdb.connect(path, read_only=False)
        after_paths = price_paths_since(conn2, "SPY")
        after_replay = replay_snapshot(conn2, "s-reopen")
        assert after_paths == before_paths == [(700.0, 500.0)]
        assert after_replay is not None
        assert after_replay["snapshot"]["snapshot_id"] == "s-reopen"
        # Stored paths drive the deterministic outcome worker after reopen.
        for t, price in [(710.0, 501.0), (720.0, 506.0)]:
            assert record_price_path(conn2, "SPY", t, price, "public-mid") is True
        out = outcome_close_tick(conn2, "SPY")
        assert did in out["closed"]
        assert sid == "s-reopen"
        conn2.close()


def test_migration_old_db_gains_price_paths_table():
    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE heatmap_snapshots_v2 (snapshot_id VARCHAR PRIMARY KEY)")
    conn.execute("INSERT INTO heatmap_snapshots_v2 VALUES ('legacy-1')")
    ensure_tables(conn)
    assert record_price_path(conn, "SPY", 800.0, 505.0, "public-mid") is True
    assert price_paths_since(conn, "SPY") == [(800.0, 505.0)]
    assert conn.execute("SELECT COUNT(*) FROM heatmap_snapshots_v2").fetchone()[0] == 1


def test_budget_refusal_skips_without_error():
    import services.solstice_price_producer as prod

    conn = duckdb.connect(":memory:")
    ensure_tables(conn)

    class _RefusingBudget:
        async def acquire_n(self, n, host="public", now=None):
            from services.public_budget import BudgetExhausted

            raise BudgetExhausted(retry_after=5, reason="token_bucket")

    p = prod.PricePathProducer(
        conn=conn, symbols=["SPY"],
        fetch_one=lambda sym: _obs("SPY", 900.0, 506.0),
        session_gate=lambda sym, now: (True, "open"),
        budget=_RefusingBudget(),
        budget_host="api.public.com",
    )
    out = p.tick(now_epoch=901.0)
    assert out["written"] == 0
    assert out["budget_refusals"] == 1
    assert price_paths_since(conn, "SPY") == []


def test_health_reports_cadence_latency_and_refusal_contract():
    import services.solstice_price_producer as prod

    conn = duckdb.connect(":memory:")
    ensure_tables(conn)
    p = prod.PricePathProducer(
        conn=conn, symbols=["SPY", "QQQ"], cadence_s=300,
        fetch_one=lambda sym: _obs(sym, 1000.0, 507.0),
        session_gate=lambda sym, now: (True, "open"),
    )
    p.tick(now_epoch=1001.0)
    h = p.health()
    assert h["version"] == "price-path-producer.v1"
    assert h["cadence_s"] == 300
    assert h["symbols"] == ["SPY", "QQQ"]
    assert h["captures"] == 2
    assert h["enabled"] is False  # flag unset in this test process
    assert h["policy"] == "swing-5min; NOT intraminute-0DTE"
    assert h["last_latency_ms"] is not None
    assert h["durable"] is False  # :memory: store never claims durable


def test_five_minute_path_cannot_claim_intraminute_resolution():
    import services.solstice_price_producer as prod

    assert prod.RESOLUTION_CLAIM == "5min-swing-only"
    assert "0DTE-intraminute" in prod.RESOLUTION_LIMIT
