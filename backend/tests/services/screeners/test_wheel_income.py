"""
Unit tests for the wheel-income premium-selling screener
(steal-list rank #3).
"""

import math

import pytest

from services.screeners.wheel_income import (
    _arr_pct,
    _normalize_contract,
    rank_calls_to_sell,
    rank_puts_to_sell,
)

SPOT = 580.0


def _put(strike: float, mid: float, iv: float = 0.30, vol: int = 100, dte: int = 30,
         expiry: str = "2026-08-15") -> dict:
    return {
        "strike": strike,
        "bid": mid - 0.05,
        "ask": mid + 0.05,
        "iv": iv,
        "volume": vol,
        "openInterest": 500,
        "expiry": expiry,
        "T": dte / 365.0,
        "dte": dte,
    }


def _call(strike: float, mid: float, iv: float = 0.30, vol: int = 100, dte: int = 30,
          expiry: str = "2026-08-15") -> dict:
    return {
        "strike": strike,
        "bid": mid - 0.05,
        "ask": mid + 0.05,
        "iv": iv,
        "volume": vol,
        "openInterest": 500,
        "expiry": expiry,
        "T": dte / 365.0,
        "dte": dte,
    }


def test_arr_pct_basic():
    # 1.50 premium / 580 strike, 30 DTE
    arr = _arr_pct(mid_per_share=1.50, collateral_per_share=580.0, dte=30)
    expected = (1.50 / 580.0) * (365 / 30) * 100
    assert math.isclose(arr, expected, rel_tol=1e-9)


def test_arr_pct_invalid():
    assert _arr_pct(0, 580, 30) == 0.0
    assert _arr_pct(1.0, 0, 30) == 0.0
    assert _arr_pct(1.0, 580, 0) == 0.0


def test_normalize_yfinance_shape():
    raw = {
        "strike": 580.0,
        "bid": 1.45,
        "ask": 1.55,
        "iv": 0.30,
        "volume": 100,
        "openInterest": 1000,
    }
    n = _normalize_contract(raw)
    assert n is not None
    assert n["mid"] == pytest.approx(1.50, rel=1e-9)
    assert n["strike"] == 580.0


def test_normalize_handles_missing_bidask():
    # Holders exist (OI>0) but no quote — mid falls back to last print.
    raw = {"strike": 580, "lastPrice": 1.50, "iv": 0.30, "openInterest": 12}
    n = _normalize_contract(raw)
    assert n["mid"] == pytest.approx(1.50, rel=1e-9)


def test_normalize_drops_no_market_rows():
    # 2026-09-03: zero prints AND zero holders = phantom quote with
    # nonsense ARR — dropped so the screener never surfaces it.
    assert _normalize_contract(
        {"strike": 250.0, "bid": 160.0, "ask": 178.0, "lastPrice": 0.0,
         "iv": 0.0, "volume": 0, "openInterest": 0, "expiry": "2026-09-18"}
    ) is None
    # …but OI holders with no volume today are a real market: kept.
    kept = _normalize_contract(
        {"strike": 250.0, "bid": 1.0, "ask": 1.2, "lastPrice": 1.1,
         "iv": 0.25, "volume": 0, "openInterest": 40, "expiry": "2026-09-18"}
    )
    assert kept is not None
    assert kept["mid"] == pytest.approx(1.10, rel=1e-9)


def test_normalize_rejects_garbage_strike():
    assert _normalize_contract({"strike": "abc"}) is None


def test_rank_puts_basic_order():
    # Test pure ordering logic — disable breakeven gating so all three
    # candidates survive filtering, then verify ARR is monotonically
    # descending in the result.
    puts = [
        _put(560, 0.80, iv=0.30, vol=200, dte=30),  # high ARR
        _put(570, 1.20, iv=0.30, vol=200, dte=30),  # lower ARR
        _put(550, 0.40, iv=0.30, vol=200, dte=30),  # lowest: low premium
    ]
    out = rank_puts_to_sell(
        puts, SPOT,
        min_iv=0.10, min_volume=10, min_dte=1, max_dte=60,
        min_breakeven_drop_pct=0.0,  # disable gate for ordering assertion
    )
    assert len(out) == 3
    arr_values = [o["annualized_return_pct"] for o in out]
    assert arr_values == sorted(arr_values, reverse=True)


def test_rank_puts_breakeven_filter():
    # BE = K - mid; we require drop_pct = (spot - be)/spot >= min_breakeven_drop_pct.
    # K=579 with mid=2 → BE=577, drop_pct = (580 - 577)/580 ≈ 0.517%
    # That fails min_breakeven_drop_pct=0.02 (= 2%) → should be filtered.
    tight = [_put(579, 2.0, iv=0.30, vol=200, dte=30)]
    out = rank_puts_to_sell(tight, SPOT, min_breakeven_drop_pct=0.02)
    assert out == []


def test_rank_puts_iv_and_volume_filters():
    low_iv = [_put(560, 1.50, iv=0.05, vol=200, dte=30)]
    low_vol = [_put(560, 1.50, iv=0.30, vol=0, dte=30)]
    out1 = rank_puts_to_sell(low_iv, SPOT, min_iv=0.10)
    assert out1 == []
    out2 = rank_puts_to_sell(low_vol, SPOT, min_volume=10)
    assert out2 == []


def test_rank_calls_basic():
    calls = [
        _call(590, 1.00, dte=30),  # 1.7% OTM
        _call(600, 0.50, dte=30),  # 3.4% OTM
    ]
    out = rank_calls_to_sell(calls, SPOT, min_strike_premium_pct=0.005)
    assert all(o["side"] == "call" for o in out)
    assert len(out) == 2


def test_rank_calls_skips_deep_itm():
    calls = [
        _call(550, 30.00, dte=30),  # deeply ITM; pinned
        _call(600, 0.50, dte=30),
    ]
    out = rank_calls_to_sell(calls, SPOT, min_strike_premium_pct=0.005)
    strikes = [o["strike"] for o in out]
    assert 600.0 in strikes
    assert 550.0 not in strikes


def test_rank_calls_zero_spot_returns_empty():
    out = rank_calls_to_sell([_call(590, 1.0, dte=30)], 0)
    assert out == []


def test_rank_puts_top_limit():
    puts = [_put(560 + i * 0.5, 0.50 + i * 0.10, dte=30) for i in range(50)]
    out = rank_puts_to_sell(puts, SPOT, top=5)
    assert len(out) == 5


# ---------------------------------------------------------------------------
# Regression — dte must derive from the `expiry` string when neither `dte`
# nor `T` is present (the documented contract). yfinance rows carry ONLY
# `expiry`, so without this every chain row normalized to dte=0 and the
# ranker dropped it — the live screener returned empty for all tickers
# (2026-07-15).
# ---------------------------------------------------------------------------
def test_normalize_derives_dte_from_expiry_string():
    from datetime import date, timedelta

    from services.screeners.wheel_income import _normalize_contract, rank_puts_to_sell

    expiry = (date.today() + timedelta(days=37)).isoformat()
    row = {"strike": 95.0, "expiry": expiry, "openInterest": 500,
           "volume": 40, "bid": 1.0, "ask": 1.2, "impliedVolatility": 0.25}

    norm = _normalize_contract(row)
    assert norm is not None
    assert norm["dte"] == 37

    ranked = rank_puts_to_sell([row], 100.0, min_dte=7, max_dte=45)
    assert len(ranked) == 1
    assert ranked[0]["strike"] == 95.0
    assert ranked[0]["dte"] == 37
