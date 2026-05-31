"""
backend/services/alert_tuner.py

Alert Precision Tuning — analyzes historical alerts vs. actual incidents
to adjust thresholds and reduce false positives by 50%.

Method:
  1. Collect historical alert firings and whether they corresponded to
     actual incidents (ground truth).
  2. Compute precision = TP / (TP + FP) per alert type.
  3. For low-precision alerts, adjust thresholds using holdout validation.
  4. Target: reduce false positives by 50% while maintaining >= 95% recall.

Usage:
    tuner = AlertTuner(historical_alerts, ground_truth)
    new_thresholds = tuner.optimize()
    report = tuner.generate_report()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class AlertRecord:
    """A single historical alert firing."""
    alert_id: str
    timestamp: float  # unix epoch
    metric_name: str
    threshold_used: float
    observed_value: float
    was_true_positive: Optional[bool] = None  # None = unlabeled


@dataclass
class TuningResult:
    """Result of threshold optimization for one alert type."""
    alert_id: str
    metric_name: str
    old_threshold: float
    new_threshold: float
    old_precision: float
    new_precision: float
    old_recall: float
    new_recall: float
    false_positive_reduction_pct: float
    n_samples: int
    n_true_positives: int
    n_false_positives: int


@dataclass
class AlertTuner:
    """Analyzes historical alerts and optimizes thresholds for precision.

    The tuner works in two phases:
      1. ANALYZE: Compute precision/recall per alert type on training data.
      2. OPTIMIZE: Grid-search threshold space on holdout data to find
         the threshold that maximizes precision while keeping recall >= 0.95.
    """

    # Minimum precision target per alert type
    MIN_PRECISION = 0.50

    # Minimum recall that must be maintained after tuning
    MIN_RECALL = 0.95

    # Fraction of data used for training (rest is holdout)
    TRAIN_FRACTION = 0.7

    def __init__(
        self,
        historical_alerts: List[AlertRecord],
        ground_truth: Optional[Dict[float, bool]] = None,
    ):
        """
        Args:
            historical_alerts: List of AlertRecord for all past firings.
            ground_truth: Optional dict mapping timestamp -> is_incident.
                          If provided, labels alerts automatically.
        """
        self._alerts = historical_alerts
        self._ground_truth = ground_truth or {}
        self._results: List[TuningResult] = []

        # Auto-label if ground truth provided
        if self._ground_truth:
            for alert in self._alerts:
                # Match within 60-second window
                for ts, is_incident in self._ground_truth.items():
                    if abs(alert.timestamp - ts) < 60:
                        alert.was_true_positive = is_incident
                        break

    def analyze_precision(self, alert_id: str) -> Dict[str, Any]:
        """Compute precision metrics for a specific alert type."""
        records = [r for r in self._alerts if r.alert_id == alert_id]
        labeled = [r for r in records if r.was_true_positive is not None]

        if not labeled:
            return {
                "alert_id": alert_id,
                "precision": None,
                "recall": None,
                "n_labeled": 0,
                "n_total": len(records),
                "status": "no_ground_truth",
            }

        tp = sum(1 for r in labeled if r.was_true_positive)
        fp = sum(1 for r in labeled if not r.was_true_positive)

        # For recall, we need total actual incidents
        total_incidents = sum(1 for v in self._ground_truth.values() if v)
        fn = total_incidents - tp if total_incidents > 0 else 0

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

        return {
            "alert_id": alert_id,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "n_labeled": len(labeled),
            "n_total": len(records),
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": max(0, fn),
            "status": "analyzed",
        }

    def optimize_threshold(self, alert_id: str) -> Optional[TuningResult]:
        """Find optimal threshold for an alert type using holdout validation.

        Grid-searches threshold candidates between the 10th and 90th
        percentile of observed values, picking the one that maximizes
        precision while maintaining recall >= MIN_RECALL.
        """
        records = [r for r in self._alerts if r.alert_id == alert_id]
        labeled = [r for r in records if r.was_true_positive is not None]

        if len(labeled) < 10:
            log.info(f"[{alert_id}] Not enough labeled data ({len(labeled)}), skipping optimization")
            return None

        # Split into train / holdout
        split_idx = int(len(labeled) * self.TRAIN_FRACTION)
        train = labeled[:split_idx]
        holdout = labeled[split_idx:]

        if len(holdout) < 3:
            log.info(f"[{alert_id}] Holdout too small ({len(holdout)}), using all data")
            train = labeled
            holdout = labeled

        values = [r.observed_value for r in train]
        old_threshold = records[0].threshold_used if records else float("inf")

        # Compute old precision on holdout
        old_tp = sum(1 for r in holdout if r.observed_value >= old_threshold and r.was_true_positive)
        old_fp = sum(1 for r in holdout if r.observed_value >= old_threshold and not r.was_true_positive)
        old_fn = sum(1 for r in holdout if r.observed_value < old_threshold and r.was_true_positive)
        old_precision = old_tp / (old_tp + old_fp) if (old_tp + old_fp) > 0 else 0.0
        old_recall = old_tp / (old_tp + old_fn) if (old_tp + old_fn) > 0 else 0.0

        # Grid search threshold candidates
        p10 = float(np.percentile(values, 10))
        p90 = float(np.percentile(values, 90))
        candidates = np.linspace(p10, p90, 50)

        best_threshold = old_threshold
        best_precision = old_precision
        best_recall = old_recall

        for candidate in candidates:
            tp = sum(1 for r in holdout if r.observed_value >= candidate and r.was_true_positive)
            fp = sum(1 for r in holdout if r.observed_value >= candidate and not r.was_true_positive)
            fn = sum(1 for r in holdout if r.observed_value < candidate and r.was_true_positive)

            prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0

            if rec >= self.MIN_RECALL and prec > best_precision:
                best_threshold = float(candidate)
                best_precision = prec
                best_recall = rec

        # Compute FP reduction
        old_fp_count = sum(1 for r in holdout if r.observed_value >= old_threshold and not r.was_true_positive)
        new_fp_count = sum(1 for r in holdout if r.observed_value >= best_threshold and not r.was_true_positive)
        fp_reduction = ((old_fp_count - new_fp_count) / old_fp_count * 100) if old_fp_count > 0 else 0.0

        result = TuningResult(
            alert_id=alert_id,
            metric_name=records[0].metric_name if records else "",
            old_threshold=round(old_threshold, 4),
            new_threshold=round(best_threshold, 4),
            old_precision=round(old_precision, 4),
            new_precision=round(best_precision, 4),
            old_recall=round(old_recall, 4),
            new_recall=round(best_recall, 4),
            false_positive_reduction_pct=round(fp_reduction, 1),
            n_samples=len(holdout),
            n_true_positives=old_tp,
            n_false_positives=old_fp,
        )

        self._results.append(result)
        log.info(
            f"[{alert_id}] Tuned: threshold {old_threshold:.2f} -> {best_threshold:.2f}, "
            f"precision {old_precision:.2%} -> {best_precision:.2%}, "
            f"FP reduction: {fp_reduction:.1f}%"
        )
        return result

    def optimize_all(self) -> List[TuningResult]:
        """Optimize thresholds for all alert types."""
        alert_ids = set(r.alert_id for r in self._alerts)
        results = []
        for alert_id in sorted(alert_ids):
            result = self.optimize_threshold(alert_id)
            if result:
                results.append(result)
        return results

    def get_new_thresholds(self) -> Dict[str, float]:
        """Return the optimized thresholds as a dict."""
        return {r.alert_id: r.new_threshold for r in self._results}

    def generate_report(self) -> str:
        """Generate a markdown report of tuning results."""
        lines = [
            "# Alert Precision Tuning Report",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            "",
            "## Summary",
            "| Alert ID | Metric | Old Threshold | New Threshold | Old Precision | New Precision | FP Reduction |",
            "|----------|--------|---------------|---------------|---------------|---------------|--------------|",
        ]

        total_fp_reduction = 0.0
        for r in self._results:
            lines.append(
                f"| {r.alert_id} | {r.metric_name} | {r.old_threshold} | {r.new_threshold} "
                f"| {r.old_precision:.2%} | {r.new_precision:.2%} | {r.false_positive_reduction_pct:.1f}% |"
            )
            total_fp_reduction += r.false_positive_reduction_pct

        avg_fp_reduction = total_fp_reduction / len(self._results) if self._results else 0.0
        lines.extend([
            "",
            f"**Average FP Reduction: {avg_fp_reduction:.1f}%**",
            "",
            "## Per-Alert Details",
        ])

        for r in self._results:
            lines.extend([
                f"### {r.alert_id}",
                f"- Metric: {r.metric_name}",
                f"- Threshold: {r.old_threshold} -> {r.new_threshold}",
                f"- Precision: {r.old_precision:.2%} -> {r.new_precision:.2%}",
                f"- Recall: {r.old_recall:.2%} -> {r.new_recall:.2%}",
                f"- FP Reduction: {r.false_positive_reduction_pct:.1f}%",
                f"- Holdout samples: {r.n_samples} (TP={r.n_true_positives}, FP={r.n_false_positives})",
                "",
            ])

        return "\n".join(lines)


def generate_synthetic_training_data(n_alerts: int = 200, fp_rate: float = 0.4) -> Tuple[List[AlertRecord], Dict[float, bool]]:
    """Generate synthetic historical alert data for testing.

    Creates alerts with a configurable false positive rate so the tuner
    can demonstrate improvement.
    """
    np.random.seed(42)
    alerts = []
    ground_truth = {}

    for i in range(n_alerts):
        ts = 1700000000.0 + i * 300  # 5-min intervals
        is_incident = np.random.random() < 0.3  # 30% actual incidents
        ground_truth[ts] = bool(is_incident)

        if is_incident:
            value = np.random.uniform(8000, 12000)  # High values = real incidents
        else:
            # FP rate determines how often non-incidents still fire
            if np.random.random() < fp_rate:
                value = np.random.uniform(7000, 9500)  # Borderline, causes FP
            else:
                value = np.random.uniform(1000, 5000)  # Clearly below threshold

        alerts.append(AlertRecord(
            alert_id="duckdb_queue_depth",
            timestamp=ts,
            metric_name="duckdb_queue_depth",
            threshold_used=9000.0,
            observed_value=round(float(value), 2),
        ))

    return alerts, ground_truth
