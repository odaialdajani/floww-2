"""
backend/tests/services/ml/test_gex_features.py

Unit tests for ``services.ml.features.add_gex_features`` — the row-wise GEX
feature augmentation introduced in Phase 4 (SPY v3).

Each test pins one contract from the spec in ``CLAUDE_REVIEW_PROMPT.md``:

  1.  Happy path — every new column varies and is finite for the core five.
  2.  Short history — gex_roc_5d is NaN, no exception.
  3.  Missing gamma_flip — distance feature is 0.0 and a warning fires.
  4.  Missing gex_by_strike — wall + HHI are NaN, no exception.
  5.  No-leakage — mutating future rows must not move features at time t.
  6.  Idempotency — re-running on output is a no-op.
  7.  Empty dataframe — schema preserved, zero rows.
  8.  Single row, no history — features that need history are NaN.
  9.  Wall density sanity — 100% mass at spot → 1.0.
  10. Herfindahl sanity — equal across N strikes → 1/N.
  11. (bonus) Non-mutation — input dataframe untouched.
"""

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add backend/ to sys.path so ``services.ml.features`` is importable regardless
# of the CWD pytest runs from. __file__ = backend/tests/services/ml/...; parent[3]
# is backend/. Matches the convention in test_gate.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.ml.features import (  # noqa: E402
    GEX_FEATURE_OUTPUT_COLS,
    add_gex_features,
)

# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────


def _make_history(values):
    """Pack a list of gex_total values into (ts, gex_total) tuples."""
    base = pd.Timestamp("2026-01-01", tz="UTC")
    return [(base + pd.Timedelta(days=i), float(v)) for i, v in enumerate(values)]


def _row(ts, spot, gex_total, history_vals, *, gamma_flip=None, gex_by_strike=None):
    return {
        "ticker": "SPY",
        "ts": ts,
        "spot": float(spot),
        "gex_total": float(gex_total),
        "gex_history": _make_history(history_vals),
        "gamma_flip": gamma_flip,
        "gex_by_strike": gex_by_strike,
    }


def _happy_df(n_rows: int = 90) -> pd.DataFrame:
    """90 rows with realistic, varying GEX history per row."""
    rng = np.random.default_rng(seed=42)  # deterministic, not synthetic-data injection
    base_ts = pd.Timestamp("2026-01-01", tz="UTC")
    rows = []
    history_pool = list(rng.normal(0.0, 1e9, size=200))
    for i in range(n_rows):
        # Per-row history: trailing 60 entries from the pool, deterministic.
        hist_window = history_pool[i : i + 60]
        gex_total = history_pool[i + 60]  # deterministic next value
        spot = 500.0 + i * 0.5
        rows.append(
            _row(
                ts=base_ts + pd.Timedelta(days=i),
                spot=spot,
                gex_total=gex_total,
                history_vals=hist_window,
                gamma_flip=spot * (1.0 + (i % 5 - 2) * 0.002),
                gex_by_strike={
                    spot - 5: rng.normal(0, 1e8),
                    spot: rng.normal(0, 1e8),
                    spot + 5: rng.normal(0, 1e8),
                    spot + 10: rng.normal(0, 1e8),
                },
            )
        )
    return pd.DataFrame(rows)


# ────────────────────────────────────────────────────────────────────────────
# 1. Happy path
# ────────────────────────────────────────────────────────────────────────────


def test_happy_path_all_columns_present_and_varying():
    df = _happy_df(90)
    out = add_gex_features(df)

    for col in GEX_FEATURE_OUTPUT_COLS:
        assert col in out.columns, f"missing column {col}"

    # Variance > 1e-6 — the SPY v3 training pipeline asserts this for every
    # feature before fit. We pin the same threshold here.
    for col in (
        "gex_zscore_60d",
        "gex_roc_5d",
        "gex_distance_to_flip_norm",
        "gex_wall_density_pct",
        "gex_herfindahl",
    ):
        var = out[col].dropna().var()
        assert var > 1e-6, f"{col} variance {var} below 1e-6 floor"

    # regime_pos may be all zero/one only if history is monotone-sign; with our
    # zero-mean draws we expect both values to appear at least once.
    assert set(out["gex_regime_pos"].unique()) == {0.0, 1.0}

    # No NaNs in the first five features on the happy path (history is long
    # enough for every row).
    for col in (
        "gex_zscore_60d",
        "gex_roc_5d",
        "gex_regime_pos",
        "gex_distance_to_flip_norm",
        "gex_wall_density_pct",
    ):
        assert out[col].isna().sum() == 0, f"{col} has unexpected NaNs"


# ────────────────────────────────────────────────────────────────────────────
# 2. Short history → ROC is NaN
# ────────────────────────────────────────────────────────────────────────────


