"""
backend/tests/services/test_predictive_alerting.py

Unit tests for predictive_alerting — forecasting + chaos scenarios.

Coverage:
    - ExponentialSmoother update and forecast
    - Confidence calculation
    - PredictiveAlertingEngine record and forecast
    - Predictive alerts generated when forecast breaches threshold
    - ChaosForecaster scenarios
    - Chaos scenario simulation
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def test_smoother_basic_forecast():
    from services.predictive_alerting import ExponentialSmoother
    s = ExponentialSmoother()
    for v in [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]:
        s.update(v)
    forecast = s.forecast(5)
    # Upward trend → forecast should be > last value (with some tolerance for smoothing)
    assert forecast > 14.5


def test_smoother_flat_forecast():
    from services.predictive_alerting import ExponentialSmoother
    s = ExponentialSmoother()
    for v in [5.0] * 20:
        s.update(v)
    forecast = s.forecast(10)
    # Flat series → forecast should be ~5
    assert abs(forecast - 5.0) < 0.5


def test_smoother_confidence():
    from services.predictive_alerting import ExponentialSmoother
    s = ExponentialSmoother()
    for v in [10.0] * 20:
        s.update(v)
    # No errors recorded yet, but enough history
    conf = s.confidence
    assert 0.0 <= conf <= 1.0


def test_smoother_not_enough_data():
    from services.predictive_alerting import ExponentialSmoother
    s = ExponentialSmoother()
    s.update(1.0)
    assert s.forecast(5) == 0.0  # level is set but trend is 0


def test_engine_record_and_forecast():
    from services.predictive_alerting import PredictiveAlertingEngine
    engine = PredictiveAlertingEngine()
    # Feed 20 samples with upward trend
    for i in range(20):
        engine.record_metric("duckdb_queue_depth", float(i * 500))
    forecast = engine.forecast_metric("duckdb_queue_depth")
    assert forecast is not None
    assert forecast.metric_name == "duckdb_queue_depth"
    assert forecast.forecast_value > 0


def test_engine_no_forecast_without_enough_data():
    from services.predictive_alerting import PredictiveAlertingEngine
    engine = PredictiveAlertingEngine()
    for i in range(3):
        engine.record_metric("duckdb_queue_depth", float(i))
    forecast = engine.forecast_metric("duckdb_queue_depth")
    assert forecast is None  # Not enough samples


def test_engine_predictive_alert_breach():
    from services.predictive_alerting import PredictiveAlertingEngine
    engine = PredictiveAlertingEngine()
    # Feed samples that trend toward the threshold (9000)
    for i in range(20):
        engine.record_metric("duckdb_queue_depth", 7000 + i * 200)
    alerts = engine.get_predictive_alerts()
    # Should predict breach since trend is upward toward 9000
    breach_alerts = [a for a in alerts if "duckdb_queue_depth" in a["alert_id"]]
    assert len(breach_alerts) >= 1


def test_engine_no_false_alerts():
    from services.predictive_alerting import PredictiveAlertingEngine
    engine = PredictiveAlertingEngine()
    # Feed stable low values
    for _i in range(20):
        engine.record_metric("duckdb_queue_depth", 100.0)
    alerts = engine.get_predictive_alerts()
    assert len(alerts) == 0


def test_chaos_scenarios_exist():
    from services.predictive_alerting import ChaosForecaster
    scenarios = ChaosForecaster.get_scenarios()
    assert len(scenarios) >= 4
    names = [s.name for s in scenarios]
    assert "duckdb_lock_contention" in names
    assert "ingestion_ws_disconnect" in names
    assert "memory_pressure" in names
    assert "databento_rate_limit" in names


def test_chaos_scenario_run():
    from services.predictive_alerting import ChaosForecaster
    result = ChaosForecaster.run_scenario("duckdb_lock_contention", {"duckdb_queue_depth": 100})
    assert result is not None
    assert result["scenario"] == "duckdb_lock_contention"
    assert result["simulated_state"]["duckdb_queue_depth"] == 15000
    assert len(result["cascade_predictions"]) > 0
    assert result["max_severity"] == "CRITICAL"


def test_chaos_scenario_not_found():
    from services.predictive_alerting import ChaosForecaster
    result = ChaosForecaster.run_scenario("nonexistent", {})
    assert result is None


def test_chaos_scenario_has_recommended_action():
    from services.predictive_alerting import ChaosForecaster
    for scenario in ChaosForecaster.get_scenarios():
        assert len(scenario.recommended_action) > 0
        assert len(scenario.cascade_predictions) > 0


def test_forecast_all():
    from services.predictive_alerting import PredictiveAlertingEngine
    engine = PredictiveAlertingEngine()
    for i in range(20):
        engine.record_metric("duckdb_queue_depth", float(i * 100))
        engine.record_metric("p99_latency", 0.05 + i * 0.01)
    forecasts = engine.forecast_all()
    assert len(forecasts) == 2
    names = [f.metric_name for f in forecasts]
    assert "duckdb_queue_depth" in names
    assert "p99_latency" in names
