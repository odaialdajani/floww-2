#!/usr/bin/env python3
"""
backend/tests/services/memory/test_memory_health.py — Tests for memory health monitor.

Run: pytest backend/tests/services/memory/test_memory_health.py -v
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from services.memory.health import (
    _metrics,
    get_health_status,
    get_prometheus_metrics,
    record_cache_hit,
    record_cache_miss,
    record_consolidation,
    record_federation_sync,
    record_pruning,
    record_query,
)


class TestMemoryHealth:
    def setup_method(self):
        """Reset metrics before each test."""
        for key in _metrics:
            if isinstance(_metrics[key], list):
                _metrics[key] = []
            elif isinstance(_metrics[key], (int, float)):
                _metrics[key] = 0
            else:
                _metrics[key] = None

    def test_record_query(self):
        record_query(10.0)
        record_query(20.0)
        record_query(30.0)
        assert _metrics["memory_query_count"] == 3

    def test_record_cache_hit(self):
        record_cache_hit()
        record_cache_hit()
        assert _metrics["memory_cache_hits"] == 2

    def test_record_cache_miss(self):
        record_cache_miss()
        assert _metrics["memory_cache_misses"] == 1

    def test_cache_hit_rate(self):
        record_cache_hit()
        record_cache_hit()
        record_cache_miss()
        status = get_health_status()
        assert abs(status["embedding_cache_hit_rate"] - 2 / 3) < 0.001

    def test_federation_sync(self):
        record_federation_sync(5.5, 10)
        status = get_health_status()
        assert status["federation_lag_seconds"] == 5.5
        assert status["federation_events_synced_total"] == 10

    def test_consolidation(self):
        record_consolidation(5)
        status = get_health_status()
        assert status["consolidation_merged_24h"] == 5
        assert status["last_consolidation_at"] is not None

    def test_pruning(self):
        record_pruning(3)
        status = get_health_status()
        assert status["pruning_stats"]["pruned_24h"] == 3

    def test_query_latency_percentiles(self):
        for i in range(100):
            record_query(float(i + 1))
        status = get_health_status()
        assert status["query_latency_p50_ms"] > 0
        assert status["query_latency_p95_ms"] > 0
        assert status["query_latency_p99_ms"] > 0

    def test_health_with_mock_client(self):
        mock_client = MagicMock()
        mock_client.get_all.return_value = {"total": 303}
        status = get_health_status(mem0_client=mock_client)
        assert status["entry_count"] == 303

    def test_health_response_time(self):
        """Health endpoint should respond quickly."""
        import time
        start = time.time()
        status = get_health_status()
        elapsed_ms = (time.time() - start) * 1000
        assert elapsed_ms < 50, f"Health check took {elapsed_ms:.1f}ms (should be < 50ms)"

    def test_prometheus_metrics(self):
        record_query(10.0)
        record_cache_hit()
        metrics_text = get_prometheus_metrics()
        assert "floww_memory_entry_count" in metrics_text
        assert "floww_memory_federation_lag_s" in metrics_text
        assert "floww_memory_cache_hit_rate" in metrics_text

    def test_health_all_fields_present(self):
        status = get_health_status()
        required_fields = [
            "entry_count", "query_count_total", "query_latency_p50_ms",
            "query_latency_p95_ms", "query_latency_p99_ms",
            "embedding_cache_hit_rate", "federation_lag_seconds",
            "federation_events_synced_total", "last_consolidation_at",
            "consolidation_merged_24h", "pruning_stats", "timestamp",
        ]
        for field in required_fields:
            assert field in status, f"Missing field: {field}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