def test_short_history_yields_nan_roc():
    # Only 3 entries — fewer than ROC's 5-day lookback.
    df = pd.DataFrame(
        [
            _row(
                ts=pd.Timestamp("2026-02-01", tz="UTC"),
                spot=500.0,
                gex_total=1e9,
                history_vals=[1.0, 2.0, 3.0],
            )
        ]
    )
    out = add_gex_features(df)
    assert pd.isna(out["gex_roc_5d"].iloc[0])
    # zscore is still defined (mean/std of 3 values is fine).
    assert not pd.isna(out["gex_zscore_60d"].iloc[0])


# ────────────────────────────────────────────────────────────────────────────
# 3. Missing gamma_flip → 0.0 + warning
# ────────────────────────────────────────────────────────────────────────────


def test_missing_gamma_flip_logs_warning_and_returns_zero(caplog):
    df = _happy_df(10).drop(columns=["gamma_flip"])
    with caplog.at_level(logging.WARNING, logger="ml.features"):
        out = add_gex_features(df)
    assert (out["gex_distance_to_flip_norm"] == 0.0).all()
    assert any("gamma_flip" in rec.message for rec in caplog.records), (
        "expected at least one warning mentioning gamma_flip"
    )


def test_per_row_nan_gamma_flip_returns_zero():
    df = _happy_df(5)
    df.loc[2, "gamma_flip"] = np.nan
    out = add_gex_features(df)
    assert out["gex_distance_to_flip_norm"].iloc[2] == 0.0
    # Other rows still computed normally.
    assert out["gex_distance_to_flip_norm"].iloc[0] != 0.0 or \
        out["gex_distance_to_flip_norm"].iloc[1] != 0.0


# ────────────────────────────────────────────────────────────────────────────
# 4. Missing gex_by_strike → NaN, no exception
# ────────────────────────────────────────────────────────────────────────────


def test_missing_gex_by_strike_yields_nan():
    df = _happy_df(8).drop(columns=["gex_by_strike"])
    out = add_gex_features(df)
    assert out["gex_wall_density_pct"].isna().all()
    assert out["gex_herfindahl"].isna().all()
    # Other features still computed.
    assert not out["gex_zscore_60d"].isna().any()


# ────────────────────────────────────────────────────────────────────────────
# 5. No-leakage guard
# ────────────────────────────────────────────────────────────────────────────


def test_no_future_leakage_in_history_aggregates():
    """
    Build a dataframe where every row's gex_history ends strictly before that
    row's ts. Compute features. Then mutate the gex_total at rows AFTER row 2
    (and also poison their history with an obviously-wrong value to be extra
    sure). Re-compute features. Row 2's features must be unchanged.
    """
    base = pd.Timestamp("2026-03-01", tz="UTC")
    rows = []
    for i in range(10):
        # History deliberately ends at i - 1 (i.e. strict t < row.ts).
        hist_vals = [float(j) * 1e8 for j in range(i)]
        rows.append(
            _row(
                ts=base + pd.Timedelta(days=i),
                spot=400.0 + i,
                gex_total=float(i) * 1e8 + 5e7,
                history_vals=hist_vals,
                gamma_flip=395.0 + i * 0.1,
                gex_by_strike={400 - 5: 1e7, 400.0 + i: 2e7, 400 + 5: 1e7},
            )
        )
    df_a = pd.DataFrame(rows)
    out_a = add_gex_features(df_a)
    target_idx = 2
    snapshot = out_a.loc[target_idx, list(GEX_FEATURE_OUTPUT_COLS)].copy()

    # Now mutate future rows — both their current values and their histories.
    df_b = df_a.copy()
    for i in range(target_idx + 1, len(df_b)):
        df_b.at[i, "gex_total"] = 9.99e15
        df_b.at[i, "spot"] = -1.0
        df_b.at[i, "gamma_flip"] = 1.0
        df_b.at[i, "gex_by_strike"] = {1: 1.0, 2: 1.0}
        # Critically, this would be a leakage bug: poisoning future history.
        df_b.at[i, "gex_history"] = [(base, 9.99e15)] * 60

    out_b = add_gex_features(df_b)
    pd.testing.assert_series_equal(
        snapshot,
        out_b.loc[target_idx, list(GEX_FEATURE_OUTPUT_COLS)],
        check_names=False,
    )


# ────────────────────────────────────────────────────────────────────────────
# 6. Idempotency
# ────────────────────────────────────────────────────────────────────────────


def test_idempotent_double_application():
    df = _happy_df(30)
    once = add_gex_features(df)
    twice = add_gex_features(once)

    # No extra columns from a second pass.
    assert list(once.columns) == list(twice.columns)

    # And values are identical (deterministic, pure function).
    pd.testing.assert_frame_equal(once, twice)


# ────────────────────────────────────────────────────────────────────────────
# 7. Empty dataframe
# ────────────────────────────────────────────────────────────────────────────


def test_empty_dataframe_preserves_schema():
    df = pd.DataFrame(
        columns=["ticker", "ts", "spot", "gex_total", "gex_history",
                 "gamma_flip", "gex_by_strike"]
    )
    out = add_gex_features(df)
    assert len(out) == 0
    for col in GEX_FEATURE_OUTPUT_COLS:
        assert col in out.columns


