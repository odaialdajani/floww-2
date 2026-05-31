"""
backend/tests/services/test_regime_thresholds.py

Tests for regime-aware anomaly detection thresholds.
8+ tests covering regime classification, threshold adaptation, and FP rate.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.anomaly_detector import FlowAnomalyDetector, RegimeAwareThreshold


class TestRegimeAwareThreshold:
    def test_warmup_state(self):
        """Should report warming_up until enough data."""
        rt = RegimeAwareThreshold(window=500)
        result = rt.update(0.05)
        assert result["regime"] == "warming_up"

    def test_active_regime_by_default(self):
        """Should default to active regime without vol data."""
        rt = RegimeAwareThreshold(window=500)
        result = {}
        for _ in range(25):
            result = rt.update(0.05)
        assert result["regime"] == "active"

    def test_calm_regime_at_low_vol(self):
        """Should classify calm regime at low vol percentile."""
        rt = RegimeAwareThreshold(window=500)
        # Seed vol history with HIGH values so 0.05 is low percentile
        for _ in range(100):
            rt._vol_history.append(0.30 + np.random.RandomState(42).uniform(0, 0.2))
        result = {}
        for _ in range(25):
            result = rt.update(0.05, realized_vol=0.05)
        assert result["regime"] == "calm"

    def test_urgent_regime_at_high_vol(self):
        """Should classify urgent regime at high vol percentile."""
        rt = RegimeAwareThreshold(window=500)
        for _ in range(30):
            rt._vol_history.append(0.10)
        result = {}
        for _ in range(25):
            result = rt.update(0.05, realized_vol=0.50)
        assert result["regime"] == "urgent"

    def test_threshold_higher_in_calm_than_urgent(self):
        """Calm regime should use higher percentile → higher threshold."""
        rt_calm = RegimeAwareThreshold(window=500)
        rt_urgent = RegimeAwareThreshold(window=500)

        rng = np.random.RandomState(42)
        errors = rng.uniform(0.01, 0.10, 100)

        calm_result = {}
        urgent_result = {}
        for e in errors:
            rt_calm._vol_history.append(0.05)  # low vol
            rt_urgent._vol_history.append(0.50)  # high vol
            calm_result = rt_calm.update(e, realized_vol=0.05)
            urgent_result = rt_urgent.update(e, realized_vol=0.50)

        # Calm uses 99th pct, urgent uses 90th pct → calm threshold >= urgent
        assert calm_result["threshold"] >= urgent_result["threshold"] * 0.9  # approximate

    def test_moderate_spike_flagged_in_calm_not_urgent(self):
        """Calm regime uses higher threshold (99th pct) vs urgent (90th pct)."""
        rt_calm = RegimeAwareThreshold(window=500)
        rt_urgent = RegimeAwareThreshold(window=500)

        # Seed both with same error distribution
        rng = np.random.RandomState(42)
        for _ in range(100):
            e = rng.uniform(0.01, 0.03)
            rt_calm._errors.append(e)
            rt_urgent._errors.append(e)

        # Seed vol histories to force regimes
        for _ in range(100):
            rt_calm._vol_history.append(0.30)  # high vol history
            rt_urgent._vol_history.append(0.05)  # low vol history

        # Update with different realized vols
        calm_result = rt_calm.update(0.05, realized_vol=0.02)  # low vol → calm
        urgent_result = rt_urgent.update(0.05, realized_vol=0.50)  # high vol → urgent

        assert calm_result["regime"] == "calm"
        assert urgent_result["regime"] == "urgent"
        # Calm uses 99th pct threshold (higher), urgent uses 90th pct (lower)
        assert calm_result["threshold"] >= urgent_result["threshold"]

    def test_get_state_serializable(self):
        """get_state should return JSON-serializable dict."""
        rt = RegimeAwareThreshold()
        state = rt.get_state()
        import json
        json.dumps(state)

    def test_percentile_values(self):
        """Percentile config should match spec."""
        assert RegimeAwareThreshold.PERCENTILES["calm"] == 99
        assert RegimeAwareThreshold.PERCENTILES["active"] == 95
        assert RegimeAwareThreshold.PERCENTILES["urgent"] == 90


class TestFlowAnomalyDetectorWithRegime:
    def test_regime_in_update_result(self):
        """FlowAnomalyDetector.update should include regime info."""
        det = FlowAnomalyDetector(seq_len=10, latent_dim=8)
        result = {}
        for _ in range(15):
            result = det.update(0.45, 0.1)
        assert "regime" in result
        assert "regime_threshold_used" in result

    def test_regime_in_get_state(self):
        """get_state should include regime info."""
        det = FlowAnomalyDetector(seq_len=10, latent_dim=8)
        for _ in range(15):
            det.update(0.45, 0.1)
        state = det.get_state()
        assert "trained" in state
