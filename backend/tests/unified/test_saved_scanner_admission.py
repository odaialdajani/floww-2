"""U07: saved dated scanner observations admitted separately from fresh scans.

Isolated tmp-store counterexamples; no provider/network calls; no expansion of
legacy example rows into fabricated history.
"""
import time

import pytest

from services.public_scan_observations import DEFAULT_MAX_AGE_SECONDS, ROWS_PER_SYMBOL, PublicScanObservations


def _row(ticker, ordinal, volume=1000.0):
    return [ticker, ordinal, "call", 165.0 + ordinal, "2026-10-16", volume,
            1.0, 2.0, 1.5, 0.01]


def _pack(ticker="AAA", received=None, rows=1, extras=True, history_status="available"):
    rows = [_row(ticker, i) for i in range(rows)]
    extra_map = {}
    if extras:
        for row in rows:
            key = f"{row[0]}|{row[2]}|{float(row[3]):g}|{row[4]}"
            extra_map[key] = {"volume_source_time": "2026-10-06T15:00:00Z"}
    return {"received_ts": received if received is not None else time.time(),
            "status": "ok", "rows": rows, "extras": extra_map,
            "event_time": "2026-10-06T20:00:00Z", "source": "public_api",
            "history_status": history_status, "selection": {}}


@pytest.fixture
def store(tmp_path):
    s = PublicScanObservations(str(tmp_path / "scan.db"))
    yield s
    s.close()


def test_save_then_page_preserves_original_receipt_and_source_clocks(store):
    received = time.time() - 3600
    assert store.save("AAA", _pack(received=received), scope="rotating") == "saved"
    page = store.page(now=time.time())
    meta = page["observations_by_ticker"]["AAA"]
    assert meta["receipt_clock_status"] == "known"
    assert meta["source_clock_status"] == "known"
    assert page["live"] is False
    assert page["trade_eligible"] is False
    assert abs(meta["receipt_age_seconds"] - 3600) < 5


def test_older_receipt_never_overwrites_newer_dated_rows(store):
    assert store.save("AAA", _pack(received=2000.0), scope="rotating") == "saved"
    assert store.save("AAA", _pack(received=1000.0), scope="rotating") == "unchanged"
    assert store.save("AAA", _pack(received=3000.0), scope="rotating") == "saved"


def test_duplicate_contract_identity_refused(store):
    pack = _pack(rows=2)
    pack["rows"][1] = list(pack["rows"][0])  # identical identity key
    with pytest.raises(ValueError):
        store.save("AAA", pack, scope="rotating")


def test_non_ok_and_malformed_packs_refused(store):
    with pytest.raises(ValueError):
        store.save("AAA", {**_pack(), "status": "failed"}, scope="rotating")
    with pytest.raises(ValueError):
        store.save("AAA", {**_pack(), "received_ts": "not-a-clock"}, scope="rotating")


def test_row_bound_refused_not_truncated(store):
    with pytest.raises(ValueError):
        store.save("AAA", _pack(rows=ROWS_PER_SYMBOL + 1), scope="rotating")


def test_missing_extras_marked_partial_not_complete(store):
    pack = _pack(rows=2)
    pack["extras"] = {}  # no quote extras for any row
    assert store.save("AAA", pack, scope="rotating") == "saved"
    page = store.page(now=time.time())
    meta = page["observations_by_ticker"]["AAA"]
    assert meta["data_status"] == "partial"
    assert meta["missing_quote_extras"] == 2
    assert meta["missing_volume_source_clocks"] == 2
    assert page["coverage"]["partial_tickers"] == 1


def test_failure_and_capacity_attempt_states_are_separate_checks(store, tmp_path):
    assert store.record_attempt("AAA", time.time(), "failed", "timeout") == "saved"
    with pytest.raises(ValueError):
        store.record_attempt("AAA", time.time(), "mysterious")
    capped = PublicScanObservations(str(tmp_path / "capped.db"), symbol_limit=1)
    assert capped.record_attempt("AAA", time.time(), "ok") == "saved"
    assert capped.record_attempt("BBB", time.time(), "ok") == "symbol_capacity"
    capped.close()


def test_future_receipt_marked_future_not_known(store):
    store.save("AAA", _pack(received=time.time() + 7200), scope="rotating")
    page = store.page(now=time.time())
    # future-dated receipts are excluded from page candidates entirely,
    # and counted as unknown-clock — never served as current rows
    assert page["rows"] == []
    assert page["coverage"]["receipt_clock_unknown_tickers"] == 1


def test_paging_filters_are_bounded_and_validated(store):
    store.save("AAA", _pack(), scope="rotating")
    with pytest.raises(ValueError):
        store.page(offset=-1)
    with pytest.raises(ValueError):
        store.page(limit=0)
    with pytest.raises(ValueError):
        store.page(max_age_seconds=DEFAULT_MAX_AGE_SECONDS + 1)
    page = store.page(universe={"OTHER"})
    assert page["rows"] == []
    assert page["total"] == 0
