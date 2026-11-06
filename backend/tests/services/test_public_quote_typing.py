"""Public request typing: an index is asked for as an index.

Public.com serves equities and indices from different books. The adapter
already has an operation-aware resolver - `resolve_public_instrument_type` -
and the chain path uses it: an SPX chain is requested as
UNDERLYING_SECURITY_FOR_INDEX_OPTION. The quote path did not: it called
`get_quotes` without an instrument type, so every quote was asked for as an
EQUITY. An index quote requested as an equity is the wrong request: the
provider does not answer it, so the spot fell through to a fallback that was
never the requested instrument.

These checks use a fake broker that records exactly what was asked for. They
pin the single-symbol contract (one quote request, typed) and the batch
contract (one request per instrument type, results merged).

No network, no credentials, no orders: the broker is a local fake.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from services.public_api import Quote, resolve_public_instrument_type


def _quote(symbol: str, instrument_type: str, bid=499.0, ask=501.0, last=500.5) -> Quote:
    """A stand-in for the provider's quote with a real mid price."""
    return Quote(
        symbol=symbol,
        instrument_type=instrument_type,
        last=last,
        bid=bid,
        ask=ask,
        bid_size=300,
        ask_size=400,
        volume=12345,
        previous_close=498.0,
        change=2.5,
        percent_change=0.5,
        timestamp=datetime.now(UTC).isoformat(),
        bid_timestamp=datetime.now(UTC).isoformat(),
        ask_timestamp=datetime.now(UTC).isoformat(),
    )


class _RecordingBroker:
    """A fake broker that records every quote request it receives."""

    def __init__(self, quotes_by_type: dict[str, list[Quote]] | None = None):
        self.calls: list[dict] = []
        self._quotes_by_type = quotes_by_type or {}

    def get_trading_account(self):
        from types import SimpleNamespace

        return SimpleNamespace(account_id="acct")

    async def get_quotes(self, symbols, account_id, instrument_type="EQUITY"):
        self.calls.append({"symbols": list(symbols), "account_id": account_id,
                           "instrument_type": instrument_type})
        known = self._quotes_by_type.get(instrument_type)
        if known is not None:
            return list(known)
        # Default: answer every requested symbol with its own type.
        return [_quote(symbol, instrument_type) for symbol in symbols]

    @property
    def types_asked_for(self) -> list[str]:
        return [call["instrument_type"] for call in self.calls]


@pytest.mark.asyncio
@pytest.mark.parametrize("symbol,expected", [
    ("SPX", "INDEX"),
    ("^SPX", "INDEX"),
    ("SPXW", "INDEX"),
    ("NDX", "INDEX"),
    ("VIX", "INDEX"),
    ("RUT", "INDEX"),
    ("SPY", "EQUITY"),
    ("QQQ", "EQUITY"),
    ("AAPL", "EQUITY"),
])
async def test_the_spot_quote_is_requested_with_the_resolved_instrument_type(symbol, expected):
    """The single-symbol quote request must carry the resolved type.

    `get_quotes` defaults to EQUITY, so an index quote was asked for as an
    equity. The provider does not answer that request for an index book, so
    the spot silently fell through to a fallback instead of the quote that
    was asked for.
    """
    from services.public_api_adapter import _resolve_spot_observation

    broker = _RecordingBroker()
    observation = await _resolve_spot_observation(broker, symbol, "acct")

    assert broker.calls, "no quote request was made"
    call = broker.calls[0]
    assert call["instrument_type"] == expected, (
        f"{symbol} was requested as {call['instrument_type']}, not {expected}")
    assert call["symbols"] == [symbol.upper().replace("^", "")], call
    assert observation["price"] is not None, observation


@pytest.mark.asyncio
async def test_the_resolver_and_the_quote_request_never_disagree():
    """The type sent on the wire is the type the resolver names."""
    from services.public_api_adapter import _resolve_spot_observation

    for symbol in ("SPX", "SPXW", "SPY", "QQQ"):
        broker = _RecordingBroker()
        await _resolve_spot_observation(broker, symbol, "acct")
        expected = resolve_public_instrument_type(symbol, "quote")
        assert broker.calls[0]["instrument_type"] == expected, symbol


@pytest.mark.asyncio
async def test_a_homogeneous_batch_stays_one_round_trip():
    """A batch of one type is still one request: the batch is the cheap path."""
    from services.public_api_adapter import fetch_quotes_from_public_api

    broker = _RecordingBroker()
    with patch("services.public_api_adapter._get_broker",
               new=AsyncMock(return_value=broker)):
        quotes = await fetch_quotes_from_public_api(["spy", "qqq"])

    assert quotes is not None
    assert set(quotes) == {"SPY", "QQQ"}
    assert len(broker.calls) == 1, broker.calls
    assert broker.calls[0]["symbols"] == ["SPY", "QQQ"]
    assert broker.calls[0]["instrument_type"] == "EQUITY"


@pytest.mark.asyncio
async def test_a_mixed_batch_asks_for_each_type_and_merges_the_results():
    """An equity and an index cannot share one request: the types differ."""
    from services.public_api_adapter import fetch_quotes_from_public_api

    broker = _RecordingBroker()
    with patch("services.public_api_adapter._get_broker",
               new=AsyncMock(return_value=broker)):
        quotes = await fetch_quotes_from_public_api(["SPY", "SPX"])

    assert quotes is not None
    assert set(quotes) == {"SPY", "SPX"}, quotes
    assert sorted(broker.types_asked_for) == ["EQUITY", "INDEX"], broker.calls
    for call in broker.calls:
        assert len(call["symbols"]) == 1, (
            "an index and an equity were asked for in one request")
        expected = resolve_public_instrument_type(call["symbols"][0], "quote")
        assert call["instrument_type"] == expected, call


@pytest.mark.asyncio
async def test_an_index_only_batch_is_asked_for_as_an_index():
    """One index alone is still one request, typed as an index."""
    from services.public_api_adapter import fetch_quotes_from_public_api

    broker = _RecordingBroker()
    with patch("services.public_api_adapter._get_broker",
               new=AsyncMock(return_value=broker)):
        quotes = await fetch_quotes_from_public_api(["SPX"])

    assert quotes is not None
    assert "SPX" in quotes, quotes
    assert len(broker.calls) == 1, broker.calls
    assert broker.calls[0]["instrument_type"] == "INDEX"


@pytest.mark.asyncio
async def test_a_failed_index_request_does_not_lose_the_equity_quotes():
    """One refused type must not discard the answers of the other."""
    from services.public_api_adapter import fetch_quotes_from_public_api

    class _HalfFailingBroker(_RecordingBroker):
        async def get_quotes(self, symbols, account_id, instrument_type="EQUITY"):
            self.calls.append({"symbols": list(symbols), "account_id": account_id,
                               "instrument_type": instrument_type})
            if instrument_type == "INDEX":
                raise RuntimeError("index book unavailable")
            return [_quote(symbol, instrument_type) for symbol in symbols]

    broker = _HalfFailingBroker()
    with patch("services.public_api_adapter._get_broker",
               new=AsyncMock(return_value=broker)):
        quotes = await fetch_quotes_from_public_api(["SPY", "SPX"])

    assert quotes is not None, "the whole batch was lost because one type failed"
    assert "SPY" in quotes, quotes
    assert "SPX" not in quotes, quotes
