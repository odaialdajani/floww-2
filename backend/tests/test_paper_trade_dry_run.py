#!/usr/bin/env python3
"""
backend/tests/test_paper_trade_dry_run.py

Unit tests for the paper-trade dry-run script.
Uses mocks — no MongoDB or Alpaca required.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.paper_trade_dry_run import (
    compute_features,
    daily_paper_trade_dry_run,
    load_active_model,
)

# The exact 23 features that compute_features returns
FEATURES_23 = {
    "call_gex": 5e6,
    "gamma_flip": 470.0,
    "gex_n_strikes": 6000.0,
    "net_gex": -1e7,
    "price_vs_sma_10": 0.02,
    "price_vs_sma_21": 0.03,
    "price_vs_sma_5": 0.01,
    "put_gex": -6e6,
    "realized_vol_21d": 0.12,
    "realized_vol_5d": 0.15,
    "ret_10d": 0.04,
    "ret_1d": 0.01,
    "ret_21d": 0.05,
    "ret_3d": 0.02,
    "ret_5d": 0.03,
    "rsi_14": 55.0,
    "sma_10": 469.0,
    "sma_21": 468.0,
    "sma_5": 470.0,
    "spot": 470.0,
    "total_dex": 1e7,
    "total_vega": 5e4,
    "total_vex": 1e5,
}


class TestLoadActiveModel:
    def test_no_model_found(self):
        """Test error when no model exists."""
        with patch("scripts.paper_trade_dry_run.Path") as mock_path:
            mock_path.return_value.glob.return_value = []
            with pytest.raises(FileNotFoundError):
                load_active_model("SPY")


class TestComputeFeatures:
    def test_compute_with_valid_data(self):
        """Test feature computation with valid data."""
        mock_db = MagicMock()

        mock_db["gex_features"].find_one.return_value = {
            "day": "2024-01-15",
            "net_gex": -1e7, "call_gex": 5e6, "put_gex": -6e6,
            "total_vex": 1e5, "total_dex": 1e7, "total_vega": 5e4,
            "gamma_flip": 470.0, "n_strikes": 6000, "spot": 470.0,
        }

        bars = []
        for i in range(30):
            bars.append({
                "date": f"2024-01-{i+1:02d}",
                "open": 470.0 + i, "high": 472.0 + i,
                "low": 468.0 + i, "close": 471.0 + i,
                "volume": 5000000,
            })
        mock_db["underlying_bars"].find.return_value.sort.return_value.limit.return_value = bars

        features = compute_features("SPY", mock_db)

        assert features is not None
        assert len(features) == 23
        assert "net_gex" in features
        assert "ret_1d" in features
        assert "sma_5" in features
        assert "rsi_14" in features
        assert features["spot"] == 470.0

    def test_compute_no_gex(self):
        """Test feature computation when no GEX data exists."""
        mock_db = MagicMock()
        mock_db["gex_features"].find_one.return_value = None

        features = compute_features("SPY", mock_db)
        assert features is None

    def test_compute_insufficient_bars(self):
        """Test feature computation with insufficient bars."""
        mock_db = MagicMock()
        mock_db["gex_features"].find_one.return_value = {
            "day": "2024-01-15", "net_gex": -1e7, "call_gex": 5e6,
            "put_gex": -6e6, "total_vex": 1e5, "total_dex": 1e7,
            "total_vega": 5e4, "gamma_flip": 470.0, "n_strikes": 6000,
            "spot": 470.0,
        }
        bars = [{"date": f"2024-01-{i+1:02d}", "close": 470.0} for i in range(5)]
        mock_db["underlying_bars"].find.return_value.sort.return_value.limit.return_value = bars

        features = compute_features("SPY", mock_db)
        assert features is None


class TestDailyPaperTradeDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_produces_valid_output(self):
        """Test that dry-run produces a valid order intent."""
        mock_db = MagicMock()

        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.preprocessing import StandardScaler

        n_features = 23
        model = GradientBoostingClassifier(n_estimators=10, random_state=42)
        model.fit(np.random.randn(100, n_features), np.random.randint(0, 2, 100))
        scaler = StandardScaler()
        scaler.fit(np.random.randn(100, n_features))

        with patch("scripts.paper_trade_dry_run.load_active_model") as mock_load, \
             patch("scripts.paper_trade_dry_run.get_db", return_value=mock_db), \
             patch("scripts.paper_trade_dry_run.compute_features", return_value=FEATURES_23.copy()):

            mock_load.return_value = (model, scaler, "models/SPY_direction_v2.0_gex.joblib")
            mock_db["underlying_bars"].find_one.return_value = {"close": 470.0}

            result = await daily_paper_trade_dry_run("SPY")

            assert result["status"] == "ok"
            assert result["ticker"] == "SPY"
            assert result["action"] in ("BUY", "SELL", "HOLD")
            assert 0 <= result["confidence"] <= 1
            assert result["dry_run"] is True
            assert result["current_price"] == 470.0

    @pytest.mark.asyncio
    async def test_dry_run_no_model(self):
        """Test dry-run when no model exists."""
        with patch("scripts.paper_trade_dry_run.load_active_model", side_effect=FileNotFoundError("no model")):
            result = await daily_paper_trade_dry_run("SPY")
            assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_dry_run_no_features(self):
        """Test dry-run when features can't be computed."""
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.preprocessing import StandardScaler

        model = GradientBoostingClassifier(n_estimators=10, random_state=42)
        model.fit(np.random.randn(100, 5), np.random.randint(0, 2, 100))
        scaler = StandardScaler()
        scaler.fit(np.random.randn(100, 5))

        with patch("scripts.paper_trade_dry_run.load_active_model") as mock_load, \
             patch("scripts.paper_trade_dry_run.get_db", return_value=MagicMock()), \
             patch("scripts.paper_trade_dry_run.compute_features", return_value=None):

            mock_load.return_value = (model, scaler, "models/SPY_direction_v2.0_gex.joblib")

            result = await daily_paper_trade_dry_run("SPY")
            assert result["status"] == "error"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
