"""B01 canonical contract: strict parsing, zero/null, legacy compat, temporal bounds.

RED->GREEN: fails before chart_history.py exists / before strict grammar.
Synthetic fixtures only, no production records.
"""
import math

import pytest


def test_reject_booleans_blank_nonfinite_preserve_zero_null():
    from services.chart_history import parse_price, parse_volume

    # Booleans never become numeric.
    assert parse_price(True) is None
    assert parse_price(False) is None
    assert parse_volume(True) is None
    assert parse_volume(False) is None
    # Blank / null / arrays / objects / NaN / Infinity rejected.
    assert parse_price(None) is None
    assert parse_price("") is None
    assert parse_price("   ") is None
    assert parse_price([]) is None
    assert parse_price({}) is None
    assert parse_price(float("nan")) is None
    assert parse_price(float("inf")) is None
    assert parse_volume(None) is None
    assert parse_volume("") is None
    assert parse_volume(float("nan")) is None
    assert parse_volume(float("inf")) is None
    # Genuine zero volume preserved, missing stays unknown.
    assert parse_volume(0) == 0.0
    assert parse_volume(0.0) == 0.0
    assert parse_volume("0") == 0.0
    assert parse_volume(None) is None
    # Valid numeric strings accepted only by explicit grammar.
    assert parse_price("123.45") == 123.45
    assert parse_price("  123.45  ") == 123.45
    assert parse_price("abc") is None
    assert parse_price("12a") is None
    # Prices positive; volume nonnegative.
    assert parse_price(0) is None
    assert parse_price(-5) is None
    assert parse_volume(-1) is None
    assert parse_price(100.5) == 100.5


def test_old_consumers_characterized():
    """Trinity WallPricePath still receives old frames[].close; VWAP unavailable."""
    from services.chart_history import legacy_close_for_trinity

    frames = [{"close": 100.0}, {"close": None}, {}]
    assert legacy_close_for_trinity(frames[0]) == 100.0
    assert legacy_close_for_trinity(frames[1]) is None
    assert legacy_close_for_trinity(frames[2]) is None
    # VWAP caption stays unavailable until qualified source exists.
    from services.chart_history import vwap_caption

    assert vwap_caption(None) == "unavailable VWAP"
    assert vwap_caption(float("nan")) == "unavailable VWAP"


def test_bar_bounds_and_availability():
    """Completed bars end at/before cursor; inferred end never proves recorded."""
    from services.chart_history import bar_is_complete, revision_is_recorded

    # Complete only when end_time <= cursor.
    assert bar_is_complete(end_time=100, cursor=100) is True
    assert bar_is_complete(end_time=101, cursor=100) is False
    # Faithful revision needs recorded availability + end<=cursor.
    assert revision_is_recorded(availability="recorded", end_time=90, cursor=100) is True
    assert revision_is_recorded(availability="inferred_bar_end", end_time=90, cursor=100) is False
    assert revision_is_recorded(availability="unknown", end_time=90, cursor=100) is False
    assert revision_is_recorded(availability="recorded", end_time=110, cursor=100) is False
