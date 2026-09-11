"""
Public.com Brokerage Tab — Trading Group
=========================================
Router prefix is `/public` mounted at `/api`, so the live paths are:

GET /api/public/portfolio — fetch the authenticated Public.com account
  portfolio positions, buying power, equity, cash, and account metadata.

GET /api/public/orders — list open + recent filled orders.

GET /api/public/account — account-level metadata.

POST /api/public/order — place a single-leg order.
  Body: {"symbol": "SPY260904C00760000", "side": "BUY", "order_type": "MARKET",
         "quantity": 1, "limit_price": 3.15, "stop_price": null,
         "time_in_force": "DAY", "instrument_type": "OPTION"}

POST /api/public/order/{order_id}/cancel — cancel an open order.

Paper trading mode by default — no live orders until the user explicitly
connects a live account and generates a secret key at
public.com/settings/security/api.

Mounted at /api/public alongside /api/public/chain + /api/public/quotes
from routes/public_api.py.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from services.public_api_adapter import _get_broker

log = logging.getLogger(__name__)

router = APIRouter(prefix="/public", tags=["public_brokerage"])
__all__ = ["router"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_money(value: Any) -> float:
    """Parse a money value that may be str, float, int, or None."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0
    return 0.0


def _parse_int(value: Any) -> int:
    """Parse an int value that may be str, int, or None."""
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return 0
    return 0


# ---------------------------------------------------------------------------
# GET /portfolio
# ---------------------------------------------------------------------------

@router.get("/portfolio")
async def get_portfolio() -> dict[str, Any]:
    """Return the authenticated Public.com account: portfolio positions,
    buying power, equity, cash, and account metadata.

    Returns 502 when PUBLIC_API_KEY is not set, invalid, or API is unreachable.
    """
    broker = await _get_broker()
    if broker is None:
        raise HTTPException(status_code=502, detail={
            "error": "no_public_api_key",
            "message": (
                "Public.com API key not configured. "
                "Generate a secret key at public.com/settings/security/api "
                "and set PUBLIC_API_KEY in your environment."
            ),
        })

    account = broker.get_trading_account()
    if account is None:
        raise HTTPException(status_code=502, detail={
            "error": "no_account",
            "message": "No Public.com trading account found for this key.",
        })

    try:
        portfolio = await broker.get_portfolio(account.account_id)
    except Exception as exc:
        log.warning("Public.com portfolio fetch failed: %s", exc)
        raise HTTPException(status_code=502, detail={
            "error": "api_error",
            "message": f"Public.com API error: {exc}",
        }) from exc

    # Flatten positions into a clean list the frontend can render directly.
    # The adapter returns raw objects with string fields — normalize to numbers.
    positions: list[dict[str, Any]] = []
    for pos in (portfolio.positions or []):
        try:
            raw = getattr(pos, "raw", {}) or {}
            if not isinstance(raw, dict):
                raw = {}
            instrument = getattr(pos, "instrument", {}) or {}
            if not isinstance(instrument, dict):
                instrument = {}

            cost_basis = _parse_money(
                getattr(pos, "cost_basis", None)
                or (raw.get("costBasis", {}) or {}).get("totalCost")
                or (instrument.get("costBasis", {}) or {}).get("totalCost")
            )
            current_value = _parse_money(
                getattr(pos, "current_value", None)
                or raw.get("currentValue")
                or (instrument.get("currentValue") if isinstance(instrument, dict) else None)
            )
            pnl = current_value - cost_basis

            day_gain_raw = (
                getattr(pos, "position_daily_gain", None)
                or raw.get("positionDailyGain")
                or {}
            )
            if isinstance(day_gain_raw, dict):
                day_gain_pct = _parse_money(day_gain_raw.get("gainPercentage"))
            else:
                day_gain_pct = _parse_money(day_gain_raw)

            instrument_type = (
                instrument.get("type", "EQUITY") if isinstance(instrument, dict) else "EQUITY"
            )

            positions.append({
                "symbol": (
                    getattr(pos, "symbol", "")
                    or (instrument.get("symbol") if isinstance(instrument, dict) else "")
                ),
                "name": (
                    getattr(pos, "name", "")
                    or (instrument.get("name") if isinstance(instrument, dict) else "")
                ),
                "quantity": _parse_int(
                    getattr(pos, "quantity", None)
                    or raw.get("quantity")
                    or (instrument.get("quantity") if isinstance(instrument, dict) else None)
                ),
                "current_price": _parse_money(
                    getattr(pos, "last_price", None)
                    or (raw.get("lastPrice") if isinstance(raw, dict) else None)
                    or ((instrument.get("lastPrice") or {}).get("lastPrice") if isinstance(instrument, dict) else None)
                ),
                "market_value": current_value,
                "cost_basis": cost_basis,
                "day_gain_pct": day_gain_pct,
                "total_gain_pct": (pnl / cost_basis * 100) if cost_basis else 0,
                "pnl": pnl,
                "asset_type": instrument_type,
                "bid": _parse_money(
                    getattr(pos, "current_price", None)
                    or (raw.get("bid") if isinstance(raw, dict) else None)
                ),
                "ask": _parse_money(
                    getattr(pos, "current_price", None)
                    or (raw.get("ask") if isinstance(raw, dict) else None)
                ),
            })
        except Exception as pos_exc:
            log.debug("Skipping malformed position: %s (%s)", pos, pos_exc)
            continue

    positions.sort(key=lambda p: abs(p["market_value"]), reverse=True)

    # Account-level money fields live on Portfolio, not Account.
    # Account is just identity (account_id, permissions, etc.).
    buying_power = _parse_money(getattr(portfolio, "buying_power", 0))
    cash = _parse_money(getattr(portfolio, "cash", 0))
    options_buying_power = _parse_money(getattr(portfolio, "options_buying_power", 0))
    total_account_value = _parse_money(getattr(portfolio, "total_account_value", 0))

    return {
        "ok": True,
        "account_id": getattr(account, "account_id", ""),
        "buying_power": buying_power,
        "options_buying_power": options_buying_power,
        "cash": cash,
        "initial_margin": _parse_money(getattr(account, "initial_margin", 0)),
        "maintenance_margin": _parse_money(getattr(account, "maintenance_margin", 0)),
        "portfolio_value": total_account_value,
        "positions": positions,
        "position_count": len(positions),
        "data_source": "public_api",
    }


