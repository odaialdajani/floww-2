"""Institutional evaluation harness primitives (RESEARCH-EVAL-1).

RED contract: no shared walk-forward primitive exists, so every research
note rolls its own splits — purge/embargo discipline is unenforceable and
costs are optional. This module provides deterministic walk-forward splits
with purge and embargo gaps, costed scoring, benchmark deltas, and a
failed-hypothesis registry. Synthetic fixtures only; no alpha claim, no
model or threshold change.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.eval_harness import (  # noqa: E402
    FailedHypothesisRegistry,
    compare_against_baseline,
    costed_hit_rate,
    walk_forward_splits,
)


class TestWalkForwardSplits:
    def test_purge_and_embargo_gaps_hold(self):
        splits = walk_forward_splits(n=100, train_size=50, test_size=10,
                                     purge=5, embargo=2)
        assert len(splits) >= 2
        for train, test in splits:
            assert max(train) + 1 + 5 <= min(test)
        for (_t1, test1), (_t2, test2) in zip(splits, splits[1:], strict=False):
            assert max(test1) + 1 + 2 <= min(test2)

    def test_no_train_test_overlap(self):
        for train, test in walk_forward_splits(n=60, train_size=30,
                                               test_size=10, purge=3, embargo=1):
            assert set(train).isdisjoint(test)

    def test_deterministic(self):
        a = walk_forward_splits(n=80, train_size=40, test_size=10, purge=2, embargo=1)
        b = walk_forward_splits(n=80, train_size=40, test_size=10, purge=2, embargo=1)
        assert a == b

    def test_zero_gaps_still_split(self):
        splits = walk_forward_splits(n=30, train_size=10, test_size=5,
                                     purge=0, embargo=0)
        assert splits
        for train, test in splits:
            assert max(train) < min(test)

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            walk_forward_splits(n=10, train_size=0, test_size=5)
        with pytest.raises(ValueError):
            walk_forward_splits(n=10, train_size=5, test_size=5, purge=-1)


class TestCostedScoring:
    def test_costed_hit_rate_hand_computed(self):
        """10 calls, 6 right at +2.0, 4 wrong at -1.0, cost 0.5 each.

        Gross = 6*2 - 4*1 = 8. Net = 8 - 10*0.5 = 3. Net hit value = 3/10.
        """
        preds = [1]*6 + [0]*4
        actual = [1]*6 + [1]*4
        assert costed_hit_rate(preds, actual, win=2.0, loss=1.0, cost=0.5) == pytest.approx(0.3)

    def test_costs_can_erase_edge(self):
        preds = [1, 1, 0, 0]
        actual = [1, 0, 0, 1]
        gross = costed_hit_rate(preds, actual, win=1.0, loss=1.0, cost=0.0)
        net = costed_hit_rate(preds, actual, win=1.0, loss=1.0, cost=1.0)
        assert gross == pytest.approx(0.0)
        assert net == pytest.approx(-1.0)


class TestBenchmarkAndRegistry:
    def test_delta_sign_and_samples(self):
        out = compare_against_baseline(candidate=0.06, baseline=0.02,
                                       n_candidate=200, n_baseline=200)
        assert out["delta"] == pytest.approx(0.04)
        assert out["winner"] == "candidate"
        assert out["n_candidate"] == 200

    def test_registry_records_failures(self):
        reg = FailedHypothesisRegistry()
        reg.record(name="mom-5d", hypothesis="5d momentum predicts 1d fwd",
                   metric=-0.01, reason="net of costs, delta negative vs baseline")
        failed = reg.list_failed()
        assert len(failed) == 1
        assert failed[0]["name"] == "mom-5d"
        assert "costs" in failed[0]["reason"]

class TestPointInTimeIntegration:
    """Integration between eval_harness and event_envelope (PR59 + PR60).

    Defect (RED): costed_hit_rate scores all rows including those with
    missing_event_time. No point-in-time gate existed between the two modules.
    Fix: pit_filter + costed_hit_rate_enveloped filter before scoring.
    """

    def test_pit_filter_excludes_missing_event_time(self):
        from services.eval_harness import pit_filter
        from services.event_envelope import is_point_in_time_complete, normalize_event

        complete = normalize_event({
            "source": "s", "symbol": "SPY",
            "event_time": "2026-09-09T14:30:00",
            "receive_time": "2026-09-09T14:30:01",
            "prediction": 1, "actual": 1,
        })
        incomplete = normalize_event({
            "source": "s", "symbol": "SPY",
            "event_time": None,
            "receive_time": "2026-09-09T14:30:01",
            "prediction": 0, "actual": 1,
        })

        preds, actuals = pit_filter([complete, incomplete])
        assert len(preds) == 1
        assert preds[0] == 1
        assert actuals[0] == 1
        assert is_point_in_time_complete(complete)
        assert not is_point_in_time_complete(incomplete)

    def test_costed_hit_rate_enveloped_filters_before_scoring(self):
        from services.eval_harness import costed_hit_rate_enveloped
        from services.event_envelope import normalize_event

        complete = normalize_event({
            "source": "s", "symbol": "SPY",
            "event_time": "2026-09-09T14:30:00",
            "receive_time": "2026-09-09T14:30:01",
            "prediction": 1, "actual": 1,
        })
        incomplete = normalize_event({
            "source": "s", "symbol": "SPY",
            "event_time": None,
            "receive_time": "2026-09-09T14:30:01",
            "prediction": 0, "actual": 1,
        })

        # With filtering: only the complete correct call scores
        score = costed_hit_rate_enveloped([complete, incomplete],
                                          win=1.0, loss=1.0, cost=0.0)
        assert score == pytest.approx(1.0)

    def test_costed_hit_rate_enveloped_empty_when_all_incomplete(self):
        from services.eval_harness import costed_hit_rate_enveloped
        from services.event_envelope import normalize_event

        rows = [
            normalize_event({"source": "s", "symbol": "SPY",
                             "event_time": None, "prediction": 1, "actual": 1}),
            normalize_event({"source": "s", "symbol": "SPY",
                             "event_time": None, "prediction": 0, "actual": 1}),
        ]
        score = costed_hit_rate_enveloped(rows, win=1.0, loss=1.0, cost=0.0)
        assert score == pytest.approx(0.0)

    def test_raw_costed_hit_rate_scores_all_rows_including_incomplete(self):
        """Document the defect: unfiltered costed_hit_rate has no PIT gate.

        This is the behavior that pit_filter + costed_hit_rate_enveloped fix.
        """
        from services.eval_harness import costed_hit_rate
        from services.event_envelope import normalize_event

        complete = normalize_event({
            "source": "s", "symbol": "SPY",
            "event_time": "2026-09-09T14:30:00",
            "receive_time": "2026-09-09T14:30:01",
            "prediction": 1, "actual": 1,
        })
        incomplete = normalize_event({
            "source": "s", "symbol": "SPY",
            "event_time": None,
            "receive_time": "2026-09-09T14:30:01",
            "prediction": 0, "actual": 1,
        })

        # Raw costed_hit_rate scores BOTH rows (defect)
        preds = [complete["payload"]["prediction"], incomplete["payload"]["prediction"]]
        actuals = [complete["payload"]["actual"], incomplete["payload"]["actual"]]
        score = costed_hit_rate(preds, actuals, win=1.0, loss=1.0, cost=0.0)
        assert score == pytest.approx(0.0)  # (1 - 1) / 2 = 0 — both scored
