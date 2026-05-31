"""
backend/tests/services/ml/test_gate.py

Unit tests for services.ml.gate — the SHIP gate that decides whether a trained
model is good enough to deploy.

Each test pins a rejection path that was previously broken. See the docstring
of services/ml/gate.py for the bug history.
"""

import sys
from pathlib import Path
from typing import Any, Dict

import pytest

# Add backend/ to path so `services.ml.gate` is importable regardless of CWD.
# __file__ = backend/tests/services/ml/test_gate.py; parents[3] = backend/.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from services.ml.gate import (
    DEFAULT_MAX_SHARPE,
    compute_trading_sharpe,
    evaluate_baselines,
    evaluate_ship_verdict,
)

# ────────────────────────────────────────────────────────────────────────────
# compute_trading_sharpe
# ────────────────────────────────────────────────────────────────────────────

def test_sharpe_returns_float():
    s = compute_trading_sharpe([1, 1, 1, 1, 1], [1, 0, 1, 0, 1])
    assert isinstance(s, float)


def test_sharpe_zero_when_no_trades_fire():
    """Pred=0 means no trade; need ≥ 2 trades for a Sharpe."""
    assert compute_trading_sharpe([0, 0, 0, 0, 0], [1, 1, 1, 1, 1]) == 0.0


def test_sharpe_zero_on_single_trade():
    # Only one pred fires; can't compute std → returns 0
    assert compute_trading_sharpe([1, 0, 0, 0, 0], [1, 1, 1, 1, 1]) == 0.0


def test_sharpe_positive_for_winning_strategy():
    # Mostly winning trades with some variance
    preds = [1] * 20
    actuals = [1] * 16 + [0] * 4  # 80% wins
    s = compute_trading_sharpe(preds, actuals)
    assert s > 5.0  # 80% hit rate at +1/-1 is a strong Sharpe


def test_sharpe_negative_for_losing_strategy():
    preds = [1] * 20
    actuals = [0] * 16 + [1] * 4  # 80% losses
    s = compute_trading_sharpe(preds, actuals)
    assert s < -5.0


def test_sharpe_near_zero_for_random_strategy():
    # Alternating wins and losses → mean return 0 → Sharpe ~ 0
    preds = [1] * 20
    actuals = [1, 0] * 10
    s = compute_trading_sharpe(preds, actuals)
    assert abs(s) < 2.0  # noisy but small


# ────────────────────────────────────────────────────────────────────────────
# evaluate_baselines
# ────────────────────────────────────────────────────────────────────────────

def test_baselines_correct_slicing_against_test_actuals():
    """Bug A + B (now fixed): baselines must be compared to test_actuals, not
    to a wrong slice of the full dataset.
    """
    test_actuals = [1, 0, 1, 0, 1, 0]
    baseline_preds = {
        "majority": [1, 1, 1, 1, 1, 1],          # accuracy = 3/6 = 0.5
        "persistence": [0, 1, 0, 1, 0, 1],       # exactly inverse → 0.0
        "logistic": [1, 0, 1, 0, 1, 0],          # perfect → 1.0
    }
    metrics = evaluate_baselines(baseline_preds, test_actuals)
    assert set(metrics.keys()) == {"majority", "persistence", "logistic"}
    assert metrics["majority"]["accuracy"] == pytest.approx(0.5)
    assert metrics["persistence"]["accuracy"] == pytest.approx(0.0)
    assert metrics["logistic"]["accuracy"] == pytest.approx(1.0)


def test_baselines_length_mismatch_silently_omitted():
    """A baseline whose preds don't match test_actuals length is omitted with no
    crash. The caller can detect this by diffing keys.
    """
    test_actuals = [1, 0, 1, 0]
    baseline_preds = {
        "majority": [1, 1, 1, 1],     # ok
        "too_short": [1, 1],          # wrong length → omitted
        "empty": [],                  # empty → omitted
    }
    metrics = evaluate_baselines(baseline_preds, test_actuals)
    assert "majority" in metrics
    assert "too_short" not in metrics
    assert "empty" not in metrics


def test_baselines_empty_when_input_empty():
    assert evaluate_baselines({}, [1, 0, 1]) == {}


# ────────────────────────────────────────────────────────────────────────────
# evaluate_ship_verdict
# ────────────────────────────────────────────────────────────────────────────

def _good_baselines() -> Dict[str, Dict[str, float]]:
    """Realistic baseline metrics — a passing model has Sharpe above these."""
    return {
        "majority":    {"accuracy": 0.50, "sharpe": 0.50},
        "persistence": {"accuracy": 0.50, "sharpe": 0.30},
        "logistic":    {"accuracy": 0.50, "sharpe": 0.70},
    }


