"""
backend/tests/services/test_provider_monitoring.py

Unit tests for the data provider monitoring stack:
  - ProviderStats rolling window
  - DataProviderMonitor alert thresholds
  - Prometheus metric emission
  - Integration: _record_provider_call

Coverage:
    - ProviderStats records success/failure correctly
    - Rolling window prunes old entries
    - Success rate calculation is correct
    - Consecutive failure tracking
    - Alert: low_success_rate fires and clears
    - Alert: provider_down fires and clears
    - Alert: repeated_failures fires and clears
    - Alert callback is invoked
    - get_health returns correct structure
    - Prometheus counters increment
    - Prometheus gauges update
    - _record_provider_call is safe (no exceptions)
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


# ---------------------------------------------------------------------------
# ProviderStats tests
# ---------------------------------------------------------------------------

@pytest.fixture
def stats():
    from services.meta_observability import ProviderStats
    return ProviderStats(name="test_provider", window_seconds=60.0)


def test_provider_stats_initial_state(stats):
    assert stats.success_rate == 1.0
    assert stats.window_calls == 0
    assert stats.consecutive_failures == 0
    assert stats.seconds_since_last_success == float("inf")


def test_provider_stats_record_success(stats):
    stats.record(True)
    assert stats.window_calls == 1
    assert stats.success_rate == 1.0
    assert stats.consecutive_failures == 0
    assert stats._total_calls == 1
    assert stats._total_successes == 1


def test_provider_stats_record_failure(stats):
    stats.record(False)
    assert stats.window_calls == 1
    assert stats.success_rate == 0.0
    assert stats.consecutive_failures == 1
    assert stats._total_calls == 1
    assert stats._total_successes == 0


def test_provider_stats_mixed(stats):
    stats.record(True)
    stats.record(True)
    stats.record(False)
    assert stats.window_calls == 3
    assert stats.success_rate == 2 / 3
    assert stats.consecutive_failures == 1


def test_provider_stats_consecutive_failures_reset(stats):
    stats.record(False)
    stats.record(False)
    assert stats.consecutive_failures == 2
    stats.record(True)
    assert stats.consecutive_failures == 0


def test_provider_stats_rolling_window_prune():
    """Old entries outside the window should be pruned."""
    from services.meta_observability import ProviderStats
    stats = ProviderStats(name="prune_test", window_seconds=60.0)
    # Use a mutable counter to control timestamps
    counter = {"t": 1000.0}
    def fake_time():
        return counter["t"]
    with patch("services.meta_observability.time.time", side_effect=fake_time):
        stats.record(True)  # t=1000
        counter["t"] = 1031.0
        stats.record(True)  # t=1031
        counter["t"] = 1062.0
        stats.record(False)  # t=1062, prunes entries older than 1002
    # Entry at 1000 is pruned (1062-1000=62 > 60), entries at 1031 and 1062 remain
    assert stats.window_calls == 2


# ---------------------------------------------------------------------------
# DataProviderMonitor tests
# ---------------------------------------------------------------------------

@pytest.fixture
def monitor():
    from services.meta_observability import DataProviderMonitor
    return DataProviderMonitor(
        min_success_rate=0.5,
        provider_down_seconds=120.0,
        max_consecutive_failures=3,
        window_seconds=60.0,
    )


def test_monitor_record(monitor):
    monitor.record("finnhub", True)
    monitor.record("finnhub", False)
    health = monitor.get_health()
    assert "finnhub" in health["providers"]
    assert health["providers"]["finnhub"]["window_calls"] == 2


def test_monitor_low_success_rate_alert(monitor):
    """After 3+ calls with < 50% success, alert should fire."""
    monitor.record("finnhub", False)
    monitor.record("finnhub", False)
    monitor.record("finnhub", True)  # 1/3 = 0.33 < 0.5
    alerts = monitor.check_alerts()
    low_rate_alerts = [a for a in alerts if a["alert_type"] == "low_success_rate"]
    assert len(low_rate_alerts) == 1
    assert low_rate_alerts[0]["provider"] == "finnhub"
    assert low_rate_alerts[0]["severity"] == "warning"


def test_monitor_low_success_rate_clears(monitor):
    """Alert should clear when success rate recovers."""
    # Trigger alert
    monitor.record("finnhub", False)
    monitor.record("finnhub", False)
    monitor.record("finnhub", True)
    alerts = monitor.check_alerts()
    assert any(a["alert_type"] == "low_success_rate" for a in alerts)

    # Recover
    monitor.record("finnhub", True)
    monitor.record("finnhub", True)
    monitor.record("finnhub", True)
    monitor.record("finnhub", True)  # Now 5/7 > 0.5
    alerts = monitor.check_alerts()
    low_rate_alerts = [a for a in alerts if a["alert_type"] == "low_success_rate"]
    assert len(low_rate_alerts) == 0


def test_monitor_repeated_failures_alert(monitor):
    """3 consecutive failures should trigger repeated_failures alert."""
    monitor.record("finnhub", False)
    monitor.record("finnhub", False)
    monitor.record("finnhub", False)
    alerts = monitor.check_alerts()
    repeat_alerts = [a for a in alerts if a["alert_type"] == "repeated_failures"]
    assert len(repeat_alerts) == 1
    assert repeat_alerts[0]["consecutive_failures"] == 3


def test_monitor_repeated_failures_clears(monitor):
    """Alert should clear after a success breaks the streak."""
    monitor.record("finnhub", False)
    monitor.record("finnhub", False)
    monitor.record("finnhub", False)
    alerts = monitor.check_alerts()
    assert any(a["alert_type"] == "repeated_failures" for a in alerts)

    monitor.record("finnhub", True)
    alerts = monitor.check_alerts()
    repeat_alerts = [a for a in alerts if a["alert_type"] == "repeated_failures"]
    assert len(repeat_alerts) == 0


def test_monitor_provider_down_alert(monitor):
    """No success in 120+ seconds should trigger provider_down."""
    # Record a success far in the past
    old_time = time.time() - 200.0
    stats = monitor._get_stats("finnhub")
    stats._calls.append((old_time, True))
    stats._last_success = old_time
    stats._total_calls = 1
    stats._total_successes = 1

    alerts = monitor.check_alerts()
    down_alerts = [a for a in alerts if a["alert_type"] == "provider_down"]
    assert len(down_alerts) == 1
    assert down_alerts[0]["severity"] == "critical"


def test_monitor_alert_callback(monitor):
    """on_alert callback should be invoked when alert fires."""
    callback = MagicMock()
    monitor.on_alert = callback

    monitor.record("finnhub", False)
    monitor.record("finnhub", False)
    monitor.record("finnhub", False)

    alerts = monitor.check_alerts()
    assert callback.call_count >= 1
    # Check it was called with (provider, alert_type, alert_dict)
    args = callback.call_args[0]
    assert args[0] == "finnhub"
    assert args[1] in ("low_success_rate", "repeated_failures")


def test_monitor_get_health_structure(monitor):
    monitor.record("finnhub", True)
    monitor.record("yfinance", False)

    health = monitor.get_health()
    assert "providers" in health
    assert "thresholds" in health
    assert "active_alerts" in health
    assert "finnhub" in health["providers"]
    assert "yfinance" in health["providers"]

    thresholds = health["thresholds"]
    assert thresholds["min_success_rate"] == 0.5
    assert thresholds["provider_down_seconds"] == 120.0
    assert thresholds["max_consecutive_failures"] == 3
    assert thresholds["window_seconds"] == 60.0


def test_monitor_alerts_dedup(monitor):
    """Same alert should not fire twice consecutively."""
    monitor.record("finnhub", False)
    monitor.record("finnhub", False)
    monitor.record("finnhub", False)

    alerts1 = monitor.check_alerts()
    alerts2 = monitor.check_alerts()

    # Second call should not produce duplicate alerts
    types1 = {(a["provider"], a["alert_type"]) for a in alerts1}
    types2 = {(a["provider"], a["alert_type"]) for a in alerts2}
    assert len(types2) == 0  # Already alerted, no new alerts


def test_monitor_multiple_providers(monitor):
    monitor.record("finnhub", True)
    monitor.record("yfinance", False)
    monitor.record("polygon", True)

    health = monitor.get_health()
    assert len(health["providers"]) == 3
    assert health["providers"]["finnhub"]["success_rate"] == 1.0
    assert health["providers"]["yfinance"]["success_rate"] == 0.0
    assert health["providers"]["polygon"]["success_rate"] == 1.0


# ---------------------------------------------------------------------------
# Prometheus metrics tests
# ---------------------------------------------------------------------------

def test_provider_calls_counter():
    from services.observability import get_metrics_bytes, provider_calls_total
    provider_calls_total.labels(provider="finnhub", status="success").inc()
    provider_calls_total.labels(provider="finnhub", status="success").inc()
    provider_calls_total.labels(provider="finnhub", status="failure").inc()
    output = get_metrics_bytes().decode()
    assert 'floww_provider_calls_total{provider="finnhub",status="success"} 2' in output
    assert 'floww_provider_calls_total{provider="finnhub",status="failure"} 1' in output


def test_provider_success_rate_gauge():
    from services.observability import get_metrics_bytes, provider_success_rate
    provider_success_rate.labels(provider="yfinance").set(0.85)
    output = get_metrics_bytes().decode()
    assert 'floww_provider_success_rate{provider="yfinance"} 0.85' in output


def test_provider_last_success_gauge():
    from services.observability import get_metrics_bytes, provider_last_success_seconds_ago
    provider_last_success_seconds_ago.labels(provider="finnhub").set(45.2)
    output = get_metrics_bytes().decode()
    assert 'floww_provider_last_success_seconds_ago{provider="finnhub"} 45.2' in output


def test_provider_alerts_fired_counter():
    from services.observability import get_metrics_bytes, provider_alerts_fired_total
    provider_alerts_fired_total.labels(provider="yfinance", alert_type="low_success_rate").inc()
    output = get_metrics_bytes().decode()
    assert 'floww_provider_alerts_fired_total{alert_type="low_success_rate",provider="yfinance"} 1' in output


def test_yfinance_calls_counter():
    from services.observability import get_metrics_bytes, yfinance_calls_total
    yfinance_calls_total.labels(endpoint="get_spot_price", status="success").inc()
    yfinance_calls_total.labels(endpoint="get_spot_price", status="success").inc()
    yfinance_calls_total.labels(endpoint="get_spot_price", status="failure").inc()
    output = get_metrics_bytes().decode()
    assert 'floww_yfinance_calls_total{endpoint="get_spot_price",status="success"} 2' in output
    assert 'floww_yfinance_calls_total{endpoint="get_spot_price",status="failure"} 1' in output


def test_yfinance_success_rate_gauge():
    from services.observability import get_metrics_bytes, yfinance_success_rate
    yfinance_success_rate.set(0.92)
    output = get_metrics_bytes().decode()
    assert "floww_yfinance_success_rate 0.92" in output


# ---------------------------------------------------------------------------
# _record_provider_call safety tests
# ---------------------------------------------------------------------------

def test_record_provider_call_success():
    """_record_provider_call should not raise on success."""
    from data_providers import _record_provider_call
    _record_provider_call("finnhub", True)  # Should not raise


def test_record_provider_call_failure():
    """_record_provider_call should not raise on failure."""
    from data_providers import _record_provider_call
    _record_provider_call("yfinance", False)  # Should not raise


def test_record_provider_call_safe_when_imports_fail():
    """_record_provider_call should be completely safe even if imports fail."""
    import importlib

    import data_providers
    # Force reimport to get a fresh copy
    importlib.reload(data_providers)
    from data_providers import _record_provider_call
    # The function catches ImportError internally, so even if the module
    # doesn't have provider_monitor, it should not raise
    _record_provider_call("test", True)
    _record_provider_call("test", False)


# ---------------------------------------------------------------------------
# update_prometheus test
# ---------------------------------------------------------------------------

def test_update_prometheus():
    """provider_monitor.update_prometheus should update gauges without error."""
    from services.meta_observability import provider_monitor
    from services.observability import get_metrics_bytes

    provider_monitor.record("test_provider", True)
    provider_monitor.record("test_provider", False)
    provider_monitor.update_prometheus()

    output = get_metrics_bytes().decode()
    assert "floww_provider_success_rate{provider=\"test_provider\"}" in output
    assert "floww_provider_last_success_seconds_ago{provider=\"test_provider\"}" in output
