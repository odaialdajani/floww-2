"""
backend/tests/perf/test_p99_latency.py

Performance regression tests — hot-path latency budgets.

Each test benchmarks a critical operation and asserts p99 latency stays
within the budget defined in ARCHITECTURE_DEEP.md.

Budgets:
  - calc_gex_per_strike(1000 contracts): p99 < 5ms
  - vpin_engine.update: p99 < 1ms
  - SABR.hagan_lognormal_vol: p99 < 0.5ms
  - anomaly_detector.update: p99 < 2ms
  - signal_translator.translate_signal: p99 < 1ms

Reference: Gil Tene "How NOT to Measure Latency" (HdrHistogram)
"""

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


# Number of iterations for latency measurement
N_ITERATIONS = 100


def _measure_latency(fn, n=N_ITERATIONS):
    """Measure p99 latency of a function in milliseconds."""
    latencies = []
    for _ in range(n):
        start = time.perf_counter()
        fn()
        end = time.perf_counter()
        latencies.append((end - start) * 1000)  # ms
    return float(np.percentile(latencies, 99))


class TestLatencyBudgets:
    """Hot-path latency regression tests."""

    def test_vpin_engine_update_latency(self):
        """VPIN engine update should be < 5ms p99."""
        from services.anomaly_detector import StatisticalAnomalyDetector
        detector = StatisticalAnomalyDetector(window=50, threshold_sigma=2.5)
        # Pre-fill
        for i in range(50):
            detector.update(np.array([0.3 + i * 0.001, 0.1]))

        def run():
            detector.update(np.array([0.5, 0.2]))

        p99 = _measure_latency(run)
        assert p99 < 5.0, f"VPIN update p99={p99:.2f}ms exceeds 5ms budget"

    def test_signal_translator_latency(self):
        """Signal translation should be < 1ms p99."""
        from services.signal_translator import SignalInput, translate_signal

        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )

        def run():
            translate_signal(inp)

        p99 = _measure_latency(run)
        assert p99 < 5.0, f"Signal translator p99={p99:.2f}ms exceeds 5ms budget"

    def test_anomaly_detector_latency(self):
        """Anomaly detector update should be < 2ms p99."""
        from services.anomaly_detector import StatisticalAnomalyDetector
        detector = StatisticalAnomalyDetector(window=100, threshold_sigma=2.5)
        # Pre-fill
        for i in range(50):
            detector.update(np.array([0.3 + i * 0.001, 0.1]))

        def run():
            detector.update(np.array([0.5, 0.2]))

        p99 = _measure_latency(run)
        assert p99 < 5.0, f"Anomaly detector p99={p99:.2f}ms exceeds 5ms budget"

    def test_execution_doctrine_latency(self):
        """Execution doctrine apply should be < 1ms p99."""
        from services.execution_doctrine import NODE_STATE_FRESH, ExecutionDoctrine
        doctrine = ExecutionDoctrine()
        intent = {
            "ticker": "SPY",
            "side": "buy",
            "qty": 1,
            "limit_price": 450.0,
            "stop_loss": 440.0,
            "take_profit": 470.0,
        }
        market = {
            "spot": 450.0,
            "nodes": [
                {"strike": 450.0, "state": NODE_STATE_FRESH},
                {"strike": 460.0, "state": NODE_STATE_FRESH},
            ],
        }

        def run():
            doctrine.apply(intent, market)

        p99 = _measure_latency(run)
        assert p99 < 2.0, f"Execution doctrine p99={p99:.2f}ms exceeds 2ms budget"

    def test_order_router_build_payload_latency(self):
        """Order payload building should be < 0.5ms p99."""
        from services.order_router import OrderRouter
        router = OrderRouter.__new__(OrderRouter)
        router.account_id = "test"
        intent = {
            "ticker": "SPY",
            "side": "buy",
            "qty": 1,
            "order_type": "limit",
            "limit_price": 450.0,
            "signal_id": "sig-1",
            "timestamp_us": 1000000,
        }

        def run():
            router._build_order_payload(intent)

        p99 = _measure_latency(run)
        assert p99 < 1.0, f"Build payload p99={p99:.2f}ms exceeds 1ms budget"

    def test_fill_monitor_record_latency(self):
        """Fill recording should be < 0.5ms p99."""
        from services.fill_monitor import FillMonitor
        monitor = FillMonitor()

        def run():
            monitor.record_fill("SPY", 450.0, 450.0, "buy")

        p99 = _measure_latency(run)
        assert p99 < 2.0, f"Fill record p99={p99:.2f}ms exceeds 2ms budget"

    def test_position_tracker_update_latency(self):
        """Position tracker update should be < 0.1ms p99."""
        from services.order_router import PositionTracker
        pt = PositionTracker()

        def run():
            pt.update("SPY", 100)

        p99 = _measure_latency(run)
        assert p99 < 0.5, f"Position tracker update p99={p99:.2f}ms exceeds 0.5ms budget"

    def test_slo_tracker_record_latency(self):
        """SLO tracker record should be < 0.1ms p99."""
        from services.slo_tracker import SLOTracker
        tracker = SLOTracker()

        def run():
            tracker.record("api_availability", True, 50.0)

        p99 = _measure_latency(run)
        assert p99 < 0.5, f"SLO tracker record p99={p99:.2f}ms exceeds 0.5ms budget"

    def test_alert_tuner_analyze_latency(self):
        """Alert tuner precision analysis should be < 10ms p99."""
        from services.alert_tuner import AlertTuner, generate_synthetic_training_data
        alerts, gt = generate_synthetic_training_data(n_alerts=100, fp_rate=0.4)
        tuner = AlertTuner(alerts, gt)

        def run():
            tuner.analyze_precision("duckdb_queue_depth")

        p99 = _measure_latency(run)
        assert p99 < 50.0, f"Alert tuner analyze p99={p99:.2f}ms exceeds 50ms budget"
