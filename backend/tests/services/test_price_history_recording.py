import duckdb

from routes.price_history import recording_summary
from services.heatmap_history import ensure_tables


def test_recording_summary_uses_actual_storage_and_ticker(tmp_path):
    class Engine:
        def __init__(self, location):
            self.conn = duckdb.connect(location)
            ensure_tables(self.conn)

        def query_strict(self, sql, args):
            result = self.conn.execute(sql, args)
            columns = [c[0] for c in result.description]
            return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]

    for location, durable in ((":memory:", False), (str(tmp_path / "history.duckdb"), True)):
        engine = Engine(location)
        try:
            engine.conn.execute("INSERT INTO heatmap_snapshots_v2 (snapshot_id,ticker,asof_ts) VALUES "
                                "('a','SPY','2026-10-06T09:00:00+00:00'),"
                                "('b','QQQ','2026-10-01T09:00:00+00:00')")
            result = recording_summary(engine, "SPY")
            assert result["durable"] is durable
            assert result["count"] == 1
            assert result["first_at"].day == 6
            assert recording_summary(engine, "IWM")["count"] == 0
        finally:
            engine.conn.close()
