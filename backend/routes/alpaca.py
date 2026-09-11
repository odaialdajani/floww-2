"""API routes for Alpaca paper trading."""

import logging
import math
import re

from fastapi import APIRouter, Depends

from auth import require_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alpaca", tags=["alpaca"])


@router.get("/account")
async def get_account(_: bool = Depends(require_api_key)):
    """Get Alpaca account info."""
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        account = await client.get_account()
        if account:
            return account
        return {"error": "Alpaca not configured. Set ALPACA_API_KEY and ALPACA_SECRET_KEY env vars."}
    except Exception as e:
        return {"error": str(e)}


@router.get("/positions")
async def get_positions(_: bool = Depends(require_api_key)):
    """Get all open positions."""
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        positions = await client.get_positions()
        return {"positions": positions, "count": len(positions)}
    except Exception as e:
        return {"error": str(e), "positions": []}


@router.get("/orders")
async def get_orders(status: str = "open", limit: int = 50, _: bool = Depends(require_api_key)):
    """Get orders."""
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        orders = await client.get_orders(status=status, limit=limit)
        return {"orders": orders, "count": len(orders)}
    except Exception as e:
        return {"error": str(e), "orders": []}


@router.get("/clock")
async def get_clock():
    """Get market clock."""
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        clock = await client.get_clock()
        if clock:
            return clock
        return {"error": "Alpaca not configured"}
    except Exception as e:
        return {"error": str(e)}


@router.get("/bars/{ticker}")
async def get_bars(ticker: str, timeframe: str = "1Day", limit: int = 100):
    """Get price bars for a ticker."""
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        bars = await client.get_bars(ticker, timeframe=timeframe, limit=limit)
        return {"ticker": ticker.upper(), "bars": bars, "count": len(bars)}
    except Exception as e:
        return {"error": str(e), "bars": []}


@router.post("/order")
async def place_order(
    symbol: str,
    qty: int,
    side: str = "buy",
    order_type: str = "market",
    limit_price: float = 0,
):
    """Place a stock order (Alpaca paper). Successful fills are journaled
    as equity seeds (fail-open) so click-to-trade lands in position memory."""
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        result = await client.place_stock_order(symbol, qty, side, order_type, limit_price)
        if result:
            _journal_equity_fill(symbol, qty, side, order_type, limit_price, result)
            return result
        return {"error": "Order failed. Check Alpaca credentials and parameters."}
    except Exception as e:
        return {"error": str(e)}


def _journal_equity_fill(symbol: str, qty: int, side: str,
                         order_type: str, limit_price: float, result: dict) -> None:
    """Journal a UI/API equity fill (fail-open, never breaks the trade)."""
    try:
        from datetime import UTC, datetime

        from services.journal_store import get_engine, init_journal_tables, save_seeds

        engine = get_engine()
        init_journal_tables(engine)
        save_seeds(engine, [{
            "ticker": symbol.upper(),
            "type": "equity",
            "action": side.lower(),
            # No strike on equity legs, but strike is PK-NOT-NULL: store 0.0
            # labeled as ref-px convention (see discord_ops approve path).
            "strike": 0.0,
            "expiry": "",
            "quantity": str(qty),
            "entry_price": None,
            "exit_price": "",
            "entry_date": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
            "exit_date": "",
            "notes": (f"API/UI {side} {qty} {symbol.upper()} "
                      f"{order_type} (Alpaca paper id={(result or {}).get('id', '')})"[:500]),
            "gex_regime": "",
            "setup": "manual equity",
            "tags": "alpaca,equity,ui-click",
            "source": "api-alpaca",
        }])
    except Exception as e:
        logger.warning("alpaca order journaling failed (non-fatal): %s", e)


@router.post("/order/option")
async def place_option_order(
    symbol: str,
    qty: int = 1,
    side: str = "buy",
    order_type: str = "limit",
    limit_price: float = 0,
):
    """Place an OPTION order on Alpaca PAPER (OCC symbol, e.g. SPY260904C00760000).

    Requires options approval on the paper account — Alpaca 403s otherwise
    and the error surfaces honestly. Successful fills journal as option
    seeds (fail-open) so click-to-trade lands in position memory.
    """
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        result = await client.place_option_order(symbol, qty, side, order_type, limit_price)
        if result:
            _journal_option_fill(symbol, qty, side, result)
            return result
        return {"error": "Option order failed. Check Alpaca options approval, credentials, and symbol."}
    except Exception as e:
        return {"error": str(e)}


