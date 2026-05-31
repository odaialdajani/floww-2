"""
backend/services/meta_observability.py

Meta-anomaly detection on Prometheus metrics themselves.
Trains an Isolation Forest on rolling metrics to detect deviations from
"time-of-day" baselines — e.g., Tuesday 2pm now vs Tuesday 2pm average.

Inputs (from Prometheus scrape):
    - ingestion_rate per symbol
    - duckdb_queue_depth
    - vpin_current per ticker
    - p99 API latency
    - websocket_connections

Output: LOW-severity warnings surfaced before they become incidents.

Model: sklearn.ensemble.IsolationForest
Persistence: ./project_oracle/models/meta_anomaly_v1.pt (joblib)
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

log = logging.getLogger(__name__)

# Model path
MODEL_DIR = Path(__file__).resolve().parents[2] / "project_oracle" / "models"
MODEL_PATH = MODEL_DIR / "meta_anomaly_v1.pt"

# Feature names (must match training order)
FEATURES = [
    "ingestion_rate_spy",
    "ingestion_rate_qqq",
    "queue_depth",
    "vpin_spy",
    "vpin_qqq",
    "p99_latency",
    "ws_connections",
    "cache_hit_ratio",
    "429_count",
    "hour_of_day",      # cyclical encoding
    "day_of_week",      # cyclical encoding
]

# Anomaly threshold (Isolation Forest decision_function score)
ANOMALY_THRESHOLD = -0.15


class MetaAnomalyDetector:
    """Detects anomalies in the metrics themselves using Isolation Forest."""

    def __init__(self):
        self._model: Any = None
        self._scaler: Any = None
        self._last_score: float = 0.0
        self._last_anomaly: bool = False
        self._training_data: List[List[float]] = []
        self._training_max = 10080  # 7 days of 1-min samples
        self._load_model()

    # ------------------------------------------------------------------
    # Model persistence
    # ------------------------------------------------------------------

    def _load_model(self):
        """Load trained model from disk."""
        try:
            import joblib
            if MODEL_PATH.exists():
                data = joblib.load(MODEL_PATH)
                self._model = data["model"]
                self._scaler = data["scaler"]
                log.info(f"Meta-anomaly model loaded from {MODEL_PATH}")
            else:
                log.info("No saved meta-anomaly model — will train on first data")
        except ImportError:
            log.warning("joblib not available — meta-anomaly detection disabled")
        except Exception as e:
            log.warning(f"Failed to load meta-anomaly model: {e}")

    def _save_model(self):
        """Save trained model to disk."""
        try:
            import joblib
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            joblib.dump({"model": self._model, "scaler": self._scaler}, MODEL_PATH)
            log.info(f"Meta-anomaly model saved to {MODEL_PATH}")
        except Exception as e:
            log.error(f"Failed to save meta-anomaly model: {e}")

    # ------------------------------------------------------------------
    # Feature extraction
    # ------------------------------------------------------------------

    def _extract_features(self, metrics_snapshot: Dict[str, float]) -> List[float]:
        """Extract feature vector from a Prometheus metrics snapshot.

        metrics_snapshot keys:
            ingestion_rate_spy, ingestion_rate_qqq, queue_depth,
            vpin_spy, vpin_qqq, p99_latency, ws_connections,
            cache_hit_ratio, 429_count
        """
        now = datetime.now(timezone.utc)
        hour = now.hour + now.minute / 60.0
        dow = now.weekday()

        # Cyclical encoding for time features
        hour_sin = np.sin(2 * np.pi * hour / 24.0)
        hour_cos = np.cos(2 * np.pi * hour / 24.0)
        dow_sin = np.sin(2 * np.pi * dow / 7.0)
        dow_cos = np.cos(2 * np.pi * dow / 7.0)

        return [
            metrics_snapshot.get("ingestion_rate_spy", 0.0),
            metrics_snapshot.get("ingestion_rate_qqq", 0.0),
            metrics_snapshot.get("queue_depth", 0.0),
            metrics_snapshot.get("vpin_spy", 0.0),
            metrics_snapshot.get("vpin_qqq", 0.0),
            metrics_snapshot.get("p99_latency", 0.0),
            metrics_snapshot.get("ws_connections", 0.0),
            metrics_snapshot.get("cache_hit_ratio", 1.0),
            metrics_snapshot.get("429_count", 0.0),
            hour_sin * 0.5 + hour_cos * 0.5,  # combined cyclical
            dow_sin * 0.5 + dow_cos * 0.5,
        ]

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def add_training_sample(self, metrics_snapshot: Dict[str, float]):
        """Add a sample to the training buffer. Triggers training when buffer is full."""
        features = self._extract_features(metrics_snapshot)
        self._training_data.append(features)

        if len(self._training_data) > self._training_max:
            self._training_data = self._training_data[-self._training_max:]

        # Auto-train every 1440 samples (1 day of 1-min data)
        if len(self._training_data) % 1440 == 0 and len(self._training_data) >= 2880:
            self.train()

    def train(self):
        """Train the Isolation Forest on collected training data."""
        try:
            from sklearn.ensemble import IsolationForest
            from sklearn.preprocessing import StandardScaler
        except ImportError:
            log.warning("sklearn not available — cannot train meta-anomaly model")
            return

        if len(self._training_data) < 100:
            log.info(f"Not enough training data ({len(self._training_data)} samples)")
            return

        X = np.array(self._training_data)
        self._scaler = StandardScaler()
        X_scaled = self._scaler.fit_transform(X)

        self._model = IsolationForest(
            n_estimators=100,
            contamination=0.05,
            random_state=42,
            n_jobs=-1,
        )
        self._model.fit(X_scaled)
        self._save_model()
        log.info(f"Meta-anomaly model trained on {len(self._training_data)} samples")

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def score(self, metrics_snapshot: Dict[str, float]) -> Dict[str, Any]:
        """Score a metrics snapshot for anomaly detection.

        Returns:
            {
                "anomaly_score": float,  # Isolation Forest decision_function
                "is_anomaly": bool,      # True if score < threshold
                "model_loaded": bool,
                "training_samples": int,
            }
        """
        features = self._extract_features(metrics_snapshot)

        # Always add to training buffer
        self.add_training_sample(metrics_snapshot)

        if self._model is None or self._scaler is None:
            return {
                "anomaly_score": 0.0,
                "is_anomaly": False,
                "model_loaded": False,
                "training_samples": len(self._training_data),
            }

        try:
            X = np.array([features])
            X_scaled = self._scaler.transform(X)
            score = float(self._model.decision_function(X_scaled)[0])
            is_anomaly = score < ANOMALY_THRESHOLD

            self._last_score = score
            self._last_anomaly = is_anomaly

            if is_anomaly:
                log.warning(
                    f"[META-ANOMALY] score={score:.4f} — deviation from time-of-day baseline"
                )

            return {
                "anomaly_score": round(score, 4),
                "is_anomaly": is_anomaly,
                "model_loaded": True,
                "training_samples": len(self._training_data),
            }
        except Exception as e:
            log.error(f"Meta-anomaly scoring failed: {e}")
            return {
                "anomaly_score": 0.0,
                "is_anomaly": False,
                "model_loaded": True,
                "training_samples": len(self._training_data),
            }

    def get_state(self) -> Dict[str, Any]:
        """Return current detector state."""
        return {
            "model_loaded": self._model is not None,
            "training_samples": len(self._training_data),
            "last_score": self._last_score,
            "last_anomaly": self._last_anomaly,
            "threshold": ANOMALY_THRESHOLD,
            "model_path": str(MODEL_PATH),
        }


# Global singleton
meta_detector = MetaAnomalyDetector()


# ---------------------------------------------------------------------------
# Data Provider Monitor — rolling success rates + alerting
# ---------------------------------------------------------------------------


@dataclass
class ProviderStats:
    """Rolling stats for a single data provider."""
    name: str
    window_seconds: float = 300.0  # 5-minute rolling window
    _calls: list = field(default_factory=list)  # list of (timestamp, success: bool)
    _last_success: float = 0.0
    _last_failure: float = 0.0
    _consecutive_failures: int = 0
    _total_calls: int = 0
    _total_successes: int = 0

    def record(self, success: bool):
        now = time.time()
        self._calls.append((now, success))
        self._total_calls += 1
        if success:
            self._total_successes += 1
            self._last_success = now
            self._consecutive_failures = 0
        else:
            self._last_failure = now
            self._consecutive_failures += 1
        # Prune old entries outside the rolling window
        cutoff = now - self.window_seconds
        self._calls = [(t, s) for t, s in self._calls if t >= cutoff]

    @property
    def success_rate(self) -> float:
        if not self._calls:
            return 1.0  # no data yet = assume healthy
        successes = sum(1 for _, s in self._calls if s)
        return successes / len(self._calls)

    @property
    def window_calls(self) -> int:
        return len(self._calls)

    @property
    def seconds_since_last_success(self) -> float:
        if self._last_success == 0:
            return float("inf")
        return time.time() - self._last_success

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures


class DataProviderMonitor:
    """
    Monitors data provider health with rolling success rates and configurable alerting.

    Usage:
        monitor = DataProviderMonitor()
        monitor.record("yfinance", success=True)
        monitor.record("finnhub", success=False)
        alerts = monitor.check_alerts()

    Alert thresholds:
        - low_success_rate: success rate < min_success_rate over the rolling window
        - provider_down: no successful call in provider_down_seconds
        - repeated_failures: consecutive_failures >= max_consecutive_failures
    """

    def __init__(
        self,
        min_success_rate: float = 0.5,
        provider_down_seconds: float = 120.0,
        max_consecutive_failures: int = 5,
        window_seconds: float = 300.0,
        on_alert: Optional[Callable[[str, str, Dict[str, Any]], None]] = None,
    ):
        self.min_success_rate = min_success_rate
        self.provider_down_seconds = provider_down_seconds
        self.max_consecutive_failures = max_consecutive_failures
        self.window_seconds = window_seconds
        self.on_alert = on_alert
        self._providers: Dict[str, ProviderStats] = {}
        self._alerted: Dict[str, set] = defaultdict(set)  # provider -> set of active alert_types

    def _get_stats(self, provider: str) -> ProviderStats:
        if provider not in self._providers:
            self._providers[provider] = ProviderStats(
                name=provider,
                window_seconds=self.window_seconds,
            )
        return self._providers[provider]

    def record(self, provider: str, success: bool):
        """Record a call result for a provider."""
        stats = self._get_stats(provider)
        stats.record(success)

    def check_alerts(self) -> List[Dict[str, Any]]:
        """
        Check all providers for alert conditions.
        Returns list of alert dicts and fires callbacks.
        """
        alerts = []
        for name, stats in self._providers.items():
            # Alert: low success rate
            if stats.window_calls >= 3 and stats.success_rate < self.min_success_rate:
                if "low_success_rate" not in self._alerted[name]:
                    alert = {
                        "provider": name,
                        "alert_type": "low_success_rate",
                        "success_rate": round(stats.success_rate, 3),
                        "threshold": self.min_success_rate,
                        "window_calls": stats.window_calls,
                        "severity": "warning",
                    }
                    alerts.append(alert)
                    self._alerted[name].add("low_success_rate")
                    if self.on_alert:
                        self.on_alert(name, "low_success_rate", alert)
            else:
                self._alerted[name].discard("low_success_rate")

            # Alert: provider down (no success in N seconds)
            if stats.seconds_since_last_success > self.provider_down_seconds and stats.window_calls > 0:
                if "provider_down" not in self._alerted[name]:
                    alert = {
                        "provider": name,
                        "alert_type": "provider_down",
                        "seconds_since_success": round(stats.seconds_since_last_success, 1),
                        "threshold_seconds": self.provider_down_seconds,
                        "severity": "critical",
                    }
                    alerts.append(alert)
                    self._alerted[name].add("provider_down")
                    if self.on_alert:
                        self.on_alert(name, "provider_down", alert)
            else:
                self._alerted[name].discard("provider_down")

            # Alert: repeated consecutive failures
            if stats.consecutive_failures >= self.max_consecutive_failures:
                if "repeated_failures" not in self._alerted[name]:
                    alert = {
                        "provider": name,
                        "alert_type": "repeated_failures",
                        "consecutive_failures": stats.consecutive_failures,
                        "threshold": self.max_consecutive_failures,
                        "severity": "warning",
                    }
                    alerts.append(alert)
                    self._alerted[name].add("repeated_failures")
                    if self.on_alert:
                        self.on_alert(name, "repeated_failures", alert)
            else:
                self._alerted[name].discard("repeated_failures")

        return alerts

    def get_health(self) -> Dict[str, Any]:
        """Return health summary for all providers."""
        providers = {}
        for name, stats in self._providers.items():
            providers[name] = {
                "success_rate": round(stats.success_rate, 3),
                "window_calls": stats.window_calls,
                "total_calls": stats._total_calls,
                "total_successes": stats._total_successes,
                "seconds_since_last_success": round(stats.seconds_since_last_success, 1),
                "consecutive_failures": stats.consecutive_failures,
            }
        return {
            "providers": providers,
            "thresholds": {
                "min_success_rate": self.min_success_rate,
                "provider_down_seconds": self.provider_down_seconds,
                "max_consecutive_failures": self.max_consecutive_failures,
                "window_seconds": self.window_seconds,
            },
            "active_alerts": self.check_alerts(),
        }

    def update_prometheus(self):
        """Update Prometheus gauges from current stats."""
        try:
            from services.observability import (
                provider_last_success_seconds_ago,
                provider_success_rate,
            )
            for name, stats in self._providers.items():
                # Set success rate gauge
                provider_success_rate.labels(provider=name).set(round(stats.success_rate, 4))
                # Set seconds since last success
                provider_last_success_seconds_ago.labels(provider=name).set(
                    round(stats.seconds_since_last_success, 1)
                )
        except Exception as e:
            log.debug(f"Failed to update Prometheus gauges: {e}")


# Global singleton
provider_monitor = DataProviderMonitor()
