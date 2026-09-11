from __future__ import annotations

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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture(autouse=True)
def _isolated_public_budget_singleton():
    # D1: the adapter debits the shared budget singleton per C8, so each
    # test starts from a full bucket; otherwise module order decides
    # who exhausts whom.
    from services.public_budget import budget

    budget.reset()
    yield
    budget.reset()


def _quote(**kw):
    q = MagicMock()
    for k, v in kw.items():
        setattr(q, k, v)
    return q


@pytest.mark.asyncio
async def test_zero_mid_price_is_not_replaced_by_last() -> None:
    from services.public_api_adapter import fetch_spot_from_public_api

    broker = MagicMock()
    account = MagicMock(account_id="acct")
    broker.get_trading_account.return_value = account
    quote = MagicMock(mid_price=0.0, last=12.0)
    quote.symbol = "SPY"
    broker.get_quotes = AsyncMock(
        return_value=[quote]
    )

    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        result = await fetch_spot_from_public_api("SPY")

    assert result == 0.0


@pytest.mark.asyncio
async def test_broker_initialization_requires_a_trading_account() -> None:
    from services.public_api_adapter import _get_broker

    with patch.dict(os.environ, {"PUBLIC_API_KEY": "secret"}, clear=True):
        broker = MagicMock()
        broker.auth = AsyncMock(return_value="token")
        broker.get_accounts = AsyncMock(return_value=[])
        broker.get_trading_account.return_value = None

        with patch(
            "services.public_api_adapter.PublicBroker",
            return_value=broker,
        ):
            import services.public_api_adapter as adapter

            adapter.BROKER = None
            result = await _get_broker()

    assert result is broker
    broker.auth.assert_awaited_once()
    broker.get_accounts.assert_awaited_once()


@pytest.mark.asyncio
async def test_public_chain_returns_none_when_chain_fetch_fails() -> None:
    from services.public_api_adapter import fetch_chain_from_public_api

    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="acct")
    broker.get_option_expirations = AsyncMock(
        return_value=["2026-09-18"]
    )
    broker.get_quotes = AsyncMock(
        return_value=[_quote(mid_price=500.0, symbol="SPY")]
    )
    broker.get_option_chain_parsed = AsyncMock(
        side_effect=RuntimeError("upstream unavailable")
    )

    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        result = await fetch_chain_from_public_api("SPY")

    assert result is None


@pytest.mark.asyncio
async def test_extract_bars_rejects_nonfinite_values() -> None:
    """Port of floww-2 dcfaf5ea finding #4: NaN/Infinity must not ship as bars."""
    from services.public_api_adapter import _extract_bars

    rows = _extract_bars([
        {"t": "2026-09-04", "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": 100},
        {"t": "2026-09-03", "o": float("nan"), "h": 2.0, "l": 0.5, "c": 1.5, "v": 100},
        {"t": "2026-09-02", "o": 1.0, "h": float("inf"), "l": 0.5, "c": 1.5, "v": 100},
        {"t": "2026-09-01", "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5, "v": float("nan")},
        {"t": "2026-08-29", "o": 1.0, "h": 2.0, "l": 0.5},  # missing close
    ], sessions="all")
    assert len(rows) == 1 and rows[0]["t"] == "2026-09-04"


@pytest.mark.asyncio
async def test_spot_refuses_wrong_symbol_substitution() -> None:
    """Port of floww-2 dcfaf5ea finding #1: never label another symbol's price."""
    from services.public_api_adapter import fetch_spot_from_public_api

    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="acct")
    wrong = MagicMock(mid_price=999.0, last=999.0)
    wrong.symbol = "QQQ"
    broker.get_quotes = AsyncMock(return_value=[wrong])

    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        assert await fetch_spot_from_public_api("SPY") is None


@pytest.mark.asyncio
async def test_spot_uses_matching_symbol() -> None:
    from services.public_api_adapter import fetch_spot_from_public_api

    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="acct")
    other = MagicMock(mid_price=999.0, last=999.0)
    other.symbol = "QQQ"
    right = MagicMock(mid_price=450.0, last=449.0)
    right.symbol = "SPY"
    broker.get_quotes = AsyncMock(return_value=[other, right])

    with patch(
        "services.public_api_adapter._get_broker",
        new=AsyncMock(return_value=broker),
    ):
        assert await fetch_spot_from_public_api("SPY") == 450.0


@pytest.mark.asyncio
async def test_transport_errors_recorded_not_429() -> None:
    """Port of floww-2 c8e12c65: httpx.TransportError (incl. timeouts, which
    are NOT builtin TimeoutError) must count as errors, not 429s."""
    import httpx

    from services.public_api_adapter import _note_public_429
    from services.public_budget import PublicBudget

    b = PublicBudget()
    with patch("services.public_budget.budget", b):
        _note_public_429(httpx.ConnectError("down"))
        _note_public_429(httpx.ReadTimeout("slow"))
    assert b.total_errors == 2
    assert b.total_429 == 0

    class FakeResp:
        status_code = 429

    class Fake429(Exception):
        response = FakeResp()

    with patch("services.public_budget.budget", b):
        _note_public_429(Fake429())
    assert b.total_429 == 1


def _session_payload() -> dict:
    def bar(t, o=10.0):
        return {"timestamp": t, "open": o, "close": o + 0.1, "high": o + 0.2,
                "low": o - 0.1, "volume": 1000}
    return {
        "preMarket": {"expectedBars": 2, "bars": [bar("2026-09-04T04:00:00-04:00"),
                                                  bar("2026-09-04T04:01:00-04:00")]},
        "regularMarket": {"expectedBars": 2, "bars": [bar("2026-09-04T09:30:00-04:00"),
                                                      bar("2026-09-04T09:31:00-04:00", o=11.0)]},
        "afterMarket": {"expectedBars": 1, "bars": [bar("2026-09-04T16:01:00-04:00")]},
    }


def test_extract_bars_defaults_to_regular_session_only() -> None:
    from services.public_api_adapter import _extract_bars

    rows = _extract_bars(_session_payload())
    assert len(rows) == 2
    assert all(r["session"] == "regular" for r in rows)
    assert rows[0]["o"] == 10.0 and rows[1]["o"] == 11.0


def test_extract_bars_all_sessions_labels_each() -> None:
    from services.public_api_adapter import _extract_bars

    rows = _extract_bars(_session_payload(), sessions="all")
    assert len(rows) == 5
    assert [r["session"] for r in rows] == ["pre", "pre", "regular", "regular", "after"]


def test_extract_bars_unknown_bucket_logged_not_regular() -> None:
    from services.public_api_adapter import _extract_bars

    payload = {"overnightBook": {"bars": [
        {"timestamp": "2026-09-04T01:00:00-04:00", "open": 1, "close": 1,
         "high": 1, "low": 1, "volume": 5}]},
        "regularMarket": {"bars": []}}
    assert _extract_bars(payload) == []  # unknown excluded by default
    rows = _extract_bars(payload, sessions="all")
    assert len(rows) == 1 and rows[0]["session"] == "unknown"


def test_extract_bars_legacy_list_shape() -> None:
    from services.public_api_adapter import _extract_bars

    rows = _extract_bars([{"t": "x", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 9}])
    assert rows == []  # session unknown -> excluded by default
    rows = _extract_bars([{"t": "x", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 9}],
                         sessions="all")
    assert len(rows) == 1 and rows[0]["session"] == "unknown"
