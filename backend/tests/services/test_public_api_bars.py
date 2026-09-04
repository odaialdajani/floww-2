"""Adapter-level tests for the Public.com STOCK data feed (bars + rich quotes).

Public.com was already floww's primary OPTIONS provider (chain + spot). These
tests pin the stocks side: ``fetch_bars_from_public_api`` and
``fetch_quotes_from_public_api``.

Every test mocks ``services.public_api_adapter._get_broker`` — nothing here
touches the network, and nothing here can reach any order/trading method.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# ---------------------------------------------------------------------------
# Fixtures — Public.com historicdata payload shape
#
# Documented in services/public_api.py's own __main__ demo:
#     bars.get("regularMarket", {}).get("bars", [])
#     bar keys: timestamp / open / high / low / close / volume
# ---------------------------------------------------------------------------

BARS_PAYLOAD = {
    "instrument": {"symbol": "SPY", "type": "EQUITY"},
    "regularMarket": {
        "bars": [
            {"timestamp": "2026-09-02T20:00:00Z", "open": 500.0, "high": 505.0,
             "low": 499.0, "close": 503.5, "volume": 1000},
            {"timestamp": "2026-09-03T20:00:00Z", "open": 503.5, "high": 508.0,
             "low": 502.0, "close": 507.25, "volume": 2000},
        ]
    },
}


def _broker_with_bars(payload):
    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="acct")
    broker.get_bars = AsyncMock(return_value=payload)
    return broker


def _broker_raising(exc, *, on="bars"):
    """A broker whose bars/quotes call raises ``exc``."""
    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="acct")
    broker.get_bars = AsyncMock(side_effect=exc if on == "bars" else None)
    broker.get_quotes = AsyncMock(side_effect=exc if on == "quotes" else None)
    return broker


# ---------------------------------------------------------------------------
# Provider telemetry: ONLY a real transport failure may be recorded as a
# provider failure. These endpoints are unauthenticated, and the "public_api"
# health counter they write to is shared with the PRIMARY options-chain path —
# so a bad ticker must not be able to trip provider-down alerts.
#
# Regression guard: this branch originally caught the builtin TimeoutError.
# httpx.TimeoutException is NOT a subclass of it and PublicBroker awaits httpx
# directly, so the branch was unreachable and NO failure could ever be recorded.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("exc", [
    __import__("httpx").ReadTimeout("timed out"),
    __import__("httpx").ConnectTimeout("timed out"),
    __import__("httpx").ConnectError("refused"),
])
@pytest.mark.asyncio
async def test_bars_record_provider_failure_on_transport_error(exc) -> None:
    from services.public_api_adapter import fetch_bars_from_public_api

    broker = _broker_raising(exc, on="bars")
    with patch("services.public_api_adapter._get_broker", new=AsyncMock(return_value=broker)), \
         patch("services.public_api_adapter._record_call") as rec:
        result = await fetch_bars_from_public_api("SPY", timeframe="1Day", limit=10)

    assert result is None
    rec.assert_called_once_with(False)


@pytest.mark.asyncio
async def test_bars_do_not_record_failure_for_a_bad_ticker() -> None:
    """An unknown symbol is a data condition, not a provider outage."""
    from services.public_api_adapter import fetch_bars_from_public_api

    broker = _broker_raising(RuntimeError("404 Not Found for BADTICKER"), on="bars")
    with patch("services.public_api_adapter._get_broker", new=AsyncMock(return_value=broker)), \
         patch("services.public_api_adapter._record_call") as rec:
        result = await fetch_bars_from_public_api("BADTICKER", timeframe="1Day", limit=10)

    assert result is None
    rec.assert_not_called()


@pytest.mark.asyncio
async def test_quotes_record_provider_failure_on_transport_error() -> None:
    from services.public_api_adapter import fetch_quotes_from_public_api

    broker = _broker_raising(__import__("httpx").ReadTimeout("timed out"), on="quotes")
    with patch("services.public_api_adapter._get_broker", new=AsyncMock(return_value=broker)), \
         patch("services.public_api_adapter._record_call") as rec:
        result = await fetch_quotes_from_public_api(["SPY"])

    assert result is None
    rec.assert_called_once_with(False)


@pytest.mark.asyncio
async def test_quotes_do_not_record_failure_for_a_bad_ticker() -> None:
    from services.public_api_adapter import fetch_quotes_from_public_api

    broker = _broker_raising(RuntimeError("404 Not Found"), on="quotes")
    with patch("services.public_api_adapter._get_broker", new=AsyncMock(return_value=broker)), \
         patch("services.public_api_adapter._record_call") as rec:
        result = await fetch_quotes_from_public_api(["BADTICKER"])

    assert result is None
    rec.assert_not_called()


def _quote(symbol="SPY", bid=499.0, ask=501.0, last=500.5):
    """A stand-in for services.public_api.Quote with a real mid_price."""
    q = MagicMock()
    q.symbol = symbol
    q.instrument_type = "EQUITY"
    q.bid = bid
    q.ask = ask
    q.last = last
    q.bid_size = 300
    q.ask_size = 400
    q.volume = 12345
    q.previous_close = 498.0
    q.change = 2.5
    q.percent_change = 0.5
    q.timestamp = "2026-09-03T20:00:00Z"
    q.mid_price = (bid + ask) / 2 if (bid is not None and ask is not None) else None
    return q


# ---------------------------------------------------------------------------
# fetch_bars_from_public_api
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bars_happy_path_returns_canonical_ohlcv_shape() -> None:
    """Bars normalise to floww's canonical shape (routes/backtest._bars_to_simple)."""
    from services.public_api_adapter import fetch_bars_from_public_api

    broker = _broker_with_bars(BARS_PAYLOAD)
    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        bars = await fetch_bars_from_public_api("SPY", timeframe="1Day", limit=100)

    assert bars is not None
    assert len(bars) == 2
    assert set(bars[0]) == {"date", "open", "high", "low", "close", "volume", "session"}
    assert bars[0]["session"] == "regular"
    assert bars[0]["date"] == "2026-09-02T20:00:00Z"
    assert bars[0]["close"] == 503.5
    assert bars[1]["volume"] == 2000
    # ascending by timestamp
    assert bars[0]["date"] < bars[1]["date"]


