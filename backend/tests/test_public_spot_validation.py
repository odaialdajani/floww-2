"""
backend/tests/test_public_spot_validation.py — weekend stale-spot incident.

2026-09-06: every Public-served spot was wrong (AFRM 81.705 vs true 72.35,
AAPL 327.4 vs 319.97, SPY 760.64 vs 770.19). Root cause: Public's equity
quote book was a frozen Friday-premarket snapshot (AFRM ask 89.0 vs bid
74.41; SPY bid 747.35/ask 773.93 crossed) and _fetch_chain_live trusted
mid_price unconditionally.

Contract pinned here:
- crossed or wide (>1%) books are rejected even with a fresh timestamp
- quotes predating the last US close are stale even with a tight book
- quotes without assessable book/ts keep legacy trust (existing mocks)
- stale Public spot falls back to yfinance close, source-tagged
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.public_api import Quote


def _q(**kw):
    base = dict(symbol="AFRM", instrument_type="EQUITY", last=None, bid=None,
                ask=None, previous_close=None, timestamp=None)
    base.update(kw)
    return Quote(**base)


FRI_AM = "2026-09-04T07:59:57Z"   # before Friday's close -> stale on weekend
FRI_PM = "2026-09-04T21:30:00Z"   # after Friday 16:00 ET close -> fresh
SUN = datetime(2026, 9, 6, 5, 0, 0)


def test_afrm_wide_book_rejected():
    from services.public_api_adapter import _public_quote_spot
    q = _q(last=74.5, bid=74.41, ask=89.0, timestamp=FRI_PM)
    price, reason = _public_quote_spot(q, now=SUN)
    assert price is None and reason == "wide-book"


def test_crossed_book_rejected():
    from services.public_api_adapter import _public_quote_spot
    q = _q(last=773.79, bid=773.93, ask=747.35, timestamp=FRI_PM)
    price, reason = _public_quote_spot(q, now=SUN)
    assert price is None and reason == "crossed-book"


def test_stale_tight_book_rejected():
    from services.public_api_adapter import _public_quote_spot
    q = _q(last=327.0, bid=326.8, ask=328.0, timestamp=FRI_AM)
    price, reason = _public_quote_spot(q, now=SUN)
    assert price is None and reason == "stale-quote"


def test_fresh_tight_book_accepted():
    from services.public_api_adapter import _public_quote_spot
    q = _q(last=327.0, bid=326.8, ask=328.0, timestamp=FRI_PM)
    price, reason = _public_quote_spot(q, now=SUN)
    assert price == pytest.approx(327.4) and reason == "public-mid"


def test_legacy_mock_shape_keeps_trust():
    from services.public_api_adapter import _public_quote_spot
    q = MagicMock()
    q.mid_price = 450.0
    q.last = 450.0
    q.bid = MagicMock()
    q.ask = MagicMock()
    q.timestamp = MagicMock()
    price, reason = _public_quote_spot(q, now=SUN)
    assert price == 450.0


def test_last_us_close_weekend():
    from services.public_api_adapter import _last_us_close_utc
    assert _last_us_close_utc(SUN).isoformat() == "2026-09-04T20:00:00+00:00"


def test_last_us_close_weekday():
    from services.public_api_adapter import _last_us_close_utc
    wed = datetime(2026, 9, 2, 12, 0, 0)
    assert _last_us_close_utc(wed).isoformat() == "2026-09-01T20:00:00+00:00"


@pytest.mark.asyncio
async def test_resolve_spot_falls_back_to_yfinance():
    from services import public_api_adapter as adapter
    broker = MagicMock()
    broker.get_quotes = AsyncMock(return_value=[
        _q(symbol="AFRM", last=74.5, bid=74.41, ask=89.0, timestamp=FRI_AM)])
    with patch.object(adapter, "_yfinance_spot", return_value=72.35):
        spot, source = await adapter._resolve_spot(broker, "AFRM", "ACCT")
    assert spot == pytest.approx(72.35)
    assert source == "yfinance-fallback"


@pytest.mark.asyncio
async def test_resolve_spot_uses_fresh_public_mid():
    from services import public_api_adapter as adapter
    broker = MagicMock()
    broker.get_quotes = AsyncMock(return_value=[
        _q(symbol="AFRM", last=72.4, bid=72.3, ask=72.5, timestamp=FRI_PM)])
    with patch.object(adapter, "_yfinance_spot") as yf:
        spot, source = await adapter._resolve_spot(
            broker, "AFRM", "ACCT", now=SUN)
    assert spot == pytest.approx(72.4)
    assert source == "public-mid"
    yf.assert_not_called()
