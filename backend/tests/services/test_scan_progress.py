"""Fair pass progress survives restart without turning bookkeeping into quotes."""
import asyncio
import sqlite3
import time
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from services import public_scanner as scanner
from services.scan_progress import ScanProgress
from tests.offline_network import deny_external_network  # noqa: F401


@pytest.mark.asyncio
async def test_scanner_restart_continues_after_completed_names(tmp_path, monkeypatch):
    path = tmp_path / "progress.sqlite3"
    monkeypatch.setenv("FLOWW_PUBLIC_PROGRESS_PATH", str(path))
    seen = []

    async def scan(names, max_expiries=2):
        seen.extend(names)
        return {name: {"status": "ok", "received_ts": time.time(), "rows": [], "extras": {}, "dealer": None}
                for name in names}

    scanner._reset_state()
    monkeypatch.setattr(scanner, "_progress_store", None, raising=False)
    monkeypatch.setattr(scanner, "scan_slice", scan)
    try:
        await scanner.scan_next(slice_size=2, universe=["SPY", "QQQ", "AAA", "ZZZ"])
        scanner._reset_state()
        monkeypatch.setattr(scanner, "_progress_store", None, raising=False)
        await scanner.scan_next(slice_size=2, universe=["SPY", "QQQ", "AAA", "ZZZ"])
        assert seen == ["SPY", "QQQ", "AAA", "ZZZ"]
    finally:
        scanner._reset_state()


def test_peek_has_no_store_provider_or_lock_side_effects(monkeypatch):
    scanner._reset_state()
    monkeypatch.setattr(scanner, "_observations_store", lambda: pytest.fail("peek opened observations"))
    monkeypatch.setattr(scanner, "_recent_findings_store", lambda: pytest.fail("peek opened findings"))
    monkeypatch.setattr(scanner, "scan_next", AsyncMock(side_effect=AssertionError("peek scanned")))
    assert scanner.peek_scan_view() is None
    monkeypatch.setattr(scanner, "_last_completed_view", {
        "columns": ["unsafe"], "rows": [["SPY", "contract", "call", 100, "2030-01-04", 200]],
        "quote_truth": {}, "dealer": {}, "coverage": {"received_at_by_ticker": {"SPY": 100},
                                                       "fresh": 1, "fresh_window_seconds": 60},
    })
    view = scanner.peek_scan_view(now=161)
    assert view["columns"] == scanner.SCAN_COLUMNS
    assert view["rows"] == [] and view["coverage"]["fresh"] == 0
    view["coverage"]["fresh"] = 999
    assert scanner._last_completed_view["coverage"]["fresh"] == 1


def outcome(now, status="ok"):
    return {"status": status, "received_ts": now} if status == "ok" else {"status": status}


def test_interrupted_claims_join_behind_unvisited_names_and_old_tokens_cannot_finish(tmp_path):
    path = tmp_path / "progress.sqlite3"
    first = ScanProgress(path, lease_seconds=10)
    lost = first.claim("full", ["SPY", "QQQ", "AAA", "ZZZ"], 2, 100)
    first.close()
    restored = ScanProgress(path, lease_seconds=10)
    try:
        claims = restored.claim("full", ["SPY", "QQQ", "AAA", "ZZZ"], 2, 111)
        assert list(claims) == ["AAA", "ZZZ"]
        assert not restored.finish("full", "SPY", lost["SPY"], outcome(111), 111)
        for name, token in claims.items():
            assert restored.finish("full", name, token, outcome(111), 111)
        assert list(restored.claim("full", ["SPY", "QQQ", "AAA", "ZZZ"], 2, 112)) == ["SPY", "QQQ"]
    finally:
        restored.close()


def test_day_rollover_and_directory_reorder_preserve_pending_order(tmp_path):
    path = tmp_path / "progress.sqlite3"
    store = ScanProgress(path)
    claims = store.claim("full", ["SPY", "QQQ", "AAA", "ZZZ"], 2, 100)
    for name, token in claims.items():
        store.finish("full", name, token, outcome(100), 100)
    store.close()
    restored = ScanProgress(path)
    try:
        assert list(restored.claim("full", ["ZZZ", "AAA", "QQQ", "SPY"], 2, 100 + 86400)) == ["AAA", "ZZZ"]
        assert restored.snapshot("full")["pass_id"] == 1
    finally:
        restored.close()