@pytest.mark.asyncio
async def test_bars_respect_limit_and_keep_most_recent() -> None:
    from services.public_api_adapter import fetch_bars_from_public_api

    broker = _broker_with_bars(BARS_PAYLOAD)
    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        bars = await fetch_bars_from_public_api("SPY", timeframe="1Day", limit=1)

    assert bars is not None
    assert len(bars) == 1
    assert bars[0]["date"] == "2026-09-03T20:00:00Z"


_MIXED_SESSION_PAYLOAD = {
    "preMarket": {"bars": [
        {"timestamp": "2026-09-03T12:00:00Z", "open": 1.0, "high": 2.0,
         "low": 0.5, "close": 1.5, "volume": 10},
    ]},
    "regularMarket": {"bars": [
        {"timestamp": "2026-09-03T20:00:00Z", "open": 2.0, "high": 3.0,
         "low": 1.5, "close": 2.5, "volume": 20},
    ]},
    "afterHours": {"bars": [
        {"timestamp": "2026-09-03T22:00:00Z", "open": 2.5, "high": 4.0,
         "low": 2.0, "close": 3.5, "volume": 30},
    ]},
}


@pytest.mark.asyncio
async def test_bars_exclude_extended_sessions_by_default() -> None:
    """Default is REGULAR SESSION ONLY.

    Merging pre/after-hours into the same series silently mixes extended-hours
    prints into what every other floww bars consumer treats as a regular-session
    series — an intraday request near the close could come back as 100%
    extended-hours bars that look identical to regular ones.
    """
    from services.public_api_adapter import fetch_bars_from_public_api

    broker = _broker_with_bars(_MIXED_SESSION_PAYLOAD)
    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        bars = await fetch_bars_from_public_api("SPY", timeframe="5Min", limit=100)

    assert bars is not None
    assert [b["date"] for b in bars] == ["2026-09-03T20:00:00Z"]
    assert {b["session"] for b in bars} == {"regular"}


