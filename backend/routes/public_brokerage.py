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

GET /api/public/execution-lifecycle/inventory — read-only lifecycle inventory
  (authenticated, default-deny): the stored execution boundary with no live path.

Auth: every endpoint requires the master key (X-API-Key, see auth.py).
Public.com orders are LIVE, not a paper simulation. New submissions are
disabled unless FLOWW_ENABLE_LIVE_PUBLIC is exactly 1 after explicit operator
authorization. Merely configuring a data key does not enable submissions.

Mounted at /api/public alongside /api/public/chain + /api/public/quotes
from routes/public_api.py.
"""
from __future__ import annotations

import logging
import math
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from auth import require_api_key
from services.public_api_adapter import _get_broker

log = logging.getLogger(__name__)

router = APIRouter(prefix="/public", tags=["public_brokerage"])
__all__ = ["router"]


def _require_live_trading_enabled() -> None:
    """Fail-closed kill-switch for the live-money order paths.

    POST /order refuses with 403 unless the operator explicitly arms live
    submissions with FLOWW_ENABLE_LIVE_PUBLIC=1. Authenticated cancellation
    remains available while submissions are disarmed.
    """
    if os.environ.get("FLOWW_ENABLE_LIVE_PUBLIC", "") != "1":
        raise HTTPException(status_code=403, detail={
            "error": "live_trading_disabled",
            "message": (
                "Live Public.com order submission is disabled. "
                "Set FLOWW_ENABLE_LIVE_PUBLIC=1 on the backend to arm it."
            ),
        })


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


def _optional_number(value: Any) -> float | None:
    """Preserve unavailable amounts and fractional quantities in account reads."""
    if value is None or isinstance(value, bool) or (isinstance(value, str) and not value.strip()):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _first_present(*values):
    return next((value for value in values if value is not None), None)


def _mapping(value):
    return value if isinstance(value, dict) else {}


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
async def get_portfolio(_: bool = Depends(require_api_key)) -> dict[str, Any]:
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

    # Preserve the broker's unknown values; never fabricate a zero holding or gain.
    positions: list[dict[str, Any]] = []
    for pos in (portfolio.positions or []):
        raw = _mapping(getattr(pos, "raw", None))
        instrument = _mapping(getattr(pos, "instrument", None))
        cost_basis = _optional_number(_first_present(
            getattr(pos, "total_cost", None), getattr(pos, "cost_basis", None), _mapping(raw.get("costBasis")).get("totalCost"),
            _mapping(instrument.get("costBasis")).get("totalCost")))
        current_value = _optional_number(_first_present(
            getattr(pos, "market_value", None), getattr(pos, "current_value", None), raw.get("currentValue"), instrument.get("currentValue")))
        pnl = current_value - cost_basis if current_value is not None and cost_basis is not None else None
        pnl = _optional_number(_first_present(getattr(pos, "pnl", None), pnl))
        day_gain = _first_present(getattr(pos, "position_daily_gain", None), raw.get("positionDailyGain"))
        day_gain_pct = _optional_number(_first_present(getattr(pos, "day_gain_pct", None), day_gain.get("gainPercentage") if isinstance(day_gain, dict) else day_gain))
        total_gain_pct = _optional_number(pnl / cost_basis * 100) if pnl is not None and cost_basis else None
        total_gain_pct = _optional_number(_first_present(getattr(pos, "pnl_pct", None), total_gain_pct))
        positions.append({
            "symbol": getattr(pos, "symbol", "") or instrument.get("symbol", ""),
            "name": getattr(pos, "name", "") or instrument.get("name", ""),
            "quantity": _optional_number(_first_present(
                getattr(pos, "quantity", None), raw.get("quantity"), instrument.get("quantity"))),
            "current_price": _optional_number(_first_present(
                getattr(pos, "last_price", None), raw.get("lastPrice"),
                _mapping(instrument.get("lastPrice")).get("lastPrice"))),
            "market_value": current_value,
            "cost_basis": cost_basis,
            "day_gain_pct": day_gain_pct,
            "total_gain_pct": total_gain_pct,
            "pnl": pnl,
            "asset_type": getattr(pos, "instrument_type", None) or instrument.get("type") or "UNKNOWN",
            "bid": _optional_number(raw.get("bid")),
            "ask": _optional_number(raw.get("ask")),
        })

    positions.sort(key=lambda p: (p["market_value"] is not None, abs(p["market_value"] or 0)), reverse=True)

    # Account-level money fields live on Portfolio, not Account.
    buying_power = _optional_number(getattr(portfolio, "buying_power", None))
    cash = _optional_number(getattr(portfolio, "cash", None))
    options_buying_power = _optional_number(getattr(portfolio, "options_buying_power", None))
    total_account_value = _optional_number(getattr(portfolio, "total_account_value", None))

    return {
        "ok": True,
        "account_id": getattr(account, "account_id", ""),
        "buying_power": buying_power,
        "options_buying_power": options_buying_power,
        "cash": cash,
        "initial_margin": _optional_number(getattr(account, "initial_margin", None)),
        "maintenance_margin": _optional_number(getattr(account, "maintenance_margin", None)),
        "portfolio_value": total_account_value,
        "positions": positions,
        "position_count": len(positions),
        "data_source": "public_api",
    }


# ---------------------------------------------------------------------------
# GET /orders
# ---------------------------------------------------------------------------

@router.get("/orders")
async def get_orders(_: bool = Depends(require_api_key)) -> dict[str, Any]:
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
async def get_account(_: bool = Depends(require_api_key)) -> dict[str, Any]:
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

@router.post("/order", dependencies=[Depends(require_api_key)])
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

        # Kill-switch AFTER validation so 422 contracts hold while disarmed.
        _require_live_trading_enabled()

        broker = await _get_broker()
        if broker is None:
            raise HTTPException(status_code=502, detail={
                "error": "no_public_api_key",
                "message": "PUBLIC_API_KEY not configured.",
            })

        account = broker.get_trading_account()
        if account is None:
            raise HTTPException(status_code=502, detail={"error": "no_account"})

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

@router.post("/order/{order_id}/cancel", dependencies=[Depends(require_api_key)])
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

    # Cancelling an existing order is allowed while new entries are disarmed.
    # The route still requires the local application key.
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


@router.get("/execution-lifecycle/inventory", dependencies=[Depends(require_api_key)])
async def execution_lifecycle_inventory() -> dict[str, Any]:
    """Read-only lifecycle inventory (authenticated, default-deny; R17-4).

    Reports the stored execution boundary — known/open/unknown intent records
    with conservative protection truth, draft stages (stored approvals and
    preflight states are draft rows, never client booleans), native workflow
    registrations, the NEW-ENTRY protection window and the recovery boundary —
    without executing recovery, any broker call or any new live path. The
    live-submission arm state is disclosed; account-wide limits stay UNSET.
    """
    from services.public_execution_lifecycle import lifecycle_inventory

    inventory = lifecycle_inventory()
    inventory["live_submission_armed"] = (
        os.environ.get("FLOWW_ENABLE_LIVE_PUBLIC", "") == "1")
    return inventory
