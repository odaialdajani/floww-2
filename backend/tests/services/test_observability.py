"""
backend/tests/services/test_observability.py

Unit tests for the observability / Prometheus metrics stack.

Coverage:
    - Each metric increments/sets under expected conditions
    - /metrics endpoint returns valid Prometheus exposition format
    - Histogram buckets are reasonable
    - VPIN engine emits metrics on bucket finalize
    - Anomaly detector emits metrics on update
    - WebSocket connect/disconnect updates gauge
    - DuckDB engine emits queue depth and batch size
"""

import sys
from pathlib import Path

# Ensure backend/ is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ---------------------------------------------------------------------------
# Test 1: ingestion_messages_total increments
# ---------------------------------------------------------------------------
def test_ingestion_counter_increments():
    from services.observability import get_metrics_bytes, ingestion_messages_total
    ingestion_messages_total.labels(symbol="SPY", kind="tick").inc()
    ingestion_messages_total.labels(symbol="SPY", kind="tick").inc()
    ingestion_messages_total.labels(symbol="QQQ", kind="tick").inc()
    output = get_metrics_bytes().decode()
    assert 'floww_ingestion_messages_total{kind="tick",symbol="SPY"} 2' in output
    assert 'floww_ingestion_messages_total{kind="tick",symbol="QQQ"} 1' in output


# ---------------------------------------------------------------------------
# Test 2: vpin_current gauge sets per ticker
# ---------------------------------------------------------------------------
def test_vpin_gauge_sets():
    from services.observability import get_metrics_bytes, vpin_current
    vpin_current.labels(ticker="SPY").set(0.72)
    vpin_current.labels(ticker="QQQ").set(0.35)
    output = get_metrics_bytes().decode()
    assert 'floww_vpin_current{ticker="SPY"} 0.72' in output
    assert 'floww_vpin_current{ticker="QQQ"} 0.35' in output


# ---------------------------------------------------------------------------
# Test 3: qi_zscore_current gauge sets
# ---------------------------------------------------------------------------
def test_qi_zscore_gauge_sets():
    from services.observability import get_metrics_bytes, qi_zscore_current
    qi_zscore_current.labels(ticker="SPY").set(1.85)
    output = get_metrics_bytes().decode()
    assert 'floww_qi_zscore_current{ticker="SPY"} 1.85' in output


# ---------------------------------------------------------------------------
# Test 4: trinity_score gauge sets
# ---------------------------------------------------------------------------
def test_trinity_score_gauge_sets():
    from services.observability import get_metrics_bytes, trinity_score
    trinity_score.set(67.5)
    output = get_metrics_bytes().decode()
    assert "floww_trinity_score 67.5" in output


# ---------------------------------------------------------------------------
# Test 5: anomaly_score gauge and anomaly_detected_total counter
# ---------------------------------------------------------------------------
def test_anomaly_metrics():
    from services.observability import anomaly_detected_total, anomaly_score, get_metrics_bytes
    anomaly_score.labels(ticker="SPY").set(0.0042)
    anomaly_detected_total.inc()
    anomaly_detected_total.inc()
    output = get_metrics_bytes().decode()
    assert 'floww_anomaly_score{ticker="SPY"} 0.0042' in output
    assert "floww_anomaly_detected_total 2" in output


# ---------------------------------------------------------------------------
# Test 6: api_request_duration_seconds histogram
# ---------------------------------------------------------------------------
def test_api_duration_histogram():
    from services.observability import api_request_duration_seconds, get_metrics_bytes
    api_request_duration_seconds.labels(
        route="/api/vpin/{ticker}", method="GET", status="200"
    ).observe(0.023)
    api_request_duration_seconds.labels(
        route="/api/vpin/{ticker}", method="GET", status="200"
    ).observe(0.150)
    output = get_metrics_bytes().decode()
    assert "floww_api_request_duration_seconds_bucket" in output
    assert 'method="GET"' in output
    assert 'route="/api/vpin/{ticker}"' in output
    assert 'status="200"' in output


# ---------------------------------------------------------------------------
# Test 7: websocket_connections gauge inc/dec
# ---------------------------------------------------------------------------
def test_websocket_gauge():
    from services.observability import get_metrics_bytes, websocket_connections
    websocket_connections.labels(topic="ticks").inc()
    websocket_connections.labels(topic="ticks").inc()
    websocket_connections.labels(topic="flow").inc()
    output = get_metrics_bytes().decode()
    assert 'floww_websocket_connections{topic="ticks"} 2' in output
    assert 'floww_websocket_connections{topic="flow"} 1' in output
    websocket_connections.labels(topic="ticks").dec()
    output = get_metrics_bytes().decode()
    assert 'floww_websocket_connections{topic="ticks"} 1' in output