@pytest.mark.asyncio
async def test_bars_include_extended_sessions_when_asked_and_tag_each_row() -> None:
    """``sessions="all"`` opts in, and every row is labelled with its session."""
    from services.public_api_adapter import fetch_bars_from_public_api

    broker = _broker_with_bars(_MIXED_SESSION_PAYLOAD)
    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        bars = await fetch_bars_from_public_api(
            "SPY", timeframe="5Min", limit=100, sessions="all",
        )

    assert bars is not None
    assert [(b["date"], b["session"]) for b in bars] == [
        ("2026-09-03T12:00:00Z", "pre"),
        ("2026-09-03T20:00:00Z", "regular"),
        ("2026-09-03T22:00:00Z", "after"),
    ]


@pytest.mark.asyncio
async def test_bars_normalize_symbol_before_calling_broker() -> None:
    """``^SPX`` must reach Public.com as ``SPX`` (same rule as the chain path)."""
    from services.public_api_adapter import fetch_bars_from_public_api

    broker = _broker_with_bars(BARS_PAYLOAD)
    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        await fetch_bars_from_public_api("^spx", timeframe="1Day", limit=10)

    assert broker.get_bars.await_args.args[0] == "SPX"


@pytest.mark.asyncio
async def test_bars_map_timeframe_to_public_period_and_aggregation() -> None:
    from services.public_api_adapter import fetch_bars_from_public_api

    broker = _broker_with_bars(BARS_PAYLOAD)
    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        await fetch_bars_from_public_api("SPY", timeframe="5min", limit=10)

    call = broker.get_bars.await_args
    assert call.args[1] == "DAY"
    assert call.kwargs["aggregation"] == "FIVE_MINUTES"


@pytest.mark.asyncio
async def test_bars_return_none_without_broker() -> None:
    """Missing PUBLIC_API_KEY → None, never an exception."""
    from services.public_api_adapter import fetch_bars_from_public_api

    with patch.dict("os.environ", {}, clear=True):
        with patch(
            "services.public_api_adapter._get_broker",
            new=AsyncMock(return_value=None),
        ):
            result = await fetch_bars_from_public_api("SPY")

    assert result is None


@pytest.mark.asyncio
async def test_bars_return_none_for_unknown_ticker() -> None:
    """An unknown symbol makes Public.com raise; the adapter absorbs it."""
    from services.public_api_adapter import fetch_bars_from_public_api

    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="acct")
    broker.get_bars = AsyncMock(side_effect=RuntimeError("404 instrument not found"))

    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        result = await fetch_bars_from_public_api("NOTATICKER")

    assert result is None


@pytest.mark.asyncio
async def test_bars_return_none_on_empty_response() -> None:
    from services.public_api_adapter import fetch_bars_from_public_api

    broker = _broker_with_bars({"regularMarket": {"bars": []}})
    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        result = await fetch_bars_from_public_api("SPY")

    assert result is None


@pytest.mark.asyncio
async def test_bars_return_none_for_unsupported_timeframe() -> None:
    """An unsupported timeframe must not reach the network at all."""
    from services.public_api_adapter import fetch_bars_from_public_api

    broker = _broker_with_bars(BARS_PAYLOAD)
    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        result = await fetch_bars_from_public_api("SPY", timeframe="3Fortnights")

    assert result is None
    broker.get_bars.assert_not_awaited()


def test_supported_bars_timeframes_are_exported() -> None:
    from services.public_api_adapter import PUBLIC_BARS_TIMEFRAMES

    assert "1Day" in PUBLIC_BARS_TIMEFRAMES
    assert "5Min" in PUBLIC_BARS_TIMEFRAMES


# ---------------------------------------------------------------------------
# fetch_quotes_from_public_api
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quotes_happy_path_returns_bid_ask_and_sizes() -> None:
    from services.public_api_adapter import fetch_quotes_from_public_api

    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="acct")
    broker.get_quotes = AsyncMock(return_value=[_quote("SPY")])

    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        quotes = await fetch_quotes_from_public_api(["SPY"])

    assert quotes is not None
    spy = quotes["SPY"]
    assert spy["spot"] == 500.0          # mid of 499/501
    assert spy["bid"] == 499.0
    assert spy["ask"] == 501.0
    assert spy["bid_size"] == 300
    assert spy["ask_size"] == 400
    assert spy["last"] == 500.5
    assert spy["data_source"] == "public_api"


