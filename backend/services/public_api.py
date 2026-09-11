"""
backend/services/public_api.py

Public.com brokerage API integration — thin async wrapper around the
Public Trading API (https://api.public.com).

Auth: long-lived secret key → short-lived JWT access token.

This is NOT the official publicdotcom-py SDK — it is a lightweight adapter
for the floww backend. Use the SDK for full-featured client work; use this
for direct backend integration where we already own the HTTP transport.

Reference implementation: https://github.com/PublicDotCom/publicdotcom-py
API docs: https://public.com/api/docs

Usage:
    from services.public_api import PublicBroker

    pb = PublicBroker(secret_key="...")
    await pb.auth()
    accounts = await pb.get_accounts()
    trading = pb.get_trading_account()
    quotes = await pb.get_quotes(["AAPL"], account_id=trading.account_id)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://api.public.com"

# Auth
TOKEN_ENDPOINT = f"{BASE_URL}/userapiauthservice/personal/access-tokens"

# Gateway prefix for all trading + marketdata calls
GW = f"{BASE_URL}/userapigateway"

DEFAULT_TOKEN_VALIDITY_MIN = 55  # mint tokens valid for ~55 min (max 1440)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Account:
    account_id: str
    account_type: str
    options_level: str
    brokerage_account_type: str
    trade_permissions: str


@dataclass
class Quote:
    symbol: str
    instrument_type: str
    last: float | None = None
    bid: float | None = None
    ask: float | None = None
    bid_size: int | None = None
    ask_size: int | None = None
    volume: int | None = None
    open_interest: int | None = None
    previous_close: float | None = None
    change: float | None = None
    percent_change: float | None = None
    timestamp: str | None = None
    option_details: dict[str, Any] | None = None
    bond_details: dict[str, Any] | None = None

    @property
    def mid_price(self) -> float | None:
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2
        return None


@dataclass
class Position:
    symbol: str
    instrument_type: str
    quantity: float
    average_cost: float | None = None
    market_value: float | None = None
    total_cost: float | None = None
    pnl: float | None = None
    pnl_pct: float | None = None
    value: float | None = None


@dataclass
class OptionContract:
    symbol: str                # OSI format (e.g. AAPL260918C00150000)
    option_type: str           # CALL or PUT
    strike: float              # in dollars (e.g. 150.00)
    expiration: str            # YYYY-MM-DD
    last: float | None = None
    bid: float | None = None
    ask: float | None = None
    bid_size: int | None = None
    ask_size: int | None = None
    volume: int | None = None
    open_interest: int | None = None
    iv: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None

    @property
    def mid(self) -> float | None:
        """NBBO mid — the executable-reference price for side inference.

        None when no two-sided quote exists; callers must treat a missing
        mid as unknown (proxy reads), never fabricate it from last.
        """
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2
        return None


@dataclass
class Order:
    order_id: str
    account_id: str
    symbol: str
    side: str                 # BUY, SELL
    order_type: str           # MARKET, LIMIT, STOP, STOP_LIMIT
    quantity: float
    filled_quantity: float = 0.0
    price: float | None = None
    limit_price: float | None = None
    stop_price: float | None = None
    status: str = "UNKNOWN"   # PENDING, OPEN, FILLED, CANCELED, REJECTED, etc.
    time_in_force: str = "DAY"
    created_at: str | None = None
    updated_at: str | None = None
    filled_at: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Portfolio:
    account_id: str
    cash: float = 0.0
    total_account_value: float = 0.0
    buying_power: float = 0.0
    options_buying_power: float = 0.0
    available_to_withdraw: float = 0.0
    equity: list[dict[str, Any]] = field(default_factory=list)
    positions: list[Position] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# PublicBroker
# ---------------------------------------------------------------------------


class PublicBroker:
    """Async client for the Public.com brokerage API.

    Token lifecycle:
        - Secret key → access token (JWT, bearer auth) via POST /access-tokens
        - Token validity: 5–1440 min (default 55)
        - Auto-refresh when token is within 30s of expiry

    Endpoints covered:
        - Auth: token mint
        - Accounts: list, trading account helper
        - Portfolio: positions, equity breakdown, buying power, orders
        - Market data: quotes, single/all instruments, option expirations,
          option chain, option greeks, historic bars
        - Trading: place single-leg & multi-leg orders, cancel, get order
        - Preflight: single-leg and multi-leg cost estimates
        - Account: history, unrealized tax lots
    """

    def __init__(
        self,
        secret_key: str,
        token_validity_min: int = DEFAULT_TOKEN_VALIDITY_MIN,
        client: httpx.AsyncClient | None = None,
    ):
        self._secret_key = secret_key
        self._token_validity_min = token_validity_min
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._client = client or self._make_client()
        self._accounts: dict[str, Account] = {}
        self._instrument_cache: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Client
    # ------------------------------------------------------------------

    @staticmethod
    def _make_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=httpx.Timeout(30.0),
            headers={
                "Content-Type": "application/json",
                "User-Agent": "floww-public-api-adapter/1.0",
            },
        )

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def auth(self, validity_min: int | None = None) -> str:
        """Exchange the secret key for a short-lived access token.

        Returns the access token. Caches it internally; subsequent API
        calls reuse the cached token until ~30s before expiry.
        """
        validity = validity_min or self._token_validity_min
        payload = {"validityInMinutes": validity, "secret": self._secret_key}
        log.debug("Minting access token (validity=%d min)", validity)
        resp = await self._client.post(TOKEN_ENDPOINT, json=payload)
        resp.raise_for_status()
        data = resp.json()
        token = data["accessToken"]
        self._access_token = token
        self._token_expires_at = time.time() + validity * 60 - 30
        log.info("Access token minted (valid ~%d min)", validity)
        return token

    def _auth_headers(self) -> dict[str, str]:
        assert self._access_token, "Not authenticated — call auth() first"
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _ensure_token(self) -> None:
        if self._access_token is None or time.time() >= self._token_expires_at:
            await self.auth()

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------

    async def get_accounts(self) -> list[Account]:
        """List all accounts for the authenticated user."""
        await self._ensure_token()
        resp = await self._client.get(f"{GW}/trading/account", headers=self._auth_headers())
        resp.raise_for_status()
        data = resp.json()
        accounts = []
        for a in data.get("accounts", []):
            acct = Account(
                account_id=a["accountId"],
                account_type=a.get("accountType", ""),
                options_level=a.get("optionsLevel", "NONE"),
                brokerage_account_type=a.get("brokerageAccountType", "CASH"),
                trade_permissions=a.get("tradePermissions", ""),
            )
            accounts.append(acct)
            self._accounts[acct.account_id] = acct
        return accounts

    def get_account(self, account_id: str) -> Account | None:
        return self._accounts.get(account_id)

    def get_trading_account(self) -> Account | None:
        """First account with BUY_AND_SELL permissions."""
        for a in self._accounts.values():
            if a.trade_permissions == "BUY_AND_SELL":
                return a
        return None

    # ------------------------------------------------------------------
    # Portfolio (positions, orders, balances)
    # ------------------------------------------------------------------

    async def get_portfolio(self, account_id: str) -> Portfolio:
        """Get portfolio snapshot: positions, orders, cash, buying power.

        Path: GET /userapigateway/trading/{accountId}/portfolio/v2
        """
        await self._ensure_token()
        url = f"{GW}/trading/{account_id}/portfolio/v2"
        resp = await self._client.get(url, headers=self._auth_headers())
        resp.raise_for_status()
        data = resp.json()
        portfolio = self._parse_portfolio(data, account_id)
        return portfolio

    def _parse_portfolio(self, data: dict[str, Any], account_id: str) -> Portfolio:
        positions = []
        for p in data.get("positions", []):
            pos = Position(
                symbol=p.get("instrument", {}).get("symbol", p.get("symbol", "")),
                instrument_type=p.get("instrument", {}).get("type", ""),
                quantity=float(p.get("quantity", 0)),
                average_cost=float(p["averageCost"]) if p.get("averageCost") else None,
                market_value=float(p["marketValue"]) if p.get("marketValue") else None,
                total_cost=float(p["totalCost"]) if p.get("totalCost") else None,
                pnl=float(p["totalGainLoss"]) if p.get("totalGainLoss") else None,
                pnl_pct=float(p["totalGainLossPercentage"]) if p.get("totalGainLossPercentage") else None,
                value=float(p["value"]) if p.get("value") else None,
            )
            positions.append(pos)

        orders = []
        for o in data.get("orders", []):
            ordr = Order(
                order_id=o.get("orderId", o.get("id", "")),
                account_id=account_id,
                symbol=o.get("instrument", {}).get("symbol", o.get("symbol", "")),
                side=o.get("orderSide", o.get("side", "")),
                order_type=o.get("orderType", o.get("type", "")),
                quantity=float(o.get("quantity", o.get("amount", 0))),
                filled_quantity=float(o.get("filledQuantity", o.get("filledAmount", 0))),
                price=float(o["price"]) if o.get("price") else None,
                limit_price=float(o["limitPrice"]) if o.get("limitPrice") else None,
                stop_price=float(o["stopPrice"]) if o.get("stopPrice") else None,
                status=o.get("status", "UNKNOWN"),
                time_in_force=o.get("timeInForce", o.get("expiration", {}).get("timeInForce", "DAY")),
                created_at=o.get("createdAt") or o.get("created_at"),
                updated_at=o.get("updatedAt") or o.get("updated_at"),
                filled_at=o.get("filledAt") or o.get("filled_at"),
                raw=o,
            )
            orders.append(ordr)

        return Portfolio(
            account_id=account_id,
            cash=float(data.get("cash", 0)),
            total_account_value=float(data.get("totalAccountValue", data.get("total_account_value", 0))),
            buying_power=float(data.get("buyingPower", {}).get("buyingPower", 0)),
            options_buying_power=float(data.get("buyingPower", {}).get("optionsBuyingPower", 0)),
            available_to_withdraw=float(data.get("availableToWithdraw", {}).get("availableToWithdraw", 0)),
            equity=data.get("equity", []),
            positions=positions,
            orders=orders,
            raw=data,
        )

    async def get_positions(self, account_id: str) -> list[Position]:
        """Convenience: positions from portfolio."""
        p = await self.get_portfolio(account_id)
        return p.positions

    async def get_open_orders(self, account_id: str) -> list[Order]:
        """Return non-terminal orders from portfolio."""
        p = await self.get_portfolio(account_id)
        return [o for o in p.orders if o.status not in ("FILLED", "CANCELED", "REJECTED")]

    # ------------------------------------------------------------------
    # Market Data — Quotes
    # ------------------------------------------------------------------

    async def get_quotes(
        self,
        symbols: list[str],
        account_id: str,
        instrument_type: str = "EQUITY",
    ) -> list[Quote]:
        """Real-time quotes for symbols.

        Path: POST /userapigateway/marketdata/{accountId}/quotes
        Body: {"instruments": [{"symbol": "AAPL", "type": "EQUITY"}, ...]}
        """
        await self._ensure_token()
        instruments = [{"symbol": s, "type": instrument_type} for s in symbols]
        payload = {"instruments": instruments}
        url = f"{GW}/marketdata/{account_id}/quotes"
        resp = await self._client.post(url, json=payload, headers=self._auth_headers())
        resp.raise_for_status()
        data = resp.json()
        quotes = []
        for q in data.get("quotes", []):
            inst = q.get("instrument", {})
            od = q.get("optionDetails")
            bd = q.get("bondDetails")
            odc = q.get("oneDayChange", {})
            quote = Quote(
                symbol=inst.get("symbol", ""),
                instrument_type=inst.get("type", instrument_type),
                last=float(q["last"]) if q.get("last") is not None else None,
                bid=float(q["bid"]) if q.get("bid") is not None else None,
                ask=float(q["ask"]) if q.get("ask") is not None else None,
                bid_size=int(q["bidSize"]) if q.get("bidSize") is not None else None,
                ask_size=int(q["askSize"]) if q.get("askSize") is not None else None,
                volume=int(q["volume"]) if q.get("volume") is not None else None,
                open_interest=int(q["openInterest"]) if q.get("openInterest") is not None else None,
                previous_close=float(q["previousClose"]) if q.get("previousClose") is not None else None,
                change=float(odc.get("change")) if odc.get("change") is not None else None,
                percent_change=float(odc.get("percentChange")) if odc.get("percentChange") is not None else None,
                timestamp=q.get("lastTimestamp"),
                option_details=od,
                bond_details=bd,
            )
            quotes.append(quote)
        return quotes

    # ------------------------------------------------------------------
    # Market Data — Instruments
    # ------------------------------------------------------------------

    async def get_instrument(
        self,
        symbol: str,
        instrument_type: str,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        """Get a single instrument's metadata.

        Path: GET /userapigateway/trading/instruments/{symbol}/{type}
        """
        await self._ensure_token()
        url = f"{GW}/trading/instruments/{symbol}/{instrument_type}"
        resp = await self._client.get(url, headers=self._auth_headers())
        resp.raise_for_status()
        data = resp.json()
        self._instrument_cache[f"{symbol}:{instrument_type}"] = data
        return data

    async def get_all_instruments(
        self,
        account_id: str | None = None,
        type_filter: list[str] | None = None,
        trading_filter: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """List all tradable instruments with optional filters.

        Path: GET /userapigateway/trading/instruments
        """
        await self._ensure_token()
        params: dict[str, Any] = {}
        if type_filter:
            params["type"] = type_filter
        if trading_filter:
            params["trading"] = trading_filter
        url = f"{GW}/trading/instruments"
        resp = await self._client.get(url, params=params or None, headers=self._auth_headers())
        resp.raise_for_status()
        data = resp.json()
        return data.get("instruments", [])

    # ------------------------------------------------------------------
    # Market Data — Option Chains & Greeks
    # ------------------------------------------------------------------

    async def get_option_expirations(
        self,
        symbol: str,
        account_id: str,
        instrument_type: str = "EQUITY",
    ) -> list[str]:
        """Available option expiration dates for an underlying.

        Path: POST /userapigateway/marketdata/{accountId}/option-expirations
        Body: {"instrument": {"symbol": "AAPL", "type": "EQUITY"}}
        """
        await self._ensure_token()
        payload = {"instrument": {"symbol": symbol, "type": instrument_type}}
        url = f"{GW}/marketdata/{account_id}/option-expirations"
        resp = await self._client.post(url, json=payload, headers=self._auth_headers())
        resp.raise_for_status()
        data = resp.json()
        return data.get("expirations", [])

    async def get_option_chain(
        self,
        symbol: str,
        expiration: str,
        account_id: str,
        instrument_type: str = "EQUITY",
    ) -> dict[str, Any]:
        """Full option chain for a single expiration (calls + puts).

        Path: POST /userapigateway/marketdata/{accountId}/option-chain
        Body: {"instrument": {"symbol": "AAPL", "type": "EQUITY"}, "expirationDate": "2026-09-18"}
        """
        await self._ensure_token()
        payload = {
            "instrument": {"symbol": symbol, "type": instrument_type},
            "expirationDate": expiration,
        }
        url = f"{GW}/marketdata/{account_id}/option-chain"
        resp = await self._client.post(url, json=payload, headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def get_option_greeks(
        self,
        osi_symbols: list[str],
        account_id: str,
    ) -> dict[str, Any]:
        """Greeks for OSI-normalized option symbols (max 250 per call).

        Path: GET /userapigateway/option-details/{accountId}/greeks?osiSymbols=...
        """
        await self._ensure_token()
        url = f"{GW}/option-details/{account_id}/greeks"
        resp = await self._client.get(url, params={"osiSymbols": osi_symbols}, headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    def _parse_option_contract(self, inst: dict[str, Any], quote_data: dict[str, Any]) -> OptionContract:
        """Parse one option contract from the chain response into OptionContract."""
        sym = inst.get("symbol", "")
        otype = "CALL" if "C" in sym[-9:-8] else "PUT" if "P" in sym[-9:-8] else ""
        # OSI format: SYMBOL + YYMMDD + C/P + 8-digit strike
        # extract strike: last 8 chars before C/P
        import re
        m = re.match(r"([A-Z]+)(\d{6})([CP])(\d{8})", sym)
        strike = float(m.group(4)) / 1000 if m else 0.0
        exp_str = ""
        if m:
            y = int(m.group(2)[:2])
            mth = int(m.group(2)[2:4])
            d = int(m.group(2)[4:6])
            exp_str = f"20{y:02d}-{mth:02d}-{d:02d}"

        od = quote_data.get("optionDetails", {})
        greeks = od.get("greeks", {}) if od else {}
        try:
            bid_size = int(quote_data["bidSize"]) if quote_data.get("bidSize") is not None else None
        except (TypeError, ValueError):
            bid_size = None
        try:
            ask_size = int(quote_data["askSize"]) if quote_data.get("askSize") is not None else None
        except (TypeError, ValueError):
            ask_size = None
        return OptionContract(
            symbol=sym,
            option_type=otype,
            strike=strike,
            expiration=exp_str,
            last=float(quote_data["last"]) if quote_data.get("last") is not None else None,
            bid=float(quote_data["bid"]) if quote_data.get("bid") is not None else None,
            ask=float(quote_data["ask"]) if quote_data.get("ask") is not None else None,
            bid_size=bid_size,
            ask_size=ask_size,
            volume=int(quote_data["volume"]) if quote_data.get("volume") is not None else None,
            open_interest=int(quote_data["openInterest"]) if quote_data.get("openInterest") is not None else None,
            iv=float(greeks.get("impliedVolatility")) if greeks.get("impliedVolatility") is not None else None,
            delta=float(greeks.get("delta")) if greeks.get("delta") is not None else None,
            gamma=float(greeks.get("gamma")) if greeks.get("gamma") is not None else None,
            theta=float(greeks.get("theta")) if greeks.get("theta") is not None else None,
            vega=float(greeks.get("vega")) if greeks.get("vega") is not None else None,
        )

    async def get_option_chain_parsed(
        self,
        symbol: str,
        expiration: str,
        account_id: str,
        instrument_type: str = "EQUITY",
    ) -> dict[str, list[OptionContract]]:
        """Get option chain with contracts parsed into OptionContract objects.

        Returns {"calls": [...], "puts": [...]}.
        """
        chain = await self.get_option_chain(symbol, expiration, account_id, instrument_type)
        result: dict[str, list[OptionContract]] = {"calls": [], "puts": []}
        for side in ("calls", "puts"):
            for contract_data in chain.get(side, []):
                inst = contract_data.get("instrument", {})
                oc = self._parse_option_contract(inst, contract_data)
                result[side].append(oc)
        return result

    # ------------------------------------------------------------------
    # Market Data — Historic Bars
    # ------------------------------------------------------------------

    async def get_bars(
        self,
        symbol: str,
        period: str,
        instrument_type: str = "EQUITY",
        aggregation: str | None = None,
        trading_session_toggle: str | None = None,
        ipo_date: str | None = None,
        purchase_date: str | None = None,
    ) -> dict[str, Any]:
        """OHLCV bar data for a symbol.

        Path: GET /userapigateway/historicdata/{instrumentType}/{symbol}/{period}[/{aggregation}]
        Periods: DAY, WEEK, MONTH, QUARTER, HALF_YEAR, YEAR, FIVE_YEARS, TEN_YEARS, ALL, YTD, SINCE_PURCHASE
        Aggregations: ONE_MINUTE, FIVE_MINUTES, TEN_MINUTES, FIFTEEN_MINUTES, THIRTY_MINUTES,
                      ONE_HOUR, ONE_DAY, ONE_WEEK, ONE_MONTH, THREE_MONTHS, SIX_MONTHS, ONE_YEAR
        """
        await self._ensure_token()
        path = f"{GW}/historicdata/{instrument_type}/{symbol}/{period}"
        if aggregation:
            path += f"/{aggregation}"
        params: dict[str, Any] = {}
        if trading_session_toggle:
            params["tradingSessionToggle"] = trading_session_toggle
        if ipo_date:
            params["ipoDate"] = ipo_date
        if purchase_date:
            params["purchaseDate"] = purchase_date
        resp = await self._client.get(path, params=params or None, headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Trading — Preflight
    # ------------------------------------------------------------------

    async def preflight_single_leg(
        self,
        account_id: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        limit_price: float | None = None,
        stop_price: float | None = None,
        time_in_force: str = "DAY",
        instrument_type: str = "EQUITY",
        equity_market_session: str | None = None,
        validate_order: bool = True,
    ) -> dict[str, Any]:
        """Cost estimate for a single-leg order before placing it.

        Path: POST /userapigateway/trading/{accountId}/preflight/single-leg
        """
        await self._ensure_token()
        payload: dict[str, Any] = {
            "instrument": {"symbol": symbol, "type": instrument_type},
            "orderSide": side,
            "orderType": order_type,
            "expiration": {"timeInForce": time_in_force},
            "quantity": str(quantity),
            "validateOrder": validate_order,
        }
        if limit_price is not None:
            payload["limitPrice"] = str(limit_price)
        if stop_price is not None:
            payload["stopPrice"] = str(stop_price)
        if instrument_type == "EQUITY" and equity_market_session:
            payload["equityMarketSession"] = equity_market_session
        url = f"{GW}/trading/{account_id}/preflight/single-leg"
        resp = await self._client.post(url, json=payload, headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def preflight_multi_leg(
        self,
        account_id: str,
        legs: list[dict[str, Any]],
        order_type: str = "LIMIT",
        quantity: int = 1,
        limit_price: float | None = None,
        stop_price: float | None = None,
        time_in_force: str = "DAY",
        expiration_time: str | None = None,
        validate_order: bool = True,
    ) -> dict[str, Any]:
        """Cost estimate for a multi-leg spread/strategy order.

        Path: POST /userapigateway/trading/{accountId}/preflight/multi-leg
        """
        await self._ensure_token()
        expiration: dict[str, Any] = {"timeInForce": time_in_force}
        if expiration_time:
            expiration["expirationTime"] = expiration_time
        payload: dict[str, Any] = {
            "orderType": order_type,
            "expiration": expiration,
            "quantity": quantity,
            "legs": legs,
            "validateOrder": validate_order,
        }
        if limit_price is not None:
            payload["limitPrice"] = str(limit_price)
        if stop_price is not None:
            payload["stopPrice"] = str(stop_price)
        url = f"{GW}/trading/{account_id}/preflight/multi-leg"
        resp = await self._client.post(url, json=payload, headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Trading — Place Order (single-leg)
    # ------------------------------------------------------------------

    async def place_order(
        self,
        account_id: str,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        limit_price: float | None = None,
        stop_price: float | None = None,
        time_in_force: str = "DAY",
        instrument_type: str = "EQUITY",
        equity_market_session: str | None = None,
        order_id: str | None = None,
        use_margin: bool = True,
    ) -> Order:
        """Place a single-leg equity/options/crypto/bond order.

        Path: POST /userapigateway/trading/{accountId}/order
        Required: orderId (UUID), instrument, orderSide, orderType, expiration, quantity
        """
        await self._ensure_token()
        if order_id is None:
            import uuid
            order_id = str(uuid.uuid4())

        payload: dict[str, Any] = {
            "orderId": order_id,
            "instrument": {"symbol": symbol, "type": instrument_type},
            "orderSide": side,
            "orderType": order_type,
            "expiration": {"timeInForce": time_in_force},
            "quantity": str(quantity),
        }
        if limit_price is not None:
            payload["limitPrice"] = str(limit_price)
        if stop_price is not None:
            payload["stopPrice"] = str(stop_price)
        if instrument_type == "EQUITY" and equity_market_session:
            payload["equityMarketSession"] = equity_market_session
        if not use_margin:
            payload["useMargin"] = False

        url = f"{GW}/trading/{account_id}/order"
        resp = await self._client.post(url, json=payload, headers=self._auth_headers())
        resp.raise_for_status()
        data = resp.json()
        return self._parse_order(data, account_id)

    async def place_market_order(
        self,
        account_id: str,
        symbol: str,
        side: str,
        quantity: float,
        instrument_type: str = "EQUITY",
        equity_market_session: str | None = None,
    ) -> Order:
        """Place a market order (convenience)."""
        return await self.place_order(
            account_id=account_id,
            symbol=symbol,
            side=side,
            order_type="MARKET",
            quantity=quantity,
            instrument_type=instrument_type,
            equity_market_session=equity_market_session,
        )

    async def place_limit_order(
        self,
        account_id: str,
        symbol: str,
        side: str,
        quantity: float,
        limit_price: float,
        time_in_force: str = "DAY",
        instrument_type: str = "EQUITY",
        equity_market_session: str | None = None,
    ) -> Order:
        """Place a limit order (convenience)."""
        return await self.place_order(
            account_id=account_id,
            symbol=symbol,
            side=side,
            order_type="LIMIT",
            quantity=quantity,
            limit_price=limit_price,
            time_in_force=time_in_force,
            instrument_type=instrument_type,
            equity_market_session=equity_market_session,
        )

    async def place_stop_order(
        self,
        account_id: str,
        symbol: str,
        side: str,
        quantity: float,
        stop_price: float,
        time_in_force: str = "DAY",
        instrument_type: str = "EQUITY",
        equity_market_session: str | None = None,
    ) -> Order:
        """Place a stop order (convenience)."""
        return await self.place_order(
            account_id=account_id,
            symbol=symbol,
            side=side,
            order_type="STOP",
            quantity=quantity,
            stop_price=stop_price,
            time_in_force=time_in_force,
            instrument_type=instrument_type,
            equity_market_session=equity_market_session,
        )

    # ------------------------------------------------------------------
    # Trading — Multi-leg Orders
    # ------------------------------------------------------------------

    async def place_multileg_order(
        self,
        account_id: str,
        legs: list[dict[str, Any]],
        order_type: str = "LIMIT",
        quantity: int = 1,
        limit_price: float | None = None,
        stop_price: float | None = None,
        time_in_force: str = "DAY",
        expiration_time: str | None = None,
        order_id: str | None = None,
        use_margin: bool = True,
    ) -> Order:
        """Place a multi-leg spread option order.

        Path: POST /userapigateway/trading/{accountId}/order/multileg
        Each leg: {"instrument": {"symbol": "OSI_SYMBOL", "type": "OPTION"},
                   "side": "BUY"/"SELL",
                   "openCloseIndicator": "OPEN"/"CLOSE",
                   "ratioQuantity": 1}
        """
        await self._ensure_token()
        if order_id is None:
            import uuid
            order_id = str(uuid.uuid4())

        expiration: dict[str, Any] = {"timeInForce": time_in_force}
        if expiration_time:
            expiration["expirationTime"] = expiration_time

        payload: dict[str, Any] = {
            "orderId": order_id,
            "orderType": order_type,
            "expiration": expiration,
            "quantity": quantity,
            "legs": legs,
        }
        if limit_price is not None:
            payload["limitPrice"] = str(limit_price)
        if stop_price is not None:
            payload["stopPrice"] = str(stop_price)
        if not use_margin:
            payload["useMargin"] = False

        url = f"{GW}/trading/{account_id}/order/multileg"
        resp = await self._client.post(url, json=payload, headers=self._auth_headers())
        resp.raise_for_status()
        data = resp.json()
        return self._parse_order(data, account_id)

    # ------------------------------------------------------------------
    # Trading — Cancel / Get Order
    # ------------------------------------------------------------------

    async def cancel_order(self, account_id: str, order_id: str) -> dict[str, Any]:
        """Cancel an open order.

        Path: POST /userapigateway/trading/{accountId}/order/{orderId}/cancel
        """
        await self._ensure_token()
        url = f"{GW}/trading/{account_id}/order/{order_id}/cancel"
        resp = await self._client.post(url, headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def get_order(self, account_id: str, order_id: str) -> Order:
        """Get order status and details.

        Path: GET /userapigateway/trading/{accountId}/order/{orderId}
        """
        await self._ensure_token()
        url = f"{GW}/trading/{account_id}/order/{order_id}"
        resp = await self._client.get(url, headers=self._auth_headers())
        resp.raise_for_status()
        data = resp.json()
        return self._parse_order(data, account_id)

    # ------------------------------------------------------------------
    # Account — History & Tax Lots
    # ------------------------------------------------------------------

    async def get_history(
        self,
        account_id: str,
        page_size: int | None = None,
        start: str | None = None,
        end: str | None = None,
        next_token: str | None = None,
    ) -> dict[str, Any]:
        """Paginated account history (trades, transfers, adjustments).

        Path: GET /userapigateway/trading/{accountId}/history
        """
        await self._ensure_token()
        params: dict[str, Any] = {}
        if page_size:
            params["pageSize"] = page_size
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        if next_token:
            params["nextToken"] = next_token
        url = f"{GW}/trading/{account_id}/history"
        resp = await self._client.get(url, params=params or None, headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def get_unrealized_tax_lots(self, account_id: str) -> dict[str, Any]:
        """Unrealized P/L by tax lot.

        Path: GET /userapigateway/trading/{accountId}/taxlots/unrealized
        """
        await self._ensure_token()
        url = f"{GW}/trading/{account_id}/taxlots/unrealized"
        resp = await self._client.get(url, headers=self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_order(data: dict[str, Any], account_id: str) -> Order:
        """Parse an order response (from place-order, get-order, or portfolio)."""
        o = data.get("order", data)  # some endpoints wrap in {"order": ...}
        inst = o.get("instrument", {})
        return Order(
            order_id=o.get("orderId", o.get("id", "")),
            account_id=account_id,
            symbol=inst.get("symbol", o.get("symbol", "")),
            side=o.get("orderSide", o.get("side", "")),
            order_type=o.get("orderType", o.get("type", "")),
            quantity=float(o.get("quantity", o.get("amount", 0))),
            filled_quantity=float(o.get("filledQuantity", o.get("filledAmount", 0))),
            price=float(o["price"]) if o.get("price") is not None else None,
            limit_price=float(o["limitPrice"]) if o.get("limitPrice") is not None else None,
            stop_price=float(o["stopPrice"]) if o.get("stopPrice") is not None else None,
            status=o.get("status", "UNKNOWN"),
            time_in_force=o.get("timeInForce", o.get("expiration", {}).get("timeInForce", "DAY")),
            created_at=o.get("createdAt") or o.get("created_at"),
            updated_at=o.get("updatedAt") or o.get("updated_at"),
            filled_at=o.get("filledAt") or o.get("filled_at"),
            raw=data,
        )


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------


async def create_broker(
    secret_key: str,
    token_validity_min: int = DEFAULT_TOKEN_VALIDITY_MIN,
) -> PublicBroker:
    """Create, authenticate, and load accounts in one call."""
    pb = PublicBroker(secret_key=secret_key, token_validity_min=token_validity_min)
    await pb.auth()
    await pb.get_accounts()
    return pb


# ---------------------------------------------------------------------------
# __main__ — smoke test against live API
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    async def _main():
        secret = os.environ.get("PUBLIC_API_KEY", "")
        pb = await create_broker(secret)
        try:
            accounts = list(pb._accounts.values())
            print(f"Accounts ({len(accounts)}):")
            for a in accounts:
                print(f"  {a.account_id}  {a.account_type:12s}  {a.brokerage_account_type:6s}  "
                      f"opts={a.options_level:6s}  perm={a.trade_permissions}")

            trading = pb.get_trading_account()
            if not trading:
                print("\nNo trading account — nothing to do")
                return

            print(f"\nTrading account: {trading.account_id}")

            # Portfolio
            portfolio = await pb.get_portfolio(trading.account_id)
            print("\nPortfolio:")
            print(f"  Cash: ${portfolio.cash:.2f}")
            print(f"  Total value: ${portfolio.total_account_value:.2f}")
            print(f"  Buying power: ${portfolio.buying_power:.2f}")
            print(f"  Options BP: ${portfolio.options_buying_power:.2f}")
            print(f"  Positions: {len(portfolio.positions)}")
            for p in portfolio.positions:
                print(f"    {p.symbol:8s}  qty={p.quantity}  "
                      f"avg=${p.average_cost}  val=${p.market_value}  "
                      f"P/L=${p.pnl} ({p.pnl_pct}%)")
            print(f"  Open orders: {len(portfolio.orders)}")
            for o in portfolio.orders:
                print(f"    {o.order_id[:8]}... {o.side} {o.order_type} "
                      f"{o.symbol} qty={o.quantity} status={o.status}")

            # Quotes
            quotes = await pb.get_quotes(["AAPL", "TSLA", "NVDA"], account_id=trading.account_id)
            print(f"\nQuotes ({len(quotes)}):")
            for q in quotes:
                print(f"  {q.symbol:6s}  last={q.last}  bid={q.bid}  ask={q.ask}  "
                      f"mid={q.mid_price}  chg={q.change}  %={q.percent_change}")

            # Option chain for AAPL nearest expiry
            exps = await pb.get_option_expirations("AAPL", trading.account_id)
            if exps:
                nearest = exps[0]
                print(f"\nAAPL options exp {nearest}:")
                chain = await pb.get_option_chain_parsed("AAPL", nearest, trading.account_id)
                for side in ("calls", "puts"):
                    contracts = chain[side][:3]
                    print(f"  {side.upper()} ({len(chain[side])} total):")
                    for c in contracts:
                        g = f"Δ={c.delta} Γ={c.gamma} ν={c.vega}" if c.delta is not None else ""
                        print(f"    {c.symbol}  K=${c.strike:.2f}  "
                              f"bid={c.bid}  ask={c.ask}  vol={c.volume}  OI={c.open_interest}  {g}")

            # Instrument lookup
            inst = await pb.get_instrument("AAPL", "EQUITY")
            print(f"\nAAPL instrument: trading={inst.get('trading')}  "
                  f"fractional={inst.get('fractionalTrading')}  "
                  f"shorting={inst.get('shortingAvailability')}")

            # Bars (last 5 regular-market bars of today)
            bars = await pb.get_bars("AAPL", "DAY", aggregation="FIVE_MINUTES")
            reg = bars.get("regularMarket", {}).get("bars", [])
            print(f"\nAAPL 5min bars today ({len(reg)} bars):")
            for b in reg[-5:]:
                print(f"  {b['timestamp'][:16]}  O={b['open']}  H={b['high']}  "
                      f"L={b['low']}  C={b['close']}  V={b['volume']}")

            # Preflight — requires sufficient buying power on the account.
            # This test account only has $20, so we skip a live preflight.
            # To test: use an account with margin, or pick a stock below
            # buying_power / 0.5 (margin requirement for long equity).
            print("\nPreflight: use pb.preflight_single_leg() with an account "
                  "that has sufficient buying power")

        finally:
            await pb.close()

    asyncio.run(_main())