def test_directory_additions_append_and_removed_names_retire_only_metadata():
    store = ScanProgress(":memory:")
    try:
        claims = store.claim("full", ["SPY", "QQQ", "AAA", "ZZZ"], 1, 100)
        store.finish("full", "SPY", claims["SPY"], outcome(100), 100)
        assert list(store.claim("full", ["NEW", "AAA", "SPY", "ZZZ"], 3, 101)) == ["AAA", "ZZZ", "NEW"]
        assert "QQQ" not in store.members("full")
        assert store.snapshot("full")["pass_id"] == 1
    finally:
        store.close()


def test_unavailable_or_older_directory_never_erases_or_reintroduces_members():
    store = ScanProgress(":memory:")
    try:
        store.claim("full", ["SPY", "AAA"], 0, 100, directory_at=100)
        store.claim("full", ["AAA", "NEW"], 0, 101, directory_at=101)
        store.claim("full", [], 0, 102, authoritative=False)
        store.claim("full", ["SPY", "AAA"], 0, 103, directory_at=100)
        assert store.members("full") == ["AAA", "NEW"]
        assert store.snapshot("full")["directory_at"] == 101
    finally:
        store.close()


def test_budget_deferrals_do_not_complete_measurement_or_starve_unvisited():
    store = ScanProgress(":memory:")
    try:
        claim = store.claim("full", ["SPY", "AAA", "ZZZ"], 1, 100)
        store.finish("full", "SPY", claim["SPY"], {"status": "deferred", "retry_after": 5}, 100)
        assert list(store.claim("full", ["SPY", "AAA", "ZZZ"], 2, 101)) == ["AAA", "ZZZ"]
        stats = store.snapshot("full")
        assert stats["attempted_in_pass"] == stats["succeeded_in_pass"] == 0
        assert stats["deferred"] == 1 and stats["pending"] == 3
        assert store.attempts("full") == {}
    finally:
        store.close()


def test_failed_names_complete_an_attempt_then_retry_on_the_next_fair_pass():
    store = ScanProgress(":memory:")
    try:
        claims = store.claim("full", ["SPY", "AAA"], 2, 100)
        store.finish("full", "SPY", claims["SPY"], outcome(100, "failed"), 100)
        store.finish("full", "AAA", claims["AAA"], outcome(100), 100)
        stats = store.snapshot("full")
        assert stats["pass_complete"] and stats["failed_in_pass"] == stats["succeeded_in_pass"] == 1
        assert list(store.claim("full", ["SPY", "AAA"], 2, 101)) == ["SPY", "AAA"]
        assert store.snapshot("full")["pass_id"] == 2
    finally:
        store.close()


def test_two_connections_cannot_duplicate_claims_or_erase_another_scope(tmp_path):
    path = tmp_path / "progress.sqlite3"
    first, second = ScanProgress(path), ScanProgress(path)
    try:
        one = first.claim("full", ["SPY", "QQQ", "AAA", "ZZZ"], 2, 100)
        two = second.claim("full", ["SPY", "QQQ", "AAA", "ZZZ"], 2, 100)
        assert set(one).isdisjoint(two) and set(one) | set(two) == {"SPY", "QQQ", "AAA", "ZZZ"}
        second.claim("override", ["SPY"], 1, 100)
        assert set(first.members("full")) == {"SPY", "QQQ", "AAA", "ZZZ"}
        first.renew("full", one["SPY"], 200)
        assert second.claim("full", ["SPY", "QQQ", "AAA", "ZZZ"], 1, 301) == {}
    finally:
        first.close()
        second.close()


