"""INCOME-04 producer: missing IV/volume must be flagged, never 0-filled silently.

The Yahoo loader's ``fillna(0)`` plus ``_normalize_contract``'s ``or 0``
defaults turned absent IV/volume into confident zeros — the browser then
rendered 0.0% IV / 0 volume for rows whose inputs were never observed.
Genuine measured zeros must keep rendering as zeros; only truly absent
inputs get the unknown flag. Ranking/filtering behavior is unchanged.
"""

import math

from services.screeners.wheel_income import (
    _normalize_contract,
    rank_calls_to_sell,
    rank_puts_to_sell,
)

SPOT = 500.0


def _row(**over):
    base = {
        "strike": 480.0,
        "bid": 4.1,
        "ask": 4.3,
        "iv": 0.25,
        "volume": 120,
        "openInterest": 500,
        "expiry": "2026-11-20",
        "dte": 37,
    }
    base.update(over)
    return base


def test_missing_iv_is_flagged_not_zeroed():
    row = _row()
    del row["iv"]
    (put,) = rank_puts_to_sell([row], SPOT)
    assert put["iv"] == 0.0
    assert put["iv_unknown"] is True


def test_none_and_nan_iv_are_flagged():
    for bad in (None, float("nan")):
        (put,) = rank_puts_to_sell([_row(iv=bad)], SPOT)
        assert put["iv_unknown"] is True, bad


def test_bool_iv_is_unknown_never_one():
    (put,) = rank_puts_to_sell([_row(iv=True)], SPOT)
    assert put["iv"] == 0.0
    assert put["iv_unknown"] is True


def test_infinite_iv_is_unknown():
    (put,) = rank_puts_to_sell([_row(iv=float("inf"))], SPOT)
    assert put["iv"] == 0.0
    assert put["iv_unknown"] is True


def test_genuine_zero_iv_is_not_flagged():
    (put,) = rank_puts_to_sell([_row(iv=0.0)], SPOT)
    assert put["iv"] == 0.0
    assert put["iv_unknown"] is False


def test_missing_volume_is_flagged_not_zeroed():
    row = _row()
    del row["volume"]
    (put,) = rank_puts_to_sell([row], SPOT)
    assert put["volume"] == 0
    assert put["volume_unknown"] is True


def test_genuine_zero_volume_with_holders_is_kept_and_not_flagged():
    (put,) = rank_puts_to_sell([_row(volume=0)], SPOT)
    assert put["volume"] == 0
    assert put["volume_unknown"] is False


def test_calls_carry_the_same_flags():
    (call,) = rank_calls_to_sell([_row(strike=520.0)], SPOT)
    assert call["iv_unknown"] is False
    assert call["volume_unknown"] is False
    row = _row(strike=520.0)
    del row["iv"]
    del row["volume"]
    (flagged,) = rank_calls_to_sell([row], SPOT)
    assert flagged["iv_unknown"] is True
    assert flagged["volume_unknown"] is True


def test_normalize_marks_unknowns():
    n = _normalize_contract(_row(iv=None, volume=None))
    assert n["iv_unknown"] is True
    assert n["volume_unknown"] is True
    assert math.isnan(n["iv"]) is False
