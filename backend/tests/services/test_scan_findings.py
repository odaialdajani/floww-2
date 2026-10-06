from services.scan_findings import ScanFindings


def test_findings_survive_restart_and_expire(tmp_path):
    path = tmp_path / "findings.sqlite3"
    store = ScanFindings(path)
    rows = [["SPY", "contract", "call", 600, "2026-10-09", 500, 100]] * 8
    store.save("SPY", 1000000, rows)
    store.close()
    restored = ScanFindings(path)
    try:
        assert restored.recent(1000061) == [{"ticker": "SPY", "received_at": 1000000,
                                           "contracts": 8, "examples": rows[:3]}]
        assert restored.recent(1000000 + 8 * 86400) == []
    finally:
        restored.close()


def test_new_empty_result_clears_obsolete_findings_and_old_reads_cannot_rewind():
    store = ScanFindings(":memory:")
    try:
        store.save("SPY", 100, [["SPY"]])
        store.save("SPY", 101, [])
        store.save("SPY", 99, [["SPY"]])
        assert store.recent(102) == []
    finally:
        store.close()


def test_universe_filter_runs_before_display_limit():
    store = ScanFindings(":memory:")
    try:
        store.save("SPY", 1000, [["SPY"]])
        for i in range(100):
            store.save(f"T{i}", 1001 + i, [[f"T{i}"]])
        assert len(store.recent(2000)) == 100
        assert [item["ticker"] for item in store.recent(2000, ["SPY"])] == ["SPY"]
        assert store.recent(2000, []) == []
    finally:
        store.close()