def _parse_occ(symbol: str) -> dict | None:
    """OCC symbol → {type, strike, expiry}. None when unparseable."""
    m = re.fullmatch(r"[A-Z]{1,6}(\d{6})([CP])(\d{8})", str(symbol or "").upper())
    if not m:
        return None
    try:
        exp = f"20{m.group(1)[:2]}-{m.group(1)[2:4]}-{m.group(1)[4:6]}"
        return {"type": "call" if m.group(2) == "C" else "put",
                "strike": int(m.group(3)) / 1000.0, "expiry": exp}
    except (TypeError, ValueError):
        return None


def _journal_option_fill(symbol: str, qty: int, side: str, result: dict) -> None:
    """Journal an option fill (fail-open, never breaks the trade)."""
    try:
        from datetime import UTC, datetime

        from services.journal_store import get_engine, init_journal_tables, save_seeds

        occ = _parse_occ(symbol) or {}
        engine = get_engine()
        init_journal_tables(engine)
        save_seeds(engine, [{
            "ticker": re.sub(r"\d{6}[CP]\d{8}$", "", str(symbol).upper()),
            "type": occ.get("type", "call"),
            "action": "buy" if side.lower() == "buy" else "sell",
            "strike": occ.get("strike"),
            "expiry": occ.get("expiry", ""),
            "quantity": str(qty),
            "entry_price": None,
            "exit_price": "",
            "entry_date": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S"),
            "exit_date": "",
            "notes": (f"Click-to-trade {side} {qty} {symbol} "
                      f"(Alpaca paper id={(result or {}).get('id', '')})"[:500]),
            "gex_regime": "",
            "setup": "click-to-trade",
            "tags": "alpaca,option,ui-click",
            "source": "api-alpaca-option",
        }])
    except Exception as e:
        logger.warning("alpaca option journaling failed (non-fatal): %s", e)


@router.delete("/position/{symbol}")
async def close_position(symbol: str):
    """Close a position.

    Open journal cards are closed only after the venue reports a confirmed
    fill with a usable average price. Accepted/pending close orders leave
    journal P&L open rather than substituting a market bar for execution.
    """
    try:
        from alpaca_client import AlpacaClient
        from services.close_intents import bind_close_order, prepare_close
        from services.journal_store import get_engine, init_journal_tables
        client = AlpacaClient()
        engine = get_engine()
        init_journal_tables(engine)
        intent = prepare_close(engine, symbol)
        if not intent["new"]:
            return {"symbol": symbol, "journal_status": "reconciliation_exception",
                    "reason": "unresolved_close_intent", "intent_id": intent["intent_id"]}
        result = await client.close_position(symbol)
        if result:
            if not result.get("id"):
                return {**result, "intent_id": intent["intent_id"],
                        "journal_status": "reconciliation_exception",
                        "reason": "close_response_missing_order_id"}
            bind_close_order(engine, intent["intent_id"], str(result["id"]))
            outcome = await reconcile_pending_close(
                symbol, str(result["id"]), client=client, engine=engine,
                close_order=result)
            closed = outcome["journal_closed"]
            result["intent_id"] = intent["intent_id"]
            if closed:
                result["journal_closed"] = closed
                result["journal_status"] = "confirmed_fill"
            else:
                result["journal_status"] = outcome["status"]
                result["journal_reason"] = outcome.get("reason", "")
            return result
        return {"error": "Failed to close position"}
    except Exception as e:
        return {"error": str(e)}


@router.get("/status")
async def get_status():
    """Get Alpaca connection status."""
    try:
        from alpaca_client import ALPACA_API_KEY, ALPACA_SECRET_KEY
        return {
            "configured": bool(ALPACA_API_KEY and ALPACA_SECRET_KEY),
            "api_key_set": bool(ALPACA_API_KEY),
            "secret_key_set": bool(ALPACA_SECRET_KEY),
            "base_url": "https://paper-api.alpaca.markets",
            "mode": "paper trading",
        }
    except Exception as e:
        return {"error": str(e)}