# ---------------------------------------------------------------------------
# GET /orders
# ---------------------------------------------------------------------------

@router.get("/orders")
async def get_orders() -> dict[str, Any]:
    """Return open + recent filled orders from Public.com."""
    broker = await _get_broker()
    if broker is None:
        raise HTTPException(status_code=502, detail={
            "error": "no_public_api_key",
            "message": "Public.com API key not configured.",
        })

    account = broker.get_trading_account()
    if account is None:
        raise HTTPException(status_code=502, detail={"error": "no_account"})

    try:
        # Use portfolio (includes all recent orders, not just open).
        portfolio = await broker.get_portfolio(account.account_id)
        orders_raw = portfolio.orders
    except Exception as exc:
        log.warning("Public.com orders fetch failed: %s", exc)
        raise HTTPException(status_code=502, detail={
            "error": "api_error",
            "message": f"Public.com API error: {exc}",
        }) from exc

    order_list: list[dict[str, Any]] = []
    for o in (orders_raw or []):
        try:
            raw = getattr(o, "raw", {}) or {}
            if not isinstance(raw, dict):
                raw = {}
            order_list.append({
                "order_id": getattr(o, "order_id", "") or raw.get("orderId", ""),
                "symbol": getattr(o, "symbol", "") or (raw.get("instrument", {}) or {}).get("symbol", ""),
                "side": getattr(o, "side", "") or raw.get("side", ""),
                "type": getattr(o, "order_type", "") or raw.get("type", ""),
                "status": getattr(o, "status", "") or raw.get("status", ""),
                "quantity": _parse_int(getattr(o, "quantity", None) or raw.get("quantity")),
                "filled_quantity": _parse_int(
                    getattr(o, "filled_quantity", None)
                    or raw.get("filledQuantity")
                ),
                "price": _parse_money(
                    getattr(o, "price", None)
                    or raw.get("averagePrice")
                ),
                "limit_price": _parse_money(
                    getattr(o, "limit_price", None)
                    or raw.get("limitPrice")
                ),
                "time_in_force": getattr(o, "time_in_force", "") or raw.get("timeInForce", ""),
                "created_at": getattr(o, "created_at", None) or raw.get("createdAt"),
                "updated_at": getattr(o, "updated_at", None) or raw.get("updatedAt"),
                "filled_at": getattr(o, "filled_at", None) or raw.get("filledAt"),
            })
        except Exception:
            continue

    return {
        "ok": True,
        "orders": order_list,
        "order_count": len(order_list),
        "data_source": "public_api",
    }


# ---------------------------------------------------------------------------
# GET /account
# ---------------------------------------------------------------------------

@router.get("/account")
async def get_account() -> dict[str, Any]:
    """Return account-level metadata: id, status, buying power, margin, flags."""
    broker = await _get_broker()
    if broker is None:
        raise HTTPException(status_code=502, detail={
            "error": "no_public_api_key",
            "message": "PUBLIC_API_KEY not set.",
        })

    account = broker.get_trading_account()
    if account is None:
        raise HTTPException(status_code=502, detail={"error": "no_account"})

    acct_raw = getattr(account, "raw", {}) or {}
    if not isinstance(acct_raw, dict):
        acct_raw = {}

    return {
        "ok": True,
        "account_id": getattr(account, "account_id", ""),
        "account_number": getattr(account, "account_number", None) or acct_raw.get("accountId"),
        "status": getattr(account, "status", "unknown") or acct_raw.get("accountType", "unknown"),
        "total_account_value": _parse_money(
            getattr(account, "total_account_value", None)
            or acct_raw.get("totalAccountValue")
        ),
        "buying_power": _parse_money(
            getattr(account, "buying_power", None)
            or acct_raw.get("buyingPower")
            or (acct_raw.get("buyingPower", {}) or {}).get("cashOnlyBuyingPower")
        ),
        "cash": _parse_money(
            getattr(account, "cash", None)
            or acct_raw.get("cash")
        ),
        "initial_margin": _parse_money(getattr(account, "initial_margin", 0)),
        "maintenance_margin": _parse_money(getattr(account, "maintenance_margin", 0)),
        "day_trading_buying_power": _parse_money(
            getattr(account, "day_trading_buying_power", 0)
            or (acct_raw.get("buyingPower", {}) or {}).get("optionsBuyingPower")
        ),
        "portfolio_value": _parse_money(
            getattr(account, "portfolio_value", None)
            or acct_raw.get("totalAccountValue")
        ),
        "data_source": "public_api",
    }


