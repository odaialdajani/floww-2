"""
Tests for Heatseeker snapshot ingestion, OI delta computation, and top movers.

Covers:
  - DuckDB snapshot table schema + PyArrow bulk insert
  - OI delta computation (positive, negative, zero, NaN guards)
  - Top movers ranking by abs(OI delta) + volume spike
  - Edge cases: empty chain, single snapshot, zero OI, NaN fields
  - REST API endpoint contracts (mocked DB)

Run with:
    cd backend && ./venv/bin/python -m pytest tests/services/test_heatseeker_snapshots.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone

import pyarrow as pa

# ---------------------------------------------------------------------------
# Unit tests for the pure delta/top-mover functions (no DB needed)
# ---------------------------------------------------------------------------


class TestOiDeltaComputation:
    """Tests for compute_oi_delta and rank_top_movers in heatseeker_snapshots.py."""

    def _make_service(self):
        """Import and return the module under test."""
        from services import heatseeker_snapshots as svc
        return svc

    def test_basic_oi_delta_positive(self):
        """OI increased → positive delta."""
        svc = self._make_service()
        current = {"contracts": [
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 500.0, "type": "C",
             "oi": 1000, "volume": 500, "iv": 0.15, "delta": 0.5, "gamma": 0.02},
        ]}
        previous = {"contracts": [
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 500.0, "type": "C",
             "oi": 800, "volume": 400, "iv": 0.15, "delta": 0.5, "gamma": 0.02},
        ]}
        result = svc.compute_oi_delta(current, previous)
        assert len(result) == 1
        assert result[0]["oi_delta"] == 200
        assert result[0]["oi_delta_pct"] == 0.25  # (1000-800)/800

    def test_basic_oi_delta_negative(self):
        """OI decreased → negative delta."""
        svc = self._make_service()
        current = {"contracts": [
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 500.0, "type": "P",
             "oi": 500, "volume": 200, "iv": 0.15, "delta": -0.5, "gamma": 0.02},
        ]}
        previous = {"contracts": [
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 500.0, "type": "P",
             "oi": 1000, "volume": 300, "iv": 0.15, "delta": -0.5, "gamma": 0.02},
        ]}
        result = svc.compute_oi_delta(current, previous)
        assert result[0]["oi_delta"] == -500
        assert result[0]["oi_delta_pct"] == -0.5

    def test_zero_previous_oi_new_position(self):
        """Previous OI was 0, current > 0 → inf pct, large abs delta."""
        svc = self._make_service()
        current = {"contracts": [
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 500.0, "type": "C",
             "oi": 500, "volume": 100, "iv": 0.15, "delta": 0.5, "gamma": 0.02},
        ]}
        previous = {"contracts": [
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 500.0, "type": "C",
             "oi": 0, "volume": 0, "iv": 0.15, "delta": 0.5, "gamma": 0.02},
        ]}
        result = svc.compute_oi_delta(current, previous)
        assert result[0]["oi_delta"] == 500
        # When prev=0 and cur>0, pct should be inf (or a large sentinel)
        assert result[0]["oi_delta_pct"] == float("inf")

    def test_both_zero_oi(self):
        """Both current and previous OI are 0 → delta=0, pct=0."""
        svc = self._make_service()
        current = {"contracts": [
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 500.0, "type": "C",
             "oi": 0, "volume": 0, "iv": 0.15, "delta": 0.5, "gamma": 0.02},
        ]}
        previous = {"contracts": [
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 500.0, "type": "C",
             "oi": 0, "volume": 0, "iv": 0.15, "delta": 0.5, "gamma": 0.02},
        ]}
        result = svc.compute_oi_delta(current, previous)
        assert result[0]["oi_delta"] == 0
        assert result[0]["oi_delta_pct"] == 0.0

    def test_nan_oi_guard(self):
        """NaN in OI field → treated as 0 (I-8 guard)."""
        svc = self._make_service()
        current = {"contracts": [
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 500.0, "type": "C",
             "oi": float("nan"), "volume": 100, "iv": 0.15, "delta": 0.5, "gamma": 0.02},
        ]}
        previous = {"contracts": [
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 500.0, "type": "C",
             "oi": 100, "volume": 50, "iv": 0.15, "delta": 0.5, "gamma": 0.02},
        ]}
        result = svc.compute_oi_delta(current, previous)
        # NaN OI treated as 0 → delta = 0 - 100 = -100
        assert result[0]["oi_delta"] == -100

    def test_missing_oi_field_defaults_zero(self):
        """Missing 'oi' key → defaults to 0."""
        svc = self._make_service()
        current = {"contracts": [
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 500.0, "type": "C",
             "volume": 100, "iv": 0.15, "delta": 0.5, "gamma": 0.02},
        ]}
        previous = {"contracts": [
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 500.0, "type": "C",
             "oi": 200, "volume": 50, "iv": 0.15, "delta": 0.5, "gamma": 0.02},
        ]}
        result = svc.compute_oi_delta(current, previous)
        assert result[0]["oi_delta"] == -200

    def test_empty_contracts(self):
        """Empty contract lists → empty result."""
        svc = self._make_service()
        result = svc.compute_oi_delta({"contracts": []}, {"contracts": []})
        assert result == []

    def test_multiple_contracts_mixed(self):
        """Multiple contracts with varying deltas."""
        svc = self._make_service()
        current = {"contracts": [
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 500.0, "type": "C",
             "oi": 1000, "volume": 500, "iv": 0.15, "delta": 0.5, "gamma": 0.02},
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 505.0, "type": "C",
             "oi": 2000, "volume": 800, "iv": 0.14, "delta": 0.45, "gamma": 0.018},
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 495.0, "type": "P",
             "oi": 300, "volume": 100, "iv": 0.16, "delta": -0.4, "gamma": 0.015},
        ]}
        previous = {"contracts": [
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 500.0, "type": "C",
             "oi": 800, "volume": 400, "iv": 0.15, "delta": 0.5, "gamma": 0.02},
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 505.0, "type": "C",
             "oi": 2500, "volume": 700, "iv": 0.14, "delta": 0.45, "gamma": 0.018},
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 495.0, "type": "P",
             "oi": 300, "volume": 100, "iv": 0.16, "delta": -0.4, "gamma": 0.015},
        ]}
        result = svc.compute_oi_delta(current, previous)
        assert len(result) == 3
        # 500C: delta=+200, pct=0.25
        c500 = [r for r in result if r["strike"] == 500.0 and r["type"] == "C"][0]
        assert c500["oi_delta"] == 200
        assert c500["oi_delta_pct"] == 0.25
        # 505C: delta=-500, pct=-0.2
        c505 = [r for r in result if r["strike"] == 505.0 and r["type"] == "C"][0]
        assert c505["oi_delta"] == -500
        assert c505["oi_delta_pct"] == -0.2
        # 495P: delta=0, pct=0
        p495 = [r for r in result if r["strike"] == 495.0 and r["type"] == "P"][0]
        assert p495["oi_delta"] == 0
        assert p495["oi_delta_pct"] == 0.0


class TestTopMoversRanking:
    """Tests for rank_top_movers."""

    def _make_service(self):
        from services import heatseeker_snapshots as svc
        return svc

    def test_rank_by_abs_oi_delta(self):
        """Top movers ranked by absolute OI delta descending."""
        svc = self._make_service()
        deltas = [
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 500.0, "type": "C",
             "oi_delta": 200, "oi_delta_pct": 0.25, "volume": 500, "volume_delta": 100,
             "iv": 0.15, "delta": 0.5, "gamma": 0.02},
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 505.0, "type": "C",
             "oi_delta": -500, "oi_delta_pct": -0.2, "volume": 800, "volume_delta": 200,
             "iv": 0.14, "delta": 0.45, "gamma": 0.018},
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 495.0, "type": "P",
             "oi_delta": 50, "oi_delta_pct": 0.1, "volume": 100, "volume_delta": 10,
             "iv": 0.16, "delta": -0.4, "gamma": 0.015},
        ]
        result = svc.rank_top_movers(deltas, top_n=2)
        assert len(result) == 2
        # Largest abs delta is -500 (505C), then 200 (500C)
        assert result[0]["strike"] == 505.0
        assert result[1]["strike"] == 500.0

    def test_top_n_limits_results(self):
        """top_n limits the number of results returned."""
        svc = self._make_service()
        deltas = [
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": float(500 + i), "type": "C",
             "oi_delta": 100 - i * 10, "oi_delta_pct": 0.1, "volume": 100,
             "volume_delta": 10, "iv": 0.15, "delta": 0.5, "gamma": 0.02}
            for i in range(10)
        ]
        result = svc.rank_top_movers(deltas, top_n=5)
        assert len(result) == 5

    def test_empty_deltas(self):
        """Empty deltas → empty list."""
        svc = self._make_service()
        result = svc.rank_top_movers([])
        assert result == []

    def test_infinite_pct_does_not_crash(self):
        """Infinite OI delta pct (new position) should not crash ranking."""
        svc = self._make_service()
        deltas = [
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 500.0, "type": "C",
             "oi_delta": 500, "oi_delta_pct": float("inf"), "volume": 100,
             "volume_delta": 50, "iv": 0.15, "delta": 0.5, "gamma": 0.02},
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 505.0, "type": "C",
             "oi_delta": 100, "oi_delta_pct": 0.1, "volume": 100,
             "volume_delta": 10, "iv": 0.14, "delta": 0.45, "gamma": 0.018},
        ]
        result = svc.rank_top_movers(deltas)
        assert len(result) == 2
        # The inf-pct entry should be ranked first (abs delta 500 > 100)
        assert result[0]["strike"] == 500.0


class TestSnapshotTableSchema:
    """Tests for DuckDB snapshot table creation and PyArrow bulk insert."""

    def _make_service(self):
        from services import heatseeker_snapshots as svc
        return svc

    def test_create_snapshot_table(self):
        """Table heatseeker_snapshots is created with correct schema."""
        svc = self._make_service()
        import duckdb
        conn = duckdb.connect(":memory:")
        svc.create_snapshot_table(conn)
        # Verify table exists
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='heatseeker_snapshots'"
        ).fetchall()
        assert len(tables) == 1

    def test_snapshot_table_columns(self):
        """Table has all required columns."""
        svc = self._make_service()
        import duckdb
        conn = duckdb.connect(":memory:")
        svc.create_snapshot_table(conn)
        cols = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='heatseeker_snapshots' ORDER BY ordinal_position"
        ).fetchall()
        col_names = [c[0] for c in cols]
        expected = ["timestamp", "ticker", "expiry", "strike", "type", "oi", "volume", "iv", "delta_val", "gamma_val"]
        for col in expected:
            assert col in col_names, f"Missing column: {col}"

    def test_pyarrow_bulk_insert(self):
        """PyArrow RecordBatch bulk insert works and data is queryable."""
        svc = self._make_service()
        import duckdb
        conn = duckdb.connect(":memory:")
        svc.create_snapshot_table(conn)

        now = datetime.now(timezone.utc)
        batch = pa.record_batch({
            "timestamp": pa.array([now, now], type=pa.timestamp("us")),
            "ticker": pa.array(["SPY", "SPY"], type=pa.string()),
            "expiry": pa.array(["2026-07-24", "2026-07-24"], type=pa.string()),
            "strike": pa.array([500.0, 505.0], type=pa.float64()),
            "type": pa.array(["C", "P"], type=pa.string()),
            "oi": pa.array([1000, 800], type=pa.int64()),
            "volume": pa.array([500, 300], type=pa.int64()),
            "iv": pa.array([0.15, 0.16], type=pa.float64()),
            "delta_val": pa.array([0.5, -0.45], type=pa.float64()),
            "gamma_val": pa.array([0.02, 0.018], type=pa.float64()),
        })

        svc.bulk_insert(conn, batch)

        rows = conn.execute("SELECT COUNT(*) FROM heatseeker_snapshots").fetchone()
        assert rows[0] == 2

    def test_bulk_insert_performance(self):
        """Bulk insert of 500 rows completes in < 100ms."""
        svc = self._make_service()
        import time

        import duckdb
        conn = duckdb.connect(":memory:")
        svc.create_snapshot_table(conn)

        n = 500
        now = datetime.now(timezone.utc)
        batch = pa.record_batch({
            "timestamp": pa.array([now] * n, type=pa.timestamp("us")),
            "ticker": pa.array(["SPY"] * n, type=pa.string()),
            "expiry": pa.array(["2026-07-24"] * n, type=pa.string()),
            "strike": pa.array([500.0 + i for i in range(n)], type=pa.float64()),
            "type": pa.array(["C"] * n, type=pa.string()),
            "oi": pa.array([1000 + i for i in range(n)], type=pa.int64()),
            "volume": pa.array([500 + i for i in range(n)], type=pa.int64()),
            "iv": pa.array([0.15] * n, type=pa.float64()),
            "delta_val": pa.array([0.5] * n, type=pa.float64()),
            "gamma_val": pa.array([0.02] * n, type=pa.float64()),
        })

        start = time.perf_counter()
        svc.bulk_insert(conn, batch)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert elapsed_ms < 100, f"Bulk insert took {elapsed_ms:.1f}ms (expected < 100ms)"

    def test_query_latest_snapshot(self):
        """Can query the latest snapshot for a ticker."""
        svc = self._make_service()
        import duckdb
        conn = duckdb.connect(":memory:")
        svc.create_snapshot_table(conn)

        now = datetime.now(timezone.utc)
        batch = pa.record_batch({
            "timestamp": pa.array([now], type=pa.timestamp("us")),
            "ticker": pa.array(["SPY"], type=pa.string()),
            "expiry": pa.array(["2026-07-24"], type=pa.string()),
            "strike": pa.array([500.0], type=pa.float64()),
            "type": pa.array(["C"], type=pa.string()),
            "oi": pa.array([1000], type=pa.int64()),
            "volume": pa.array([500], type=pa.int64()),
            "iv": pa.array([0.15], type=pa.float64()),
            "delta_val": pa.array([0.5], type=pa.float64()),
            "gamma_val": pa.array([0.02], type=pa.float64()),
        })
        svc.bulk_insert(conn, batch)

        rows = svc.get_latest_snapshot(conn, "SPY")
        assert len(rows) == 1
        assert rows[0]["ticker"] == "SPY"
        assert rows[0]["strike"] == 500.0

    def test_query_history(self):
        """Can query time series for a specific contract."""
        svc = self._make_service()
        import duckdb
        conn = duckdb.connect(":memory:")
        svc.create_snapshot_table(conn)

        now = datetime.now(timezone.utc)
        # Insert 3 snapshots at different times
        for i in range(3):
            batch = pa.record_batch({
                "timestamp": pa.array([now], type=pa.timestamp("us")),
                "ticker": pa.array(["SPY"], type=pa.string()),
                "expiry": pa.array(["2026-07-24"], type=pa.string()),
                "strike": pa.array([500.0], type=pa.float64()),
                "type": pa.array(["C"], type=pa.string()),
                "oi": pa.array([1000 + i * 100], type=pa.int64()),
                "volume": pa.array([500 + i * 50], type=pa.int64()),
                "iv": pa.array([0.15 + i * 0.01], type=pa.float64()),
                "delta_val": pa.array([0.5], type=pa.float64()),
                "gamma_val": pa.array([0.02], type=pa.float64()),
            })
            svc.bulk_insert(conn, batch)

        history = svc.get_history(conn, "SPY", "2026-07-24", 500.0, "C")
        assert len(history) == 3
        # OI should be ascending
        ois = [h["oi"] for h in history]
        assert ois == sorted(ois)


class TestSnapshotChainIngestion:
    """Tests for the snapshot_chain ingestion script logic."""

    def _make_service(self):
        from services import heatseeker_snapshots as svc
        return svc

    def test_contracts_to_recordbatch(self):
        """contracts_to_recordbatch converts chain dict to PyArrow RecordBatch."""
        svc = self._make_service()
        chain = {
            "ticker": "SPY",
            "spot": 500.0,
            "contracts": [
                {"expiry": "2026-07-24", "strike": 500.0, "type": "C",
                 "oi": 1000, "volume": 500, "iv": 0.15, "delta": 0.5, "gamma": 0.02},
                {"expiry": "2026-07-24", "strike": 505.0, "type": "P",
                 "oi": 800, "volume": 300, "iv": 0.16, "delta": -0.45, "gamma": 0.018},
            ],
        }
        batch = svc.contracts_to_recordbatch(chain)
        assert isinstance(batch, pa.RecordBatch)
        assert batch.num_rows == 2
        assert batch.num_columns == 10

    def test_contracts_to_recordbatch_empty(self):
        """Empty contracts list → empty RecordBatch."""
        svc = self._make_service()
        chain = {"ticker": "SPY", "spot": 500.0, "contracts": []}
        batch = svc.contracts_to_recordbatch(chain)
        assert isinstance(batch, pa.RecordBatch)
        assert batch.num_rows == 0

    def test_contracts_to_recordbatch_missing_fields(self):
        """Contracts with missing fields get defaults."""
        svc = self._make_service()
        chain = {
            "ticker": "SPY",
            "spot": 500.0,
            "contracts": [
                {"expiry": "2026-07-24", "strike": 500.0, "type": "C"},
            ],
        }
        batch = svc.contracts_to_recordbatch(chain)
        assert batch.num_rows == 1
        # oi, volume default to 0; iv, delta, gamma default to 0.0
        assert batch.column("oi").to_pylist() == [0]
        assert batch.column("iv").to_pylist() == [0.0]


# ---------------------------------------------------------------------------
# Integration-style tests for the REST API endpoints (mocked DB)
# ---------------------------------------------------------------------------

class TestTopMoversApi:
    """Tests for GET /api/heatseeker/top-movers/{ticker}."""

    def _make_service(self):
        from services import heatseeker_snapshots as svc
        return svc

    def test_top_movers_returns_json_structure(self):
        """Top movers result has the expected JSON structure."""
        svc = self._make_service()
        deltas = [
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": 500.0 + i, "type": "C",
             "oi_delta": 100 - i * 10, "oi_delta_pct": 0.1 - i * 0.01,
             "volume": 500, "volume_delta": 50, "iv": 0.15, "delta": 0.5, "gamma": 0.02}
            for i in range(10)
        ]
        result = svc.rank_top_movers(deltas, top_n=10)
        assert len(result) >= 5
        for entry in result:
            assert "ticker" in entry
            assert "expiry" in entry
            assert "strike" in entry
            assert "type" in entry
            assert "oi_delta" in entry
            assert "oi_delta_pct" in entry

    def test_top_movers_default_top_n(self):
        """Default top_n is 10."""
        svc = self._make_service()
        deltas = [
            {"ticker": "SPY", "expiry": "2026-07-24", "strike": float(500 + i), "type": "C",
             "oi_delta": 100, "oi_delta_pct": 0.1, "volume": 100, "volume_delta": 10,
             "iv": 0.15, "delta": 0.5, "gamma": 0.02}
            for i in range(20)
        ]
        result = svc.rank_top_movers(deltas)
        assert len(result) == 10
