"""
backend/tests/services/test_public_api_integration.py

Phase 3 integration tests — verify the Public API adapter produces
the same shape as the existing fetch_spot_and_chains_merged().

These tests mock PublicBroker (the raw Public.com API client) and
verify the adapter layer produces floww-shaped dicts — NOT live API
calls. PublicBroker itself is tested separately in its own repo.
"""
from __future__ import annotations

# Make backend/services importable (same pattern as other tests)
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _h2_isolated_public_budget(monkeypatch):
    """H2: adapter-level acquire debits the shared singleton even behind fake
    brokers. Isolate every test with a fresh high-capacity budget so file
    order can never starve a suite. Production behavior unchanged."""
    from services import public_budget as pb_mod
    monkeypatch.setattr(
        pb_mod, "budget",
        pb_mod.PublicBudget(capacity=10000, refill_per_sec=10000.0))

_BACKEND = os.path.join(os.path.dirname(__file__), "..", "..")


@pytest.fixture(autouse=True)
def _isolated_public_budget_singleton():
    # D1: the adapter debits the shared budget singleton per C8, so each
    # test starts from a full bucket; otherwise module order decides
    # who exhausts whom.
    from services.public_budget import budget

    budget.reset()
    yield
    budget.reset()
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


def _quote(**kw):
    q = MagicMock()
    for k, v in kw.items():
        setattr(q, k, v)
    return q


@pytest.fixture
def mock_option_contract():
    """A single OptionContract that the adapter will flatten."""
    c = MagicMock()
    c.symbol = "SPY260918C00520000"
    c.option_type = "CALL"
    c.strike = 520.0
    c.expiration = "2026-09-18"
    c.last = 5.50
    c.bid = 5.20
    c.ask = 5.80
    c.volume = 1200
    c.open_interest = 5000
    c.iv = 0.18
    c.delta = 0.65
    c.gamma = 0.02
    c.theta = -0.03
    c.vega = 0.10
    return c


@pytest.fixture
def mock_broker(mock_option_contract):
    """A fully-mocked PublicBroker with canned data for SPY.

    Uses MagicMock (sync) for the broker object since the adapter
    calls get_trading_account() without await. The awaitable methods
    are AsyncMock attached to the sync broker.
    """
    broker = MagicMock()

    # Sync method — adapter calls without await
    trading = MagicMock()
    trading.account_id = "acc-123"
    broker.get_trading_account.return_value = trading

    # Async methods — adapter awaits these
    broker.get_option_expirations = AsyncMock(
        return_value=["2026-09-18", "2026-10-16"]
    )

    quote = MagicMock()
    quote.mid_price = 520.50
    quote.last = 520.50
    quote.symbol = "SPY"
    broker.get_quotes = AsyncMock(return_value=[quote])

    # Return two calls + two puts for 2026-09-18 only
    calls = [mock_option_contract, MagicMock()]
    calls[1].symbol = "SPY260918C00530000"
    calls[1].option_type = "CALL"
    calls[1].strike = 530.0
    calls[1].expiration = "2026-09-18"
    calls[1].iv = 0.15
    calls[1].delta = 0.45

    puts = [MagicMock()]
    puts[0].symbol = "SPY260918P00510000"
    puts[0].option_type = "PUT"
    puts[0].strike = 510.0
    puts[0].expiration = "2026-09-18"
    puts[0].iv = 0.14
    puts[0].delta = -0.40
    puts[0].open_interest = 3000

    def _chain_side_effect(symbol, expiration, account_id):
        if expiration == "2026-09-18":
            return {"calls": calls, "puts": puts}
        return {"calls": [], "puts": []}

    broker.get_option_chain_parsed = AsyncMock(
        side_effect=_chain_side_effect
    )

    return broker


# ------------------------------------------------------------------
# Test fetch_chain_from_public_api
# ------------------------------------------------------------------


