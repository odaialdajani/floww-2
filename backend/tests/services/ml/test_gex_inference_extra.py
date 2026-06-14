"""
tests/services/ml/test_gex_inference_extra.py

Additional edge-case and numerical tests for compute_gex_features and _empty_gex_features.
Complements test_gex_inference.py with oracle-value assertions.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.ml.gex_inference import (
    GEX_REQUIRED_FEATURES,
    _empty_gex_features,
    compute_gex_features,
)


class TestEmptyGexFeatures:
    def test_all_defaults_present(self):
        result = _empty_gex_features({})
        expected_keys = {
            "call_gex", "put_gex", "net_call_gex", "net_put_gex", "net_gex",
            "gamma_flip", "dist_to_flip", "gex_n_strikes",
            "put_call_ratio",
            "total_dex", "total_vega", "total_vex",
            "realized_vol_t1", "realized_vol_t3",
            "realized_vol_rolling_3d", "realized_vol_rolling_5d",
            "net_gex_roc_1d", "net_gex_roc_3d",
            "net_gex_roc_5d", "net_gex_zscore_60d",
        }
        assert expected_keys.issubset(result.keys())

    def test_default_values(self):
        result = _empty_gex_features({})
        assert result["call_gex"] == 0.0
        assert result["put_gex"] == 0.0
        assert result["net_gex"] == 0.0
        assert result["gamma_flip"] == 0.0
        assert result["put_call_ratio"] == 1.0

    def test_preserves_existing_keys(self):
        result = _empty_gex_features({"call_gex": 999.0})
        assert result["call_gex"] == 999.0

    def test_returns_same_dict(self):
        d = {}
        result = _empty_gex_features(d)
        assert result is d


class TestComputeGexFeaturesEdgeCases:

    def _make_contract(self, cp="C", strike=500.0, gamma=0.01, oi=1000,
                       iv=0.20, delta=0.5, volume=100):
        return {
            "expiry": "2024-06-21", "strike": strike, "type": cp,
            "gamma": gamma, "oi": oi, "iv": iv, "delta": delta,
            "volume": volume, "bid": 1.0, "ask": 1.1,
        }

    def test_zero_spot_returns_empty(self):
        chain = {"spot": 0.0, "contracts": [self._make_contract()]}
        result = compute_gex_features(chain)
        assert result["net_gex"] == 0.0

    def test_negative_spot_returns_empty(self):
        chain = {"spot": -100.0, "contracts": [self._make_contract()]}
        result = compute_gex_features(chain)
        assert result["net_gex"] == 0.0

    def test_empty_contracts(self):
        chain = {"spot": 500.0, "contracts": []}
        result = compute_gex_features(chain)
        assert result["net_gex"] == 0.0
        assert result["gamma_flip"] == 0.0

    def test_zero_gamma_contracts_skipped(self):
        chain = {
            "spot": 500.0,
            "contracts": [self._make_contract(gamma=0.0, oi=10000)],
        }
        result = compute_gex_features(chain)
        assert result["net_gex"] == 0.0

    def test_zero_oi_contracts_skipped(self):
        chain = {
            "spot": 500.0,
            "contracts": [self._make_contract(gamma=0.01, oi=0)],
        }
        result = compute_gex_features(chain)
        assert result["net_gex"] == 0.0

    def test_zero_strike_contracts_skipped(self):
        chain = {
            "spot": 500.0,
            "contracts": [self._make_contract(strike=0.0)],
        }
        result = compute_gex_features(chain)
        assert result["net_gex"] == 0.0

    def test_single_call_only(self):
        chain = {"spot": 500.0, "contracts": [self._make_contract("C", strike=500.0)]}
        result = compute_gex_features(chain)
        assert result["call_gex"] > 0.0
        assert result["put_gex"] == 0.0
        assert result["net_gex"] == result["call_gex"]

    def test_single_put_only(self):
        chain = {"spot": 500.0, "contracts": [self._make_contract("P", strike=500.0)]}
        result = compute_gex_features(chain)
        assert result["put_gex"] < 0.0
        assert result["call_gex"] == 0.0

    def test_call_put_symmetry(self):
        chain = {
            "spot": 500.0,
            "contracts": [
                self._make_contract("C", strike=500.0, gamma=0.01, oi=1000),
                self._make_contract("P", strike=500.0, gamma=0.01, oi=1000),
            ],
        }
        result = compute_gex_features(chain)
        assert result["net_gex"] == pytest.approx(0.0, abs=1e-6)

    def test_net_gex_decomposition(self):
        chain = {
            "spot": 500.0,
            "contracts": [
                self._make_contract("C", strike=495, gamma=0.015, oi=2000),
                self._make_contract("C", strike=500, gamma=0.010, oi=1500),
                self._make_contract("P", strike=495, gamma=0.012, oi=1800),
                self._make_contract("P", strike=505, gamma=0.008, oi=2200),
            ],
        }
        result = compute_gex_features(chain)
        assert result["net_gex"] == pytest.approx(
            result["net_call_gex"] + result["net_put_gex"], rel=1e-9
        )

    def test_gex_formula_single_call(self):
        spot = 530.0
        gamma = 0.02
        oi = 500
        expected = gamma * oi * 100.0 * spot * spot * 0.01
        chain = {"spot": spot, "contracts": [self._make_contract("C", strike=spot, gamma=gamma, oi=oi)]}
        result = compute_gex_features(chain)
        assert result["call_gex"] == pytest.approx(expected, rel=1e-9)

    def test_dist_to_flip_range(self):
        chain = {
            "spot": 500.0,
            "contracts": [
                self._make_contract("C", strike=480),
                self._make_contract("C", strike=490),
                self._make_contract("C", strike=500),
                self._make_contract("P", strike=480),
                self._make_contract("P", strike=490),
            ],
        }
        result = compute_gex_features(chain)
        assert -1.0 < result["dist_to_flip"] < 1.0

    def test_gex_n_strikes_counts_unique(self):
        chain = {
            "spot": 500.0,
            "contracts": [
                self._make_contract("C", strike=500),
                self._make_contract("P", strike=500),
                self._make_contract("C", strike=505),
                self._make_contract("P", strike=505),
            ],
        }
        result = compute_gex_features(chain)
        assert result["gex_n_strikes"] == 2.0

    def test_put_call_ratio_formula(self):
        chain = {
            "spot": 500.0,
            "contracts": [
                self._make_contract("C", strike=500, oi=3000),
                self._make_contract("P", strike=495, oi=1500),
            ],
        }
        result = compute_gex_features(chain)
        assert result["put_call_ratio"] == pytest.approx(1500.0 / 3000.0)

    def test_realized_vol_ordering(self):
        chain = {
            "spot": 500.0,
            "contracts": [
                self._make_contract("C", iv=0.25),
                self._make_contract("P", iv=0.27),
            ],
        }
        result = compute_gex_features(chain)
        rv_t1 = result["realized_vol_t1"]
        assert result["realized_vol_t3"] == pytest.approx(rv_t1 * 0.95)
        assert result["realized_vol_rolling_5d"] == pytest.approx(rv_t1 * 0.98)

    def test_total_vex_equals_net_gex_scaled(self):
        chain = {
            "spot": 500.0,
            "contracts": [
                self._make_contract("C", gamma=0.02, oi=2000),
                self._make_contract("P", gamma=0.015, oi=1500),
            ],
        }
        result = compute_gex_features(chain)
        assert result["total_vex"] == pytest.approx(result["net_gex"] * 0.01)

    @pytest.mark.xfail(reason="BUG: gex_concentration is in GEX_REQUIRED_FEATURES but compute_gex_features never sets it")
    def test_feature_set_superset_of_gex_required(self):
        chain = {
            "spot": 500.0,
            "contracts": [
                self._make_contract("C", strike=495),
                self._make_contract("C", strike=500),
                self._make_contract("P", strike=495),
                self._make_contract("P", strike=500),
            ],
        }
        result = compute_gex_features(chain)
        assert GEX_REQUIRED_FEATURES.issubset(result.keys())

    def test_missing_optional_keys_zero(self):
        chain = {"spot": 500.0, "contracts": [self._make_contract()]}
        result = compute_gex_features(chain)
        assert result["net_gex_roc_1d"] == 0.0
        assert result["net_gex_zscore_60d"] == 0.0


class TestFetchOptionsChainGuard:
    def test_returns_none_for_empty_options(self, monkeypatch):
        import types
        mock_yf = types.ModuleType("yfinance")

        class MockTicker:
            options = []

        mock_yf.Ticker = MockTicker
        monkeypatch.setitem(sys.modules, "yfinance", mock_yf)
        from services.ml.gex_inference import fetch_options_chain
        result = fetch_options_chain("SPY")
        assert result is None
