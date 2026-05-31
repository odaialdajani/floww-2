"""ML promotion gate — decides whether a trained model can be SHIPPED.

Extracted from ``scripts/train_spy_model.py`` (2026-05-18) after
``reports/multiticker_model_audit.md`` identified three compounding bugs in the
inline gate that made it accept every model:

  - **Bug A** (length check): ``if len(preds) == len(y)`` could never be true.
    Baseline predictions accumulate over *test folds* (~n_splits × test_size),
    not the full dataset length. The check evaluated False, so
    ``baseline_metrics`` was always ``{}``.
  - **Bug B** (wrong y slice): ``y[:len(preds_arr)]`` compared baseline
    test-fold predictions to the *first N elements of y* — which is the
    train slice, not the test-fold actuals.
  - **Bug C** (unsafe default): ``baseline_metrics.get(b, {}).get("sharpe", -999)``
    returned -999 for every missing baseline. ``sharpe > -999`` was always
    true, so any model passed. That's how TLT v1.0 shipped with Sharpe 0.00.

Plus a structural gap (no Sharpe sanity cap) that let SPY v1.0 ship with
Sharpe 31.5 — a textbook in-sample artifact.

This module fixes all four. Each rejection mode has a unit test in
``backend/tests/services/ml/test_gate.py``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np

DEFAULT_MAX_SHARPE: float = 10.0
"""Above this Sharpe, daily-direction predictions are presumed in-sample fit.

Real daily-direction strategies almost never sustain Sharpe above ~3 OOS over
multi-year windows. A value above 10 with our sample sizes is overwhelmingly
an in-sample artifact, leakage, or a measurement error — automatic reject
regardless of whether the model "beats baselines."
"""

DEFAULT_REQUIRED_BASELINES: Tuple[str, ...] = ("majority", "persistence", "logistic")
"""Every model must beat all three on Sharpe to be eligible for SHIP."""


def compute_trading_sharpe(predictions: List[int], actuals: List[int]) -> float:
    """Annualized Sharpe of a simple long-only-on-positive-prediction strategy.

    Trade only when ``pred == 1``. Win = +1 if actual == 1, else -1.
    Flat predictions (``pred == 0`` or any other value) are skipped — they do
    not contribute returns or trades.

    Returns 0.0 if fewer than 2 trades fire (Sharpe is undefined).
    """
    rets: List[float] = []
    for pred, actual in zip(predictions, actuals):
        if pred == 1:
            rets.append(1.0 if actual == 1 else -1.0)
    if len(rets) < 2:
        return 0.0
    return float(np.mean(rets) / (np.std(rets) + 1e-8) * np.sqrt(252))


def evaluate_baselines(
    baseline_preds: Dict[str, List[int]],
    test_actuals: List[int],
) -> Dict[str, Dict[str, float]]:
    """Compute per-baseline ``{accuracy, sharpe}`` against test-fold actuals.

    ``baseline_preds`` keys are baseline names (e.g. ``"majority"``); values
    are the per-baseline predictions concatenated across test folds, in the
    same fold order as ``test_actuals``.

    Length-mismatched or empty entries are silently omitted (the caller can
    detect this by comparing input vs output keys).
    """
    actuals_arr = np.array(test_actuals)
    metrics: Dict[str, Dict[str, float]] = {}
    for name, preds in baseline_preds.items():
        if not preds or len(preds) != len(actuals_arr):
            continue
        preds_arr = np.array(preds[: len(actuals_arr)])
        acc = float(np.mean(preds_arr == actuals_arr))
        sharpe = compute_trading_sharpe(preds_arr.tolist(), test_actuals)
        metrics[name] = {"accuracy": acc, "sharpe": sharpe}
    return metrics


def evaluate_ship_verdict(
    model_results: Dict[str, Dict[str, Any]],
    baseline_metrics: Dict[str, Dict[str, float]],
    max_sharpe: float = DEFAULT_MAX_SHARPE,
    required_baselines: Tuple[str, ...] = DEFAULT_REQUIRED_BASELINES,
) -> Optional[str]:
    """Decide which (if any) model passes the SHIP gate.

    Side effect: mutates each ``model_results[k]`` dict to set
    ``beats_baselines`` (bool) and, on rejection, ``rejection_reason`` (str)
    so the caller can serialize the gate outcome into the training report.

    Returns the name of the best SHIP-eligible model, or ``None``.

    Gate criteria (all must hold for SHIP):

      1. ``model_results[k]["status"] == "ok"``
      2. ``model_results[k]["sharpe"] <= max_sharpe`` (sanity cap)
      3. every name in ``required_baselines`` is a key in ``baseline_metrics``
      4. ``model_results[k]["sharpe"]`` strictly exceeds every required
         baseline's Sharpe

    Among models passing all four, the one with highest Sharpe wins.
    """
    best_model: Optional[str] = None
    best_sharpe = -np.inf

    for model_type, result in model_results.items():
        if result.get("status") != "ok":
            continue
        sharpe = result.get("sharpe", -np.inf)

        # 2. Sanity cap on Sharpe — reject implausible values regardless of baselines.
        if sharpe > max_sharpe:
            result["beats_baselines"] = False
            result["rejection_reason"] = (
                f"sharpe {sharpe:.2f} > MAX_PLAUSIBLE_DAILY_SHARPE "
                f"({max_sharpe}); likely in-sample or measurement artifact"
            )
            continue

        # 3. All required baselines present (fail-closed on missing).
        missing = [b for b in required_baselines if b not in baseline_metrics]
        if missing:
            result["beats_baselines"] = False
            result["rejection_reason"] = f"missing baselines: {missing}"
            continue

        # 4. Beat every required baseline on Sharpe.
        beats_all = all(
            sharpe > baseline_metrics[b]["sharpe"]
            for b in required_baselines
        )
        result["beats_baselines"] = beats_all
        if not beats_all:
            result["rejection_reason"] = (
                "did not beat all of "
                + ", ".join(
                    f"{b}({baseline_metrics[b]['sharpe']:.2f})"
                    for b in required_baselines
                )
            )
        elif sharpe > best_sharpe:
            best_sharpe = sharpe
            best_model = model_type

    return best_model
