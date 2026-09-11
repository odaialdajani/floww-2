"""Institutional evaluation primitives: walk-forward splits, costed scoring.

Walk-forward splits enforce purge (gap between train end and test start)
and embargo (gap after each test block) so label overlap cannot leak the
future into training. Scoring is always net of per-decision costs.
Benchmark comparison reports deltas with sample sizes — never a bare
win-rate. Failed hypotheses belong in FailedHypothesisRegistry, not in
a drawer. Synthetic use only; no alpha claim.
"""
from __future__ import annotations

from typing import Any


def walk_forward_splits(n: int, train_size: int, test_size: int,
                        purge: int = 0, embargo: int = 0
                        ) -> list[tuple[list[int], list[int]]]:
    """Deterministic walk-forward (train, test) index splits.

    Walk starts at 0; each block advances by test_size + embargo.
    Train block is [start, start+train); test block starts after purge.
    Blocks that would overrun n are dropped.
    """
    for name, value in (("train_size", train_size), ("test_size", test_size)):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise ValueError(f"{name} must be a positive int")
    for name, value in (("purge", purge), ("embargo", embargo), ("n", n)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{name} must be a non-negative int")
    splits: list[tuple[list[int], list[int]]] = []
    start = 0
    while True:
        train_end = start + train_size
        test_start = train_end + purge
        test_end = test_start + test_size
        if test_end > n:
            break
        splits.append((list(range(start, train_end)),
                       list(range(test_start, test_end))))
        start += test_size + embargo
    return splits


def costed_hit_rate(predictions: list[int], actuals: list[int],
                    *, win: float = 1.0, loss: float = 1.0,
                    cost: float = 0.0) -> float:
    """Mean per-decision P&L net of costs. Correct call earns win, miss loses
    loss, every decision pays cost (spread + slippage + fees)."""
    if len(predictions) != len(actuals) or not predictions:
        raise ValueError("predictions and actuals must be non-empty and aligned")
    total = 0.0
    for pred, actual in zip(predictions, actuals, strict=True):
        total += (win if pred == actual else -loss) - cost
    return total / len(predictions)


def compare_against_baseline(*, candidate: float, baseline: float,
                             n_candidate: int, n_baseline: int) -> dict[str, Any]:
    """Report a benchmark delta with its sample sizes.

    Deliberately significance-free: a delta without uncertainty is a
    measurement, not a verdict. Callers must supply out-of-sample,
    costed metrics on both sides.
    """
    return {
        "delta": candidate - baseline,
        "winner": ("candidate" if candidate > baseline
                   else "baseline" if baseline > candidate else "tie"),
        "n_candidate": n_candidate,
        "n_baseline": n_baseline,
    }


class FailedHypothesisRegistry:
    """Append-only log of rejected hypotheses with reasons."""

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    def record(self, *, name: str, hypothesis: str,
               metric: float, reason: str) -> dict[str, Any]:
        entry = {"name": name, "hypothesis": hypothesis,
                 "metric": metric, "reason": reason}
        self._entries.append(entry)
        return entry

    def list_failed(self) -> list[dict[str, Any]]:
        return list(self._entries)


def pit_filter(envelopes, pred_key="prediction", actual_key="actual"):
    """Return (predictions, actuals) from point-in-time-complete envelopes only.

    Consumers of eval_harness with event_envelope data must filter before
    scoring. Rows with missing_event_time are excluded — unknown stays unknown.
    """
    from services.event_envelope import is_point_in_time_complete  # local import

    filtered = [e for e in envelopes if is_point_in_time_complete(e)]
    preds = [e["payload"].get(pred_key) for e in filtered]
    actuals = [e["payload"].get(actual_key) for e in filtered]
    return preds, actuals


def costed_hit_rate_enveloped(envelopes, *, win=1.0, loss=1.0, cost=0.0,
                              pred_key="prediction", actual_key="actual"):
    """Score net of costs from event_envelope-wrapped rows.

    Filters to point-in-time-complete envelopes before scoring. Rows missing
    event_time are excluded; no timestamp is fabricated.

    IMPORTANT: this function is infrastructure-only. callers must opt in by
    using costed_hit_rate_enveloped rather than raw costed_hit_rate; the
    unfiltered function remains available for legacy script paths that
    supply already-validated rows.
    """
    preds, actuals = pit_filter(envelopes, pred_key=pred_key, actual_key=actual_key)
    if not preds:
        return 0.0
    return costed_hit_rate(preds, actuals, win=win, loss=loss, cost=cost)
