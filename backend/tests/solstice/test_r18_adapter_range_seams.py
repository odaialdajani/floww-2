"""R18-C1 adapter seams: fetch_option_expiry_listing + fetch_chain_for_expiries.

Deterministic fake broker (same convention as TestChainCache); no network.
Pins the range-analytics.v1 adapter contract: full listing (not first-N),
bounded EXACT-date fetch with per-expiry skip accountability, 2+N budget
pre-debit shape, and identity-bound caching (a different date set cannot
reuse the cached chain).
"""
from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "backend")

import pytest

import services.public_api_adapter as adapter
from services.public_api import OptionContract, Quote


def _mk_broker(spot=600.0, fail_expiries=frozenset()):
    fail_expiries = frozenset(fail_expiries or ())
    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="TEST-ACCT")

    fut1 = (datetime.now(UTC) + timedelta(days=21)).date().isoformat()
    fut2 = (datetime.now(UTC) + timedelta(days=35)).date().isoformat()
    stamp = datetime.now(UTC).isoformat()

    async def quotes(symbols, account_id):
        return [Quote(symbol=symbols[0], instrument_type="EQUITY", last=spot,
                      bid=spot - .01, ask=spot + .01, timestamp=stamp,
                      bid_timestamp=stamp, ask_timestamp=stamp)]

    async def expirations(symbol, account_id, instrument_type=None):
        return [fut1, fut2]

    def _mk_contract(expiry, side):
        return OptionContract(
            symbol=f"TEST{expiry.replace('-', '')[2:]}{'C' if side == 'calls' else 'P'}00590000",
            option_type="CALL" if side == "calls" else "PUT",
            strike=590.0, expiration=expiry, bid=4.9, ask=5.1,
            volume=750, open_interest=1500, iv=0.22, delta=0.5,
            gamma=0.02, bid_timestamp=stamp, ask_timestamp=stamp,
            greeks_source="vendor", oi_effective_date="2026-10-03")

    async def chain(symbol, expiry, account_id, instrument_type=None):
        if expiry in fail_expiries:
            raise RuntimeError("vendor boom")
        return {"calls": [_mk_contract(expiry, "calls")],
                "puts": [_mk_contract(expiry, "puts")]}

    broker.get_quotes = AsyncMock(side_effect=quotes)
    broker.get_option_expirations = AsyncMock(side_effect=expirations)
    broker.get_option_chain_parsed = AsyncMock(side_effect=chain)
    return broker, (fut1, fut2)


@pytest.fixture(autouse=True)
def _clean_cache():
    adapter._clear_chain_cache()
    yield
    adapter._clear_chain_cache()


def test_expiry_listing_returns_full_vendor_list():
    broker, (fut1, fut2) = _mk_broker()
    with patch.object(adapter, "_get_broker", new=AsyncMock(return_value=broker)):
        listing = asyncio.run(adapter.fetch_option_expiry_listing("TEST"))
    assert listing is not None
    assert listing["expiries"] == [fut1, fut2]
    assert listing["n_listed"] == 2
    assert listing["listing_capped"] is False
    assert listing["data_source"] == "public_api"


def test_exact_window_fetch_reports_skipped_expiry():
    broker, (fut1, fut2) = _mk_broker()
    with patch.object(adapter, "_get_broker", new=AsyncMock(return_value=broker)):
        ok = asyncio.run(adapter.fetch_chain_for_expiries("TEST", [fut1, fut2]))
    assert ok is not None and ok["skipped"] == []
    assert ok["expiries"] == [fut1, fut2] or sorted(ok["expiries"]) == sorted([fut1, fut2])
    assert len(ok["contracts"]) == 4  # call+put per expiry
    assert ok["requested_expiries"] == [fut1, fut2]
    assert ok["budget_pre_debit"] == 4  # 2 + N admitted expiries
    assert ok["attempt_cap"] == 2

    # One expiry fails at the vendor: skip is recorded with the reason; the
    # surviving expiry still delivers contracts. Nothing silently absent.
    broker2, _ = _mk_broker(fail_expiries={fut2})
    adapter._clear_chain_cache()
    with patch.object(adapter, "_get_broker", new=AsyncMock(return_value=broker2)):
        partial = asyncio.run(adapter.fetch_chain_for_expiries("TEST", [fut1, fut2]))
    assert partial is not None
    assert partial["skipped"] == [{"expiry": fut2, "reason": "CHAIN_FETCH_FAILED"}]
    assert len(partial["contracts"]) == 2


def test_window_cache_identity_binds_dates():
    broker, (fut1, fut2) = _mk_broker()
    with patch.object(adapter, "_get_broker", new=AsyncMock(return_value=broker)):
        a = asyncio.run(adapter.fetch_chain_for_expiries("TEST", [fut1]))
        b = asyncio.run(adapter.fetch_chain_for_expiries("TEST", [fut1]))
        # Second identical call served from the identity-bound chain cache.
        assert broker.get_option_chain_parsed.await_count == 1
        c = asyncio.run(adapter.fetch_chain_for_expiries("TEST", [fut1, fut2]))
    assert a is not None and b is not None
    # A different window never reuses the narrower cached chain.
    assert len(c["contracts"]) == 4
    assert broker.get_option_chain_parsed.await_count == 3  # 1 + 0 + 2


def test_no_broker_returns_none():
    with patch.object(adapter, "_get_broker", new=AsyncMock(return_value=None)):
        assert asyncio.run(adapter.fetch_option_expiry_listing("TEST")) is None
        assert asyncio.run(adapter.fetch_chain_for_expiries("TEST", ["2026-10-26"])) is None
