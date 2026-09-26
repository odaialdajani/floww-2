from concurrent.futures import ThreadPoolExecutor
from threading import Event

import duckdb


def test_failed_recording_cannot_rollback_an_acknowledged_engine_write(monkeypatch):
    import services.duckdb_engine as engine_module
    from services.heatmap_history import record_snapshot

    raw = duckdb.connect(":memory:")
    began, release, write_started, write_done = (Event() for _ in range(4))

    class PausedConnection:
        def execute(self, sql, *args, **kwargs):
            if sql == "BEGIN":
                raw.execute(sql)
                began.set()
                assert release.wait(5), "test did not release recording"
                return self
            if sql.startswith("INSERT") and "heatmap_snapshots_v2" in sql:
                raise RuntimeError("controlled snapshot failure")
            raw.execute(sql, *args, **kwargs)
            return self

        def __getattr__(self, name):
            return getattr(raw, name)

    conn = PausedConnection()
    monkeypatch.setattr(engine_module.duckdb, "connect", lambda *a, **kw: conn)
    engine = engine_module.DuckDBEngine()
    engine.execute_write("CREATE TABLE acknowledged_rows (value INTEGER)")

    def ingest():
        write_started.set()
        assert engine.execute_write_bulk("acknowledged_rows", ["value"], [(1,)]) == 1
        write_done.set()

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            recording = pool.submit(record_snapshot, conn, {
                "ticker": "SPY", "asof": "2030-01-02T14:00:00Z", "strikes": [],
            }, "test", "controlled-recording")
            assert began.wait(5)
            writing = pool.submit(ingest)
            assert write_started.wait(5)
            crossed_transaction = write_done.wait(0.2)
            release.set()
            assert recording.result(timeout=5) is None
            writing.result(timeout=5)
        assert raw.execute("SELECT count(*) FROM acknowledged_rows").fetchone()[0] == 1
        assert not crossed_transaction
    finally:
        release.set()
        engine.close()