@pytest.mark.asyncio
async def test_quotes_support_batch_symbols_in_one_call() -> None:
    from services.public_api_adapter import fetch_quotes_from_public_api

    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="acct")
    broker.get_quotes = AsyncMock(
        return_value=[_quote("SPY"), _quote("QQQ", bid=400.0, ask=402.0, last=401.0)]
    )

    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        quotes = await fetch_quotes_from_public_api(["spy", "qqq"])

    assert quotes is not None
    assert set(quotes) == {"SPY", "QQQ"}
    assert quotes["QQQ"]["spot"] == 401.0
    # one batched round-trip, symbols normalised
    assert broker.get_quotes.await_count == 1
    assert broker.get_quotes.await_args.args[0] == ["SPY", "QQQ"]


@pytest.mark.asyncio
async def test_quotes_accept_a_single_string_ticker() -> None:
    from services.public_api_adapter import fetch_quotes_from_public_api

    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="acct")
    broker.get_quotes = AsyncMock(return_value=[_quote("SPX")])

    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        quotes = await fetch_quotes_from_public_api("^spx")

    assert quotes is not None
    assert broker.get_quotes.await_args.args[0] == ["SPX"]
    assert "SPX" in quotes


@pytest.mark.asyncio
async def test_quotes_zero_mid_price_is_not_replaced_by_last() -> None:
    """Same contract as fetch_spot_from_public_api: 0.0 mid is a real price."""
    from services.public_api_adapter import fetch_quotes_from_public_api

    q = _quote("SPY", bid=0.0, ask=0.0, last=12.0)
    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="acct")
    broker.get_quotes = AsyncMock(return_value=[q])

    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        quotes = await fetch_quotes_from_public_api(["SPY"])

    assert quotes is not None
    assert quotes["SPY"]["spot"] == 0.0


@pytest.mark.asyncio
async def test_quotes_return_none_without_broker() -> None:
    from services.public_api_adapter import fetch_quotes_from_public_api

    with patch.dict("os.environ", {}, clear=True):
        with patch(
            "services.public_api_adapter._get_broker",
            new=AsyncMock(return_value=None),
        ):
            result = await fetch_quotes_from_public_api(["SPY"])

    assert result is None


@pytest.mark.asyncio
async def test_quotes_return_none_without_trading_account() -> None:
    from services.public_api_adapter import fetch_quotes_from_public_api

    broker = MagicMock()
    broker.get_trading_account.return_value = None

    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        result = await fetch_quotes_from_public_api(["SPY"])

    assert result is None


@pytest.mark.asyncio
async def test_quotes_return_none_for_unknown_ticker() -> None:
    from services.public_api_adapter import fetch_quotes_from_public_api

    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="acct")
    broker.get_quotes = AsyncMock(return_value=[])

    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        result = await fetch_quotes_from_public_api(["NOTATICKER"])

    assert result is None


@pytest.mark.asyncio
async def test_quotes_return_none_on_upstream_error() -> None:
    from services.public_api_adapter import fetch_quotes_from_public_api

    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="acct")
    broker.get_quotes = AsyncMock(side_effect=RuntimeError("upstream unavailable"))

    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        result = await fetch_quotes_from_public_api(["SPY"])

    assert result is None


@pytest.mark.asyncio
async def test_quotes_return_none_for_empty_symbol_list() -> None:
    from services.public_api_adapter import fetch_quotes_from_public_api

    result = await fetch_quotes_from_public_api([])
    assert result is None


# ---------------------------------------------------------------------------
# Safety — this lane is DATA ONLY
# ---------------------------------------------------------------------------


def test_adapter_never_references_order_placement() -> None:
    """The adapter must not expose Public.com's LIVE trading gateway."""
    import pathlib

    src = pathlib.Path(
        __file__
    ).resolve().parents[2] / "services" / "public_api_adapter.py"
    text = src.read_text(encoding="utf-8")
    for forbidden in ("place_order", "place_multi_leg_order", "cancel_order"):
        assert forbidden not in text, f"{forbidden} must not appear in the data adapter"