def test_earlier_bookkeeping_fields_extend_without_resetting_a_saved_queue(tmp_path):
    path = tmp_path / "earlier-progress.sqlite3"
    store = ScanProgress(path)
    claims = store.claim("full", ["SPY", "QQQ", "AAA"], 1, 100)
    store.finish("full", "SPY", claims["SPY"], outcome(100), 100)
    store.close()
    with sqlite3.connect(path) as conn:
        conn.execute("ALTER TABLE scan_scope DROP COLUMN directory_at")
        conn.execute("ALTER TABLE scan_name DROP COLUMN attempt_status")
    restored = ScanProgress(path)
    try:
        assert list(restored.claim("full", ["SPY", "QQQ", "AAA"], 1, 101)) == ["QQQ"]
        assert restored.snapshot("full")["directory_at"] is None
        assert restored.attempts("full")["SPY"]["status"] is None
    finally:
        restored.close()


@pytest.mark.asyncio
async def test_corrupt_or_unwritable_progress_is_visible_without_new_chain_reads(tmp_path, monkeypatch):
    path = tmp_path / "corrupt.sqlite3"
    path.write_text("not a database")
    scanner._reset_state()
    scanner._progress_store = ScanProgress(path)
    read = AsyncMock(side_effect=AssertionError("provider must stay paused"))
    monkeypatch.setattr(scanner, "scan_slice", read)
    try:
        view = await scanner.scan_next(universe=["SPY", "AAA"])
        assert view["coverage"]["progress"]["status"] == "unavailable"
        read.assert_not_called()
        assert path.read_text() == "not a database"
        monkeypatch.setattr(scanner._progress_store, "claim", lambda *a, **kw: (_ for _ in ()).throw(OSError("unwritable")))
        view = await scanner.scan_next(universe=["SPY", "AAA"])
        assert view["coverage"]["progress"]["status"] == "unavailable"
        read.assert_not_called()
    finally:
        scanner._reset_state()


@pytest.mark.asyncio
async def test_provider_directory_is_full_option_scope_without_favorites_or_row_limit(tmp_path, monkeypatch):
    from services import market_catalog

    names = ["SPY"] + [f"T{i:05d}" for i in range(350)]
    monkeypatch.delenv("FLOWW_PUBLIC_UNIVERSE", raising=False)
    monkeypatch.setattr(market_catalog, "get_catalog", AsyncMock(return_value={"complete_provider_catalog": True, "stale": False,
                                                                             "asof": "2026-10-06T14:00:00Z", "total": 400}))
    monkeypatch.setattr(market_catalog, "cached_scan_symbols", lambda: names)
    scanner._reset_state()
    scanner._progress_store = ScanProgress(tmp_path / "provider-progress.sqlite3")
    seen = []

    async def scan(tickers, max_expiries=2):
        seen.extend(tickers)
        return {ticker: {"status": "failed"} for ticker in tickers}

    monkeypatch.setattr(scanner, "scan_slice", scan)
    try:
        view = await scanner.scan_next(slice_size=2)
        assert view["coverage"]["universe"] == view["coverage"]["eligible_option_tickers"] == 351
        assert view["coverage"]["provider_listed_tickers"] == 400
        assert view["coverage"]["scope_kind"] == "provider_option_enabled"
        assert view["coverage"]["progress"]["pending"] == 349
        assert len(view["tickers"]) == 351 and seen == names[:2]
        monkeypatch.setattr(market_catalog, "get_catalog", AsyncMock(return_value={"complete_provider_catalog": False, "stale": True, "asof": None, "total": 0}))
        monkeypatch.setattr(market_catalog, "cached_scan_symbols", lambda: [])
        unavailable = await scanner.scan_next(slice_size=2)
        assert unavailable["coverage"]["progress"]["status"] == "awaiting_directory"
        assert unavailable["coverage"]["progress"]["pending"] == 349
        assert seen == names[:2]
    finally:
        scanner._reset_state()


@pytest.mark.asyncio
async def test_budget_refusal_stays_deferred_and_never_becomes_fresh(monkeypatch):
    from services.public_budget import BudgetExhausted

    scanner._reset_state()
    monkeypatch.setattr("services.public_api_adapter.fetch_chain_from_public_api", AsyncMock(side_effect=BudgetExhausted(reason="token_bucket")))
    try:
        view = await scanner.scan_next(slice_size=1, universe=["SPY", "AAA"])
        coverage = view["coverage"]
        assert coverage["progress"]["deferred"] == 1 and coverage["progress"]["succeeded_in_pass"] == 0
        assert coverage["attempted"] == coverage["fresh"] == 0
        assert coverage["never_scanned"] == 2
    finally:
        scanner._reset_state()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["write", "lost_lease"])
