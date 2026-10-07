from datetime import UTC, datetime

import pytest

from services.agent.access.horizon import _calendar
from services.related_correlations import compare_series

NOW = datetime(2026, 10, 7, 12, tzinfo=UTC)


def series(symbol, returns=None, n=31):
    days = [day.date().isoformat() for day in _calendar().sessions_window("2026-10-06", -n)]
    values = [100.0]
    returns = returns if returns is not None else [(0.01 if i % 2 else -0.005) + i * 0.00005 for i in range(n - 1)]
    for change in returns:
        values.append(values[-1] * (1 + change))
    return {
        "ticker": symbol,
        "bars": [{"date": day, "close": value} for day, value in zip(days, values, strict=True)],
        "event_time": "2026-10-06T20:00:00+00:00",
        "received_at": "2026-10-07T12:00:00+00:00",
        "price_basis": "provider_reported",
        "adjustment_policy": "unknown",
    }


@pytest.mark.parametrize("scale,expected", [(2, 1), (-0.5, -1)])
def test_returns_not_price_levels_define_positive_and_inverse_comparisons(scale, expected):
    changes = [(0.01 if i % 2 else -0.006) + i * 0.00005 for i in range(30)]
    result = compare_series(series("AAA", changes), series("BBB", [r * scale for r in changes]), window=30, now=NOW)
    assert result["coefficient"] == pytest.approx(expected, abs=1e-12)
    assert result["paired_returns"] == 30 and result["requested_returns"] == 30
    assert result["start_date"] == series("AAA")["bars"][0]["date"]
    assert result["end_date"] == "2026-10-06"


def test_exact_previous_and_current_session_intervals_never_bridge_a_missing_close():
    left, right = series("AAA"), series("BBB")
    right["bars"].pop(10)
    result = compare_series(left, right, window=30, now=NOW)
    assert result["paired_returns"] == 28
    assert result["partial"] is True
    assert result["coefficient"] == pytest.approx(1)


def test_short_new_listing_is_partial_not_a_claim_of_ninety_returns():
    result = compare_series(series("AAA", n=21), series("BBB", n=21), window=90, now=NOW)
    assert result["paired_returns"] == 20 and result["requested_returns"] == 90
    assert result["partial"] is True and result["coefficient"] == pytest.approx(1)


@pytest.mark.parametrize("n", [1, 2, 20])
def test_less_than_twenty_paired_returns_is_unknown_not_zero(n):
    result = compare_series(series("AAA", n=n), series("BBB", n=n), window=30, now=NOW)
    assert result["coefficient"] is None and result["reason"] == "insufficient_paired_returns"


def test_zero_variance_is_unknown_and_true_zero_correlation_is_distinct():
    result = compare_series(series("AAA", [0] * 30), series("BBB"), window=30, now=NOW)
    assert result["coefficient"] is None and result["reason"] == "zero_variance"
    x = [0.01, -0.01, 0.01, -0.01] * 5
    y = [0.01, 0.01, -0.01, -0.01] * 5
    result = compare_series(series("AAA", x, n=21), series("BBB", y, n=21), window=30, now=NOW)
    assert abs(result["coefficient"]) < 1e-12 and result["paired_returns"] == 20


def test_stale_and_failed_latest_read_keep_the_original_series_clocks():
    left, right = series("AAA"), series("BBB")
    right["bars"].pop()
    right["event_time"] = "2026-10-05T20:00:00+00:00"
    right["received_at"] = "2026-10-05T21:00:00+00:00"
    right["latest_fetch"] = {
        "status": "failed",
        "attempted_at": "2026-10-07T12:00:00+00:00",
        "reason": "provider_read_failed",
    }
    result = compare_series(left, right, window=30, now=NOW)
    assert result["stale"] is True and result["paired_returns"] == 29
    assert result["comparison_clock"]["received_at"] == right["received_at"]
    assert result["comparison_clock"]["latest_fetch"]["status"] == "failed"
    assert result["adjustment_policy"] == "unknown" and result["split_dividend_flag"] == "unverified"
