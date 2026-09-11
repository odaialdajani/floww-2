from datetime import datetime
from zoneinfo import ZoneInfo

import duckdb
import pytest

from services.duckdb_engine import DuckDBEngine
from services.research_data_seam import stored_research_alerts


def test_real_duckdb_columns_timestamp_and_error_contract():
    engine = DuckDBEngine(":memory:")
    try:
        with pytest.raises(duckdb.CatalogException):
            stored_research_alerts(engine.query_strict, "SPY")
        engine.execute_write(
            "CREATE TABLE flow_alerts_daily (under VARCHAR, exp DATE, bias VARCHAR, conviction DOUBLE, asof_ts TIMESTAMP, asof_date DATE)"
        )
        now = datetime.now(ZoneInfo("America/New_York")).replace(microsecond=0)
        engine.execute_write(
            "INSERT INTO flow_alerts_daily VALUES (?, ?, ?, ?, ?, ?)",
            [("SPY", now.date().isoformat(), "BULLISH", 80, now.isoformat(), now.date().isoformat())],
        )
        rows = stored_research_alerts(engine.query_strict, "SPY")
        assert len(rows) == 1
        assert rows[0]["asof_ts"] == now
        assert rows[0]["expiry"] == now.date()
        assert stored_research_alerts(engine.query_strict, "QQQ") == []
    finally:
        engine.close()
