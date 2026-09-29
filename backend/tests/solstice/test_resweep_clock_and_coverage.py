"""Resweep part 2: the clock and the wall-coverage holes.

H5 - the tz-database-free US DST rule was applied to PRE-2007 instants and
     is wrong there by up to 60 minutes (2003-04-05: rule says 13:00
     -04:00, reality is 12:00 -05:00). The fallback returned that wrong
     hour with no flag anywhere. It now refuses outside its declared
     validity window, and the conversion reports WHICH path answered.
H6 - wall_metric_breakdown dropped contracts whose strike could not be read
     with a bare `continue` and NO count, so a wall whose members all had
     unreadable strikes reported n_contracts=0 and looked identical to a
     wall with no contracts there.
"""

from __future__ import annotations

import builtins
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.exposure_metrics import wall_metric_breakdown  # noqa: E402
from services.eastern_clock import (  # noqa: E402
    US_DST_RULE_VALID_FROM,
    eastern_at_safe,
    eastern_at_safe_provenance,
)

WALLS = [{"wall_id": "K100", "members": [100]}]


def _no_tzdata(monkeypatch):
    real = builtins.__import__

    def fake(name, *a, **k):
        if name.startswith("zoneinfo"):
            raise ModuleNotFoundError("no tzdata")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)


# ---- H5: the DST rule has a validity window and must respect it ----

def test_rule_fallback_declares_its_source_and_keeps_the_instant():
    utc = datetime(2030, 6, 15, 13, 30, tzinfo=UTC)
    got, prov = eastern_at_safe_provenance(utc)
    assert prov["source"] == "tzdata"
    assert got.timestamp() == utc.timestamp()


def test_rule_fallback_refuses_pre_2007_instead_of_guessing(monkeypatch):
    _no_tzdata(monkeypatch)
    with pytest.raises(ValueError, match="only valid from"):
        eastern_at_safe(datetime(2003, 4, 5, 17, 0, tzinfo=UTC))
    assert US_DST_RULE_VALID_FROM == 2007


def test_rule_fallback_still_answers_inside_its_window(monkeypatch):
    _no_tzdata(monkeypatch)
    utc = datetime(2030, 6, 15, 13, 30, tzinfo=UTC)
    got, prov = eastern_at_safe_provenance(utc)
    assert prov["source"] == "us_dst_rule"
    assert prov["rule_valid"] is True
    assert got.timestamp() == utc.timestamp()
    assert got.strftime("%H:%M") == "09:30"


def test_pre_2007_is_correct_when_the_tz_database_answers():
    """Refusing on the fallback must not mean refusing when we can know."""
    utc = datetime(2003, 4, 5, 17, 0, tzinfo=UTC)
    got, prov = eastern_at_safe_provenance(utc)
    assert prov["source"] == "tzdata"
    assert got.strftime("%H:%M %z") == "12:00 -0500"


def test_naive_input_is_refused_on_both_paths(monkeypatch):
    with pytest.raises(ValueError):
        eastern_at_safe(datetime(2026, 6, 15, 13, 30))
    _no_tzdata(monkeypatch)
    with pytest.raises(ValueError):
        eastern_at_safe(datetime(2026, 6, 15, 13, 30))


# ---- H6: the excluded population must be counted ----

def _c(strike, **kw):
    base = {"osi": "a", "strike": strike, "expiry": "E", "type": "call",
            "gamma": 0.01, "delta": 0.5, "oi": 100, "volume": 50, "multiplier": 100}
    base.update(kw)
    return base


def test_unreadable_strike_is_counted_not_silently_dropped():
    out = wall_metric_breakdown(WALLS, [_c(None), _c(float("nan")), _c(True), "junk"], 100.0)
    row = out["K100"]
    assert row["n_contracts"] == 0
    assert row["unreadable_strike"] == 4, "every dropped contract must be counted"
    assert row["not_a_member"] == 0
    assert row["daddex_gross"] == 0.0 and row["daddex_usable"] == 0


def test_non_member_and_unreadable_are_different_facts():
    out = wall_metric_breakdown(WALLS, [_c(200), _c(None)], 100.0)
    row = out["K100"]
    assert row["not_a_member"] == 1
    assert row["unreadable_strike"] == 1
    assert row["n_contracts"] == 0


def test_string_strike_from_storage_still_matches():
    """A DB DOUBLE read back as a string is not a defect; it must still join."""
    out = wall_metric_breakdown(WALLS, [_c("100")], 100.0)
    assert out["K100"]["n_contracts"] == 1
    assert out["K100"]["daddex_usable"] == 1
    assert out["K100"]["volume_usable"] == 1


def test_a_real_member_is_unaffected_by_the_counting():
    out = wall_metric_breakdown(WALLS, [_c(100), _c(None)], 100.0)
    row = out["K100"]
    assert (row["n_contracts"], row["unreadable_strike"]) == (1, 1)
    assert row["daddex_gross"] == 5000.0
    assert row["volume_gross"] == 5000.0
