"""Synthetic + scipy.stats reference tests for live ML feature pipeline.

Mirrors the dual-anchor pattern from ``kelly_replay``: hand-pinned
arithmetic + scipy.stats cross-check. All tests are deterministic —
no live yfinance calls required.

Hand-derived values originate from a 3-contract synthetic chain. The
implementation formula is::

    gex_unit = gamma * oi * 100 * spot * spot * 0.01

with spot=100 ⇒ ``100 * 100 * 100 * 0.01 = 10_000`` so the formula
collapses to ``gex_unit = gamma * oi * 10_000``.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.mark.parametrize("values", [[], [1.0], [1.0, 2.0], [1.0, 2.0, 3.0], [7.0] * 8])
def test_kurtosis_short_and_constant_inputs(values):
    from services.ml_realtime_features import _kurtosis
    assert _kurtosis(values) == 0.0


@pytest.mark.parametrize("helper", ["compute_gex_features", "compute_oi_features", "compute_iv_features"])
def test_empty_feature_chain_is_finite(helper):
    from services import ml_realtime_features as features
    result = getattr(features, helper)({"spot": 100.0, "contracts": []})
    assert result
    assert all(value == 0.0 for value in result.values())


@pytest.mark.parametrize("helper", ["compute_gex_features", "compute_oi_features", "compute_iv_features"])
def test_full_option_type_names_match_short_names(helper, synthetic_chain):
    from services import ml_realtime_features as features
    expanded = {**synthetic_chain, "contracts": [
        {**contract, "type": {"C": "CALL", "P": "PUT"}[contract["type"]]}
        for contract in synthetic_chain["contracts"]
    ]}
    original = getattr(features, helper)(synthetic_chain)
    actual = getattr(features, helper)(expanded)
    assert actual == pytest.approx(original)
    assert all(np.isfinite(value) for value in actual.values())


@pytest.mark.parametrize("helper", ["compute_oi_features", "compute_iv_features"])
def test_zero_spot_keeps_oi_and_iv_features_finite(helper, synthetic_chain):
    from services import ml_realtime_features as features
    result = getattr(features, helper)({**synthetic_chain, "spot": 0.0})
    assert all(np.isfinite(value) for value in result.values())
    assert all(value == 0.0 for key, value in result.items() if key.startswith("atm_"))


def test_no_positive_iv_returns_existing_zero_feature_contract(synthetic_chain):
    from services.ml_realtime_features import compute_iv_features
    chain = {**synthetic_chain, "contracts": [
        {**contract, "iv": 0.0} for contract in synthetic_chain["contracts"]
    ]}
    result = compute_iv_features(chain)
    assert len(result) == 11
    assert all(value == 0.0 for value in result.values())


# ────────────────────────────────────────────────────────────────────
# Synthetic chain anchored to hand-derived values
# ────────────────────────────────────────────────────────────────────

@pytest.fixture
def synthetic_chain() -> dict:
    """A 3-contract chain with hand-pinnable arithmetic.

    gex_unit (= γ * oi * 10_000 with spot=100):
      +------+------+-----+-----+-------+------+------+
      | type |  K   |  γ  | OI  |  Δ    |  IV  | sign |
      +------+------+-----+-----+-------+------+------+
      |  C   | 100  |0.05 |  10 | 0.50  | 0.25 |  +1  |
      |  C   | 110  |0.03 |  20 | 0.30  | 0.30 |  +1  |
      |  P   |  90  |0.04 |  15 |-0.40  | 0.28 |  -1  |
      +------+------+-----+-----+-------+------+------+

    ⇒ gex_by_strike = {100: +5000, 110: +6000,  90: -6000}
    ⇒ net_gex = 5000; total_abs_gex = 17000
    ⇒ king_strike = 90 (argmax abs=6000 ties broken by lowest index)
    """
    return {
        "spot": 100.0,
        "contracts": [
            {"type": "C", "strike": 100, "gamma": 0.05, "oi": 10,
             "delta": 0.50, "iv": 0.25, "volume": 0,
             "bid": 5.0, "ask": 5.2, "last": 5.1},
            {"type": "C", "strike": 110, "gamma": 0.03, "oi": 20,
             "delta": 0.30, "iv": 0.30, "volume": 0,
             "bid": 1.0, "ask": 1.1, "last": 1.05},
            {"type": "P", "strike": 90,  "gamma": 0.04, "oi": 15,
             "delta": -0.40, "iv": 0.28, "volume": 0,
             "bid": 1.0, "ask": 1.2, "last": 1.10},
        ],
    }


@pytest.fixture
def synthetic_chain_5() -> dict:
    """5-strike chain so the kurtosis formula is exercised (n≥4).

    gex_by_strike from this chain:
      80 (P): -5000; 90 (P): -6000; 100 (C): +5000;
      110 (C): +6000; 120 (C): +5000.

    Values list (ascending): [-5000, -6000, +5000, +6000, +5000]
                              sorted = [-6000, -5000, +5000, +5000, +6000]
    scipy.stats.kurtosis(values, fisher=True) returns the same excess
    kurtosis as the implementation's
    ``np.mean(((x - mu)/sigma)**4) - 3`` formula.
    """
    return {
        "spot": 100.0,
        "contracts": [
            {"type": "P", "strike": 80, "gamma": 0.05, "oi": 10,
             "delta": -0.55, "iv": 0.32, "volume": 0,
             "bid": 2.0, "ask": 2.1, "last": 2.05},
            {"type": "P", "strike": 90, "gamma": 0.04, "oi": 15,
             "delta": -0.40, "iv": 0.28, "volume": 0,
             "bid": 1.0, "ask": 1.2, "last": 1.10},
            {"type": "C", "strike": 100, "gamma": 0.05, "oi": 10,
             "delta": 0.50, "iv": 0.25, "volume": 0,
             "bid": 5.0, "ask": 5.2, "last": 5.1},
            {"type": "C", "strike": 110, "gamma": 0.03, "oi": 20,
             "delta": 0.30, "iv": 0.30, "volume": 0,
             "bid": 1.0, "ask": 1.1, "last": 1.05},
            {"type": "C", "strike": 120, "gamma": 0.02, "oi": 25,
             "delta": 0.20, "iv": 0.32, "volume": 0,
             "bid": 0.5, "ask": 0.6, "last": 0.55},
        ],
    }


# ────────────────────────────────────────────────────────────────────
# Class 1 — GEX feature hand-pin arithmetic
# ────────────────────────────────────────────────────────────────────

class TestGexFeatureHandpin:
    """Hand-pin the per-strike arithmetic for the 3-contract chain."""

    def test_compute_gex_features_net_gex_total_abs(
        self, synthetic_chain
    ) -> None:
        from services.ml_realtime_features import compute_gex_features
        feats = compute_gex_features(synthetic_chain)
        # 5000 + 6000 - 6000 = 5000
        assert feats["net_gex"] == pytest.approx(5000.0, abs=1e-6)
        # |5000| + |6000| + |-6000| = 17000
        assert feats["total_abs_gex"] == pytest.approx(17000.0, abs=1e-6)

    def test_compute_gex_features_normalized_ratio(
        self, synthetic_chain
    ) -> None:
        from services.ml_realtime_features import compute_gex_features
        feats = compute_gex_features(synthetic_chain)
        # 5000 / 17000 ≈ 0.29412
        assert feats["net_gex_normalized"] == pytest.approx(
            5000 / 17000, abs=1e-6
        )
        assert feats["positive_gex"] == pytest.approx(11000.0, abs=1e-6)
        assert feats["negative_gex"] == pytest.approx(-6000.0, abs=1e-6)
        # gex_ratio = 11000 / (|−6000| + ε) ≈ 1.8333
        assert feats["gex_ratio"] == pytest.approx(11000 / 6000, abs=1e-3)

    def test_compute_gex_features_king_and_regime(
        self, synthetic_chain
    ) -> None:
        from services.ml_realtime_features import compute_gex_features
        feats = compute_gex_features(synthetic_chain)
        # abs values at strikes [90, 100, 110] = [6000, 5000, 6000]
        # np.argmax → 0 (first occurrence of max) → king_strike=90
        assert feats["king_strike"] == pytest.approx(90.0, abs=1e-6)
        # gex_by_strike[90] = -6000 (put, sign-1)
        assert feats["king_gex"] == pytest.approx(-6000.0, abs=1e-6)
        # king_distance_pct = (100 - 90) / 100 = 0.10
        assert feats["king_distance_pct"] == pytest.approx(0.10, abs=1e-6)
        # net_gex=5000 > 0 ⇒ positive regime
        assert feats["gex_regime_positive"] == pytest.approx(1.0, abs=1e-6)
        assert feats["gex_regime_negative"] == pytest.approx(0.0, abs=1e-6)

    def test_compute_gex_features_floor_and_ceiling(
        self, synthetic_chain
    ) -> None:
        from services.ml_realtime_features import compute_gex_features
        feats = compute_gex_features(synthetic_chain)
        # floor_strike requires k<spot AND gex>0. Only 90 < 100 but
        # gex=-6000 (negative) → no eligible strikes → default 0.0.
        assert feats["floor_strike"] == pytest.approx(0.0, abs=1e-6)
        assert feats["floor_gex"] == pytest.approx(0.0, abs=1e-6)
        assert feats["floor_distance_pct"] == pytest.approx(0.0, abs=1e-6)
        # ceiling_strike requires k>spot AND gex<0. Only 110 > 100
        # but gex=+6000 (positive) → no eligible strikes → default 0.0.
        assert feats["ceiling_strike"] == pytest.approx(0.0, abs=1e-6)
        assert feats["ceiling_gex"] == pytest.approx(0.0, abs=1e-6)
        assert feats["ceiling_distance_pct"] == pytest.approx(0.0, abs=1e-6)

    def test_compute_gex_features_concentration_and_counts(
        self, synthetic_chain
    ) -> None:
        from services.ml_realtime_features import compute_gex_features
        feats = compute_gex_features(synthetic_chain)
        # 3 strikes, all in top-5 ⇒ concentration = 1.0
        assert feats["gex_top5_concentration"] == pytest.approx(
            1.0, abs=1e-6
        )
        assert feats["gex_num_strikes"] == pytest.approx(3.0, abs=1e-6)

    def test_compute_gex_features_empty_returns_zero_kurtosis(
        self, synthetic_chain
    ) -> None:
        """3-strike chain → impl's ``_kurtosis`` early-returns 0.0
        because ``len(values) < 4``. Pin this contract explicitly.
        """
        from services.ml_realtime_features import compute_gex_features
        feats = compute_gex_features(synthetic_chain)
        assert feats["gex_kurtosis"] == pytest.approx(0.0, abs=1e-9)

    def test_compute_gex_features_kurtosis_scipy_crosscheck(
        self, synthetic_chain_5
    ) -> None:
        """5-strike chain → 5 gex_by_strike values → n=5 ≥ 4 so
        the kurtosis formula is exercised. Cross-check against
        ``scipy.stats.kurtosis(values, fisher=True)``.
        """
        from services.ml_realtime_features import compute_gex_features
        scipy_stats = __import__("scipy.stats", fromlist=["kurtosis"])
        feats = compute_gex_features(synthetic_chain_5)
        gex_values = [
            -5000.0,  # 80 P
            -6000.0,  # 90 P
            5000.0,   # 100 C
            6000.0,   # 110 C
            5000.0,   # 120 C
        ]
        scipy_kurtosis = float(
            scipy_stats.kurtosis(gex_values, fisher=True)
        )
        # Impl: ``np.mean(((x-mu)/sigma) ** 4) - 3`` matches Fisher=True.
        assert feats["gex_kurtosis"] == pytest.approx(
            scipy_kurtosis, abs=1e-4
        )


# ────────────────────────────────────────────────────────────────────
# Class 2 — OI feature hand-pin arithmetic
# ────────────────────────────────────────────────────────────────────

class TestOiFeatureHandpin:
    """Hand-pin open-interest per-strike aggregates."""

    def test_compute_oi_features_totals_and_ratio(
        self, synthetic_chain
    ) -> None:
        from services.ml_realtime_features import compute_oi_features
        feats = compute_oi_features(synthetic_chain)
        assert feats["total_call_oi"] == pytest.approx(30.0, abs=1e-6)
        assert feats["total_put_oi"] == pytest.approx(15.0, abs=1e-6)
        # 15 / (30 + ε) ≈ 0.5
        assert feats["put_call_oi_ratio"] == pytest.approx(0.5, abs=1e-3)

    def test_compute_oi_features_atm_window(
        self, synthetic_chain
    ) -> None:
        from services.ml_realtime_features import compute_oi_features
        feats = compute_oi_features(synthetic_chain)
        # ATM window: |strike-spot|/spot < 0.01 → within $1 of spot=100
        # Only strike=100 hits a call; no puts at strike=100.
        assert feats["atm_call_oi"] == pytest.approx(10.0, abs=1e-6)
        assert feats["atm_put_oi"] == pytest.approx(0.0, abs=1e-6)
        assert feats["atm_put_call_oi_ratio"] == pytest.approx(
            0.0, abs=1e-3
        )

    def test_compute_oi_features_weighted_strike(
        self, synthetic_chain
    ) -> None:
        from services.ml_realtime_features import compute_oi_features
        feats = compute_oi_features(synthetic_chain)
        # (100*10 + 110*20 + 90*15) / 45 = 4550 / 45 ≈ 101.1111
        assert feats["oi_weighted_strike"] == pytest.approx(
            4550 / 45, abs=1e-3
        )
        assert feats["oi_weighted_distance"] == pytest.approx(
            (100 - 4550 / 45) / 100, abs=1e-5
        )


# ────────────────────────────────────────────────────────────────────
# Class 3 — IV feature hand-pin arithmetic
# ────────────────────────────────────────────────────────────────────

class TestIvFeatureHandpin:
    """Hand-pin implied-volatility aggregates."""

    def test_compute_iv_features_means_and_skew(
        self, synthetic_chain
    ) -> None:
        from services.ml_realtime_features import compute_iv_features
        feats = compute_iv_features(synthetic_chain)
        # avg_call_iv = (0.25 + 0.30)/2 = 0.275
        assert feats["avg_call_iv"] == pytest.approx(0.275, abs=1e-6)
        # avg_put_iv = 0.28
        assert feats["avg_put_iv"] == pytest.approx(0.28, abs=1e-6)
        # iv_skew = 0.28 - 0.275 = 0.005
        assert feats["iv_skew"] == pytest.approx(0.005, abs=1e-6)
        # all_ivs = [0.25, 0.30, 0.28]; avg = 0.83/3
        assert feats["avg_iv"] == pytest.approx(0.83 / 3, abs=1e-4)
        assert feats["min_iv"] == pytest.approx(0.25, abs=1e-6)
        assert feats["max_iv"] == pytest.approx(0.30, abs=1e-6)
        assert feats["iv_range"] == pytest.approx(0.05, abs=1e-6)

    def test_compute_iv_features_atm_and_25delta(
        self, synthetic_chain
    ) -> None:
        from services.ml_realtime_features import compute_iv_features
        feats = compute_iv_features(synthetic_chain)
        # ATM window: |strike-100|/100 < 0.005 → only strike=100
        assert feats["atm_iv"] == pytest.approx(0.25, abs=1e-6)
        # 25-delta band: 0.20 ≤ |delta| ≤ 0.30
        # puts: put@90 has |delta|=0.40 (FAIL) → empty → 0.0
        # calls: call@100 has delta=0.50 (FAIL), call@110 delta=0.30 (PASS)
        assert feats["put_25d_iv"] == pytest.approx(0.0, abs=1e-6)
        assert feats["call_25d_iv"] == pytest.approx(0.30, abs=1e-6)
        assert feats["iv_25d_skew"] == pytest.approx(-0.30, abs=1e-6)


# ────────────────────────────────────────────────────────────────────
# Class 4 — Price feature hand-pin + RSI / realized vol cross-checks
# ────────────────────────────────────────────────────────────────────

class TestPriceFeatureHandpin:
    """Pin technical indicators on a deterministic price series."""

    @pytest.fixture
    def alt_price_df(self) -> pd.DataFrame:
        """30-row DataFrame; the last 15 rows (idx 15-29) alternate
        100.5 / 100.0 / 100.5 / ...; idx 0-14 hold constant 100.0.

        For the Wilder RSI over the 14-tick window ``iloc[idx-14:idx]``
        = ``iloc[15:29]`` (the 14 closes at idx 15-28):
          14 daily diffs with offset (idx - 15):
            even offsets 0,2,4,...,12 (7 entries) → +0.5 gain
            odd offsets  1,3,5,...,13 (7 entries) → -0.5 loss
          avg_gain = avg_loss = 0.5; RS = 1; RSI = 50.
        """
        n = 30
        closes = [100.0] * 15 + [
            100.5 if i % 2 == 0 else 100.0 for i in range(15)
        ]
        closes = closes[:n]
        df = pd.DataFrame({
            "Close": closes,
            "Open": closes,
            "High": [c + 0.05 for c in closes],
            "Low": [c - 0.05 for c in closes],
            "Volume": [1_000_000.0] * n,
        })
        return df

    def test_compute_price_features_wilder_rsi_50(self, alt_price_df) -> None:
        """Alternating +0.5/-0.5 ⇒ Wilder RSI = 50 exactly.

        Implementation uses ``(losses + 1e-8)`` to avoid div-by-zero,
        so the value rounds very close to 50.0 (smoke output was
        49.99999996428571 — error ~3.6e-8). ``abs=1e-4`` is plenty of
        headroom for the 1e-8 epsilon term; tighten beyond that to
        surface domain-formula drift.
        """
        from services.ml_realtime_features import (
            compute_price_features_realtime,
        )
        feats = compute_price_features_realtime(alt_price_df)
        assert feats["rsi_14"] == pytest.approx(50.0, abs=1e-4)

    def test_compute_price_features_realized_vol_scipy_crosscheck(
        self, alt_price_df
    ) -> None:
        """Cross-check ``realized_vol_20d`` against the same formula
        the implementation uses: ``iloc[idx-20:idx].pct_change().std()
        * sqrt(252)``.
        """
        from services.ml_realtime_features import (
            compute_price_features_realtime,
        )
        feats = compute_price_features_realtime(alt_price_df)
        idx = len(alt_price_df) - 1  # 29
        window = alt_price_df["Close"].iloc[idx - 20:idx]  # indices 9..28
        expected = float(
            window.pct_change().dropna().std() * np.sqrt(252)
        )
        assert feats["realized_vol_20d"] == pytest.approx(
            expected, abs=1e-6
        )

    def test_compute_price_features_ma_uses_correct_window(
        self, alt_price_df
    ) -> None:
        """MA windows use ``iloc[idx-window:idx]`` (excludes idx).

        For idx=29 window=5: ``iloc[24:29]`` = indices 24,25,26,27,28
        = [100.0, 100.5, 100.0, 100.5, 100.0]; mean = 100.0.
        close_to_ma_5 = (100.5 - 100.0) / (100.0 + ε) ≈ 0.005.
        """
        from services.ml_realtime_features import (
            compute_price_features_realtime,
        )
        feats = compute_price_features_realtime(alt_price_df)
        idx = len(alt_price_df) - 1
        window = alt_price_df["Close"].iloc[idx - 5:idx]
        expected_ma5 = float(window.mean())
        assert feats["ma_5"] == pytest.approx(expected_ma5, abs=1e-6)
        assert feats["close_to_ma_5"] == pytest.approx(
            (100.5 - expected_ma5) / (expected_ma5 + 1e-8), abs=1e-6
        )

    def test_compute_price_features_return_1d_uses_correct_shift(
        self, alt_price_df
    ) -> None:
        """Return-1d uses ``iloc[idx-period:idx]`` — so the previous
        close is ``iloc[idx-1] = iloc[28] = 100.0`` and the current
        close is 100.5. Return = (100.5 - 100.0)/100.0 ≈ 0.005.
        """
        from services.ml_realtime_features import (
            compute_price_features_realtime,
        )
        feats = compute_price_features_realtime(alt_price_df)
        idx = len(alt_price_df) - 1
        prev = float(alt_price_df["Close"].iloc[idx - 1])
        assert feats["return_1d"] == pytest.approx(
            (alt_price_df["Close"].iloc[idx] - prev) / (prev + 1e-8),
            abs=1e-6,
        )

    def test_compute_price_features_short_series_falls_back(self) -> None:
        """idx < window ⇒ MA falls back to current close and
        realized_vol_20d falls back to 0.0. Use a monotonically
        increasing 10-row series (idx=9) so all 50/20/14 windows
        are NOT available.
        """
        from services.ml_realtime_features import (
            compute_price_features_realtime,
        )
        closes = [100.0 + i for i in range(10)]  # idx=9 < 50
        df = pd.DataFrame({
            "Close": closes,
            "Open": closes,
            "High": [c + 0.05 for c in closes],
            "Low": [c - 0.05 for c in closes],
            "Volume": [1_000_000.0] * 10,
        })
        feats = compute_price_features_realtime(df)
        # MA fall-back to current close for large windows.
        assert feats["ma_50"] == pytest.approx(109.0, abs=1e-6)
        assert feats["close_to_ma_50"] == pytest.approx(0.0, abs=1e-6)
        # realized_vol_20d fallback for idx < 20.
        assert feats["realized_vol_20d"] == pytest.approx(0.0, abs=1e-6)
        # RSI fallback for idx < 14.
        assert feats["rsi_14"] == pytest.approx(50.0, abs=1e-6)



# ────────────────────────────────────────────────────────────────────
# Sentiment feature-column tests (steal-list deferred-(b) ship).
# Verifies that `compute_features_for_inference` always emits
# `sentiment_score` + `sentiment_available` and that the sorted
# `feature_names` list alphabetises them with the rest.
# All tests use the synthetic_chain fixture but stub `fetch_price_history`
# + `fetch_live_chain` so no yfinance fetches happen.
# ────────────────────────────────────────────────────────────────────

class TestSentimentFeatureColumn:
    """Pins the canonical sentiment columns in the realtime feature dict."""

    def _stub_price_history(self, monkeypatch, n=30):
        """Stub the price-history fetch so compute_features_for_inference
        sees a valid 30-row history without hitting yfinance."""
        import pandas as pd

        from services import ml_realtime_features as mrf
        closes = [100.0 + 0.1 * i for i in range(n)]
        df = pd.DataFrame({
            "Close": closes,
            "Open": closes,
            "High": [c + 0.05 for c in closes],
            "Low": [c - 0.05 for c in closes],
            "Volume": [1_000_000.0] * n,
        })
        monkeypatch.setattr(mrf, "fetch_price_history", lambda ticker, days=60: df)
        monkeypatch.setattr(mrf, "fetch_live_chain",
                            lambda ticker, max_expiries=2: {
                                "spot": closes[-1],
                                "contracts": [],
                                "expiries": [],
                            })

    def test_sentiment_columns_present_in_features(
        self, monkeypatch, synthetic_chain
    ) -> None:
        """Default precomputed_sentiment=None emits sentiment_score=0.0
        and sentiment_available=0.0 (matches 1.0/0.0 convention for ML trees).
        """
        from services import ml_realtime_features as mrf
        from services.ml_realtime_features import compute_features_for_inference
        monkeypatch.setattr(mrf, "fetch_live_chain",
                            lambda ticker, max_expiries=2: synthetic_chain)
        self._stub_price_history(monkeypatch)
        out = compute_features_for_inference("SPY")
        assert out is not None
        assert "sentiment_score" in out["features"]
        assert "sentiment_available" in out["features"]
        assert out["features"]["sentiment_score"] == 0.0
        assert out["features"]["sentiment_available"] == 0.0
        assert "sentiment_score" in out["feature_names"]
        assert "sentiment_available" in out["feature_names"]
        # alphabetic sort puts sentiment right after realized_vol_20d / rsi_14
        names = out["feature_names"]
        # Confirm both columns are in the alphabetical list
        assert names.index("sentiment_score") > 0
        assert names.index("sentiment_available") > 0

    def test_sentiment_injection_populates_columns(
        self, monkeypatch, synthetic_chain
    ) -> None:
        """precomputed_sentiment with avg_vader=0.6 + avg_textblob=0.4
        propagates through to columns: 0.5 score + 1.0 available flag."""
        from services import ml_realtime_features as mrf
        from services.ml_realtime_features import compute_features_for_inference
        monkeypatch.setattr(mrf, "fetch_live_chain",
                            lambda ticker, max_expiries=2: synthetic_chain)
        self._stub_price_history(monkeypatch)
        precomputed = {
            "avg_vader": 0.6, "avg_textblob": 0.4, "tweet_count": 5,
            "bullish_count": 4, "bearish_count": 1, "neutral_count": 0,
            "sentiment_label": "positive", "confidence": 0.8,
            "top_tweets": [],
        }
        out = compute_features_for_inference("SPY",
                                             precomputed_sentiment=precomputed)
        assert out is not None
        assert out["features"]["sentiment_score"] == pytest.approx(0.5, abs=1e-4)
        assert out["features"]["sentiment_available"] == 1.0
        assert out["sentiment_available"] is True

    def test_sentiment_extraction_failure_yields_zero(
        self, monkeypatch, synthetic_chain
    ) -> None:
        """Malformed precomputed_sentiment (None + wrong keys) degrades
        gracefully to 0.0 + 0.0 instead of raising."""
        from services import ml_realtime_features as mrf
        from services.ml_realtime_features import compute_features_for_inference
        monkeypatch.setattr(mrf, "fetch_live_chain",
                            lambda ticker, max_expiries=2: synthetic_chain)
        self._stub_price_history(monkeypatch)
        out = compute_features_for_inference("SPY", precomputed_sentiment=None)
        assert out is not None
        assert out["features"]["sentiment_score"] == 0.0
        assert out["features"]["sentiment_available"] == 0.0
