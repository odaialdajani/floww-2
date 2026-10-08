"""OpenCode probe slice for U07 (claim in docs/unified/U07/OPENCODE-CLAIM.md).

ScanFindings dated-observation semantics on isolated :memory: stores.
No source edits, no provider calls.
"""
from services.scan_findings import ScanFindings


def store():
    return ScanFindings(":memory:")


def test_examples_capped_at_three_not_a_tape():
    db = store()
    db.save("SPY", 1000.0, [{"id": i} for i in range(10)])
    rows = db.saved_records(now=2000.0)
    assert len(rows) == 1
    assert rows[0]["contracts"] == 10
    assert len(rows[0]["examples"]) == 3


def test_stale_write_never_overwrites_newer():
    db = store()
    db.save("SPY", 2000.0, [{"id": "new"}])
    db.save("SPY", 1000.0, [{"id": "stale"}])
    rows = db.saved_records(now=3000.0)
    assert rows[0]["examples"] == [{"id": "new"}]


def test_window_bounds_exclude_future_and_expired():
    db = store()
    db.save("OLD", 1000.0, [{"id": 1}])
    db.save("GOOD", 8 * 86400.0, [{"id": 2}])
    db.save("FUTURE", 9 * 86400.0 + 100.0, [{"id": 3}])
    now = 9 * 86400.0
    tickers = [r["ticker"] for r in db.recent(now=now)]
    assert "GOOD" in tickers
    assert "OLD" not in tickers and "FUTURE" not in tickers


def test_recent_caps_at_100_saved_records_goes_further():
    db = store()
    for i in range(150):
        db.save(f"T{i:03d}", float(1000 + i), [{"id": i}])
    now = 2000.0
    assert len(db.recent(now=now)) == 100
    assert len(db.saved_records(now=now)) == 150


def test_recent_drops_zero_contract_rows():
    db = store()
    db.save("EMPTY", 1000.0, [])
    assert db.recent(now=2000.0) == []
