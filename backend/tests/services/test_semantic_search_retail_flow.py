"""
backend/tests/services/test_semantic_search_retail_flow.py

Tests for semantic search with retail flow descriptions.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from services.graph_trade_service import GraphTradeService
from services.semantic_search import SemanticSearchEngine


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".duckdb")
    os.close(fd)
    os.unlink(path)  # Remove the empty file so DuckDB can create a fresh DB
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def service(db_path):
    svc = GraphTradeService(db_path)
    svc.ensure_schema()
    yield svc
    svc.close()


@pytest.fixture
def engine(db_path):
    eng = SemanticSearchEngine(db_path)
    yield eng
    eng.close()


def _populate_test_data(service):
    """Populate test database with trades and retail flows."""
    # Insert trades
    for i in range(5):
        service.upsert_trade({
            "id": f"trade_{i}",
            "symbol": "SPY",
            "side": "BUY" if i % 2 == 0 else "SELL",
            "quantity": 100,
            "entry_price": 450.0,
            "exit_price": 452.0 if i % 2 == 0 else 448.0,
            "pnl": 200.0 if i % 2 == 0 else -200.0,
            "pnl_pct": 0.44 if i % 2 == 0 else -0.44,
            "trade_type": "paper",
            "entry_time": f"2026-05-22T{10 + i}:00:00",
            "exit_time": f"2026-05-22T{10 + i}:05:00",
            "holding_period_bars": 5,
            "strategy": "VPIN_HFT",
        })

    # Insert retail flows
    flow_data = [
        (0.85, 0.1, 0.02, 0.78, 2.5, "bullish"),
        (0.72, 0.15, 0.05, 0.65, 1.8, "bullish"),
        (-0.55, 0.35, 0.2, 0.25, 0.6, "bearish"),
        (-0.78, 0.4, 0.25, 0.18, 0.4, "bearish"),
        (0.15, 0.22, 0.1, 0.45, 1.0, "neutral"),
    ]
    for i, (score, sr, br, slr, cpr, sentiment) in enumerate(flow_data):
        flow_id = f"rfs_{i}"
        service.upsert_retail_flow_score({
            "id": flow_id,
            "symbol": "SPY",
            "timestamp": f"2026-05-22T{10 + i}:00:00",
            "sweep_ratio": sr,
            "block_ratio": br,
            "small_lot_ratio": slr,
            "premium_concentration": 0.15,
            "call_put_ratio": cpr,
            "total_volume": 50000,
            "total_premium": 2500000,
            "trade_count": 300,
            "avg_trade_size": 150,
            "retail_flow_score": score,
        })
        service.upsert_price_movement({
            "id": f"pm_{i}",
            "symbol": "SPY",
            "timestamp": f"2026-05-22T{10 + i}:05:00",
            "start_price": 450.0,
            "end_price": 450.0 + score * 5,
            "price_change": score * 5,
            "price_change_pct": score * 1.1,
            "direction": "UP" if score > 0 else "DOWN",
            "timeframe": "5m",
            "volume": 50000,
        })
        service.add_retail_flow_movement_edge(flow_id, f"pm_{i}", confidence=0.9)


class TestRetailFlowTextGeneration:
    """Tests for retail flow text conversion."""

    def test_bullish_flow_text(self, engine):
        """Bullish flow should contain bullish keywords."""
        text = engine._retail_flow_to_text({
            "symbol": "SPY",
            "retail_flow_score": 0.85,
            "sweep_ratio": 0.1,
            "block_ratio": 0.02,
            "small_lot_ratio": 0.78,
            "call_put_ratio": 2.5,
            "premium_concentration": 0.12,
        })
        assert "bullish" in text
        assert "retail flow" in text
        assert "call heavy" in text
        assert "retail dominated" in text

    def test_bearish_flow_text(self, engine):
        """Bearish flow should contain bearish keywords."""
        text = engine._retail_flow_to_text({
            "symbol": "SPY",
            "retail_flow_score": -0.78,
            "sweep_ratio": 0.4,
            "block_ratio": 0.25,
            "small_lot_ratio": 0.18,
            "call_put_ratio": 0.4,
            "premium_concentration": 0.35,
        })
        assert "bearish" in text
        assert "put heavy" in text
        assert "institutional sweep" in text
        assert "large block" in text

    def test_neutral_flow_text(self, engine):
        """Neutral flow should contain neutral keywords."""
        text = engine._retail_flow_to_text({
            "symbol": "SPY",
            "retail_flow_score": 0.1,
            "sweep_ratio": 0.15,
            "block_ratio": 0.05,
            "small_lot_ratio": 0.5,
            "call_put_ratio": 1.0,
            "premium_concentration": 0.12,
        })
        assert "neutral" in text


class TestSemanticSearchIndexing:
    """Tests for semantic search indexing with retail flows."""

    def test_index_trades(self, engine, service):
        """Index trades returns correct count."""
        for i in range(3):
            service.upsert_trade({
                "id": f"trade_idx_{i}",
                "symbol": "SPY",
                "side": "BUY",
                "quantity": 100,
                "entry_price": 450.0,
                "exit_price": 452.0,
                "pnl": 200.0,
                "pnl_pct": 0.44,
                "trade_type": "paper",
                "entry_time": f"2026-05-22T{10 + i}:00:00",
                "exit_time": f"2026-05-22T{10 + i}:05:00",
                "holding_period_bars": 5,
                "strategy": "VPIN_HFT",
            })
        count = engine.index_trades()
        assert count == 3

    def test_index_retail_flows(self, engine, service):
        """Index retail flows returns correct count."""
        for i in range(3):
            service.upsert_retail_flow_score({
                "id": "rfs_idx_{}".format(i),
                "symbol": "SPY",
                "timestamp": "2026-05-22T10:0{}:00".format(i),
                "sweep_ratio": 0.1,
                "block_ratio": 0.05,
                "small_lot_ratio": 0.6,
                "premium_concentration": 0.12,
                "call_put_ratio": 1.5,
                "total_volume": 50000,
                "total_premium": 2500000,
                "trade_count": 300,
                "avg_trade_size": 150,
                "retail_flow_score": 0.5,
            })
        count = engine.index_retail_flows()
        assert count == 3

    def test_index_all(self, engine, service):
        """Index all returns combined count."""
        for i in range(2):
            service.upsert_trade({
                "id": "trade_all_{}".format(i),
                "symbol": "SPY",
                "side": "BUY",
                "quantity": 100,
                "entry_price": 450.0,
                "exit_price": 452.0,
                "pnl": 200.0,
                "pnl_pct": 0.44,
                "trade_type": "paper",
                "entry_time": "2026-05-22T10:0{}:00".format(i),
                "exit_time": "2026-05-22T10:0{}:00".format(i),
                "holding_period_bars": 5,
                "strategy": "VPIN_HFT",
            })
        for i in range(3):
            service.upsert_retail_flow_score({
                "id": "rfs_all_{}".format(i),
                "symbol": "SPY",
                "timestamp": "2026-05-22T10:0{}:00".format(i),
                "sweep_ratio": 0.1,
                "block_ratio": 0.05,
                "small_lot_ratio": 0.6,
                "premium_concentration": 0.12,
                "call_put_ratio": 1.5,
                "total_volume": 50000,
                "total_premium": 2500000,
                "trade_count": 300,
                "avg_trade_size": 150,
                "retail_flow_score": 0.5,
            })
        total = engine.index_all()
        assert total == 5


class TestSemanticSearchQueries:
    """Tests for semantic search queries with retail flow."""

    @pytest.fixture(autouse=True)
    def setup_data(self, engine, service):
        _populate_test_data(service)

    def test_search_bullish_retail_flow(self, engine):
        """Natural language query for bullish retail flow."""
        engine.index_all()
        results = engine.search("bullish retail flow", top_k=5)
        assert len(results) > 0
        # Top results should be retail_flow type
        flow_results = [r for r in results if r["doc_type"] == "retail_flow"]
        assert len(flow_results) > 0

    def test_search_sweep_heavy(self, engine):
        """Query for sweep-heavy flow."""
        engine.index_all()
        results = engine.search("sweep heavy institutional", top_k=5)
        assert len(results) > 0

    def test_search_with_doc_type_filter(self, engine):
        """Filter search to only retail_flow docs."""
        engine.index_all()
        results = engine.search(
            "retail flow", top_k=10, doc_type="retail_flow"
        )
        assert all(r["doc_type"] == "retail_flow" for r in results)

    def test_search_retail_flow_bullish(self, engine):
        """search_retail_flow_bullish returns bullish flows."""
        engine.index_all()
        results = engine.search_retail_flow_bullish(top_k=5)
        for r in results:
            assert r["doc_type"] == "retail_flow"
            assert r["item"]["retail_flow_score"] > 0.3

    def test_search_retail_flow_bearish(self, engine):
        """search_retail_flow_bearish returns bearish flows."""
        engine.index_all()
        results = engine.search_retail_flow_bearish(top_k=5)
        for r in results:
            assert r["doc_type"] == "retail_flow"
            assert r["item"]["retail_flow_score"] < -0.3

    def test_search_sweep_heavy_flow(self, engine):
        """search_sweep_heavy_flow returns sweep-heavy events."""
        engine.index_all()
        results = engine.search_sweep_heavy_flow(top_k=5)
        for r in results:
            assert r["doc_type"] == "retail_flow"

    def test_search_small_lot_dominated(self, engine):
        """search_small_lot_dominated returns retail-dominated events."""
        engine.index_all()
        results = engine.search_small_lot_dominated(top_k=5)
        for r in results:
            assert r["doc_type"] == "retail_flow"

    def test_search_flow_with_price_movement(self, engine):
        """search_flow_with_price_movement returns flow events with price direction."""
        engine.index_all()
        results = engine.search_flow_with_price_movement("UP", top_k=5)
        for r in results:
            assert r["doc_type"] == "retail_flow"

    def test_search_returns_relevance_scores(self, engine):
        """All results should have relevance scores."""
        engine.index_all()
        results = engine.search("retail flow", top_k=5)
        for r in results:
            assert "relevance" in r
            assert 0 <= r["relevance"] <= 1

    def test_search_returns_text(self, engine):
        """All results should have searchable text."""
        engine.index_all()
        results = engine.search("retail flow", top_k=5)
        for r in results:
            assert "text" in r
            assert len(r["text"]) > 0

    def test_search_empty_index(self, engine):
        """Search on empty index returns empty results."""
        results = engine.search("bullish retail flow", top_k=5)
        assert results == []
