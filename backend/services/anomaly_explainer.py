"""
backend/services/anomaly_explainer.py

Anomaly Explanation Generator — when an anomaly is detected, generates
a natural language explanation of what likely caused it.

Integrates with:
  - anomaly_detector.py (FlowAnomalyDetector)
  - vpin_engine.py (VpinEngine)
  - predictive_alerting.py (PredictiveAlertingEngine)

Example output:
  "VPIN spiked to 0.87 due to large block trade in SPY calls.
   Order flow toxicity increased 3.2x above 20-day average.
   Quote imbalance shifted to -0.65 (heavy sell pressure).
   Regime: urgent (realized vol > 95th percentile)."
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

log = logging.getLogger(__name__)


# Known anomaly patterns and their typical causes
ANOMALY_PATTERNS = {
    "vpin_spike": {
        "triggers": ["large block trade", "unusual options activity", "earnings surprise",
                     "index rebalancing", "forced liquidation"],
        "context_hints": {
            "high_delta": "directional hedging activity",
            "high_gamma": "gamma squeeze positioning",
            "negative_qi": "aggressive sell pressure",
            "positive_qi": "aggressive buy pressure",
        },
    },
    "qi_divergence": {
        "triggers": ["iceberg order", "spoofing layer", "dark pool print",
                     "market maker rebalancing"],
        "context_hints": {
            "vpin_low": "low toxicity — likely spoofing or iceberg",
            "vpin_high": "high toxicity — informed flow likely",
        },
    },
    "latency_spike": {
        "triggers": ["network congestion", "DuckDB lock contention",
                     "GC pause", "rate limit backoff"],
        "context_hints": {
            "queue_depth_high": "backpressure from ingestion queue",
            "ws_connections_zero": "WebSocket connection dropped",
        },
    },
    "ingestion_stall": {
        "triggers": ["Schwab token expiry", "Databento rate limit",
                     "network partition", "API key rotation"],
        "context_hints": {
            "token_expiring": "OAuth token within 5 minutes of expiry",
            "rate_limit": "API rate limit hit — backing off",
        },
    },
}


@dataclass
class AnomalyExplanation:
    """A natural language explanation for an anomaly."""
    title: str
    summary: str
    details: List[str]
    contributing_factors: List[str]
    regime: str
    confidence: float
    recommended_action: str
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "summary": self.summary,
            "details": self.details,
            "contributing_factors": self.contributing_factors,
            "regime": self.regime,
            "confidence": self.confidence,
            "recommended_action": self.recommended_action,
            "raw_data": self.raw_data,
        }

    def to_message(self) -> str:
        """Format as a concise alert message."""
        parts = [f"{self.title}", f"{self.summary}", ""]
        if self.details:
            parts.append("Details:")
            for d in self.details:
                parts.append(f"  - {d}")
        if self.contributing_factors:
            parts.append("Contributing factors:")
            for f in self.contributing_factors:
                parts.append(f"  - {f}")
        parts.append(f"Regime: {self.regime} | Confidence: {self.confidence:.0%}")
        parts.append(f"Action: {self.recommended_action}")
        return "\n".join(parts)


class AnomalyExplainer:
    """Generates natural language explanations for flow toxicity anomalies.

    Correlates VPIN, Quote Imbalance, and regime data to identify the
    most likely cause of an anomaly and explain it in plain English.
    """

    def __init__(self, history_window: int = 100):
        self._vpin_history: List[float] = []
        self._qi_history: List[float] = []
        self._history_window = history_window

    def update(self, vpin: float, qi: float):
        """Update rolling history with latest observations."""
        self._vpin_history.append(vpin)
        self._qi_history.append(qi)
        if len(self._vpin_history) > self._history_window:
            self._vpin_history.pop(0)
        if len(self._qi_history) > self._history_window:
            self._qi_history.pop(0)

    def explain(
        self,
        anomaly_result: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> AnomalyExplanation:
        """Generate a natural language explanation for an anomaly.

        Args:
            anomaly_result: Output from FlowAnomalyDetector.update()
            context: Optional additional context (e.g., queue depth, token status)

        Returns:
            AnomalyExplanation with human-readable analysis.
        """
        ctx = context or {}
        vpin = ctx.get("vpin", anomaly_result.get("anomaly_score", 0.0))
        qi = ctx.get("quote_imbalance", 0.0)
        regime = anomaly_result.get("regime", "active")
        zscore = anomaly_result.get("zscore", 0.0)
        score = anomaly_result.get("anomaly_score", 0.0)

        # Compute historical baselines
        vpin_baseline = float(np.mean(self._vpin_history)) if self._vpin_history else 0.5
        vpin_std = float(np.std(self._vpin_history)) if len(self._vpin_history) > 5 else 0.1
        qi_baseline = float(np.mean(self._qi_history)) if self._qi_history else 0.0

        # Build details
        details = []
        contributing_factors = []

        # VPIN analysis
        if vpin > vpin_baseline + 2 * vpin_std:
            ratio = vpin / (vpin_baseline + 1e-9)
            details.append(
                f"VPIN spiked to {vpin:.3f} — {ratio:.1f}x above "
                f"20-period average of {vpin_baseline:.3f}"
            )
            # Pick most likely trigger based on severity and regime
            if regime == "urgent" and vpin > 0.8:
                cause = "forced liquidation or large block trade"
            elif regime == "urgent":
                cause = "unusual options activity or directional hedging"
            elif vpin > 0.7:
                cause = "earnings surprise or index rebalancing"
            else:
                cause = "increased informed flow"
            contributing_factors.append(f"Primary: {cause}")

        # Quote Imbalance analysis
        qi_deviation = abs(qi - qi_baseline)
        if qi_deviation > 0.3:
            direction = "sell" if qi < 0 else "buy"
            details.append(
                f"Quote imbalance at {qi:.3f} — heavy {direction} pressure "
                f"(baseline: {qi_baseline:.3f})"
            )
            qi_hint = ANOMALY_PATTERNS["vpin_spike"]["context_hints"].get(
                f"{'negative' if qi < 0 else 'positive'}_qi",
                f"{direction}-side pressure"
            )
            contributing_factors.append(f"Order book: {qi_hint}")

        # Regime context
        if regime == "urgent":
            contributing_factors.append("Market regime: urgent (realized vol > 95th percentile)")
            contributing_factors.append("Higher baseline volatility — threshold adjusted to 90th percentile")
        elif regime == "calm":
            contributing_factors.append("Market regime: calm (low realized vol)")
            contributing_factors.append("Anomalies in calm regime are more significant — threshold at 99th percentile")

        # Correlation: VPIN + QI alignment
        if vpin > 0.6 and abs(qi) > 0.4:
            alignment = "confirmed" if (qi < 0 and vpin > 0.6) or (qi > 0 and vpin > 0.6) else "mixed"
            if alignment == "confirmed":
                direction_informed = "informed selling" if qi < 0 else "informed buying"
                contributing_factors.append(
                    f"VPIN-QI alignment: {direction_informed} pressure confirmed by both signals"
                )

        # System-level context
        queue_depth = ctx.get("queue_depth", 0)
        if queue_depth > 5000:
            contributing_factors.append(f"System stress: DuckDB queue depth at {queue_depth}")

        ws_connections = ctx.get("ws_connections", -1)
        if ws_connections == 0:
            contributing_factors.append("Data freshness: WebSocket connections at 0 — data may be stale")

        # Determine confidence
        data_richness = min(1.0, len(self._vpin_history) / 50.0)
        signal_strength = min(1.0, zscore / 5.0) if zscore > 0 else 0.0
        confidence = round(0.4 * data_richness + 0.6 * signal_strength, 2)
        confidence = max(0.1, min(1.0, confidence))

        # Build title and summary
        if vpin > 0.8:
            title = "CRITICAL: Extreme Flow Toxicity Detected"
            summary = (
                f"VPIN at {vpin:.3f} indicates extreme flow toxicity. "
                f"Likely caused by {contributing_factors[0].split(': ', 1)[-1] if contributing_factors else 'unknown'}."
            )
        elif vpin > 0.6:
            title = "WARNING: Elevated Flow Toxicity"
            summary = (
                f"VPIN at {vpin:.3f} is elevated. "
                f"Anomaly score: {score:.6f} (z-score: {zscore:.2f})."
            )
        else:
            title = "Flow Toxicity Anomaly"
            summary = f"Anomaly detected (score: {score:.6f}, regime: {regime})."

        # Determine recommended action
        if regime == "urgent" and vpin > 0.8:
            recommended_action = (
                "PAUTIOUS: Extreme toxicity in urgent regime. "
                "Consider reducing position size. Check for earnings/events."
            )
        elif vpin > 0.7 and qi < -0.5:
            recommended_action = (
                "WATCH: Strong sell-side toxicity. "
                "Monitor for continuation or reversal. Tighten stops."
            )
        elif vpin > 0.7 and qi > 0.5:
            recommended_action = (
                "WATCH: Strong buy-side toxicity. "
                "Momentum may continue but watch for exhaustion."
            )
        else:
            recommended_action = (
                "MONITOR: Elevated toxicity. No immediate action required."
            )

        return AnomalyExplanation(
            title=title,
            summary=summary,
            details=details,
            contributing_factors=contributing_factors,
            regime=regime,
            confidence=confidence,
            recommended_action=recommended_action,
            raw_data={
                "vpin": vpin,
                "qi": qi,
                "vpin_baseline": round(vpin_baseline, 4),
                "zscore": zscore,
                "anomaly_score": score,
                "queue_depth": queue_depth,
                "ws_connections": ws_connections,
            },
        )


# Global instance
explainer = AnomalyExplainer()