async def test_failed_checkpoint_stops_queued_provider_dispatch(monkeypatch, failure):
    from services.public_budget import PublicBudget

    scanner._reset_state()
    store = scanner._progress_store
    if failure == "write":
        monkeypatch.setattr(store, "finish", lambda *a, **kw: (_ for _ in ()).throw(OSError("simulated unavailable progress")))
    else:
        monkeypatch.setattr(store, "finish", lambda *a, **kw: False)
    monkeypatch.setattr(scanner, "_get_adv", None)
    monkeypatch.setattr("services.public_budget.budget", PublicBudget(capacity=60, refill_per_sec=0, max_inflight=99))
    original = scanner.scan_slice
    seen = []

    async def serial(names, max_expiries=2):
        return await original(names, max_expiries=max_expiries, concurrency=1)

    async def fetch(ticker, max_expiries=2, **kwargs):
        seen.append(ticker)
        return {"ticker": ticker, "spot": 100, "contracts": [], "stale": False,
                "fetched_at": datetime.now(UTC).isoformat()}

    monkeypatch.setattr(scanner, "scan_slice", serial)
    monkeypatch.setattr("services.public_api_adapter.fetch_chain_from_public_api", fetch)
    try:
        view = await scanner.scan_next(slice_size=6, universe=["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"])
        assert seen == ["AAA"]
        assert view["coverage"]["fresh"] == view["coverage"]["attempted"] == 1
        assert view["coverage"]["progress"]["status"] == "unavailable"
        assert view["coverage"]["progress"]["succeeded_in_pass"] == 0
    finally:
        scanner._reset_state()


@pytest.mark.asyncio
async def test_failed_lease_renewal_pauses_queue_without_cancelling_started_read(monkeypatch):
    from services.public_budget import PublicBudget

    scanner._reset_state()
    store = scanner._progress_store
    store.lease_seconds = .03
    monkeypatch.setattr(store, "renew", lambda *a, **kw: (_ for _ in ()).throw(OSError("simulated lost renewal")))
    monkeypatch.setattr(scanner, "_get_adv", None)
    monkeypatch.setattr("services.public_budget.budget", PublicBudget(capacity=60, refill_per_sec=0, max_inflight=99))
    original = scanner.scan_slice
    captured, seen = {}, []
    started, release = asyncio.Event(), asyncio.Event()
    received = datetime.now(UTC).isoformat()

    async def serial(names, max_expiries=2):
        captured["context"] = scanner._progress_context.get()
        return await original(names, max_expiries=max_expiries, concurrency=1)

    async def fetch(ticker, max_expiries=2, **kwargs):
        seen.append(ticker)
        if ticker == "AAA":
            started.set()
            await release.wait()
        return {"ticker": ticker, "spot": 100, "contracts": [], "stale": False, "fetched_at": received}

    monkeypatch.setattr(scanner, "scan_slice", serial)
    monkeypatch.setattr("services.public_api_adapter.fetch_chain_from_public_api", fetch)
    task = asyncio.create_task(scanner.scan_next(slice_size=3, universe=["AAA", "BBB", "CCC"]))
    try:
        await asyncio.wait_for(started.wait(), 1)
        for _ in range(100):
            if captured["context"]["error"] is not None:
                break
            await asyncio.sleep(.002)
        assert captured["context"]["error"] == "SCAN_PROGRESS_UNAVAILABLE"
        assert seen == ["AAA"] and not task.done()
        release.set()
        view = await asyncio.wait_for(task, 1)
        assert seen == ["AAA"]
        assert scanner._slices["AAA"]["ts"] == datetime.fromisoformat(received).timestamp()
        assert view["coverage"]["fresh"] == 1
        assert view["coverage"]["progress"]["status"] == "unavailable"
    finally:
        release.set()
        if not task.done():
            await task
        scanner._reset_state()
