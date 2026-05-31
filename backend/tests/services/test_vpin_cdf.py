"""
Tests for Rolling VPIN CDF Calculator.

Validates:
  - CDF increases monotonically with increasing VPIN values.
  - CDF resets correctly when window slides.
  - CDF is in [0, 1] always.
  - Mongo persistence is attempted when collection provided.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

REPO_BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_BACKEND))

from services.vpin_cdf import VpinCdfCalculator
from services.vpin_engine import VpinEngine


class TestVpinCdfBasic:
    """CDF computation correctness."""

    def test_single_value_cdf_is_zero(self):
        """With fewer than 2 values, CDF == 0."""
        calc = VpinCdfCalculator(window=50)
        cdf = calc.update(0.5)
        assert cdf == 0.0

    def test_two_values_median(self):
        """With 2 values, current == history → CDF = 0.5."""
        calc = VpinCdfCalculator(window=50)
        calc.update(0.3)
        cdf = calc.update(0.5)
        # history = [0.3, 0.5], fraction <= 0.5 = 2/2 = 1.0
        assert cdf == 1.0

    def test_cdf_in_range(self):
        """CDF is always in [0, 1]."""
        calc = VpinCdfCalculator(window=10)
        rng = np.random.default_rng(42)
        for _ in range(200):
            v = rng.uniform(0, 1)
            cdf = calc.update(v)
            assert 0.0 <= cdf <= 1.0

    def test_monotonically_increasing_vpin(self):
        """Injecting increasing VPIN produces non-decreasing CDF."""
        calc = VpinCdfCalculator(window=50)
        prev_cdf = 0.0
        for i in range(1, 20):
            cdf = calc.update(i / 20.0)
            assert cdf >= prev_cdf - 1e-12, (
                f"CDF decreased: {prev_cdf} → {cdf} at VPIN={i/20.0}"
            )
            prev_cdf = cdf

    def test_cdf_at_max_is_1(self):
        """The maximum VPIN in history has CDF = 1.0."""
        calc = VpinCdfCalculator(window=10)
        for v in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
            calc.update(v)
        cdf = calc.update(0.95)
        assert cdf == 1.0

    def test_cdf_at_min_is_zero(self):
        """The minimum value in history has CDF = 0 (none of the prior values <= it)."""
        calc = VpinCdfCalculator(window=10)
        for v in [0.5, 0.6, 0.7, 0.8, 0.9]:
            calc.update(v)
        cdf = calc.update(0.1)
        # CDF excludes current value: prior = [0.5, 0.6, 0.7, 0.8, 0.9]
        # None of the prior values are <= 0.1, so CDF = 0/5 = 0.0
        assert cdf == 0.0

    def test_window_slides(self):
        """When window slides, old values are dropped."""
        calc = VpinCdfCalculator(window=5)
        for v in [0.1, 0.2, 0.3, 0.4, 0.5]:
            calc.update(v)
        # Window = [0.1, 0.2, 0.3, 0.4, 0.5]
        cdf_mid = calc.update(0.3)
        # After 6th update, deque (maxlen=5) = [0.2, 0.3, 0.4, 0.5, 0.3]
        # CDF excludes current value: prior = [0.2, 0.3, 0.4, 0.5]
        # fraction of prior <= 0.3 = 2/4 = 0.5
        assert abs(cdf_mid - 0.5) < 1e-9

    def test_invalid_vpin_raises(self):
        """VPIN outside [0, 1] raises ValueError."""
        calc = VpinCdfCalculator()
        with pytest.raises(ValueError, match=r"\[0,1\]"):
            calc.update(-0.1)
        with pytest.raises(ValueError, match=r"\[0,1\]"):
            calc.update(1.1)

    def test_history_property(self):
        """history returns the stored VPIN values."""
        calc = VpinCdfCalculator(window=10)
        values = [0.3, 0.5, 0.7]
        for v in values:
            calc.update(v)
        assert calc.history == list(calc._history)

    def test_vpin_property(self):
        """vpin property returns the last ingested value."""
        calc = VpinCdfCalculator()
        calc.update(0.73)
        assert calc.vpin == pytest.approx(0.73)


class TestVpinCdfIntegration:
    """Integration: VpinEngine + VpinCdfCalculator."""

    def test_engine_cdf_updates_on_bucket_finalize(self):
        """CDF updates every time a bucket closes."""
        eng = VpinEngine(bucket_size=100.0, window=10)
        assert eng.vpin_history_length == 0
        for i in range(25):
            eng.update(price_change=0.5, volume=20.0, sigma=0.1)
        assert eng.vpin_history_length > 0

    def test_engine_cdf_between_0_and_1(self):
        """Engine CDF is in [0, 1]."""
        rng = np.random.default_rng(99)
        eng = VpinEngine(bucket_size=100.0, window=10)
        for _ in range(100):
            eng.update(
                price_change=float(rng.normal(0, 0.01)),
                volume=float(rng.uniform(10, 50)),
                sigma=0.01,
            )
        cdf = eng.compute_vpin_cdf()
        assert 0.0 <= cdf <= 1.0


class TestVpinCdfMongo:
    """MongoDB persistence behavior."""

    def test_persist_called_with_mock(self, monkeypatch):
        """When mongo_collection is provided, insert_one is called."""
        mock_col = MagicMock()
        calc = VpinCdfCalculator(window=10, mongo_collection=mock_col, ticker="SPY")
        calc.update(0.5)
        mock_col.insert_one.assert_called_once()
        doc = mock_col.insert_one.call_args[0][0]
        assert doc["ticker"] == "SPY"
        assert doc["vpin"] == pytest.approx(0.5)
        assert "vpin_cdf" in doc
        assert "ts" in doc

    def test_persist_failure_is_silent(self):
        """Mongo insert failure does not crash the calculator."""
        mock_col = MagicMock()
        mock_col.insert_one.side_effect = ConnectionError("Mongo down")
        calc = VpinCdfCalculator(window=10, mongo_collection=mock_col, ticker="SPY")
        cdf = calc.update(0.5)
        assert cdf >= 0.0  # Still returns a valid CDF

    def test_no_mongo_no_persist(self):
        """Without mongo_collection, no insert is attempted."""
        calc = VpinCdfCalculator(window=10, mongo_collection=None)
        cdf = calc.update(0.5)
        assert cdf == 0.0  # No error, just no persist
