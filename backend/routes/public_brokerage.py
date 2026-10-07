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


def _admission_store_conn() -> Any | None:
    """Durable handle for admission reads (monkeypatchable in tests).

    None (no engine) means the deployment has no admission store: the
    legacy kill-switch-only path applies and is disclosed as such.
    """
    try:
        from services.duckdb_engine import db as eng

        return eng.conn if hasattr(eng, "conn") else None
    except Exception:
        return None


def _require_order_admission_if_policy(
    account_id: str, symbol: str, side: str, quantity: float,
    limit_price: float | None, request: dict[str, Any],
    stop_price: float | None = None, time_in_force: str = "DAY",
    order_type: str = "LIMIT", instrument_type: Any = None,
    equity_market_session: Any = None, operator: str = "",
) -> dict[str, Any] | None:
    """Full admission enforcement on the broker-reachable path (S8).

    This gate runs only AFTER the kill-switch, so it runs armed: every
    store/policy problem refuses. No admission store, store-query
    failure, or missing required policy refuses (fail closed) — the
    legacy kill-switch-only path is closed on the armed route; it
    survives only disarmed (kill-switch refuses first) and is disclosed
    as such. With a required v2 policy installed, a body approval_id
    must verify against the server-recomputed order fingerprint
    (account/symbol/side/quantity/limit/stop/TIF/order-type/instrument/
    session) presented by its author (operator must equal the stored
    approved_by), else refusal. Cancellation and reconciliation paths
    are untouched by this gate.
    Returns None when placement may proceed, else a refusal detail dict.
    """
    from services import execution_admission as adm

    conn = _admission_store_conn()
    if conn is None:
        return {"error": "POLICY_STORE_UNAVAILABLE",
                "message": "No admission store; refusing live submission."}
    policy = adm.get_account_policy_required(conn, account_id)
    if policy.get("reason") == "POLICY_UNSET":
        return {"error": "POLICY_UNSET",
                "message": "No required account policy installed; refusing "
                           "live submission. Install one via "
                           "POST /admission/policies, then present a bound "
                           "order approval."}
    if not policy.get("ok"):
        return {"error": policy.get("reason", "POLICY_STORE_UNAVAILABLE"),
                "message": "Admission store unreadable; refusing live submission."}
    approval_id = request.get("approval_id")
    verified = adm.verify_order_approval(
        conn, approval_id, account_id, symbol, side, quantity, limit_price,
        stop_price=stop_price, time_in_force=time_in_force,
        order_type=order_type, instrument_type=instrument_type,
        equity_market_session=equity_market_session, operator=operator)
    if not verified.get("ok"):
        return {"error": verified.get("reason", "APPROVAL_INVALID"),
                "message": "A stored order approval bound to these exact order "
                           "fields is required while an account policy is installed. "
                           "Create one via POST /admission/order-approvals.",
                "detail": verified.get("detail")}
    return None


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
    consumed_fp = None
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
        if isinstance(request.get("quantity", 1), bool):
            raise HTTPException(status_code=422, detail={
                "error": "bad_quantity",
                "message": "quantity must be a number, not a boolean",
            })
        if quantity <= 0 or not math.isfinite(quantity):
            raise HTTPException(status_code=422, detail={
                "error": "bad_quantity",
                "message": "quantity must be a finite positive number",
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
        if ((limit_price is not None and not math.isfinite(limit_price))
                or (stop_price is not None
                    and not math.isfinite(stop_price))):
            raise HTTPException(status_code=422, detail={
                "error": "bad_price",
                "message": "limit_price/stop_price must be finite numbers",
            })
        time_in_force = request.get("time_in_force", "DAY")
        instrument_type = request.get("instrument_type", "EQUITY")
        equity_market_session = request.get("equity_market_session")
        operator = request.get("operator", "")

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

        # Admission gate AFTER account resolution (needs the account) and
        # BEFORE any broker placement. The gate runs armed only
        # (kill-switch above refused otherwise): store/policy problems
        # refuse, and a stored approval must verify against the
        # server-recomputed fingerprint presented by its author.
        # Cancellation and reconciliation paths are untouched.
        admission_refusal = _require_order_admission_if_policy(
            getattr(account, "account_id", ""), symbol, side, quantity,
            limit_price, request, stop_price=stop_price,
            time_in_force=time_in_force, order_type=order_type,
            instrument_type=instrument_type,
            equity_market_session=equity_market_session,
            operator=operator)
        if admission_refusal is not None:
            raise HTTPException(status_code=403, detail=admission_refusal)

        # Single-use consumption (S17): verify passed, so burn the approval
        # BEFORE any broker placement — the guarded store UPDATE admits
        # exactly one placement per approval, closing the r19-recorded gap
        # where a same-ID replay within the <=24h validity window placed a
        # second order. Consume failures (already-used, revoked, store
        # unavailable) refuse 403 with ZERO broker calls; a subsequently
        # failed placement burns the approval anyway (fail-closed — the
        # operator re-approves with a fresh row; never refunded).
        from services import execution_admission as _adm

        fp = _adm.order_fingerprint(
            getattr(account, "account_id", ""), symbol, side, quantity,
            limit_price, stop_price=stop_price, time_in_force=time_in_force,
            order_type=order_type, instrument_type=instrument_type,
            equity_market_session=equity_market_session)
        consumed = _adm.consume_order_approval(
            _admission_store_conn(), request.get("approval_id"),
            fingerprint=fp, operator=operator,
            account_id=getattr(account, "account_id", ""))
        if not consumed.get("ok"):
            raise HTTPException(status_code=403, detail={
                "error": consumed.get("reason", "APPROVAL_CONSUME_FAILED"),
                "message": "The presented approval is single-use and was not "
                           "consumable (already used, revoked, or the store "
                           "is unavailable); refusing placement.",
                "detail": consumed.get("detail"),
            })
        consumed_fp = fp

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

        completed = _adm.complete_placement_attempt(
            _admission_store_conn(), fp, request.get("approval_id"),
            order.order_id)
        response = {
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
            "approval_id": request.get("approval_id"),
            "approval_consumed": consumed.get("ok") is True,
        }
        if not completed.get("ok"):
            # The economic effect happened — the 200 stands. A stuck
            # in-flight claim would wrongly fence later placements, so
            # disclose it for operator resolution instead of failing.
            response["placement_journal"] = completed.get(
                "reason", "STORE_UNAVAILABLE")
            response["placement_journal_note"] = (
                "placement succeeded but its completion was not journaled; "
                "resolve the in-flight claim via POST "
                "/api/admission/placement-attempts/resolve before resubmitting")
        return response
    except HTTPException:
        raise
    except Exception as exc:
        logging.getLogger(__name__).warning("Public.com place_order failed: %s", exc)
        detail = {
            "error": "api_error",
            "message": f"Public.com API error: {exc}",
        }
        if consumed_fp is not None:
            # S17b: the approval was consumed but placement failed with
            # unknown outcome (ambiguous ACK — the broker may have placed
            # despite raising). Journal the attempt so any resubmission of
            # this exact fingerprint refuses PLACEMENT_OUTCOME_UNKNOWN
            # until an operator reconciles broker state and resolves it.
            # A journal failure is disclosed, never silent: resubmission
            # is then unguarded and must be reconciled manually.
            journaled = _adm.record_placement_attempt(
                _admission_store_conn(), consumed_fp,
                request.get("approval_id"),
                getattr(account, "account_id", ""),
                f"{type(exc).__name__}: {exc}")
            if journaled.get("ok"):
                detail["placement_outcome"] = (
                    "UNKNOWN — resubmission of this exact order refuses "
                    "until reconciled and resolved")
            else:
                detail["attempt_journal"] = journaled.get(
                    "reason", "STORE_UNAVAILABLE")
                detail["attempt_journal_note"] = (
                    "the failed attempt could not be journaled; resubmission "
                    "is unguarded — reconcile broker state manually before "
                    "any retry")
        raise HTTPException(status_code=502, detail=detail) from exc


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
