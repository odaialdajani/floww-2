from datetime import UTC, datetime

import pytest

from services.agent.access.horizon import _calendar
from services.related_price_series import validate_daily_payload

NOW = datetime(2026, 10, 7, 12, tzinfo=UTC)


def payload(symbol="AAA", n=31):
    days = [day.date().isoformat() for day in _calendar().sessions_window("2026-10-06", -n)]
    return {
        "symbol": symbol,
        "period": "YEAR",
        "regularMarket": {
            "bars": [
                {"date": day, "open": 100 + i, "high": 102 + i, "low": 99 + i, "close": 101 + i, "volume": 1000}
                for i, day in enumerate(days)
            ]
        },
    }


def test_valid_regular_closes_keep_source_and_receipt_clocks_separate():
    result = validate_daily_payload("AAA", payload(), now=NOW, received_at=NOW)
    assert len(result["bars"]) == 31 and result["event_time"] == "2026-10-06T20:00:00+00:00"
    assert result["received_at"] == NOW.isoformat()
    assert result["price_basis"] == "provider_reported" and result["adjustment_policy"] == "unknown"


@pytest.mark.parametrize("bad", [True, {"count": 3}, None])
def test_supplied_leading_fill_is_rejected_not_silently_called_real_history(bad):
    raw = payload()
    raw["leadingFill"] = bad
    result = validate_daily_payload("AAA", raw, now=NOW, received_at=NOW)
    assert result["status"] == "unavailable" and not result["bars"]
    assert result["reason"] == "filled_history"


def test_current_unclosed_and_future_bars_are_never_admitted():
    raw = payload()
    raw["regularMarket"]["bars"] += [
        {"date": day, "open": 500, "high": 501, "low": 499, "close": 500} for day in ["2026-10-07", "2026-10-08"]
    ]
    result = validate_daily_payload("AAA", raw, now=NOW, received_at=NOW)
    assert result["bars"][-1]["date"] == "2026-10-06"
    assert result["excluded"]["unclosed"] == 1 and result["excluded"]["future"] == 1


def test_conflicting_duplicates_and_bad_prices_leave_gaps_not_forward_fills():
    raw = payload()
    row = dict(raw["regularMarket"]["bars"][10])
    row.update(close=200, high=201)
    raw["regularMarket"]["bars"].append(row)
    raw["regularMarket"]["bars"][20]["close"] = float("nan")
    result = validate_daily_payload("AAA", raw, now=NOW, received_at=NOW)
    assert len(result["bars"]) == 29 and result["excluded"]["conflict"] == 1 and result["excluded"]["invalid"] == 1


def test_identical_duplicates_collapse_and_unsorted_input_does_not_invent_dates():
    raw = payload()
    raw["regularMarket"]["bars"].append(dict(raw["regularMarket"]["bars"][0]))
    raw["regularMarket"]["bars"].reverse()
    result = validate_daily_payload("AAA", raw, now=NOW, received_at=NOW)
    assert len(result["bars"]) == 31 and result["bars"][0]["date"] < result["bars"][-1]["date"]


def test_wrong_symbol_and_future_receipt_fail_closed():
    assert validate_daily_payload("BBB", payload(), now=NOW, received_at=NOW)["reason"] == "symbol_mismatch"
    assert (
        validate_daily_payload("AAA", payload(), now=NOW, received_at=datetime(2026, 10, 8, tzinfo=UTC))["reason"]
        == "invalid_clock"
    )
