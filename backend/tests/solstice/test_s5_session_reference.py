"""S5 session reference honesty (R10-09).

The old helper requested 1Day bars and called the result "exposure-weighted"
when a single daily row reduces to (H+L+C)/3 regardless of volume, and no
Greek/OI population enters the computation. These pin the two named modes,
the legacy alias, and the explicit unavailability of holiday/early-close /
stale-prior-session cases.
"""

from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SESSION_DATE = "2026-09-28"


def _bar(**over):
    row = {
        "date": f"{SESSION_DATE}T00:00:00Z",
        "open": 100.0, "high": 102.0, "low": 98.0, "close": 101.0,
        "volume": 1000, "session": "regular",
    }
    row.update(over)
    return row


@pytest.fixture
def source():
    return importlib.reload(importlib.import_module("services.session_levels_source"))


def _patch(source, monkeypatch, rows):
    seen: list[dict] = []

    async def fake_bars(ticker, **kw):
        seen.append({"ticker": ticker, **kw})
        return rows

    monkeypatch.setattr(source, "fetch_bars_from_public_api", fake_bars)
    return seen


def test_bar_vwap_is_volume_weighted_and_intraday(source, monkeypatch):
    """Unlike the daily mode, volume genuinely changes the answer."""
    light = [_bar(high=101.0, low=99.0, close=100.0, volume=100)]
    heavy = [_bar(high=101.0, low=99.0, close=100.0, volume=100_000)]
    _patch(source, monkeypatch, light)
    low = asyncio.run(source.session_bar_vwap_for_ticker("SPY", SESSION_DATE))
    _patch(source, monkeypatch, heavy)
    high = asyncio.run(source.session_bar_vwap_for_ticker("SPY", SESSION_DATE))
    # (H+L+C)/3 = 100.0 either way with a single bar, so prove the
    # multi-bar case: the weight must actually move the value.
    _patch(source, monkeypatch, [
        _bar(high=120.0, low=120.0, close=120.0, volume=1),
        _bar(high=80.0, low=80.0, close=80.0, volume=1_000),
    ])
    weighted = asyncio.run(source.session_bar_vwap_for_ticker("SPY", SESSION_DATE))
    _patch(source, monkeypatch, [
        _bar(high=120.0, low=120.0, close=120.0, volume=100),
        _bar(high=80.0, low=80.0, close=80.0, volume=100),
    ])
    equal = asyncio.run(source.session_bar_vwap_for_ticker("SPY", SESSION_DATE))
    assert weighted["value"] < equal["value"]
    assert weighted["value"] == pytest.approx((120 * 1 + 80 * 1000) / 1001, rel=1e-9)
    assert equal["value"] == pytest.approx(100.0, rel=1e-9)
    assert low["status"] == "ok" and high["status"] == "ok"
    assert low["label"] == "session_bar_vwap"
    assert low["timeframe"] == "15Min"
    assert low["value_kind"] == "volume_weighted_bar_typical_price"
    assert low["is_market_vwap"] is False
    assert low["timestamp_convention"]
    assert low["coverage"]["bars_used"] == 1


def test_daily_mode_is_named_and_admits_no_volume_or_exposure_weighting(source, monkeypatch):
    _patch(source, monkeypatch, [_bar()])
    out = asyncio.run(source.session_daily_typical_price_for_ticker("SPY", SESSION_DATE))
    assert out["label"] == "session_daily_typical_price"
    assert out["value_kind"] == "daily_typical_price"
    assert out["timeframe"] == "1Day"
    assert out["value"] == pytest.approx(100.3333333, rel=1e-6)
    assert "NOT volume-weighted" in out["not_computed_because"]
    assert "NOT exposure-weighted" in out["not_computed_because"]


def test_single_daily_bar_ignores_volume_scale_which_is_why_it_is_not_vwap(source, monkeypatch):
    _patch(source, monkeypatch, [_bar(volume=1)])
    low = asyncio.run(source.session_daily_typical_price_for_ticker("SPY", SESSION_DATE))
    _patch(source, monkeypatch, [_bar(volume=1_000_000)])
    high = asyncio.run(source.session_daily_typical_price_for_ticker("SPY", SESSION_DATE))
    assert low["value"] == high["value"]  # the R10-09 observation, now explained


def test_legacy_alias_is_the_daily_mode_and_no_longer_claims_exposure(source, monkeypatch):
    _patch(source, monkeypatch, [_bar()])
    out = asyncio.run(source.session_exposure_level_for_ticker("SPY", SESSION_DATE))
    assert out["label"] == "session_daily_typical_price"
    assert "exposure" not in out["label"]
    assert out["value_kind"] == "daily_typical_price"


def test_holiday_early_close_and_stale_rows_stay_explicit(source, monkeypatch):
    for rows, reason in (
        ([], "NO_BARS"),
        ([_bar(volume=0), _bar(volume=None)], "NO_VOLUME"),
        ([_bar(volume=1, high=None)], "NO_VOLUME"),
        ([_bar(date="2026-09-25T00:00:00Z")], "NO_VOLUME"),  # prior session
    ):
        _patch(source, monkeypatch, rows)
        out = asyncio.run(source.session_bar_vwap_for_ticker("SPY", SESSION_DATE))
        assert out["value"] is None
        assert out["reason"] == reason
        assert "never substituted" in out["not_computed_because"]


def test_blank_ticker_never_reaches_the_provider(source, monkeypatch):
    seen: list[dict] = []

    async def counting(ticker, **kw):
        seen.append({"ticker": ticker})
        return []

    monkeypatch.setattr(source, "fetch_bars_from_public_api", counting)
    for fn in (source.session_bar_vwap_for_ticker, source.session_daily_typical_price_for_ticker):
        out = asyncio.run(fn("", SESSION_DATE))
        assert out["value"] is None and out["reason"] == "NO_TICKER"
        assert out["is_market_vwap"] is False
    assert seen == []
