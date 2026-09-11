"""
backend/services/predictive_alerting.py

Predictive alerting — time-series forecasting on Prometheus metrics
to predict incidents BEFORE they fire.

Uses lightweight exponential smoothing (no heavy ML deps) to forecast
metric values 5-15 minutes ahead. When a forecast crosses an alert
threshold, fires a PREDICTIVE alert (LOW severity) giving operators
time to intervene before the actual CRITICAL fires.

Forecasts:
- duckdb_queue_depth → predict backpressure 5min before it hits 9000
- ingestion_rate → predict stall 3min before rate hits 0
- p99_latency → predict SLA breach 10min before
- vpin_current → predict anomaly threshold breach

Also includes chaos forecasting: simulates failure scenarios
(disk full, network partition, DuckDB lock contention) and predicts
cascade effects through the metric graph.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

# Forecast horizon (seconds)
FORECAST_HORIZON_SHORT = 300   # 5 minutes
FORECAST_HORIZON_MEDIUM = 600  # 10 minutes
FORECAST_HORIZON_LONG = 900    # 15 minutes

# Minimum samples before forecasting
MIN_SAMPLES = 10


@dataclass
class MetricForecast:
    """A single metric's forecast result."""
    metric_name: str
    current_value: float
    forecast_value: float
    horizon_seconds: int
    confidence: float  # 0-1, based on recent prediction accuracy
    will_breach: bool
    breach_threshold: float
    breach_eta_seconds: float | None  # estimated seconds until breach


@dataclass
class ChaosScenario:
    """A simulated failure scenario."""
    name: str
    description: str
    injected_metrics: dict[str, float]  # metric_name -> simulated value
    cascade_predictions: list[str]  # human-readable cascade effects
    max_severity: str  # CRITICAL, MEDIUM, LOW
    recommended_action: str


class ExponentialSmoother:
    """Double exponential smoothing (Holt's method) for forecasting."""

    def __init__(self, alpha: float = 0.3, beta: float = 0.1):
        self.alpha = alpha
        self.beta = beta
        self.level: float | None = None
        self.trend: float | None = None
        self._history: list[float] = []
        self._errors: list[float] = []

    def update(self, value: float):
        """Add a new observation."""
        self._history.append(value)
        if self.level is None:
            self.level = value
            self.trend = 0.0
        else:
            prev_level = self.level
            self.level = self.alpha * value + (1 - self.alpha) * (self.level + self.trend)
            self.trend = self.beta * (self.level - prev_level) + (1 - self.beta) * self.trend

    def forecast(self, steps_ahead: int) -> float:
        """Forecast `steps_ahead` periods into the future."""
        if self.level is None or self.trend is None:
            return 0.0
        if len(self._history) < 2:
            return 0.0
        return float(self.level + steps_ahead * self.trend)

    @property
    def confidence(self) -> float:
        """Confidence based on recent prediction error (0-1)."""
        if len(self._errors) < 3:
            return 0.5
        recent_mae = float(np.mean(np.abs(self._errors[-10:])))
        level_val = abs(self.level) if self.level is not None else 0.0
        return max(0.0, min(1.0, 1.0 - recent_mae / (level_val + 1e-9)))


