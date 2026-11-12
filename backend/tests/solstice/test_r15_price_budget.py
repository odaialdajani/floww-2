"""The price producer returns only its own PublicBudget job slot, never tokens."""

import asyncio
from datetime import UTC, datetime

import duckdb
import pytest

from services import heatmap_history
from services import solstice_price_producer as producer
from services.public_budget import PublicBudget


class CountingBudget(PublicBudget):
    def __init__(self, *, capacity=8, max_inflight=1):
        super().__init__(capacity=capacity, refill_per_sec=0, max_inflight=max_inflight)
        self.releases = 0

    def release(self):
        self.releases += 1
        super().release()


@pytest.fixture
def conn():
    with duckdb.connect(":memory:", config={"threads": 1}) as connection:
        heatmap_history.ensure_tables(connection)
        yield connection


def observation(symbol, at=100):
    return {"ticker": symbol, "price": 500, "source": "synthetic-public-mid",
            "event_time": datetime.fromtimestamp(at, UTC).isoformat(),
            "fetched_at": datetime.fromtimestamp(at + 0.4, UTC).isoformat()}


def price_producer(conn, budget, fetch, *, symbols=("SPY",), session_gate=None):
    return producer.PricePathProducer(
        conn=conn, symbols=list(symbols), budget=budget, fetch_one=fetch,
        session_gate=session_gate or (lambda symbol, now: (True, "open")))


def test_one_slot_budget_serves_both_symbols_and_later_ticks(conn):
    """Missing release must not starve the next symbol or next scheduled tick."""
    budget = CountingBudget()
    calls = []

    def fetch(symbol):
        assert budget.status()["inflight"] == 1
        calls.append(symbol)
        return observation(symbol, 100 + len(calls))

    instance = price_producer(conn, budget, fetch, symbols=("SPY", "QQQ"))
    assert instance.tick(110)["written"] == 2
    assert instance.tick(111)["written"] == 2
    assert calls == ["SPY", "QQQ", "SPY", "QQQ"]
    assert budget.status()["inflight"] == 0
    assert budget.status()["available"] == 4  # four tokens remain spent
    assert budget.releases == 4
    assert conn.execute("SELECT ticker, at_ts, received_at FROM price_paths_v1 ORDER BY at_ts").fetchall() == [
        ("SPY", 101.0, "1970-01-01T00:01:41.400000+00:00"),
        ("QQQ", 102.0, "1970-01-01T00:01:42.400000+00:00"),
        ("SPY", 103.0, "1970-01-01T00:01:43.400000+00:00"),
        ("QQQ", 104.0, "1970-01-01T00:01:44.400000+00:00"),
    ]


@pytest.mark.parametrize(("case", "counter"), [
    ("fetch_error", "gaps"), ("non_dict", "gaps"), ("invalid_price", "gaps"),
    ("missing_event", "gaps"), ("duplicate", "duplicates"),
    ("store_false", "gaps"), ("store_error", "errors"),
])
def test_non_success_paths_release_only_the_acquired_slot(conn, monkeypatch, case, counter):
    budget = CountingBudget()
    if case == "duplicate":
        assert heatmap_history.record_price_path(conn, "SPY", 100, 500, "fixture")

    def fetch(symbol):
        if case == "fetch_error":
            raise ConnectionError("synthetic unavailable quote")
        if case == "non_dict":
            return None
        value = observation(symbol)
        if case == "invalid_price":
            value["price"] = float("nan")
        if case == "missing_event":
            value["event_time"] = None
        return value

    def failed_write(*args, **kwargs):
        if case == "store_error":
            raise RuntimeError("synthetic rejected commit")
        return False

    with monkeypatch.context() as patch:
        if case in {"store_false", "store_error"}:
            patch.setattr(heatmap_history, "record_price_path", failed_write)
        instance = price_producer(conn, budget, fetch)
        assert instance.tick(101)[counter] == 1
    assert budget.status()["inflight"] == 0
    assert budget.status()["available"] == 7
    assert budget.releases == 1
    instance.fetch_one = lambda symbol: observation(symbol, 200)
    assert instance.tick(201)["written"] == 1
    assert budget.status()["available"] == 6
    assert budget.releases == 2


@pytest.mark.parametrize("asynchronous", [False, True])
def test_cancelled_fetch_propagates_after_returning_owned_slot(conn, asynchronous):
    budget = CountingBudget()

    def cancelled(symbol):
        raise asyncio.CancelledError()

    async def async_cancelled(symbol):
        raise asyncio.CancelledError()

    instance = price_producer(conn, budget, async_cancelled if asynchronous else cancelled)
    with pytest.raises(asyncio.CancelledError):
        instance.tick(101)
    assert budget.status()["inflight"] == 0
    assert budget.status()["available"] == 7
    assert budget.releases == 1
    instance.fetch_one = lambda symbol: observation(symbol)
    assert instance.tick(102)["written"] == 1


@pytest.mark.parametrize("reason", ["inflight", "tokens", "closed"])
def test_unadmitted_symbol_never_returns_a_peers_slot(conn, reason):
    budget = CountingBudget(capacity=1 if reason == "tokens" else 8,
                            max_inflight=2 if reason == "tokens" else 1)
    asyncio.run(budget.acquire_n(1, "api.public.com"))  # another job owns this slot

    def forbidden_fetch(symbol):
        pytest.fail("unadmitted/closed producer must not fetch")

    gate = (lambda symbol, now: (False, "closed")) if reason == "closed" else None
    instance = price_producer(conn, budget, forbidden_fetch, session_gate=gate)
    try:
        result = instance.tick(101)
        assert result["closed_skips" if reason == "closed" else "budget_refusals"] == 1
        assert budget.status()["inflight"] == 1
        assert budget.status()["available"] == (0 if reason == "tokens" else 7)
        assert budget.releases == 0
    finally:
        budget.release()  # the peer's owner performs its cleanup


def test_budget_without_acquisition_method_cannot_release_a_peer(conn):
    peer = CountingBudget()
    asyncio.run(peer.acquire_n(1, "api.public.com"))

    class NoAdmission:
        release = peer.release

    try:
        instance = price_producer(conn, NoAdmission(), lambda symbol: observation(symbol))
        assert instance.tick(101)["written"] == 1
        assert peer.status()["inflight"] == 1
        assert peer.releases == 0
    finally:
        peer.release()


def test_replacing_budget_during_fetch_returns_the_original_owned_slot(conn):
    owned, peer = CountingBudget(), CountingBudget()
    asyncio.run(peer.acquire_n(1, "api.public.com"))

    def fetch(symbol):
        instance.budget = peer
        return observation(symbol)

    instance = price_producer(conn, owned, fetch)
    try:
        assert instance.tick(101)["written"] == 1
        assert owned.status()["inflight"] == 0
        assert owned.releases == 1
        assert peer.status()["inflight"] == 1
        assert peer.releases == 0
    finally:
        peer.release()


@pytest.mark.asyncio
async def test_async_admission_not_driven_inside_running_loop_cannot_borrow_peer_slot(conn):
    budget = CountingBudget()
    await budget.acquire_n(1, "api.public.com")

    def forbidden_fetch(symbol):
        pytest.fail("unsupported running-loop admission must fail closed before fetch")

    try:
        instance = price_producer(conn, budget, forbidden_fetch)
        assert instance.tick(101)["budget_refusals"] == 1
        assert instance.errors == 1
        assert budget.status()["inflight"] == 1
        assert budget.status()["available"] == 7
        assert budget.releases == 0
    finally:
        budget.release()