async def reconcile_pending_close(symbol: str, order_id: str,
                                  client=None, engine=None, close_order=None) -> dict:
    """Re-poll the venue for a pending close order and journal a confirmed fill.

    Eventual reconciliation for closes that left journal_status=pending_fill:
    fetches the venue order by id, then validates its persisted close intent.
    Only exact reserved rows can close on a finite, fully attributed fill.
    Fail-open: never raises; unknown/missing/failed states report honestly.
    """
    try:
        if not order_id:
            return {"symbol": symbol, "order_id": order_id,
                    "reconciled": False, "journal_closed": 0,
                    "status": "unknown"}
        if client is None:
            from alpaca_client import AlpacaClient
            client = AlpacaClient()
        from services.close_intents import apply_close_fill
        from services.journal_store import get_engine
        if engine is None:
            engine = get_engine()
        order = close_order if close_order is not None else await client.get_order(str(order_id))
        return {"symbol": symbol, "order_id": order_id,
                **apply_close_fill(engine, symbol, order_id, order)}
    except Exception as e:
        logger.warning("alpaca reconcile failed for %s: %s", symbol, e)
        return {"symbol": symbol, "order_id": order_id,
                "reconciled": False, "journal_closed": 0,
                "status": "unknown", "error": str(e)}


@router.post("/reconcile-close")
async def reconcile_close(payload: dict,
                          _: bool = Depends(require_api_key)):
    """Reconcile a pending paper-close order. Body: {symbol, order_id}."""
    try:
        return await reconcile_pending_close(
            str(payload.get("symbol", "")).upper(),
            str(payload.get("order_id", "")),
        )
    except Exception as e:
        return {"error": str(e)}


@router.get("/reconciliation-exceptions")
async def get_reconciliation_exceptions(_: bool = Depends(require_api_key)):
    """Expose unresolved attribution explicitly; never synthesize a fill."""
    from services.close_intents import reconciliation_exceptions
    from services.journal_store import get_engine
    return {"exceptions": reconciliation_exceptions(get_engine())}


def _signed_qty(action, quantity) -> float:
    """Net quantity for one instrument; invalid data makes drift unknown."""
    qty = float(quantity)
    action = str(action or "").lower()
    if not math.isfinite(qty) or qty < 0 or action not in ("buy", "sell"):
        raise ValueError("invalid journal quantity/action")
    return -qty if action == "sell" else qty


async def check_position_journal_drift(symbol: str, client=None,
                                       engine=None) -> dict:
    """Compare venue position against net open journal cards (read-only).

    Returns venue_qty, journal_qty, drift (venue minus journal), and
    status aligned/drift/unknown. Mutates nothing; never raises.
    """
    try:
        from services.close_intents import journal_asset_symbol
        from services.journal_store import get_engine

        sym = str(symbol or "").upper()
        if client is None:
            from alpaca_client import AlpacaClient
            client = AlpacaClient()
        positions = await client.get_positions()
        if not isinstance(positions, list):
            return {"symbol": sym, "venue_qty": None, "journal_qty": None,
                    "drift": None, "status": "unknown"}
        venue_qty = 0.0
        for pos in positions:
            if not isinstance(pos, dict):
                raise ValueError("malformed venue position")
            if str(pos.get("symbol") or "").upper() != sym:
                continue
            qty = float(pos.get("qty"))
            if not math.isfinite(qty):
                raise ValueError("nonfinite venue quantity")
            venue_qty += qty
        if engine is None:
            engine = get_engine()
        rows = engine.query("SELECT ticker,type,action,strike,expiry,quantity "
                            "FROM flow_journal_trades WHERE COALESCE(exit_date,'')='' "
                            "AND exit_price IS NULL")
        journal_qty = sum(
            _signed_qty(t.get("action"), t.get("quantity"))
            for t in rows if journal_asset_symbol(t) == sym
        )
        drift = venue_qty - journal_qty
        if not math.isfinite(drift):
            raise ValueError("nonfinite position total")
        return {"symbol": sym, "venue_qty": venue_qty,
                "journal_qty": journal_qty, "drift": drift,
                "status": "aligned" if drift == 0 else "drift"}
    except Exception as e:
        logger.warning("alpaca drift check failed for %s: %s", symbol, e)
        return {"symbol": str(symbol or "").upper(), "venue_qty": None,
                "journal_qty": None, "drift": None,
                "status": "unknown", "error": str(e)}


@router.get("/position-journal-drift/{symbol}")
async def position_journal_drift(symbol: str,
                                 _: bool = Depends(require_api_key)):
    """Read-only venue-vs-journal quantity check for one symbol."""
    try:
        return await check_position_journal_drift(symbol)
    except Exception as e:
        return {"error": str(e)}