# ---------------------------------------------------------------------------
# POST /order — place a single-leg order
# ---------------------------------------------------------------------------

@router.post("/order")
async def place_order(request: dict[str, Any]) -> dict[str, Any]:
    """Place a single-leg order via Public.com.

    Body:
        symbol:             OSI symbol for options (SPY260904C00760000), ticker for equity
        side:               BUY or SELL
        order_type:         MARKET, LIMIT, STOP, STOP_LIMIT
        quantity:           number of contracts/shares
        limit_price:        required for LIMIT/STOP_LIMIT
        stop_price:         required for STOP/STOP_LIMIT
        time_in_force:      DAY, GTC, etc.
        instrument_type:    EQUITY, OPTION, CRYPTO, BOND
        equity_market_session: optional for EQUITY
    """
    broker = await _get_broker()
    if broker is None:
        raise HTTPException(status_code=502, detail={
            "error": "no_public_api_key",
            "message": "PUBLIC_API_KEY not configured.",
        })

    account = broker.get_trading_account()
    if account is None:
        raise HTTPException(status_code=502, detail={"error": "no_account"})

    try:
        symbol = request.get("symbol", "")
        side = request.get("side", "BUY")
        order_type = request.get("order_type", "MARKET")
        try:
            quantity = float(request.get("quantity", 1))
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail={
                "error": "bad_quantity",
                "message": f"quantity must be a number, got {request.get('quantity')!r}",
            }) from None
        if quantity <= 0:
            raise HTTPException(status_code=422, detail={
                "error": "bad_quantity",
                "message": "quantity must be positive",
            })
        limit_price = request.get("limit_price")
        stop_price = request.get("stop_price")
        try:
            limit_price = float(limit_price) if limit_price else None
            stop_price = float(stop_price) if stop_price else None
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail={
                "error": "bad_price",
                "message": "limit_price/stop_price must be numbers",
            }) from None
        time_in_force = request.get("time_in_force", "DAY")
        instrument_type = request.get("instrument_type", "EQUITY")
        equity_market_session = request.get("equity_market_session")

        order = await broker.place_order(
            account_id=account.account_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            limit_price=float(limit_price) if limit_price else None,
            stop_price=float(stop_price) if stop_price else None,
            time_in_force=time_in_force,
            instrument_type=instrument_type,
            equity_market_session=equity_market_session,
        )

        # Derive status from raw response — the Order object's status may
        # be None for unfilled LIMIT orders.
        status = order.status
        if status is None and order.raw:
            raw_order = order.raw.get("order", order.raw)
            status = raw_order.get("status", "UNKNOWN")

        return {
            "ok": True,
            "order_id": order.order_id,
            "symbol": order.symbol,
            "side": order.side,
            "order_type": order.order_type,
            "quantity": order.quantity,
            "price": order.price,
            "limit_price": float(limit_price) if limit_price else None,
            "stop_price": float(stop_price) if stop_price else None,
            "status": status,
            "created_at": order.created_at,
            "data_source": "public_api",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logging.getLogger(__name__).warning("Public.com place_order failed: %s", exc)
        raise HTTPException(status_code=502, detail={
            "error": "api_error",
            "message": f"Public.com API error: {exc}",
        }) from exc


# ---------------------------------------------------------------------------
# POST /order/{order_id}/cancel
# ---------------------------------------------------------------------------

@router.post("/order/{order_id}/cancel")
async def cancel_order(order_id: str) -> dict[str, Any]:
    """Cancel an open order by ID. Uses DELETE under the hood (Public API
    accepts DELETE to .../order/{id}; POST to .../cancel returns 404)."""
    broker = await _get_broker()
    if broker is None:
        raise HTTPException(status_code=502, detail={
            "error": "no_public_api_key",
            "message": "PUBLIC_API_KEY not configured.",
        })

    account = broker.get_trading_account()
    if account is None:
        raise HTTPException(status_code=502, detail={"error": "no_account"})

    try:
        result = await broker.cancel_order(account.account_id, order_id)
        return {
            "ok": True,
            "order_id": order_id,
            "status": result.get("status", "CANCELED"),
            "data_source": "public_api",
        }
    except Exception as exc:
        logging.getLogger(__name__).warning("Public.com cancel_order failed: %s", exc)
        raise HTTPException(status_code=502, detail={
            "error": "api_error",
            "message": f"Public.com API error: {exc}",
        }) from exc
