"""
backend/tests/services/test_retail_flow_graph.py

Tests for retail flow score nodes and price movement nodes in the knowledge graph.
"""

from __future__ import annotations

import os

# Ensure backend is on sys.path
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from services.graph_trade_service import GraphTradeService


@pytest.fixture
def db_path():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".duckdb")
    os.close(fd)
    os.unlink(path)  # Remove the empty file so DuckDB can create a fresh DB
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def service(db_path):
    """Create a GraphTradeService with test database."""
    svc = GraphTradeService(db_path)
    svc.ensure_schema()
    yield svc
    svc.close()


@pytest.fixture
def sample_flow():
    """Sample retail flow score data."""
    return {
        "id": f"rfs_{uuid.uuid4().hex[:8]}",
        "symbol": "SPY",
        "timestamp": "2026-05-22T10:00:00",
        "sweep_ratio": 0.15,
        "block_ratio": 0.05,
        "small_lot_ratio": 0.65,
        "premium_concentration": 0.12,
        "call_put_ratio": 1.8,
        "total_volume": 50000,
        "total_premium": 2500000,
        "trade_count": 350,
        "avg_trade_size": 143,
        "retail_flow_score": 0.72,
    }


@pytest.fixture
def sample_movement():
    """Sample price movement data."""
    return {
        "id": f"pm_{uuid.uuid4().hex[:8]}",
        "symbol": "SPY",
        "timestamp": "2026-05-22T10:05:00",
        "start_price": 450.0,
        "end_price": 452.5,
        "price_change": 2.5,
        "price_change_pct": 0.5556,
        "direction": "UP",
        "timeframe": "5m",
        "volume": 50000,
    }


@pytest.fixture
def sample_trade():
    """Sample trade data."""
    return {
        "id": f"trade_{uuid.uuid4().hex[:8]}",
        "symbol": "SPY",
        "side": "BUY",
        "quantity": 100,
        "entry_price": 450.0,
        "exit_price": 452.5,
        "pnl": 250.0,
        "pnl_pct": 0.5556,
        "trade_type": "paper",
        "entry_time": "2026-05-22T10:00:00",
        "exit_time": "2026-05-22T10:05:00",
        "holding_period_bars": 5,
        "strategy": "VPIN_HFT",
    }