# ────────────────────────────────────────────────────────────────────────────
# 8. Single row, no history
# ────────────────────────────────────────────────────────────────────────────


def test_single_row_no_history_preserved():
    df = pd.DataFrame(
        [
            _row(
                ts=pd.Timestamp("2026-04-01", tz="UTC"),
                spot=500.0,
                gex_total=1.23e9,
                history_vals=[],
                gamma_flip=499.0,
                gex_by_strike={500.0: 1e8, 505.0: 5e7},
            )
        ]
    )
    out = add_gex_features(df)
    assert len(out) == 1  # row preserved
    # zscore + roc both require history → NaN; regime is from current row → defined.
    assert pd.isna(out["gex_zscore_60d"].iloc[0])
    assert pd.isna(out["gex_roc_5d"].iloc[0])
    assert out["gex_regime_pos"].iloc[0] == 1.0
    # Distance feature works on current-row data alone.
    assert not pd.isna(out["gex_distance_to_flip_norm"].iloc[0])


# ────────────────────────────────────────────────────────────────────────────
# 9. Wall density sanity
# ────────────────────────────────────────────────────────────────────────────


def test_wall_density_full_concentration_at_spot():
    spot = 500.0
    df = pd.DataFrame(
        [
            _row(
                ts=pd.Timestamp("2026-04-01", tz="UTC"),
                spot=spot,
                gex_total=1e8,
                history_vals=[1e7, 2e7, 3e7, 4e7, 5e7, 6e7, 7e7],
                gamma_flip=spot,
                # 100% of |GEX| sits exactly at spot — must collapse to 1.0.
                gex_by_strike={spot: 1e9},
            )
        ]
    )
    out = add_gex_features(df)
    assert out["gex_wall_density_pct"].iloc[0] == pytest.approx(1.0)


def test_wall_density_zero_when_mass_far_from_spot():
    spot = 500.0
    df = pd.DataFrame(
        [
            _row(
                ts=pd.Timestamp("2026-04-01", tz="UTC"),
                spot=spot,
                gex_total=1e8,
                history_vals=[1e7, 2e7, 3e7, 4e7, 5e7, 6e7, 7e7],
                gamma_flip=spot,
                # Mass sits at ±10% — well outside the ±1% band → 0.0.
                gex_by_strike={spot * 0.9: 1e9, spot * 1.1: 1e9},
            )
        ]
    )
    out = add_gex_features(df)
    assert out["gex_wall_density_pct"].iloc[0] == pytest.approx(0.0)


# ────────────────────────────────────────────────────────────────────────────
# 10. Herfindahl sanity
# ────────────────────────────────────────────────────────────────────────────


def test_herfindahl_equal_distribution_equals_1_over_n():
    n = 5
    spot = 500.0
    df = pd.DataFrame(
        [
            _row(
                ts=pd.Timestamp("2026-04-01", tz="UTC"),
                spot=spot,
                gex_total=1e8,
                history_vals=[1e7, 2e7, 3e7, 4e7, 5e7, 6e7, 7e7],
                gamma_flip=spot,
                gex_by_strike={spot + k: 1e8 for k in range(n)},
            )
        ]
    )
    out = add_gex_features(df)
    assert out["gex_herfindahl"].iloc[0] == pytest.approx(1.0 / n)


def test_herfindahl_full_concentration_equals_one():
    df = pd.DataFrame(
        [
            _row(
                ts=pd.Timestamp("2026-04-01", tz="UTC"),
                spot=500.0,
                gex_total=1e8,
                history_vals=[1e7, 2e7, 3e7, 4e7, 5e7, 6e7, 7e7],
                gamma_flip=500.0,
                gex_by_strike={500.0: 1e9},
            )
        ]
    )
    out = add_gex_features(df)
    assert out["gex_herfindahl"].iloc[0] == pytest.approx(1.0)


# ────────────────────────────────────────────────────────────────────────────
# 11. Bonus — non-mutation
# ────────────────────────────────────────────────────────────────────────────


def test_input_dataframe_not_mutated():
    df = _happy_df(20)
    cols_before = list(df.columns)
    snapshot = df.copy(deep=True)
    _ = add_gex_features(df)
    # No new columns added to input.
    assert list(df.columns) == cols_before
    # Input contents identical.
    pd.testing.assert_frame_equal(df, snapshot)


# ────────────────────────────────────────────────────────────────────────────
# 12. Bonus — output column count is stable across calls
# ────────────────────────────────────────────────────────────────────────────


def test_output_column_set_matches_constant():
    df = _happy_df(5)
    out = add_gex_features(df)
    assert set(GEX_FEATURE_OUTPUT_COLS).issubset(set(out.columns))


def test_missing_required_column_raises_keyerror():
    df = _happy_df(3).drop(columns=["gex_total"])
    with pytest.raises(KeyError, match="gex_total"):
        add_gex_features(df)
