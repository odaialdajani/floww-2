"""
backend/tests/services/test_correlation_engine.py

Tests for the cross-asset/exchange VPIN CDF correlation engine.
8+ tests covering initialization, correlation computation, z-score
transforms, and edge cases.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.correlation_engine import CorrelationEngine


class TestCorrelationEngineInit:
    """Test initialization and configuration."""

    def test_default_init(self):
        eng = CorrelationEngine()
        assert eng.window == 60
        assert "SPY" in eng.assets
        assert "NYSE" in eng.exchanges
        assert eng.asset_corr_zscore == 0.0
        assert eng.exchange_corr_zscore == 0.0

    def test_custom_init(self):
        eng = CorrelationEngine(
            window=30, assets=["AAPL", "MSFT"], exchanges=["NYSE", "ARCA"]
        )
        assert eng.window == 30
        assert eng.assets == ["AAPL", "MSFT"]
        assert eng.exchanges == ["NYSE", "ARCA"]

    def test_invalid_window(self):
        with pytest.raises(ValueError, match="window must be >= 2"):
            CorrelationEngine(window=1)


class TestCorrelationEngineUpdate:
    """Test data ingestion."""

    def test_update_asset(self):
        eng = CorrelationEngine(window=10)
        eng.update_asset("SPY", 0.7)
        assert len(eng._asset_history["SPY"]) == 1
        assert eng._asset_history["SPY"][0] == 0.7

    def test_update_exchange(self):
        eng = CorrelationEngine(window=10)
        eng.update_exchange("NYSE", 0.5)
        assert len(eng._exchange_history["NYSE"]) == 1

    def test_batch_update(self):
        eng = CorrelationEngine(window=10)
        eng.update(
            asset_vpin_cdfs={"SPX": 0.6, "SPY": 0.7, "QQQ": 0.5},
            exchange_vpin_cdfs={"NYSE": 0.4, "NASDAQ": 0.5},
        )
        assert len(eng._asset_history["SPY"]) == 1
        assert len(eng._exchange_history["NASDAQ"]) == 1

    def test_unknown_symbol_ignored(self):
        eng = CorrelationEngine(window=10)
        eng.update_asset("UNKNOWN", 0.5)  # should not raise
        assert len(eng._asset_history["SPY"]) == 0


class TestCorrelationEngineCorr:
    """Test correlation computation with known inputs."""

    def test_correlated_spikes_high_zscore(self):
        """Inject correlated VPIN spikes → high correlation z-score."""
        eng = CorrelationEngine(window=60)
        rng = np.random.default_rng(42)
        base = rng.uniform(0.3, 0.5, 50)
        for i in range(50):
            # All assets move together (correlated)
            noise = rng.normal(0, 0.02)
            eng.update_asset("SPX", float(base[i] + noise))
            eng.update_asset("SPY", float(base[i] + noise))
            eng.update_asset("QQQ", float(base[i] + noise))

        asset_z = eng.compute_asset_correlation()
        assert asset_z > 1.0, f"Expected high z-score for correlated data, got {asset_z}"

    def test_uncorrelated_spikes_low_zscore(self):
        """Inject uncorrelated VPIN spikes → low correlation z-score."""
        eng = CorrelationEngine(window=60)
        rng = np.random.default_rng(123)
        for _ in range(50):
            eng.update_asset("SPX", float(rng.uniform(0, 1)))
            eng.update_asset("SPY", float(rng.uniform(0, 1)))
            eng.update_asset("QQQ", float(rng.uniform(0, 1)))

        asset_z = eng.compute_asset_correlation()
        assert abs(asset_z) < 2.0, f"Expected low z-score for uncorrelated data, got {asset_z}"

    def test_exchange_correlated(self):
        """Inject correlated exchange VPIN → high exchange z-score."""
        eng = CorrelationEngine(window=60)
        rng = np.random.default_rng(99)
        base = rng.uniform(0.4, 0.6, 50)
        for i in range(50):
            for exch in ["NYSE", "NASDAQ", "BATS"]:
                eng.update_exchange(exch, float(base[i] + rng.normal(0, 0.01)))

        exch_z = eng.compute_exchange_correlation()
        assert exch_z > 1.0, f"Expected high exchange z-score, got {exch_z}"

    def test_insufficient_data_returns_zero(self):
        """With < 2 data points, correlation should be 0."""
        eng = CorrelationEngine(window=10)
        eng.update_asset("SPY", 0.5)
        eng.update_asset("QQQ", 0.6)
        z = eng.compute_asset_correlation()
        assert z == 0.0

    def test_compute_returns_tuple(self):
        """compute() returns (exchange_z, asset_z)."""
        eng = CorrelationEngine(window=10)
        result = eng.compute()
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], float)
        assert isinstance(result[1], float)

    def test_fisher_z_transform(self):
        """Fisher z-transform: r=0 → z=0, r=0.5 → z≈0.549."""
        eng = CorrelationEngine(window=10)
        assert eng._fisher_z_transform(0.0) == pytest.approx(0.0, abs=1e-6)
        assert eng._fisher_z_transform(0.5) == pytest.approx(0.5493, abs=0.01)

    def test_rolling_window_eviction(self):
        """Old data should be evicted when window is exceeded."""
        eng = CorrelationEngine(window=5)
        for i in range(10):
            eng.update_asset("SPY", float(i))
        assert len(eng._asset_history["SPY"]) == 5

    def test_get_state(self):
        """get_state returns complete state dict."""
        eng = CorrelationEngine(window=10)
        eng.update_asset("SPY", 0.7)
        state = eng.get_state()
        assert "config" in state
        assert "zscores" in state
        assert "history_lengths" in state
        assert state["config"]["window"] == 10
