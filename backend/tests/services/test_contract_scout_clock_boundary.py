"""Quote event clocks must not fabricate fresh read-only scout candidates."""

from datetime import UTC, datetime, timedelta

import pytest

from services.contract_scout import _age_s, scout_candidates, scout_shortlist_rows
from tests.offline_network import deny_external_network  # noqa: F401

NOW = datetime(2030, 1, 2, 14, tzinfo=UTC)


def _contract(**changes):
    row = {"osi": "CLOCK", "type": "put", "strike": 500, "expiry": "2030-01-02",
           "bid": 1.0, "ask": 1.2, "delta": -0.5, "volume": 500, "T": 0.5 / 365,
           "bid_timestamp": NOW.isoformat(), "ask_timestamp": NOW.isoformat()}
    return row | changes


def _scout(row, strict=True):
    return scout_candidates([row], "PUTS", 500, now_s=NOW.timestamp(),
                            session_date="2030-01-02" if strict else None)


@pytest.mark.parametrize("strict", [True, False])
@pytest.mark.parametrize("side", ["bid", "ask"])
@pytest.mark.parametrize("ahead", [0.001, 1, 86400])
def test_future_quote_side_never_ranks(side, ahead, strict):
    future = (NOW + timedelta(seconds=ahead)).isoformat()
    result = _scout(_contract(**{f"{side}_timestamp": future}), strict)
    assert result["n_eligible"] == 0, result
    assert result["rejected"] == {f"FUTURE_{side.upper()}_TIMESTAMP": 1}
    assert scout_shortlist_rows(result, "PUTS") == []


@pytest.mark.parametrize("ask_ahead", [1, 60])
def test_two_future_clocks_do_not_collapse_to_zero_age(ask_ahead):
    result = _scout(_contract(bid_timestamp=(NOW + timedelta(seconds=1)).isoformat(),
                              ask_timestamp=(NOW + timedelta(seconds=ask_ahead)).isoformat()))
    assert result["n_eligible"] == 0, result
    assert result["rejected"] == {"FUTURE_BID_TIMESTAMP": 1}


@pytest.mark.parametrize("side", ["bid", "ask"])
def test_invalid_clock_is_distinct_from_missing_clock(side):
    missing = _scout(_contract(**{f"{side}_timestamp": None}))
    invalid = _scout(_contract(**{f"{side}_timestamp": "not-a-clock"}))
    assert missing["n_eligible"] == invalid["n_eligible"] == 0
    # Preserve existing strict missing-time rejection compatibility.
    assert missing["rejected"] == {f"STALE_{side.upper()}": 1}
    assert invalid["rejected"] == {f"INVALID_{side.upper()}_TIMESTAMP": 1}


def test_age_preserves_signed_future_offset():
    assert _age_s((NOW + timedelta(seconds=60)).isoformat(), NOW.timestamp()) == -60
    assert _age_s(None, NOW.timestamp()) is None
    assert _age_s("not-a-clock", NOW.timestamp()) is None


@pytest.mark.parametrize("age", [0, 30])
def test_measured_fresh_and_stale_boundary_controls(age):
    timestamp = (NOW - timedelta(seconds=age)).isoformat()
    result = _scout(_contract(bid_timestamp=timestamp, ask_timestamp=timestamp))
    assert result["n_eligible"] == 1
    assert result["rejected"] == {}


def test_ordinary_stale_and_skew_controls_remain_rejected():
    stale = (NOW - timedelta(seconds=31)).isoformat()
    skewed = (NOW - timedelta(seconds=6)).isoformat()
    assert _scout(_contract(bid_timestamp=stale))["rejected"] == {"STALE_BID": 1}
    assert _scout(_contract(ask_timestamp=skewed))["rejected"] == {"STALE_ASK": 1}


def test_legacy_missing_timestamps_remain_allowed_only_in_fixture_mode():
    result = _scout(_contract(bid_timestamp=None, ask_timestamp=None), strict=False)
    assert result["n_eligible"] == 1
