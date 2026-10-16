"""Regression checks from independent historical payload review."""
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from services import conviction_rank as rank
from services import meta_observability as monitoring
from services import observability


def test_provider_age_updates_every_provider_including_never_succeeded(monkeypatch):
    age, rate = Mock(), Mock()
    monkeypatch.setattr(observability, "provider_last_success_seconds_ago", age)
    monkeypatch.setattr(observability, "provider_success_rate", rate)
    monitor = monitoring.DataProviderMonitor()
    monitor._providers = {
        "first": SimpleNamespace(success_rate=0.8, seconds_since_last_success=12.5),
        "never": SimpleNamespace(success_rate=0.0, seconds_since_last_success=None),
        "last": SimpleNamespace(success_rate=1.0, seconds_since_last_success=0.0),
    }
    monitor.update_prometheus()
    assert age.mock_calls == [
        call.labels(provider="first"), call.labels().set(12.5),
        call.labels(provider="never"), call.labels().set(float("inf")),
        call.labels(provider="last"), call.labels().set(0.0),
    ]
    assert rate.labels.call_count == 3


def test_empty_provider_monitor_has_no_swallowed_unbound_local(monkeypatch):
    debug = Mock()
    monkeypatch.setattr(monitoring.log, "debug", debug)
    monitoring.DataProviderMonitor().update_prometheus()
    debug.assert_not_called()


@pytest.mark.parametrize("opportunity", [None, {}, {"opportunity_score": None}, {"regime": "unknown"}])
def test_opportunity_absence_is_missing_not_a_measured_zero(opportunity):
    row = rank.rank_one("SPY", opportunity=opportunity)
    assert row["evidence"]["opportunity_status"] == "missing"
    assert row["evidence"]["components"]["opportunity"] == 0


@pytest.mark.parametrize("opportunity", [True, False, float("nan"), float("inf"), float("-inf"), "nan", "", [], {}])
def test_malformed_opportunity_measurement_is_not_ok(opportunity):
    assert rank._norm_opp({"opportunity_score": opportunity}) == (0.0, "invalid")


@pytest.mark.parametrize("score,expected", [(0, 0), ("0", 0), (5, 0.5), ("5", 0.5), (10, 1)])
def test_measured_opportunity_values_keep_existing_units(score, expected):
    assert rank._norm_opp({"opportunity_score": score}) == (expected, "ok")


@pytest.mark.parametrize("normalizer", [rank._norm_flow, rank._norm_conf])
@pytest.mark.parametrize("raw", [True, False, float("nan"), float("inf"), float("-inf"), "nan", "", []])
def test_sibling_scorers_do_not_label_malformed_numbers_ok(normalizer, raw):
    assert normalizer(raw) == (0.0, "invalid")


@pytest.mark.parametrize("confidence", [True, False, float("nan"), float("inf"), "nan", [], {}])
def test_model_confidence_must_be_a_real_measurement(confidence):
    assert rank._norm_ml({"prediction": "BULLISH", "confidence": confidence}) == (0.0, "invalid")


def test_explicit_zero_model_confidence_is_not_replaced_with_default():
    # Independent formula from existing documented magnitude weighting:
    # abs(UP - neutral) * (0.5 + 0.5 * confidence) = 0.5 * 0.5.
    assert rank._norm_ml({"prediction": "BULLISH", "confidence": 0}) == (0.25, "ok")