class TestRetailFlowScoreCrud:
    """Tests for retail flow score CRUD operations."""

    def test_upsert_retail_flow_score(self, service, sample_flow):
        """Insert a retail flow score node."""
        service.upsert_retail_flow_score(sample_flow)
        assert service.get_retail_flow_count() == 1

    def test_upsert_retail_flow_score_idempotent(self, service, sample_flow):
        """Upsert same flow twice should not duplicate."""
        service.upsert_retail_flow_score(sample_flow)
        service.upsert_retail_flow_score(sample_flow)
        assert service.get_retail_flow_count() == 1

    def test_upsert_retail_flow_scores_batch(self, service):
        """Batch insert retail flow scores."""
        flows = [
            {
                "id": f"rfs_{i}_{uuid.uuid4().hex[:8]}",
                "symbol": "SPY",
                "timestamp": f"2026-05-22T{10 + i}:00:00",
                "sweep_ratio": 0.1 * i,
                "block_ratio": 0.05 * i,
                "small_lot_ratio": 0.5 + i * 0.05,
                "premium_concentration": 0.1,
                "call_put_ratio": 1.0 + i * 0.2,
                "total_volume": 50000 + i * 1000,
                "total_premium": 2500000,
                "trade_count": 300,
                "avg_trade_size": 150,
                "retail_flow_score": 0.1 * i,
            }
            for i in range(1, 6)
        ]
        count = service.upsert_retail_flow_scores_batch(flows)
        assert count == 5
        assert service.get_retail_flow_count() == 5

    def test_get_retail_flow_scores_by_symbol(self, service):
        """Query retail flow scores by symbol."""
        for i in range(3):
            service.upsert_retail_flow_score({
                "id": f"rfs_spy_{i}",
                "symbol": "SPY",
                "timestamp": f"2026-05-22T{10 + i}:00:00",
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
        for i in range(2):
            service.upsert_retail_flow_score({
                "id": f"rfs_qqq_{i}",
                "symbol": "QQQ",
                "timestamp": f"2026-05-22T{10 + i}:00:00",
                "sweep_ratio": 0.2,
                "block_ratio": 0.1,
                "small_lot_ratio": 0.4,
                "premium_concentration": 0.2,
                "call_put_ratio": 0.8,
                "total_volume": 40000,
                "total_premium": 1800000,
                "trade_count": 250,
                "avg_trade_size": 160,
                "retail_flow_score": -0.3,
            })
        spy_flows = service.get_retail_flow_scores_by_symbol("SPY")
        assert len(spy_flows) == 3
        qqq_flows = service.get_retail_flow_scores_by_symbol("QQQ")
        assert len(qqq_flows) == 2

    def test_get_retail_flow_scores_by_score(self, service):
        """Query retail flow scores by score range."""
        scores = [0.8, 0.5, 0.1, -0.2, -0.7]
        for i, score in enumerate(scores):
            service.upsert_retail_flow_score({
                "id": f"rfs_score_{i}",
                "symbol": "SPY",
                "timestamp": f"2026-05-22T{10 + i}:00:00",
                "sweep_ratio": 0.1,
                "block_ratio": 0.05,
                "small_lot_ratio": 0.6,
                "premium_concentration": 0.12,
                "call_put_ratio": 1.5,
                "total_volume": 50000,
                "total_premium": 2500000,
                "trade_count": 300,
                "avg_trade_size": 150,
                "retail_flow_score": score,
            })
        bullish = service.get_retail_flow_scores_by_score(min_score=0.3)
        assert len(bullish) == 2  # 0.8, 0.5
        bearish = service.get_retail_flow_scores_by_score(max_score=-0.1)
        assert len(bearish) == 2  # -0.2, -0.7


class TestPriceMovementCrud:
    """Tests for price movement CRUD operations."""

    def test_upsert_price_movement(self, service, sample_movement):
        """Insert a price movement node."""
        service.upsert_price_movement(sample_movement)
        assert service.get_price_movement_count() == 1

    def test_upsert_price_movement_idempotent(self, service, sample_movement):
        """Upsert same movement twice should not duplicate."""
        service.upsert_price_movement(sample_movement)
        service.upsert_price_movement(sample_movement)
        assert service.get_price_movement_count() == 1

    def test_upsert_price_movements_batch(self, service):
        """Batch insert price movements."""
        movements = [
            {
                "id": f"pm_{i}_{uuid.uuid4().hex[:8]}",
                "symbol": "SPY",
                "timestamp": f"2026-05-22T{10 + i}:00:00",
                "start_price": 450.0 + i,
                "end_price": 451.0 + i,
                "price_change": 1.0,
                "price_change_pct": 0.22,
                "direction": "UP",
                "timeframe": "5m",
                "volume": 50000,
            }
            for i in range(5)
        ]
        count = service.upsert_price_movements_batch(movements)
        assert count == 5

    def test_get_price_movements_by_symbol(self, service):
        """Query price movements by symbol."""
        for i, direction in enumerate(["UP", "UP", "DOWN"]):
            service.upsert_price_movement({
                "id": f"pm_dir_{i}",
                "symbol": "SPY",
                "timestamp": f"2026-05-22T{10 + i}:00:00",
                "start_price": 450.0,
                "end_price": 451.0 if direction == "UP" else 449.0,
                "price_change": 1.0 if direction == "UP" else -1.0,
                "price_change_pct": 0.22 if direction == "UP" else -0.22,
                "direction": direction,
                "timeframe": "5m",
                "volume": 50000,
            })
        up_movements = service.get_price_movements_by_symbol("SPY", direction="UP")
        assert len(up_movements) == 2
        down_movements = service.get_price_movements_by_symbol("SPY", direction="DOWN")
        assert len(down_movements) == 1


class TestRetailFlowEdges:
    """Tests for retail flow edge operations."""

    def test_retail_flow_symbol_edge(self, service, sample_flow):
        """Link retail flow to symbol."""
        service.upsert_retail_flow_score(sample_flow)
        service.upsert_symbol({
            "id": "sym_spy",
            "name": "SPY",
            "asset_class": "equity",
        })
        service.add_retail_flow_symbol_edge(sample_flow["id"], "sym_spy")

    def test_retail_flow_movement_edge(self, service, sample_flow, sample_movement):
        """Link retail flow to price movement."""
        service.upsert_retail_flow_score(sample_flow)
        service.upsert_price_movement(sample_movement)
        service.add_retail_flow_movement_edge(
            sample_flow["id"], sample_movement["id"], confidence=0.9
        )

    def test_trade_retail_flow_edge(self, service, sample_flow, sample_trade):
        """Link trade to retail flow."""
        service.upsert_trade(sample_trade)
        service.upsert_retail_flow_score(sample_flow)
        service.add_trade_retail_flow_edge(
            sample_trade["id"], sample_flow["id"], confidence=0.7
        )


class TestRetailFlowGraphQueries:
    """Tests for retail flow graph queries."""

    def test_get_retail_flow_with_movements(self, service):
        """MATCH (rfs)-[:INFLUENCED]->(pm)."""
        flow_id = "rfs_gw_001"
        mov_id = "pm_gw_001"
        service.upsert_retail_flow_score({
            "id": flow_id,
            "symbol": "SPY",
            "timestamp": "2026-05-22T10:00:00",
            "sweep_ratio": 0.2,
            "block_ratio": 0.1,
            "small_lot_ratio": 0.5,
            "premium_concentration": 0.15,
            "call_put_ratio": 1.5,
            "total_volume": 50000,
            "total_premium": 2500000,
            "trade_count": 300,
            "avg_trade_size": 150,
            "retail_flow_score": 0.6,
        })
        service.upsert_price_movement({
            "id": mov_id,
            "symbol": "SPY",
            "timestamp": "2026-05-22T10:05:00",
            "start_price": 450.0,
            "end_price": 452.0,
            "price_change": 2.0,
            "price_change_pct": 0.44,
            "direction": "UP",
            "timeframe": "5m",
            "volume": 50000,
        })
        service.add_retail_flow_movement_edge(flow_id, mov_id, confidence=0.9)

        results = service.get_retail_flow_with_movements()
        assert len(results) == 1
        assert results[0]["flow_id"] == flow_id
        assert results[0]["movement_id"] == mov_id
        assert results[0]["direction"] == "UP"

    def test_get_trades_with_retail_flow(self, service):
        """MATCH (t)-[:INFLUENCED_BY_RETAIL]->(rfs)."""
        trade_id = "trade_gwr_001"
        flow_id = "rfs_gwr_001"
        service.upsert_trade({
            "id": trade_id,
            "symbol": "SPY",
            "side": "BUY",
            "quantity": 100,
            "entry_price": 450.0,
            "exit_price": 452.0,
            "pnl": 200.0,
            "pnl_pct": 0.4444,
            "trade_type": "paper",
            "entry_time": "2026-05-22T10:00:00",
            "exit_time": "2026-05-22T10:05:00",
            "holding_period_bars": 5,
            "strategy": "VPIN_HFT",
        })
        service.upsert_retail_flow_score({
            "id": flow_id,
            "symbol": "SPY",
            "timestamp": "2026-05-22T10:00:00",
            "sweep_ratio": 0.2,
            "block_ratio": 0.1,
            "small_lot_ratio": 0.5,
            "premium_concentration": 0.15,
            "call_put_ratio": 1.5,
            "total_volume": 50000,
            "total_premium": 2500000,
            "trade_count": 300,
            "avg_trade_size": 150,
            "retail_flow_score": 0.6,
        })
        service.add_trade_retail_flow_edge(trade_id, flow_id, confidence=0.7)

        results = service.get_trades_with_retail_flow()
        assert len(results) == 1
        assert results[0]["trade_id"] == trade_id
        assert results[0]["flow_id"] == flow_id

    def test_get_full_retail_flow_context(self, service):
        """Get retail flow + movements + trades."""
        flow_id = "rfs_fc_001"
        mov_id = "pm_fc_001"
        trade_id = "trade_fc_001"

        service.upsert_retail_flow_score({
            "id": flow_id,
            "symbol": "SPY",
            "timestamp": "2026-05-22T10:00:00",
            "sweep_ratio": 0.2,
            "block_ratio": 0.1,
            "small_lot_ratio": 0.5,
            "premium_concentration": 0.15,
            "call_put_ratio": 1.5,
            "total_volume": 50000,
            "total_premium": 2500000,
            "trade_count": 300,
            "avg_trade_size": 150,
            "retail_flow_score": 0.6,
        })
        service.upsert_price_movement({
            "id": mov_id,
            "symbol": "SPY",
            "timestamp": "2026-05-22T10:05:00",
            "start_price": 450.0,
            "end_price": 452.0,
            "price_change": 2.0,
            "price_change_pct": 0.44,
            "direction": "UP",
            "timeframe": "5m",
            "volume": 50000,
        })
        service.upsert_trade({
            "id": trade_id,
            "symbol": "SPY",
            "side": "BUY",
            "quantity": 100,
            "entry_price": 450.0,
            "exit_price": 452.0,
            "pnl": 200.0,
            "pnl_pct": 0.4444,
            "trade_type": "paper",
            "entry_time": "2026-05-22T10:00:00",
            "exit_time": "2026-05-22T10:05:00",
            "holding_period_bars": 5,
            "strategy": "VPIN_HFT",
        })

        service.add_retail_flow_movement_edge(flow_id, mov_id, confidence=0.9)
        service.add_trade_retail_flow_edge(trade_id, flow_id, confidence=0.7)

        context = service.get_full_retail_flow_context(flow_id)
        assert "retail_flow" in context
        assert len(context["price_movements"]) == 1
        assert len(context["trades"]) == 1

    def test_get_full_retail_flow_context_not_found(self, service):
        """Query for non-existent flow returns empty dict."""
        context = service.get_full_retail_flow_context("nonexistent")
        assert context == {}


class TestRetailFlowStats:
    """Tests for retail flow aggregate statistics."""

    def test_get_retail_flow_stats_empty(self, service):
        """Stats with no data."""
        stats = service.get_retail_flow_stats()
        assert stats["total_flow_scores"] == 0

    def test_get_retail_flow_stats(self, service):
        """Stats with data."""
        scores = [0.8, 0.5, -0.3, -0.7, 0.1]
        for i, score in enumerate(scores):
            service.upsert_retail_flow_score({
                "id": f"rfs_stats_{i}",
                "symbol": "SPY",
                "timestamp": f"2026-05-22T{10 + i}:00:00",
                "sweep_ratio": 0.1 + i * 0.05,
                "block_ratio": 0.05,
                "small_lot_ratio": 0.6,
                "premium_concentration": 0.12,
                "call_put_ratio": 1.5,
                "total_volume": 50000,
                "total_premium": 2500000,
                "trade_count": 300,
                "avg_trade_size": 150,
                "retail_flow_score": score,
            })
        stats = service.get_retail_flow_stats()
        assert stats["total_flow_scores"] == 5
        assert stats["bullish_count"] == 2   # 0.8, 0.5
        assert stats["bearish_count"] == 2   # -0.3, -0.7
        assert stats["neutral_count"] == 1   # 0.1


class TestGraphStats:
    """Test that graph_stats includes retail flow counts."""

    def test_graph_stats_include_retail(self, service, sample_flow, sample_movement):
        """Graph stats should include retail_flow_scores and price_movements."""
        service.upsert_retail_flow_score(sample_flow)
        service.upsert_price_movement(sample_movement)
        service.add_retail_flow_movement_edge(
            sample_flow["id"], sample_movement["id"]
        )

        stats = service.get_graph_stats()
        assert stats["retail_flow_scores"] == 1
        assert stats["price_movements"] == 1
        assert stats["retail_flow_movement_edges"] == 1