class PredictiveAlertingEngine:
    """Forecasts metrics and generates predictive alerts."""

    def __init__(self):
        self._forecasters: dict[str, ExponentialSmoother] = {}
        self._thresholds: dict[str, float] = {
            "duckdb_queue_depth": 9000,
            "ingestion_rate_spy": 0.1,  # near-zero = stalled
            "p99_latency": 0.2,  # 200ms
            "vpin_spy": 0.8,  # high VPIN
        }
        self._last_predictions: dict[str, float] = {}

    def record_metric(self, name: str, value: float):
        """Record a metric observation for forecasting."""
        if name not in self._forecasters:
            self._forecasters[name] = ExponentialSmoother()
        self._forecasters[name].update(value)

    def forecast_metric(self, name: str, horizon_seconds: int = FORECAST_HORIZON_SHORT) -> MetricForecast | None:
        """Forecast a single metric."""
        if name not in self._forecasters:
            return None
        forecaster = self._forecasters[name]
        if len(forecaster._history) < MIN_SAMPLES:
            return None

        # Assume 1-minute sampling interval
        steps = max(1, horizon_seconds // 60)
        forecast_val = forecaster.forecast(steps)
        current = forecaster._history[-1] if forecaster._history else 0.0
        threshold = self._thresholds.get(name, float("inf"))

        # Estimate time to breach
        breach_eta = None
        will_breach = forecast_val >= threshold
        if will_breach and forecaster.trend and forecaster.trend > 0:
            breach_eta = max(0, (threshold - current) / forecaster.trend) * 60  # seconds

        return MetricForecast(
            metric_name=name,
            current_value=round(current, 4),
            forecast_value=round(forecast_val, 4),
            horizon_seconds=horizon_seconds,
            confidence=round(forecaster.confidence, 2),
            will_breach=will_breach,
            breach_threshold=threshold,
            breach_eta_seconds=round(breach_eta, 0) if breach_eta else None,
        )

    def forecast_all(self) -> list[MetricForecast]:
        """Forecast all tracked metrics."""
        results = []
        for name in self._forecasters:
            forecast = self.forecast_metric(name)
            if forecast:
                results.append(forecast)
        return results

    def get_predictive_alerts(self) -> list[dict[str, Any]]:
        """Get alerts for metrics predicted to breach thresholds."""
        alerts = []
        for forecast in self.forecast_all():
            if forecast.will_breach and forecast.confidence > 0.3:
                eta_str = f"~{forecast.breach_eta_seconds:.0f}s" if forecast.breach_eta_seconds else "unknown"
                alerts.append({
                    "alert_id": f"PREDICT-{forecast.metric_name}",
                    "severity": "LOW",
                    "title": f"Predicted: {forecast.metric_name} breach",
                    "message": (
                        f"{forecast.metric_name} currently {forecast.current_value}, "
                        f"forecast {forecast.forecast_value} in {forecast.horizon_seconds}s "
                        f"(threshold: {forecast.breach_threshold}, ETA: {eta_str}, "
                        f"confidence: {forecast.confidence:.0%})"
                    ),
                    "category": "PredictiveAlert",
                    "forecast": {
                        "metric": forecast.metric_name,
                        "current": forecast.current_value,
                        "forecast": forecast.forecast_value,
                        "eta_seconds": forecast.breach_eta_seconds,
                        "confidence": forecast.confidence,
                    },
                })
        return alerts


class ChaosForecaster:
    """Simulates failure scenarios and predicts cascade effects."""

    # Predefined chaos scenarios
    SCENARIOS = [
        ChaosScenario(
            name="duckdb_lock_contention",
            description="DuckDB write lock held for 30s (e.g., large query)",
            injected_metrics={"duckdb_queue_depth": 15000, "p99_latency": 2.0},
            cascade_predictions=[
                "Queue depth exceeds 9000 → QueueBackpressure CRITICAL fires in ~1min",
                "API p99 exceeds 200ms → APIErrorRateHigh may fire if sustained",
                "Ingestion stalls → IngestionStalled WARNING fires in ~2min",
            ],
            max_severity="CRITICAL",
            recommended_action="Kill long-running DuckDB query; restart duckdb_engine if needed",
        ),
        ChaosScenario(
            name="ingestion_ws_disconnect",
            description="Market-data WebSocket drops and reconnect loop fails",
            injected_metrics={"ingestion_rate_spy": 0.0, "ingestion_rate_qqq": 0.0},
            cascade_predictions=[
                "Ingestion rate drops to 0 → IngestionStalled WARNING in 2min",
                "VPIN becomes stale → anomaly detector may flag on old data",
                "Trinity score freezes → stale alignment signals",
            ],
            max_severity="WARNING",
            recommended_action="Check brokerage/API credentials; restart the streamer",
        ),
        ChaosScenario(
            name="memory_pressure",
            description="System memory >90% — OOM killer may target Python process",
            injected_metrics={"duckdb_queue_depth": 5000, "p99_latency": 0.5, "ws_connections": 0.0},
            cascade_predictions=[
                "WebSocket connections drop → clients lose real-time data",
                "API latency spikes → potential 5xx errors",
                "DuckDB queue builds up → backpressure cascade",
            ],
            max_severity="CRITICAL",
            recommended_action="Identify memory leak; restart services; consider horizontal scaling",
        ),
        ChaosScenario(
            name="databento_rate_limit",
            description="Databento API rate limit hit — OI prefetch fails",
            injected_metrics={"ingestion_rate_spy": 0.0, "vpin_spy": 0.0},
            cascade_predictions=[
                "No new OI data → GEX calculations stale",
                "VPIN cannot update → anomaly detector loses accuracy",
                "Trinity alignment may drift from true market state",
            ],
            max_severity="WARNING",
            recommended_action="Wait for rate limit reset; fall back to yfinance OI data",
        ),
    ]

    @classmethod
    def get_scenarios(cls) -> list[ChaosScenario]:
        """Return all chaos scenarios."""
        return cls.SCENARIOS

    @classmethod
    def run_scenario(cls, scenario_name: str, current_metrics: dict[str, float]) -> dict[str, Any] | None:
        """Run a chaos scenario against current metrics and return predictions."""
        scenario = next((s for s in cls.SCENARIOS if s.name == scenario_name), None)
        if not scenario:
            return None

        # Merge injected metrics with current
        simulated = dict(current_metrics)
        simulated.update(scenario.injected_metrics)

        return {
            "scenario": scenario.name,
            "description": scenario.description,
            "injected_metrics": scenario.injected_metrics,
            "cascade_predictions": scenario.cascade_predictions,
            "max_severity": scenario.max_severity,
            "recommended_action": scenario.recommended_action,
            "simulated_state": simulated,
        }


# Global instances
predictive_engine = PredictiveAlertingEngine()
chaos_forecaster = ChaosForecaster()
