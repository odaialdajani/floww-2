from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routes import public_brokerage as brokerage


@pytest.mark.asyncio
async def test_portfolio_preserves_unknown_values_and_fractional_positions(monkeypatch):
    positions = [
        SimpleNamespace(symbol="KNOWN", quantity="1.5", cost_basis="100", current_value="120",
                        last_price="80", instrument={"type": "EQUITY"},
                        position_daily_gain={"gainPercentage": "2.5"}),
        SimpleNamespace(symbol="UNKNOWN", quantity=None, cost_basis=None, current_value=None,
                        last_price=None, instrument={}, position_daily_gain={}),
        SimpleNamespace(symbol="ZERO", quantity="0", cost_basis="0", current_value="0",
                        last_price="0", raw={"currentValue": "999"}, instrument={"type": "OPTION"},
                        position_daily_gain={"gainPercentage": "0"}),
    ]
    broker = SimpleNamespace(
        get_trading_account=lambda: SimpleNamespace(account_id="fixture"),
        get_portfolio=AsyncMock(return_value=SimpleNamespace(positions=positions)),
    )
    monkeypatch.setattr(brokerage, "_get_broker", AsyncMock(return_value=broker))
    result = await brokerage.get_portfolio()
    by_symbol = {p["symbol"]: p for p in result["positions"]}
    assert by_symbol["KNOWN"]["quantity"] == 1.5
    assert by_symbol["KNOWN"]["pnl"] == 20
    assert by_symbol["KNOWN"]["total_gain_pct"] == 20
    assert by_symbol["KNOWN"]["day_gain_pct"] == 2.5
    for field in ("quantity", "current_price", "cost_basis", "market_value", "pnl", "total_gain_pct", "day_gain_pct"):
        assert by_symbol["UNKNOWN"][field] is None, field
    assert by_symbol["UNKNOWN"]["asset_type"] == "UNKNOWN"
    assert by_symbol["ZERO"]["market_value"] == 0
    assert by_symbol["ZERO"]["day_gain_pct"] == 0
    assert by_symbol["ZERO"]["total_gain_pct"] is None
    assert result["portfolio_value"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [True, "", "nan", "inf", "bad"])
async def test_invalid_position_amounts_are_unavailable(monkeypatch, bad):
    broker = SimpleNamespace(
        get_trading_account=lambda: SimpleNamespace(account_id="fixture"),
        get_portfolio=AsyncMock(return_value=SimpleNamespace(positions=[
            SimpleNamespace(symbol="SPY", cost_basis=bad, current_value="100")
        ])),
    )
    monkeypatch.setattr(brokerage, "_get_broker", AsyncMock(return_value=broker))
    position = (await brokerage.get_portfolio())["positions"][0]
    assert position["cost_basis"] is None
    assert position["pnl"] is None
    assert position["total_gain_pct"] is None


@pytest.mark.asyncio
async def test_documented_portfolio_response_reaches_route_without_losing_fields(monkeypatch):
    from services.public_api import PublicBroker

    # Documented /portfolio/v2 fields; no broker client or network is created.
    payload = {"positions": [{"instrument": {"symbol": "SPY", "name": "SPY Fund", "type": "EQUITY"},
        "quantity": "1.5", "currentValue": "120", "lastPrice": {"lastPrice": "80"},
        "costBasis": {"totalCost": "100", "unitCost": "66.6667", "gainValue": "20", "gainPercentage": "20"},
        "positionDailyGain": {"gainPercentage": "2.5"}}], "orders": [], "cash": "0"}
    parsed = PublicBroker._parse_portfolio(None, payload, "fixture")
    broker = SimpleNamespace(get_trading_account=lambda: SimpleNamespace(account_id="fixture"),
        get_portfolio=AsyncMock(return_value=parsed))
    monkeypatch.setattr(brokerage, "_get_broker", AsyncMock(return_value=broker))
    result = await brokerage.get_portfolio()
    position = result["positions"][0]
    assert position["market_value"] == 120
    assert position["cost_basis"] == 100
    assert position["pnl"] == 20
    assert position["total_gain_pct"] == 20
    assert position["day_gain_pct"] == 2.5
    assert position["current_price"] == 80
    assert position["asset_type"] == "EQUITY"
    assert position["quantity"] == 1.5
    assert result["cash"] == 0
    for field in ("buying_power", "portfolio_value", "initial_margin", "maintenance_margin"):
        assert result[field] is None, field


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, "bad", "nan", "inf", True])
async def test_actual_portfolio_decoder_preserves_unavailable_balances_and_quantities(monkeypatch, value):
    from services.public_api import PublicBroker

    parsed = PublicBroker._parse_portfolio(None, {"positions": [{"instrument": {"symbol": "SPY"}, "quantity": value}],
        "orders": [], "cash": value, "buyingPower": None, "totalAccountValue": value}, "fixture")
    broker = SimpleNamespace(get_trading_account=lambda: SimpleNamespace(account_id="fixture"),
        get_portfolio=AsyncMock(return_value=parsed))
    monkeypatch.setattr(brokerage, "_get_broker", AsyncMock(return_value=broker))
    result = await brokerage.get_portfolio()
    assert result["positions"][0]["quantity"] is None
    assert result["cash"] is None
    assert result["buying_power"] is None
    assert result["portfolio_value"] is None
