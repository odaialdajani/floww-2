"""
backend/tests/services/test_ml_realtime_features.py

Unit tests for services/ml_realtime_features.py — the real-time feature
computation pipeline used for ML inference.

Strategy: construct synthetic (deterministic) inputs so every numeric
assertion can be verified by hand.  No yfinance/network calls in tests.

Tested public API:
  - compute_price_features_realtime
  - compute_gex_features
  - compute_oi_features
  - compute_iv_features
  - _empty_gex   (internal, but deterministic)
  - _kurtosis    (internal, but deterministic)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from services.ml_realtime_features import (
    _empty_gex,
    _kurtosis,
    compute_gex_features,
    compute_iv_features,
    compute_oi_features,
    compute_price_features_realtime,
)

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _make_price_df(n: int = 60, base: float = 100.0, seed: int = 42) -> pd.DataFrame:
    """Deterministic price DataFrame with n rows starting near `base`."""
    rng = np.random.default_rng(seed)
    close = base + np.cumsum(rng.standard_normal(n))
    high = close + np.abs(rng.standard_normal(n)) * 0.5
    low = close - np.abs(rng.standard_normal(n)) * 0.5
    open_ = close + rng.standard_normal(n) * 0.3
    return pd.DataFrame({
        "Open": open_,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": rng.integers(1_000_000, 10_000_000, size=n).astype(float),
    })


def _make_chain(
    spot: float = 500.0,
    n_strikes: int = 10,
    seed: int = 0,
) -> dict:
    """Build a synthetic options-chain dict mirroring fetch_live_chain output."""
    rng = np.random.default_rng(seed)
    strikes = [spot + i * 5 for i in range(-n_strikes, n_strikes + 1)]
    contracts = []
    for k in strikes:
        # Call
        gamma = rng.uniform(0.01, 0.10)
        oi = int(rng.integers(100, 10_000))
        iv = rng.uniform(0.10, 0.50)
        contracts.append({
            "expiry": "2026-07-01",
            "strike": float(k),
            "type": "C",
            "oi": oi,
            "volume": int(rng.integers(0, 5_000)),
            "iv": iv,
            "delta": rng.uniform(0.1, 0.9),
            "gamma": gamma,
            "bid": rng.uniform(0.5, 5.0),
            "ask": rng.uniform(0.5, 5.0),
            "last": rng.uniform(0.5, 5.0),
        })
        # Put
        gamma_p = rng.uniform(0.01, 0.10)
        oi_p = int(rng.integers(100, 10_000))
        iv_p = rng.uniform(0.10, 0.50)
        contracts.append({
            "expiry": "2026-07-01",
            "strike": float(k),
            "type": "P",
            "oi": oi_p,
            "volume": int(rng.integers(0, 5_000)),
            "iv": iv_p,
            "delta": rng.uniform(-0.9, -0.1),
            "gamma": gamma_p,
            "bid": rng.uniform(0.5, 5.0),
            "ask": rng.uniform(0.5, 5.0),
            "last": rng.uniform(0.5, 5.0),
        })
    return {"spot": spot, "contracts": contracts, "expiries": ["2026-07-01"]}


# ======================================================================
# _empty_gex
# ======================================================================

class TestEmptyGex:
    def test_returns_all_zero_floats(self):
        g = _empty_gex()
        assert isinstance(g, dict)
        for k, v in g.items():
            assert isinstance(v, float), f"{k}: {v!r} is not float"
            assert v == 0.0, f"{k}: expected 0.0 got {v}"

    def test_expected_keys_present(self):
        g = _empty_gex()
        for key in [
            "net_gex", "total_abs_gex", "net_gex_normalized",
            "king_strike", "king_gex", "king_distance_pct",
            "gex_regime_positive", "gex_regime_negative",
            "positive_gex", "negative_gex", "gex_ratio",
            "floor_strike", "floor_gex", "floor_distance_pct",
            "ceiling_strike", "ceiling_gex", "ceiling_distance_pct",
            "gex_top5_concentration", "gex_mean", "gex_std",
            "gex_skew", "gex_kurtosis", "gex_num_strikes",
        ]:
            assert key in g, f"Missing key: {key}"


# ======================================================================
# _kurtosis
# ======================================================================

class TestKurtosis:
    def test_returns_zero_for_fewer_than_4_values(self):
        assert _kurtosis([1.0, 2.0, 3.0]) == 0.0

    def test_returns_zero_for_constant_array(self):
        # std == 0 → must return 0.0
        assert _kurtosis([5.0, 5.0, 5.0, 5.0, 5.0]) == 0.0

    def test_excess_kurtosis_of_normal_is_near_zero(self):
        # For a normal distribution excess kurtosis ≈ 0
        rng = np.random.default_rng(99)
        vals = rng.standard_normal(10_000).tolist()
        k = _kurtosis(vals)
        assert abs(k) < 0.5, f"kurtosis={k}, expected near 0 for normal"

    def test_uniform_has_negative_excess_kurtosis(self):
        # Uniform distribution has excess kurtosis = -1.2
        rng = np.random.default_rng(7)
        vals = rng.uniform(0, 1, 10_000).tolist()
        k = _kurtosis(vals)
        assert -2.0 < k < -0.5, f"kurtosis={k}, expected approx -1.2 for uniform"

    def test_two_values_only(self):
        assert _kurtosis([1.0, 2.0]) == 0.0


# ======================================================================
# compute_price_features_realtime
# ======================================================================

class TestComputePriceFeaturesRealtime:
    def _base_with_trend(self, n=60):
        """Uptrending series: close = 100, 101, 102, ..."""
        close = np.arange(n, dtype=float) + 100.0
        high = close + 0.5
        low = close - 0.5
        open_ = close - 0.25
        return pd.DataFrame({
            "Open": open_, "High": high, "Low": low,
            "Close": close, "Volume": np.full(n, 1_000_000.0),
        })

    def test_returns_dict(self):
        df = _make_price_df()
        result = compute_price_features_realtime(df)
        assert isinstance(result, dict)
        assert "spot" in result
        assert "close" in result

    def test_spot_equals_last_close(self):
        df = self._base_with_trend()
        result = compute_price_features_realtime(df)
        assert result["spot"] == pytest.approx(159.0)  # 100 + 59
        assert result["close"] == result["spot"]

    def test_high_low_range(self):
        df = self._base_with_trend()
        result = compute_price_features_realtime(df)
        # high=159.5, low=158.5 → range = 1.0
        assert result["high_low_range"] == pytest.approx(1.0)

    def test_open_close_diff(self):
        df = self._base_with_trend()
        result = compute_price_features_realtime(df)
        # close=159.0, open=158.75 → diff=0.25
        assert result["open_close_diff"] == pytest.approx(0.25)

    def test_ma_5_when_enough_data(self):
        df = self._base_with_trend()
        result = compute_price_features_realtime(df)
        # iloc[idx-window:idx] excludes current row → iloc[54:59] = 154..158
        # mean = (154+155+156+157+158)/5 = 780/5 = 156.0
        assert result["ma_5"] == pytest.approx(156.0)

    def test_close_to_ma_5(self):
        df = self._base_with_trend()
        result = compute_price_features_realtime(df)
        # ma_5 = 156.0, close = 159.0 → (159 - 156) / 156 = 3/156
        expected = (159.0 - 156.0) / 156.0
        assert result["close_to_ma_5"] == pytest.approx(expected, rel=1e-6)

    def test_return_1d(self):
        df = self._base_with_trend()
        result = compute_price_features_realtime(df)
        # (159 - 158) / 158 = 1/158
        expected = 1.0 / 158.0
        assert result["return_1d"] == pytest.approx(expected, rel=1e-6)

    def test_return_3d(self):
        df = self._base_with_trend()
        result = compute_price_features_realtime(df)
        # (159 - 156) / 156 = 3/156
        expected = 3.0 / 156.0
        assert result["return_3d"] == pytest.approx(expected, rel=1e-6)

    def test_rsi_14_uptrending(self):
        """Uptrending series → RSI should be high (many up days)."""
        df = self._base_with_trend(60)
        result = compute_price_features_realtime(df)
        # In a perfect uptrend every day is up → gains > 0, losses = 0
        # RS → inf, RSI → 100
        assert result["rsi_14"] == pytest.approx(100.0)

    def test_rsi_14_default_when_insufficient_data(self):
        """Not enough data (< 14) → RSI defaults to 50."""
        df = _make_price_df(n=10)
        result = compute_price_features_realtime(df)
        assert result["rsi_14"] == pytest.approx(50.0)

    def test_macd_zero_when_insufficient_data(self):
        df = _make_price_df(n=20)
        result = compute_price_features_realtime(df)
        assert result["macd"] == pytest.approx(0.0)

    def test_realized_vol_20d_zero_when_insufficient(self):
        df = _make_price_df(n=15)
        result = compute_price_features_realtime(df)
        assert result["realized_vol_20d"] == pytest.approx(0.0)

    def test_all_return_periods_present(self):
        df = _make_price_df()
        result = compute_price_features_realtime(df)
        for period in [1, 2, 3, 5, 10, 20]:
            assert f"return_{period}d" in result

    def test_all_ma_windows_present(self):
        df = _make_price_df()
        result = compute_price_features_realtime(df)
        for w in [5, 10, 20, 50]:
            assert f"ma_{w}" in result
            assert f"close_to_ma_{w}" in result

    def test_fallback_ma_when_not_enough_history(self):
        """When idx < window for MA, ma should fall back to close."""
        df = _make_price_df(n=12)
        result = compute_price_features_realtime(df)
        close = df.iloc[-1]["Close"]
        # ma_20 not enough data → should be close
        assert result["ma_20"] == pytest.approx(close)
        assert result["close_to_ma_20"] == pytest.approx(0.0)

    def test_return_20d_fallback(self):
        df = _make_price_df(n=15)
        result = compute_price_features_realtime(df)
        # idx=14, period=20 → not enough → 0.0
        assert result["return_20d"] == pytest.approx(0.0)

    def test_all_values_are_finite(self):
        df = _make_price_df()
        result = compute_price_features_realtime(df)
        for k, v in result.items():
            assert np.isfinite(v), f"{k}={v} is not finite"


# ======================================================================
# compute_gex_features  (golden-oracle tests)
# ======================================================================

class TestComputeGexFeatures:
    def _manual_chain(self):
        """Hand-crafted 4-contract chain for golden-oracle validation.

        spot = 100.0
          Call K=100 gamma=0.10 OI=2000 → gex = +0.10*2000*100*100*100*0.01 = +2_000_000
          Put  K=100 gamma=0.04 OI=2000 → gex = -0.04*2000*100*100*100*0.01 = -800_000
          Call K=105 gamma=0.03 OI=500  → gex = +0.03*500*100*100*100*0.01  = +150_000
          Put  K=105 gamma=0.05 OI=3000 → gex = -0.05*3000*100*100*100*0.01 = -1_500_000

        Per-strike:
          K=100: +2_000_000 + (-800_000) = +1_200_000
          K=105: +150_000 + (-1_500_000) = -1_350_000

        net_gex = -150_000
        total_abs_gex = 2_550_000
        net_gex_normalized = -150_000 / 2_550_000 ≈ -0.0588235...
        king_strike = 105 (largest |gex| = 1_350_000)
        king_gex = -1_350_000
        king_distance_pct = (100 - 105) / 100 = -0.05
        gex_regime_negative = 1.0
        positive_gex = 1_200_000
        negative_gex = -1_350_000
        gex_ratio = 1_200_000 / 1_350_000 = 0.8888888...
        floor_strike: highest strike < spot with positive gex → none (K=100 == spot)
        ceiling_strike: lowest strike > spot with negative gex → 105
          ceiling_distance_pct = (105 - 100) / 100 = 0.05
          ceiling_gex = -1_350_000
        """
        spot = 100.0
        contracts = [
            {"expiry": "2026-07-01", "strike": 100.0, "type": "C",
             "oi": 2000, "volume": 0, "iv": 0.2, "delta": 0.5,
             "gamma": 0.10, "bid": 0.0, "ask": 0.0, "last": 0.0},
            {"expiry": "2026-07-01", "strike": 100.0, "type": "P",
             "oi": 2000, "volume": 0, "iv": 0.2, "delta": -0.5,
             "gamma": 0.04, "bid": 0.0, "ask": 0.0, "last": 0.0},
            {"expiry": "2026-07-01", "strike": 105.0, "type": "C",
             "oi": 500, "volume": 0, "iv": 0.2, "delta": 0.3,
             "gamma": 0.03, "bid": 0.0, "ask": 0.0, "last": 0.0},
            {"expiry": "2026-07-01", "strike": 105.0, "type": "P",
             "oi": 3000, "volume": 0, "iv": 0.2, "delta": -0.7,
             "gamma": 0.05, "bid": 0.0, "ask": 0.0, "last": 0.0},
        ]
        return {"spot": spot, "contracts": contracts, "expiries": ["2026-07-01"]}

    def test_net_gex_golden(self):
        chain = self._manual_chain()
        result = compute_gex_features(chain)
        # K100: +2M - 800K = +1.2M; K105: +150K - 1.5M = -1.35M
        # net = 1.2M + (-1.35M) = -150K
        assert result["net_gex"] == pytest.approx(-150_000.0)

    def test_total_abs_gex_golden(self):
        chain = self._manual_chain()
        result = compute_gex_features(chain)
        assert result["total_abs_gex"] == pytest.approx(2_550_000.0)

    def test_net_gex_normalized_golden(self):
        chain = self._manual_chain()
        result = compute_gex_features(chain)
        expected = -150_000.0 / 2_550_000.0
        assert result["net_gex_normalized"] == pytest.approx(expected, rel=1e-6)

    def test_king_strike_is_largest_abs_gex(self):
        chain = self._manual_chain()
        result = compute_gex_features(chain)
        # K=105 has |gex| = 1.35M > K=100 |gex| = 1.2M
        assert result["king_strike"] == pytest.approx(105.0)
        assert result["king_gex"] == pytest.approx(-1_350_000.0)

    def test_king_distance_pct(self):
        chain = self._manual_chain()
        result = compute_gex_features(chain)
        # (spot - king_strike) / spot = (100 - 105) / 100 = -0.05
        assert result["king_distance_pct"] == pytest.approx(-0.05)

    def test_gex_regime_flags_negative(self):
        chain = self._manual_chain()
        result = compute_gex_features(chain)
        assert result["gex_regime_positive"] == 0.0
        assert result["gex_regime_negative"] == 1.0

    def test_positive_and_negative_gex(self):
        chain = self._manual_chain()
        result = compute_gex_features(chain)
        assert result["positive_gex"] == pytest.approx(1_200_000.0)
        assert result["negative_gex"] == pytest.approx(-1_350_000.0)

    def test_gex_ratio(self):
        chain = self._manual_chain()
        result = compute_gex_features(chain)
        # 1.2M / 1.35M = 8/9
        assert result["gex_ratio"] == pytest.approx(8.0 / 9.0, rel=1e-6)

    def test_ceiling_features(self):
        chain = self._manual_chain()
        result = compute_gex_features(chain)
        # smallest strike > spot with negative gex → K=105
        assert result["ceiling_strike"] == pytest.approx(105.0)
        assert result["ceiling_gex"] == pytest.approx(-1_350_000.0)
        assert result["ceiling_distance_pct"] == pytest.approx(0.05)

    def test_floor_zero_when_no_below_spot_positive(self):
        chain = self._manual_chain()
        result = compute_gex_features(chain)
        # All positives are at K=100 which equals spot, not below.
        assert result["floor_strike"] == pytest.approx(0.0)
        assert result["floor_distance_pct"] == pytest.approx(0.0)

    def test_gex_num_strikes(self):
        chain = self._manual_chain()
        result = compute_gex_features(chain)
        # 2 distinct strikes (100, 105)
        assert result["gex_num_strikes"] == pytest.approx(2.0)

    def test_gex_mean_and_std(self):
        chain = self._manual_chain()
        result = compute_gex_features(chain)
        values = [1_200_000.0, -1_350_000.0]
        expected_mean = float(np.mean(values))
        expected_std = float(np.std(values))
        assert result["gex_mean"] == pytest.approx(expected_mean)
        assert result["gex_std"] == pytest.approx(expected_std)

    def test_gex_skew_iqr(self):
        chain = self._manual_chain()
        result = compute_gex_features(chain)
        values = [1_200_000.0, -1_350_000.0]
        q75 = float(np.percentile(values, 75))
        q25 = float(np.percentile(values, 25))
        assert result["gex_skew"] == pytest.approx(q75 - q25)

    def test_gex_kurtosis(self):
        chain = self._manual_chain()
        result = compute_gex_features(chain)
        values = [1_200_000.0, -1_350_000.0]
        expected_k = _kurtosis(values)
        assert result["gex_kurtosis"] == pytest.approx(expected_k)

    def test_top5_concentration_with_few_strikes(self):
        chain = self._manual_chain()
        result = compute_gex_features(chain)
        # Only 2 strikes, so top-5 = total → concentration = 1.0
        assert result["gex_top5_concentration"] == pytest.approx(1.0)

    def test_top5_concentration_with_many_strikes(self):
        rng = np.random.default_rng(1)
        spot = 500.0
        n = 20
        strikes = [spot + i * 5 for i in range(-n, n + 1)]
        contracts = []
        for k in strikes:
            g = rng.uniform(0.01, 0.10)
            oi = int(rng.integers(100, 10_000))
            sign = 1.0 if k <= spot else -1.0
            contracts.append({
                "expiry": "2026-07-01", "strike": float(k),
                "type": "C" if sign > 0 else "P",
                "oi": oi, "volume": 0, "iv": 0.2, "delta": 0.5 * sign,
                "gamma": g, "bid": 0.0, "ask": 0.0, "last": 0.0,
            })
        chain = {"spot": spot, "contracts": contracts, "expiries": ["2026-07-01"]}
        result = compute_gex_features(chain)
        # top5_concentration must be between 0 and 1
        assert 0.0 < result["gex_top5_concentration"] <= 1.0

    def test_empty_chain_returns_empty_gex(self):
        chain = {"spot": 0.0, "contracts": [], "expiries": []}
        result = compute_gex_features(chain)
        empty = _empty_gex()
        for k in empty:
            assert result[k] == pytest.approx(0.0)

    def test_zero_gamma_contracts_are_excluded(self):
        """Contracts with gamma=0 should not contribute to GEX."""
        spot = 100.0
        contracts = [
            {"expiry": "2026-07-01", "strike": 100.0, "type": "C",
             "oi": 1000, "volume": 0, "iv": 0.2, "delta": 0.5,
             "gamma": 0.0, "bid": 0.0, "ask": 0.0, "last": 0.0},
        ]
        chain = {"spot": spot, "contracts": contracts, "expiries": ["2026-07-01"]}
        result = compute_gex_features(chain)
        # gamma=0 → no contracts qualify → empty gex
        assert result["net_gex"] == pytest.approx(0.0)

    def test_call_positive_put_negative_sign_convention(self):
        """Verify calls add, puts subtract from GEX."""
        spot = 100.0
        contracts = [
            {"expiry": "2026-07-01", "strike": 100.0, "type": "C",
             "oi": 1000, "volume": 0, "iv": 0.2, "delta": 0.5,
             "gamma": 0.01, "bid": 0.0, "ask": 0.0, "last": 0.0},
        ]
        chain = {"spot": spot, "contracts": contracts, "expiries": ["2026-07-01"]}
        result = compute_gex_features(chain)
        assert result["net_gex"] > 0.0

        # Same with a put
        contracts[0]["type"] = "P"
        result2 = compute_gex_features(chain)
        assert result2["net_gex"] < 0.0

    def test_positive_regime(self):
        """Pure-call chain → positive regime."""
        spot = 100.0
        contracts = [
            {"expiry": "2026-07-01", "strike": 100.0, "type": "C",
             "oi": 1000, "volume": 0, "iv": 0.2, "delta": 0.5,
             "gamma": 0.01, "bid": 0.0, "ask": 0.0, "last": 0.0},
        ]
        chain = {"spot": spot, "contracts": contracts, "expiries": ["2026-07-01"]}
        result = compute_gex_features(chain)
        assert result["gex_regime_positive"] == 1.0
        assert result["gex_regime_negative"] == 0.0

    def test_all_values_finite(self):
        chain = _make_chain()
        result = compute_gex_features(chain)
        for k, v in result.items():
            assert np.isfinite(v), f"{k}={v} is not finite"

    def test_floor_found_below_spot(self):
        """When there IS a positive-gex strike below spot, floor should find it."""
        spot = 200.0
        contracts = [
            # Below spot, positive GEX call
            {"expiry": "2026-07-01", "strike": 190.0, "type": "C",
             "oi": 5000, "volume": 0, "iv": 0.2, "delta": 0.6,
             "gamma": 0.05, "bid": 0.0, "ask": 0.0, "last": 0.0},
            # Above spot, negative GEX put (so ceiling works too)
            {"expiry": "2026-07-01", "strike": 210.0, "type": "P",
             "oi": 5000, "volume": 0, "iv": 0.2, "delta": -0.6,
             "gamma": 0.05, "bid": 0.0, "ask": 0.0, "last": 0.0},
        ]
        chain = {"spot": spot, "contracts": contracts, "expiries": ["2026-07-01"]}
        result = compute_gex_features(chain)
        assert result["floor_strike"] == pytest.approx(190.0)
        # floor_distance_pct = (200 - 190) / 200 = 0.05
        assert result["floor_distance_pct"] == pytest.approx(0.05)

    def test_CALL_type_recognized(self):
        """CALL (uppercase full) should be treated same as C."""
        spot = 100.0
        contracts = [
            {"expiry": "2026-07-01", "strike": 100.0, "type": "CALL",
             "oi": 1000, "volume": 0, "iv": 0.2, "delta": 0.5,
             "gamma": 0.01, "bid": 0.0, "ask": 0.0, "last": 0.0},
        ]
        chain = {"spot": spot, "contracts": contracts, "expiries": ["2026-07-01"]}
        result = compute_gex_features(chain)
        # CALL in ("C", "CALL") → positive sign
        assert result["net_gex"] > 0.0

    def test_PUT_type_recognized(self):
        """PUT should be treated same as P."""
        spot = 100.0
        contracts = [
            {"expiry": "2026-07-01", "strike": 100.0, "type": "PUT",
             "oi": 1000, "volume": 0, "iv": 0.2, "delta": -0.5,
             "gamma": 0.01, "bid": 0.0, "ask": 0.0, "last": 0.0},
        ]
        chain = {"spot": spot, "contracts": contracts, "expiries": ["2026-07-01"]}
        result = compute_gex_features(chain)
        # PUT not in ("C", "CALL") → negative sign
        assert result["net_gex"] < 0.0


# ======================================================================
# compute_oi_features
# ======================================================================

class TestComputeOiFeatures:
    def _balanced_chain(self):
        spot = 500.0
        calls = []
        puts = []
        for k in [490, 495, 500, 505, 510]:
            calls.append({
                "expiry": "2026-07-01", "strike": float(k), "type": "C",
                "oi": 1000, "volume": 500, "iv": 0.2, "delta": 0.5,
                "gamma": 0.01, "bid": 0.0, "ask": 0.0, "last": 0.0,
            })
            puts.append({
                "expiry": "2026-07-01", "strike": float(k), "type": "P",
                "oi": 2000, "volume": 800, "iv": 0.25, "delta": -0.5,
                "gamma": 0.01, "bid": 0.0, "ask": 0.0, "last": 0.0,
            })
        return {
            "spot": spot,
            "contracts": calls + puts,
            "expiries": ["2026-07-01"],
        }

    def test_total_call_and_put_oi(self):
        chain = self._balanced_chain()
        result = compute_oi_features(chain)
        # 5 calls * 1000 OI = 5000
        assert result["total_call_oi"] == pytest.approx(5000.0)
        # 5 puts * 2000 OI = 10000
        assert result["total_put_oi"] == pytest.approx(10000.0)

    def test_put_call_oi_ratio(self):
        chain = self._balanced_chain()
        result = compute_oi_features(chain)
        # 10000 / 5000 = 2.0
        assert result["put_call_oi_ratio"] == pytest.approx(2.0)

    def test_atm_oi_within_1pct(self):
        chain = self._balanced_chain()
        result = compute_oi_features(chain)
        # spot=500, ATM band = [495, 505], so K=500 is ATM
        # call at K=500: OI=1000; put at K=500: OI=2000
        assert result["atm_call_oi"] == pytest.approx(1000.0)
        assert result["atm_put_oi"] == pytest.approx(2000.0)
        assert result["atm_put_call_oi_ratio"] == pytest.approx(2.0)

    def test_volume_features(self):
        chain = self._balanced_chain()
        result = compute_oi_features(chain)
        # 5 calls * 500 = 2500
        assert result["total_call_volume"] == pytest.approx(2500.0)
        # 5 puts * 800 = 4000
        assert result["total_put_volume"] == pytest.approx(4000.0)
        # 4000 / 2500 = 1.6
        assert result["put_call_volume_ratio"] == pytest.approx(1.6)

    def test_oi_weighted_strike(self):
        chain = self._balanced_chain()
        result = compute_oi_features(chain)
        # calls: 1000*(490+495+500+505+510) = 1000*2500 = 2_500_000
        # puts: 2000*(490+495+500+505+510) = 2000*2500 = 5_000_000
        # total OI = 15000, weighted sum = 7_500_000 → 500.0
        assert result["oi_weighted_strike"] == pytest.approx(500.0)
        assert result["oi_weighted_distance"] == pytest.approx(0.0)

    def test_empty_chain_returns_zeros(self):
        chain = {"spot": 0.0, "contracts": [], "expiries": []}
        result = compute_oi_features(chain)
        assert result["total_call_oi"] == pytest.approx(0.0)
        assert result["total_put_oi"] == pytest.approx(0.0)

    def test_zero_spot_no_atm_crash(self):
        chain = {"spot": 0.0, "contracts": [
            {"expiry": "2026-07-01", "strike": 100.0, "type": "C",
             "oi": 100, "volume": 0, "iv": 0.2, "delta": 0.5,
             "gamma": 0.01, "bid": 0.0, "ask": 0.0, "last": 0.0},
        ]}
        result = compute_oi_features(chain)
        # spot=0 → atm branch returns zeros
        assert result["atm_call_oi"] == pytest.approx(0.0)

    def test_all_values_finite(self):
        chain = _make_chain()
        result = compute_oi_features(chain)
        for k, v in result.items():
            assert np.isfinite(v), f"{k}={v} is not finite"


# ======================================================================
# compute_iv_features
# ======================================================================

class TestComputeIvFeatures:
    def _simple_chain(self):
        spot = 500.0
        contracts = []
        # 3 calls with IV
        for k in [490, 500, 510]:
            contracts.append({
                "expiry": "2026-07-01", "strike": float(k), "type": "C",
                "oi": 100, "volume": 0, "iv": 0.15,
                "delta": 0.5, "gamma": 0.01,
                "bid": 0.0, "ask": 0.0, "last": 0.0,
            })
        # 3 puts with IV
        for k in [490, 500, 510]:
            contracts.append({
                "expiry": "2026-07-01", "strike": float(k), "type": "P",
                "oi": 100, "volume": 0, "iv": 0.25,
                "delta": -0.5, "gamma": 0.01,
                "bid": 0.0, "ask": 0.0, "last": 0.0,
            })
        return {"spot": spot, "contracts": contracts, "expiries": ["2026-07-01"]}

    def test_avg_call_iv_golden(self):
        chain = self._simple_chain()
        result = compute_iv_features(chain)
        # All calls have IV=0.15
        assert result["avg_call_iv"] == pytest.approx(0.15)

    def test_avg_put_iv_golden(self):
        chain = self._simple_chain()
        result = compute_iv_features(chain)
        assert result["avg_put_iv"] == pytest.approx(0.25)

    def test_iv_skew_is_put_minus_call(self):
        chain = self._simple_chain()
        result = compute_iv_features(chain)
        # 0.25 - 0.15 = 0.10
        assert result["iv_skew"] == pytest.approx(0.10)

    def test_avg_iv_all_contracts(self):
        chain = self._simple_chain()
        result = compute_iv_features(chain)
        # 3*0.15 + 3*0.25 = 1.20 / 6 = 0.20
        assert result["avg_iv"] == pytest.approx(0.20)

    def test_min_max_iv(self):
        chain = self._simple_chain()
        result = compute_iv_features(chain)
        assert result["min_iv"] == pytest.approx(0.15)
        assert result["max_iv"] == pytest.approx(0.25)
        assert result["iv_range"] == pytest.approx(0.10)

    def test_atm_iv(self):
        chain = self._simple_chain()
        result = compute_iv_features(chain)
        # ATM: |strike - 500|/500 < 0.005 → only K=500 qualifies
        # At K=500: call IV=0.15, put IV=0.25 → mean = 0.20
        assert result["atm_iv"] == pytest.approx(0.20)

    def test_no_iv_contracts_returns_zeros(self):
        chain = {"spot": 500.0, "contracts": [
            {"expiry": "2026-07-01", "strike": 500.0, "type": "C",
             "oi": 100, "volume": 0, "iv": 0.0,
             "delta": 0.5, "gamma": 0.01,
             "bid": 0.0, "ask": 0.0, "last": 0.0,
            },
        ]}
        result = compute_iv_features(chain)
        # iv=0 filtered out → no calls, no puts → empty dict of zeros
        assert result["avg_call_iv"] == pytest.approx(0.0)
        assert result["avg_put_iv"] == pytest.approx(0.0)

    def test_25d_iv_buckets(self):
        spot = 500.0
        contracts = [
            # 25d put (delta -0.25)
            {"expiry": "2026-07-01", "strike": 480.0, "type": "P",
             "oi": 100, "volume": 0, "iv": 0.30,
             "delta": -0.25, "gamma": 0.01,
             "bid": 0.0, "ask": 0.0, "last": 0.0},
            # 25d call (delta 0.25)
            {"expiry": "2026-07-01", "strike": 520.0, "type": "C",
             "oi": 100, "volume": 0, "iv": 0.18,
             "delta": 0.25, "gamma": 0.01,
             "bid": 0.0, "ask": 0.0, "last": 0.0},
            # 50d call (delta 0.50) — should NOT be in 25d bucket
            {"expiry": "2026-07-01", "strike": 500.0, "type": "C",
             "oi": 100, "volume": 0, "iv": 0.99,
             "delta": 0.50, "gamma": 0.01,
             "bid": 0.0, "ask": 0.0, "last": 0.0},
        ]
        chain = {"spot": spot, "contracts": contracts, "expiries": ["2026-07-01"]}
        result = compute_iv_features(chain)
        assert result["put_25d_iv"] == pytest.approx(0.30)
        assert result["call_25d_iv"] == pytest.approx(0.18)
        assert result["iv_25d_skew"] == pytest.approx(0.30 - 0.18)

    def test_all_values_finite(self):
        chain = _make_chain()
        result = compute_iv_features(chain)
        for k, v in result.items():
            assert np.isfinite(v), f"{k}={v} is not finite"

    def test_zero_spot_no_atm_crash(self):
        chain = {"spot": 0.0, "contracts": [
            {"expiry": "2026-07-01", "strike": 100.0, "type": "C",
             "oi": 100, "volume": 0, "iv": 0.2,
             "delta": 0.5, "gamma": 0.01,
             "bid": 0.0, "ask": 0.0, "last": 0.0},
        ]}
        result = compute_iv_features(chain)
        assert result["atm_iv"] == pytest.approx(0.0)


# ======================================================================
# Integration-style: compute_* functions work together
# ======================================================================

class TestIntegration:
    def test_full_chain_produces_all_feature_categories(self):
        """Ensure GEX + OI + IV together produce non-overlapping feature sets."""
        chain = _make_chain(spot=500.0, n_strikes=10)
        gex = compute_gex_features(chain)
        oi = compute_oi_features(chain)
        iv = compute_iv_features(chain)

        all_keys = set(gex) | set(oi) | set(iv)
        assert len(all_keys) == len(gex) + len(oi) + len(iv), \
            "Feature keys should not overlap between GEX/OI/IV"

    def test_synthetic_price_plus_chain(self):
        """End-to-end: price features + chain features from synthetic data."""
        df = _make_price_df()
        chain = _make_chain()

        price_feats = compute_price_features_realtime(df)
        gex_feats = compute_gex_features(chain)
        oi_feats = compute_oi_features(chain)
        iv_feats = compute_iv_features(chain)

        combined = {**price_feats, **gex_feats, **oi_feats, **iv_feats}

        # Should have many features
        assert len(combined) > 30

        # All finite
        for k, v in combined.items():
            assert np.isfinite(v), f"{k}={v} not finite"
