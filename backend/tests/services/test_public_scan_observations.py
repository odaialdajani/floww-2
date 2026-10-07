"""Dated broad observations are paginated evidence, never current flow."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from services import public_scanner as scanner


def row(ticker, index=0, volume=500):
    return [ticker, f"{ticker}-contract-{index}", "call", 100 + index, "2026-10-16", volume, 100, .3, .5, 100]


def store_type():
    from services.public_scan_observations import PublicScanObservations
    return PublicScanObservations


def pack(ticker, received, rows=None):
    rows = [row(ticker)] if rows is None else rows
    return dict(status="ok", dealer=None, received_ts=received, event_time="2026-10-07T11:00:00+00:00", rows=rows,
                extras={scanner.ckey_of(r[0], r[2], r[3], r[4]): {"mid": 2.5, "volume_data_received_at": received,
                         "volume_source_time": received - 120, "bid_source_time": None} for r in rows},
                selection={"retained_rows": len(rows), "eligible_rows": len(rows), "rows_truncated": False},
                expiries_checked=2, history_status="available", history_capped=False, contract_conflicts=0)


def test_retention_covers_provider_scope_not_latest_five_hundred_or_hundred_results():
    store = store_type()(":memory:")
    try:
        universe = [f"T{i:05}" for i in range(8838)]
        for ticker in universe:
            store.save(ticker, pack(ticker, 1000), scope="provider-options:2")
        pages = [store.page(now=2000, universe=universe, offset=offset, limit=500) for offset in range(0, 8838, 500)]
        assert sum(len(page["rows"]) for page in pages) == 8838
        assert pages[0]["total"] == 8838
        assert pages[0]["coverage"]["observed_tickers"] == 8838
        assert pages[0]["coverage"]["missing_tickers"] == 0
        assert pages[0]["coverage"]["symbol_limit"] >= 8838
        assert pages[-1]["next_offset"] is None
    finally:
        store.close()


def test_saved_rows_extras_and_clocks_survive_restart_and_are_dated(tmp_path):
    path = tmp_path / "broad.sqlite3"
    store = store_type()(path)
    payload = pack("SPY", 1000, [row("SPY", i) for i in range(120)])
    store.save("SPY", payload, scope="provider-options:2")
    store.close()
    reopened = store_type()(path)
    try:
        result = reopened.page(now=2000, universe=["SPY"], limit=500)
        assert result["rows"] == payload["rows"]
        assert result["quote_truth"] == payload["extras"]
        evidence = result["observations_by_ticker"]["SPY"]
        assert evidence["received_at"] == 1000
        assert evidence["event_time"] == payload["event_time"]
        assert evidence["scope"] == "provider-options:2"
        assert evidence["expiries_checked"] == 2
        assert evidence["receipt_age_seconds"] == 1000
        assert evidence["source_age_seconds"] is None  # event clock is later than this synthetic read clock
        assert evidence["source_clock_status"] == "future"
        assert result["coverage"]["stale_tickers"] == 1
        assert result["trade_eligible"] is False
        assert result["live"] is False
    finally:
        reopened.close()


def test_empty_checks_do_not_evict_other_positive_rows_and_failed_check_keeps_previous():
    store = store_type()(":memory:")
    try:
        store.save("SPY", pack("SPY", 1000), scope="provider-options:2")
        for i in range(501):
            store.save(f"N{i}", pack(f"N{i}", 1001 + i, []), scope="provider-options:2")
        store.record_attempt("SPY", 1700, "failed")
        result = store.page(now=1800, universe=["SPY", "UNSEEN", *[f"N{i}" for i in range(501)]])
        assert result["rows"] == [row("SPY")]
        assert result["coverage"]["observed_tickers"] == 502
        assert result["coverage"]["missing_tickers"] == 1
        assert result["coverage"]["zero_result_tickers"] == 501
        assert result["coverage"]["latest_failed_tickers"] == 1
        assert result["observations_by_ticker"]["SPY"]["received_at"] == 1000
        assert result["observations_by_ticker"]["SPY"]["latest_attempt_status"] == "failed"
    finally:
        store.close()


@pytest.mark.asyncio
async def test_first_batch_eta_is_unknown_instead_of_assuming_one_second_pauses(monkeypatch):
    from services.public_budget import PublicBudget
    scanner._reset_state()
    monkeypatch.setattr("services.public_budget.budget", PublicBudget(capacity=60, refill_per_sec=60, max_inflight=99))
    monkeypatch.setattr(scanner, "scan_slice", AsyncMock(return_value={"SPY": pack("SPY", datetime.now(UTC).timestamp())}))
    try:
        result = await scanner.scan_next(slice_size=1, universe=["SPY", "QQQ"])
        assert result["coverage"]["estimated_pass_seconds"] is None
        assert result["coverage"]["pass_estimate_basis"] == "unknown_until_two_batches"
    finally:
        scanner._reset_state()


def test_actual_quote_clocks_are_not_lost_from_scanner_extras():
    received = datetime(2026, 10, 7, 14, 0, tzinfo=UTC).timestamp()
    contract = dict(osi="SPY-contract", type="call", strike=100, expiry="2026-10-16", volume=500, oi=100,
                    bid=2, ask=3, last=3, volume_timestamp=received-120, bid_timestamp=received-2,
                    ask_timestamp=received-1, last_timestamp=received-1)
    _, extras = scanner.unusual_rows_from_chain(dict(ticker="SPY", spot=100, contracts=[contract]), now=received)
    extra = next(iter(extras.values()))
    assert extra["volume_source_time"] == received - 120
    assert extra["bid_source_time"] == received - 2
    assert extra["ask_source_time"] == received - 1
    assert extra["last_source_time"] == received - 1
    assert extra["volume_data_received_at"] == received


@pytest.mark.asyncio
async def test_measured_pass_estimate_includes_six_hundred_second_offhours_pause(monkeypatch):
    from types import SimpleNamespace

    from services.public_budget import PublicBudget
    scanner._reset_state()
    clock = [1000.0]
    monkeypatch.setattr(scanner, "time", SimpleNamespace(time=lambda: clock[0], monotonic=lambda: clock[0]))
    monkeypatch.setattr("services.public_budget.budget", PublicBudget(capacity=100, refill_per_sec=100, max_inflight=99))
    universe = [f"T{i:02}" for i in range(24)]
    async def fetched(tickers, **_):
        return {ticker: pack(ticker, clock[0]) for ticker in tickers}
    monkeypatch.setattr(scanner, "scan_slice", fetched)
    try:
        first = await scanner.scan_next(slice_size=12, universe=universe)
        assert first["coverage"]["estimated_pass_seconds"] is None
        clock[0] += 600
        second = await scanner.scan_next(slice_size=12, universe=universe)
        assert second["coverage"]["estimated_pass_seconds"] == 1200
        assert second["coverage"]["measured_checks_per_second"] == pytest.approx(12/600)
        assert second["coverage"]["pass_estimate_basis"] == "measured_inter_batch_throughput"
        assert len(second["rows"]) == 12  # the fresh lane still expires the earlier batch
        dated = scanner._dated_observations_store().page(now=clock[0], universe=universe)
        assert dated["total"] == 24  # saved observations survive the 60-second live window
        assert dated["coverage"]["stale_tickers"] == 12
    finally:
        scanner._reset_state()


def test_filters_page_counts_and_missing_are_distinct():
    store = store_type()(":memory:")
    try:
        rows = [row("SPY", 0, 500), row("SPY", 1, 5000)]
        rows[1][4] = "2026-10-23"
        store.save("SPY", pack("SPY", 1000, rows), scope="provider-options:2")
        store.save("QQQ", pack("QQQ", 1090, [row("QQQ", 0, 6000)]), scope="provider-options:2")
        page = store.page(now=1100, universe=["SPY", "QQQ", "UNSEEN"], limit=1)
        assert page["total"] == 3 and page["count"] == 1 and page["next_offset"] == 1
        assert page["coverage"]["missing_tickers"] == 1
        assert page["rows"][0][0] == "QQQ"
        second = store.page(now=1100, universe=["SPY", "QQQ", "UNSEEN"], limit=2, offset=1)
        assert second["rows"] == rows and second["next_offset"] is None
        filtered = store.page(now=1100, universe=["SPY", "QQQ"], ticker="spy", min_volume=1000, expiry="2026-10-23", age="stale")
        assert filtered["rows"] == [rows[1]] and filtered["total"] == 1
        assert store.page(now=1100, universe=["SPY"], age="recent")["total"] == 0
        assert store.page(now=1100, universe=["SPY"], contract_type="put")["total"] == 0
        assert store.page(now=1100, universe=["SPY"], scope="provider-options:6")["total"] == 0
        assert store.page(now=1100, universe=["SPY"], offset=99)["next_offset"] is None
        assert store.page(now=1100, universe=[])["coverage"]["observed_tickers"] == 0
    finally:
        store.close()


def test_capacity_does_not_prune_other_stocks_and_unknown_extras_stay_unknown():
    store = store_type()(":memory:", symbol_limit=1)
    try:
        unknown = pack("SPY", 1000)
        unknown["extras"] = {}
        store.save("SPY", unknown, scope="provider-options:2")
        assert store.save("QQQ", pack("QQQ", 1001), scope="provider-options:2") == "symbol_capacity"
        result = store.page(now=1100, universe=["SPY", "QQQ"])
        assert result["rows"] == unknown["rows"]
        assert result["quote_truth"] == {}
        assert result["coverage"]["capacity_covers_current_universe"] is False
        assert result["coverage"]["missing_tickers"] == 1
        evidence = next(iter(result["row_observations"].values()))
        assert evidence["received_at"] == 1000
        assert evidence["volume_source_time"] is None and evidence["volume_clock_status"] == "unknown"
        assert evidence["quote_source_time"] is None and evidence["quote_clock_status"] == "unknown"
        assert evidence["trade_eligible"] is False
    finally:
        store.close()


def test_old_reads_and_old_check_failures_cannot_rewind_saved_evidence():
    store = store_type()(":memory:")
    try:
        newer = pack("SPY", 1000)
        store.save("SPY", newer, scope="provider-options:2")
        assert store.save("SPY", pack("SPY", 999, []), scope="provider-options:2") == "unchanged"
        store.record_attempt("SPY", 1002, "failed")
        store.record_attempt("SPY", 1001, "ok")
        result = store.page(now=1003, universe=["SPY"])
        assert result["rows"] == newer["rows"]
        assert result["observations_by_ticker"]["SPY"]["latest_attempt_status"] == "failed"
        evidence = next(iter(result["row_observations"].values()))
        assert evidence["volume_source_age_seconds"] == 123
        assert evidence["receipt_age_seconds"] == 3
        assert evidence["volume_source_time"] == 880  # never borrowed from receipt time
    finally:
        store.close()


def test_legacy_examples_page_beyond_hundred_and_rich_zero_result_wins():
    from services.scan_findings import ScanFindings
    legacy = ScanFindings(":memory:")
    rich = store_type()(":memory:")
    universe = [f"T{i:03}" for i in range(125)]
    try:
        for name in universe:
            legacy.save(name, 1000, [row(name, i) for i in range(10)])
        assert len(legacy.recent(now=1100)) == 100  # the old endpoint keeps its original cap
        records = legacy.saved_records(now=1100)
        assert len(records) == 125
        rich.save(universe[0], pack(universe[0], 1001, []), scope="provider-options:2")
        pages = [rich.page(now=1100, universe=universe, offset=offset, limit=100, legacy_records=records) for offset in (0, 100, 200, 300)]
        assert pages[0]["total"] == 124 * 3
        rows = [row for page in pages for row in page["rows"]]
        assert len(rows) == 372
        assert universe[0] not in {item[0] for item in rows}
        assert pages[0]["coverage"]["observed_tickers"] == 125
        assert pages[0]["coverage"]["legacy_limited_tickers"] == 124
        assert pages[0]["quote_truth"] == {}
        detail = next(iter(pages[0]["row_observations"].values()))
        assert detail["data_status"] == "legacy_limited"
        assert detail["received_at"] == 1000 and detail["volume_source_time"] is None
        assert detail["quote_extras_available"] is False
        assert pages[0]["legacy_examples_included"] is True
        assert next(item for item in pages[0]["observations_by_ticker"].values())["original_retained_rows"] == 10
    finally:
        legacy.close()
        rich.close()


def test_legacy_read_does_not_create_or_change_its_file(tmp_path):
    import hashlib

    from services.scan_findings import ScanFindings
    path = tmp_path / "legacy.sqlite3"
    store = ScanFindings(path)
    assert store.saved_records(now=2000) == []
    assert not path.exists()
    store.save("SPY", 1000, [row("SPY")])
    store.close()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    assert store.saved_records(now=1100)[0]["received_at"] == 1000
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
    store.close()


def test_payload_and_contract_bounds_do_not_admit_partial_writes():
    store = store_type()(":memory:", payload_limit=1024)
    try:
        large = pack("SPY", 1000, [row("SPY", i) for i in range(20)])
        assert store.save("SPY", large, scope="provider-options:2") == "payload_capacity"
        assert store.page(now=1100, universe=["SPY"])["coverage"]["missing_tickers"] == 1
        assert store.page(now=1100, universe=["SPY"])["coverage"]["payload_bytes"] == 0
        with pytest.raises(ValueError, match="contract bound"):
            store.save("SPY", pack("SPY", 1000, [row("SPY", i) for i in range(121)]), scope="provider-options:2")
    finally:
        store.close()


def test_stock_order_spreads_before_server_cap_and_received_order_keeps_all_rows():
    store = store_type()(":memory:")
    try:
        stock_rows = [row("SPY", i) for i in range(120)]
        store.save("SPY", pack("SPY", 1100, stock_rows), scope="provider-options:2")
        others = [f"T{i:02}" for i in range(10)]
        for name in others:
            store.save(name, pack(name, 1000, [row(name, i) for i in range(3)]), scope="provider-options:2")
        first = store.page(now=1200, universe=["SPY", *others], limit=12)
        assert {record[0] for record in first["rows"]} == {"SPY", *others}
        pages = [store.page(now=1200, universe=["SPY", *others], offset=offset, limit=100) for offset in (0, 100)]
        actual = [tuple(record) for page in pages for record in page["rows"]]
        expected = [tuple(record) for record in stock_rows] + [tuple(row(name, i)) for name in others for i in range(3)]
        assert len(actual) == len(set(actual)) == 150
        assert set(actual) == set(expected)
        received = store.page(now=1200, universe=["SPY", *others], limit=100, order="received")
        assert {record[0] for record in received["rows"]} == {"SPY"}
        assert received["total"] == first["total"] == 150
    finally:
        store.close()