def test_verdict_rejects_implausible_sharpe():
    """SPY v1.0 had Sharpe 31.5 (in-sample). The sanity cap must reject it
    regardless of whether it beats baselines.
    """
    results: Dict[str, Dict[str, Any]] = {
        "lightgbm": {"status": "ok", "sharpe": 31.5},
    }
    best = evaluate_ship_verdict(results, _good_baselines())
    assert best is None
    assert results["lightgbm"]["beats_baselines"] is False
    assert "MAX_PLAUSIBLE_DAILY_SHARPE" in results["lightgbm"]["rejection_reason"]


def test_verdict_rejects_at_default_cap_boundary():
    """Exactly at the cap is allowed (the comparison is `>`, not `>=`)."""
    results = {
        "exactly_cap": {"status": "ok", "sharpe": DEFAULT_MAX_SHARPE},
        "above_cap":   {"status": "ok", "sharpe": DEFAULT_MAX_SHARPE + 0.01},
    }
    evaluate_ship_verdict(results, _good_baselines())
    assert results["exactly_cap"]["beats_baselines"] is True
    assert results["above_cap"]["beats_baselines"] is False


def test_verdict_rejects_zero_edge_when_baselines_present():
    """TLT v1.0 shipped with Sharpe 0.00 because the old gate defaulted missing
    baselines to -999. With real baselines present, Sharpe 0 must fail.
    """
    results = {"lightgbm": {"status": "ok", "sharpe": 0.0}}
    best = evaluate_ship_verdict(results, _good_baselines())
    assert best is None
    assert results["lightgbm"]["beats_baselines"] is False
    assert "did not beat" in results["lightgbm"]["rejection_reason"]


def test_verdict_fails_closed_on_missing_baselines():
    """When baseline_metrics is empty (Bug A: prior gate always produced this
    empty dict), the gate must REJECT, not auto-accept.
    """
    results = {"lightgbm": {"status": "ok", "sharpe": 5.0}}
    best = evaluate_ship_verdict(results, baseline_metrics={})
    assert best is None
    assert results["lightgbm"]["beats_baselines"] is False
    assert "missing baselines" in results["lightgbm"]["rejection_reason"]


def test_verdict_fails_closed_on_partial_baselines():
    """One required baseline missing → reject. No partial credit."""
    partial = {"majority": {"accuracy": 0.5, "sharpe": 0.5}}  # missing 2 of 3
    results = {"lightgbm": {"status": "ok", "sharpe": 5.0}}
    best = evaluate_ship_verdict(results, partial)
    assert best is None
    assert results["lightgbm"]["beats_baselines"] is False


def test_verdict_accepts_plausible_model():
    results = {"lightgbm": {"status": "ok", "sharpe": 2.5}}
    best = evaluate_ship_verdict(results, _good_baselines())
    assert best == "lightgbm"
    assert results["lightgbm"]["beats_baselines"] is True
    assert results["lightgbm"].get("rejection_reason") is None


def test_verdict_picks_highest_sharpe_among_passing():
    results = {
        "xgboost":  {"status": "ok", "sharpe": 1.5},
        "lightgbm": {"status": "ok", "sharpe": 2.5},
    }
    best = evaluate_ship_verdict(results, _good_baselines())
    assert best == "lightgbm"
    assert results["xgboost"]["beats_baselines"] is True
    assert results["lightgbm"]["beats_baselines"] is True


def test_verdict_skips_failed_status():
    results = {
        "xgboost":  {"status": "error", "sharpe": 999.0},   # status != ok → skipped
        "lightgbm": {"status": "ok", "sharpe": 2.5},
    }
    best = evaluate_ship_verdict(results, _good_baselines())
    assert best == "lightgbm"
    # xgboost is not mutated because its status was not "ok"
    assert "beats_baselines" not in results["xgboost"]


def test_verdict_no_candidates_returns_none():
    results: Dict[str, Dict[str, Any]] = {}
    assert evaluate_ship_verdict(results, _good_baselines()) is None


def test_verdict_respects_custom_max_sharpe():
    """Caller can tighten the cap (e.g. require Sharpe ≤ 3 for stricter envs)."""
    results = {"lightgbm": {"status": "ok", "sharpe": 5.0}}
    # Default would accept; with max_sharpe=3 it must reject.
    best = evaluate_ship_verdict(results, _good_baselines(), max_sharpe=3.0)
    assert best is None
    assert "MAX_PLAUSIBLE_DAILY_SHARPE" in results["lightgbm"]["rejection_reason"]


def test_verdict_respects_custom_required_baselines():
    """Caller can require a different baseline set."""
    results = {"lightgbm": {"status": "ok", "sharpe": 2.5}}
    # Pass only one baseline that is in the required tuple.
    partial = {"only_baseline": {"accuracy": 0.5, "sharpe": 0.5}}
    best = evaluate_ship_verdict(
        results, partial, required_baselines=("only_baseline",)
    )
    assert best == "lightgbm"
    assert results["lightgbm"]["beats_baselines"] is True