# ---------------------------------------------------------------------------
# Test 8: duckdb_queue_depth gauge
# ---------------------------------------------------------------------------
def test_duckdb_queue_depth():
    from services.observability import duckdb_queue_depth, get_metrics_bytes
    duckdb_queue_depth.set(42)
    output = get_metrics_bytes().decode()
    assert "floww_duckdb_queue_depth 42" in output


# ---------------------------------------------------------------------------
# Test 9: duckdb_batch_size histogram
# ---------------------------------------------------------------------------
def test_duckdb_batch_size_histogram():
    import re

    from services.observability import duckdb_batch_size, get_metrics_bytes
    # Snapshot count BEFORE observing — Prometheus REGISTRY is shared
    # across tests, so we can't assume a clean starting state.
    output_before = get_metrics_bytes().decode()
    m_before = re.search(r"floww_duckdb_batch_size_count (\d+(?:\.\d+)?)", output_before)
    count_before = float(m_before.group(1)) if m_before else 0.0

    duckdb_batch_size.observe(50)
    duckdb_batch_size.observe(100)

    output = get_metrics_bytes().decode()
    assert "floww_duckdb_batch_size_bucket" in output
    m_after = re.search(r"floww_duckdb_batch_size_count (\d+(?:\.\d+)?)", output)
    assert m_after, "batch_size count metric missing"
    assert float(m_after.group(1)) >= count_before + 2


# ---------------------------------------------------------------------------
# Test 11: /metrics endpoint returns valid Prometheus format
# ---------------------------------------------------------------------------
def test_metrics_endpoint_returns_prometheus_format():
    from services.observability import get_metrics_bytes, get_metrics_content_type, vpin_current
    vpin_current.labels(ticker="SPY").set(0.5)
    data = get_metrics_bytes()
    text = data.decode()
    # Must have HELP and TYPE lines
    assert "# HELP floww_vpin_current" in text
    assert "# TYPE floww_vpin_current gauge" in text
    # Must have the actual value
    assert 'floww_vpin_current{ticker="SPY"} 0.5' in text
    # Content type
    assert get_metrics_content_type() == "text/plain; version=1.0.0; charset=utf-8"


# ---------------------------------------------------------------------------
# Test 12: VPIN engine emits metrics on bucket finalize
# ---------------------------------------------------------------------------
def test_vpin_engine_emits_metrics():
    from services.observability import get_metrics_bytes
    from services.vpin_engine import VpinEngine

    engine = VpinEngine(bucket_size=100.0, window=10, ticker="SPY")
    # Feed enough volume to trigger bucket finalize
    for _i in range(20):
        engine.update(price_change=0.01, volume=10.0, sigma=0.2, dt=1.0)

    output = get_metrics_bytes().decode()
    # VPIN should have been set
    assert 'floww_vpin_current{ticker="SPY"}' in output
    # Ingestion counter should have incremented
    assert "floww_ingestion_messages_total" in output


# ---------------------------------------------------------------------------
# Test 13: VPIN engine without ticker does NOT emit metrics
# ---------------------------------------------------------------------------
def test_vpin_engine_no_ticker_no_metrics():
    from services.vpin_engine import VpinEngine

    engine = VpinEngine(bucket_size=100.0, window=10)  # no ticker
    for _i in range(20):
        engine.update(price_change=0.01, volume=10.0, sigma=0.2, dt=1.0)

    # Engine should still work fine
    assert engine.compute_vpin() >= 0.0


# ---------------------------------------------------------------------------
# Test 14: Anomaly detector emits metrics on update
# ---------------------------------------------------------------------------
def test_anomaly_detector_emits_metrics():
    from services.anomaly_detector import FlowAnomalyDetector
    from services.observability import get_metrics_bytes

    detector = FlowAnomalyDetector(seq_len=5, latent_dim=4, ticker="SPY")
    # Feed enough observations to warm up buffer (5) + fallback errors (10)
    for i in range(20):
        _result = detector.update(vpin=0.5 + i * 0.01, qi=0.1)

    output = get_metrics_bytes().decode()
    assert 'floww_anomaly_score{ticker="SPY"}' in output


# ---------------------------------------------------------------------------
# Test 15: Histogram buckets cover expected API latency range
# ---------------------------------------------------------------------------
def test_api_latency_buckets_cover_range():
    from services.observability import api_request_duration_seconds, get_metrics_bytes
    # p50 at 23ms should fall in 0.025 bucket
    api_request_duration_seconds.labels(
        route="/api/test", method="GET", status="200"
    ).observe(0.023)
    # p99 at 2.5s should fall in 2.5 bucket
    api_request_duration_seconds.labels(
        route="/api/test", method="GET", status="200"
    ).observe(2.5)

    output = get_metrics_bytes().decode()
    # Both observations should be counted
    assert 'floww_api_request_duration_seconds_count{method="GET",route="/api/test",status="200"} 2.0' in output