class TestFetchChainFromPublicApi:
    """Verify the adapter returns floww-shaped dicts when PublicBroker
    returns data."""

    @pytest.mark.asyncio
    async def test_returns_expected_keys(self, mock_broker):
        from services.public_api_adapter import fetch_chain_from_public_api

        with patch("services.public_api_adapter._get_broker",
                   new=AsyncMock(return_value=mock_broker)):
            result = await fetch_chain_from_public_api("SPY", max_expiries=2)

        assert result is not None
        assert result["ticker"] == "SPY"
        assert result["data_source"] == "public_api"
        assert "spot" in result
        assert "expiries" in result
        assert "contracts" in result
        assert isinstance(result["spot"], float)
        assert isinstance(result["expiries"], list)
        assert isinstance(result["contracts"], list)

    @pytest.mark.asyncio
    async def test_spot_comes_from_quote(self, mock_broker):
        from services.public_api_adapter import fetch_chain_from_public_api

        with patch("services.public_api_adapter._get_broker",
                   new=AsyncMock(return_value=mock_broker)):
            result = await fetch_chain_from_public_api("SPY")

        assert result["spot"] == 520.50

    @pytest.mark.asyncio
    async def test_expiries_match_broker(self, mock_broker):
        from services.public_api_adapter import fetch_chain_from_public_api

        with patch("services.public_api_adapter._get_broker",
                   new=AsyncMock(return_value=mock_broker)):
            result = await fetch_chain_from_public_api("SPY")

        assert result["expiries"] == ["2026-09-18", "2026-10-16"]

    @pytest.mark.asyncio
    async def test_contracts_only_from_first_expiry(self, mock_broker):
        """get_option_chain_parsed only returned data for 2026-09-18;
        2026-10-16 should yield zero contracts."""
        from services.public_api_adapter import fetch_chain_from_public_api

        with patch("services.public_api_adapter._get_broker",
                   new=AsyncMock(return_value=mock_broker)):
            result = await fetch_chain_from_public_api("SPY")

        # Only the 2026-09-18 contracts should be present
        for c in result["contracts"]:
            assert c["expiry"] == "2026-09-18"

    @pytest.mark.asyncio
    async def test_contract_shape_matches_cvserver(self, mock_broker):
        """Each contract dict must have the keys that the existing
        fetch_spot_and_chains_merged consumers expect."""
        from services.public_api_adapter import fetch_chain_from_public_api

        with patch("services.public_api_adapter._get_broker",
                   new=AsyncMock(return_value=mock_broker)):
            result = await fetch_chain_from_public_api("SPY")

        required = {"expiry", "T", "type", "strike", "oi", "iv",
                    "delta", "gamma", "theta", "vega", "bid", "ask",
                    "volume", "oi_source"}
        for c in result["contracts"]:
            assert set(c.keys()) >= required
            assert c["oi_source"] == "public_api"

    @pytest.mark.asyncio
    async def test_calls_and_puts_both_present(self, mock_broker):
        from services.public_api_adapter import fetch_chain_from_public_api

        with patch("services.public_api_adapter._get_broker",
                   new=AsyncMock(return_value=mock_broker)):
            result = await fetch_chain_from_public_api("SPY")

        types = {c["type"] for c in result["contracts"]}
        assert "call" in types
        assert "put" in types

    @pytest.mark.asyncio
    async def test_max_expiries_limit_respected(self, mock_broker):
        """max_expiries=1 should only fetch one expiry."""
        from services.public_api_adapter import fetch_chain_from_public_api

        with patch("services.public_api_adapter._get_broker",
                   new=AsyncMock(return_value=mock_broker)):
            result = await fetch_chain_from_public_api("SPY", max_expiries=1)

        assert len(result["expiries"]) == 1
        assert result["expiries"][0] == "2026-09-18"

    @pytest.mark.asyncio
    async def test_normalizes_symbol(self, mock_broker):
        """SPX^ should become SPX."""
        from services.public_api_adapter import fetch_chain_from_public_api

        with patch("services.public_api_adapter._get_broker",
                   new=AsyncMock(return_value=mock_broker)):
            await fetch_chain_from_public_api("SPX^")

        mock_broker.get_option_expirations.assert_called_once_with("SPX",
                                                                   "acc-123")


# ------------------------------------------------------------------
# Test no-key / no-broker paths
# ------------------------------------------------------------------


class TestNoPublicApiKey:
    """When PUBLIC_API_KEY is absent, the adapter returns None — the
    calling code (fetch_spot_and_chains_merged) falls back to cvserver."""

    @pytest.mark.asyncio
    async def test_fetch_chain_returns_none_without_key(self):
        from services.public_api_adapter import fetch_chain_from_public_api

        with patch.dict("os.environ", {}, clear=True):
            with patch("services.public_api_adapter._get_broker",
                       new=AsyncMock(return_value=None)):
                result = await fetch_chain_from_public_api("SPY")

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_spot_returns_none_without_key(self):
        from services.public_api_adapter import fetch_spot_from_public_api

        with patch.dict("os.environ", {}, clear=True):
            with patch("services.public_api_adapter._get_broker",
                       new=AsyncMock(return_value=None)):
                result = await fetch_spot_from_public_api("SPY")

        assert result is None


# ------------------------------------------------------------------
# Test empty-chain path
# ------------------------------------------------------------------


class TestEmptyChain:
    """When the broker returns expirations but 0 contracts (e.g. no
    quotes available), the adapter returns None so the fallback kicks in."""

    @pytest.mark.asyncio
    async def test_zero_contracts_returns_none(self):
        broker = MagicMock()
        trading = MagicMock()
        trading.account_id = "acc-123"
        broker.get_trading_account.return_value = trading
        broker.get_option_expirations = AsyncMock(
            return_value=["2026-09-18"]
        )
        broker.get_quotes = AsyncMock(
            return_value=[_quote(mid_price=520.50, symbol="SPY")]
        )
        broker.get_option_chain_parsed = AsyncMock(
            return_value={"calls": [], "puts": []}
        )

        from services.public_api_adapter import fetch_chain_from_public_api

        with patch("services.public_api_adapter._get_broker",
                   new=AsyncMock(return_value=broker)):
            result = await fetch_chain_from_public_api("SPY")

        assert result is None
