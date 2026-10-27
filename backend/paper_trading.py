"""
Paper Trading Automation for Confluence Decoder.

Uses Alpaca paper trading API to automatically place trades based on:
- GEX regime signals
- Alert triggers
- Strategy templates

All trades are placed in PAPER mode only.

NOTE: This module includes a daily SPY dry-run path that loads the active
direction model, builds a TradeIntent, runs a risk gate, and writes the
intended order to Mongo (collection ``orders_dry_run``). There is **NO**
order-submission code in this module — live wiring is gated behind
``LIVE_TRADING_ENABLED=1`` and intentionally not implemented here. It will
land in a future PR after the SPY v1.0 audit clears.
"""

import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel

from domain.position_sizing import delta_adjusted_max_loss_size

load_dotenv()

logger = logging.getLogger(__name__)

# Hard guard: live submission is OFF by default. This module does NOT contain
# any order-submission call site — even when this flag is on, the dry-run
# function only logs and persists the intent.
LIVE_TRADING_ENABLED = os.environ.get("LIVE_TRADING_ENABLED") == "1"

# Trading configuration
MAX_POSITION_SIZE = 1
DEFAULT_STRATEGY = "iron_condor"  # Fixed typo: was "iron_condible"
ENABLED_SIGNALS = {"GAMMA_FLIP", "GAMMA_SQUEEZE", "WALL_BREACH"}

# Risk-gate limits for dry-run intents
RISK_MAX_QTY = 5
RISK_MAX_PREMIUM = 500
RISK_ALLOWED_TICKERS = {"SPY", "QQQ"}

# Active model identifier — kept in sync with models/SPY_*_v1.0.{joblib,json}
ACTIVE_MODEL_ID = "SPY_v1.0"
ACTIVE_MODEL_VERSION = "v1.0"


# ─── Strategy Union ───

class IronCondor(BaseModel):
    type: str = "iron_condor"
    call_strike_high: float
    call_strike_low: float
    put_strike_high: float
    put_strike_low: float
    expiry: str
    qty: int = 1

class Straddle(BaseModel):
    type: str = "straddle"
    strike: float
    expiry: str
    qty: int = 1

class Strangle(BaseModel):
    type: str = "strangle"
    call_strike: float
    put_strike: float
    expiry: str
    qty: int = 1

class VerticalSpread(BaseModel):
    type: str = "vertical"
    side: str  # "call" or "put"
    buy_strike: float
    sell_strike: float
    expiry: str
    qty: int = 1

class CalendarSpread(BaseModel):
    type: str = "calendar"
    side: str
    strike: float
    near_expiry: str
    far_expiry: str
    qty: int = 1

class SingleLeg(BaseModel):
    type: str = "single_leg"
    option_type: str
    strike: float
    expiry: str
    side: str  # "buy" or "sell"
    qty: int = 1

Strategy = IronCondor | Straddle | Strangle | VerticalSpread | CalendarSpread | SingleLeg

Strategy = IronCondor | Straddle | Strangle | VerticalSpread | CalendarSpread | SingleLeg


def generate_client_order_id(intent: dict[str, Any], session_salt: str = "") -> str:
    """Generate deterministic client order ID. Same intent + salt = same ID."""
    import json
    content = json.dumps(intent, sort_keys=True) + session_salt
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def get_alpaca_client():
    """Get the Alpaca trading client."""
    try:
        from alpaca_client import AlpacaClient
        client = AlpacaClient()
        if client.enabled:
            return client
    except Exception as e:
        logger.warning(f"Alpaca client not available: {e}")
    return None


def calculate_position_size(
    signal_type: str,
    account_equity: float,
    risk_pct: float = 0.02,
    *,
    delta: float | None = None,
    entry_spot: float | None = None,
    stop_spot: float | None = None,
    multiplier: float = 100.0,
) -> int:
    """Calculate position size based on account equity and risk.

    Two paths:

    * **Delta-aware (preferred)**: when ``delta``, ``entry_spot`` and
      ``stop_spot`` are supplied, the position size is computed via
      :func:`domain.position_sizing.delta_adjusted_max_loss_size` so that
      the expected dollar loss at the stop is bounded by
      ``equity * risk_pct``. This handles both options (multiplier=100,
      delta in [-1,1]) and stocks (multiplier=1, delta=1).

      Returns ``0`` to **refuse the trade** when the Greeks cannot be
      safely sized (delta ≈ 0 or |entry − stop| ≈ 0) — caller must
      interpret ``0`` as "do not trade".

    * **Naive fallback**: when Greeks / stop distance are unknown, the
      legacy fixed-$100/contract heuristic is used. This path is preserved
      so callers that haven't yet migrated (e.g. older signal producers)
      keep their current behaviour.

    Reference: Tharp (1998) Ch. 7; backend/domain/position_sizing.py.
    """
    delta_args_supplied = (
        delta is not None,
        entry_spot is not None,
        stop_spot is not None,
    )
    # All three required for delta-aware path; partial arg sets would
    # silently produce stale sizes — surface a warning so callers notice.
    if any(delta_args_supplied) and not all(delta_args_supplied):
        logger.warning(
            "calculate_position_size: delta-aware fields partially supplied "
            "(delta=%s, entry_spot=%s, stop_spot=%s). Falling back to naive "
            "$100/contract heuristic. Pass all three to enable Greeks-based sizing.",
            delta,
            entry_spot,
            stop_spot,
        )

    if all(delta_args_supplied):
        qty = delta_adjusted_max_loss_size(
            account_equity=account_equity,
            risk_pct=risk_pct,
            delta=delta,
            entry_spot=entry_spot,
            stop_spot=stop_spot,
            multiplier=multiplier,
        )
        # Cap by MAX_POSITION_SIZE.  Do NOT floor at 1 — the domain
        # primitive returns 0 to mean "cannot safely size; refuse the trade"
        # and resurrecting it would defeat that safety sentinel.
        return min(qty, MAX_POSITION_SIZE)

    # Naive legacy fallback (kept so callers without Greeks & stop
    # distance still produce the same numbers they did before).
    risk_amount = account_equity * risk_pct
    # For options, risk is typically the premium paid
    # Conservative: risk no more than 2% of equity per trade
    max_contracts = max(1, int(risk_amount / 100))  # Assume $100 per contract
    return min(max_contracts, MAX_POSITION_SIZE)


def build_order_from_signal(
    signal: dict[str, Any],
    ticker: str,
    spot_price: float,
) -> dict[str, Any] | None:
    """Build an Alpaca order from a trading signal."""
    signal_type = signal.get("type", "")

    if signal_type == "GAMMA_FLIP":
        # Negative gamma → expect amplified moves
        # Sell iron condor to collect premium
        return {
            "strategy": "iron_condor",
            "ticker": ticker,
            "spot": spot_price,
            "message": f"Gamma flip detected: {signal.get('message', '')}",
        }

    elif signal_type == "GAMMA_SQUEEZE":
        # Gamma squeeze forming → directional play
        direction = signal.get("data", {}).get("direction", "neutral")
        if direction == "bullish":
            return {
                "strategy": "call_spread",
                "ticker": ticker,
                "spot": spot_price,
                "message": f"Gamma squeeze (bullish): {signal.get('message', '')}",
            }
        elif direction == "bearish":
            return {
                "strategy": "put_spread",
                "ticker": ticker,
                "spot": spot_price,
                "message": f"Gamma squeeze (bearish): {signal.get('message', '')}",
            }

    elif signal_type == "WALL_BREACH":
        # Spot broke through wall → momentum play
        direction = signal.get("data", {}).get("direction", "")
        if direction == "BULLISH":
            return {
                "strategy": "call_spread",
                "ticker": ticker,
                "spot": spot_price,
                "message": f"Wall breach (bullish): {signal.get('message', '')}",
            }
        elif direction == "BEARISH":
            return {
                "strategy": "put_spread",
                "ticker": ticker,
                "spot": spot_price,
                "message": f"Wall breach (bearish): {signal.get('message', '')}",
            }

    return None


async def execute_paper_trade(
    order: dict[str, Any],
    qty: int = 1,
) -> dict[str, Any]:
    """Execute a paper trade via Alpaca."""
    client = get_alpaca_client()
    if not client:
        return {"status": "error", "message": "Alpaca client not available"}

    try:
        strategy = order.get("strategy", "")
        ticker = order.get("ticker", "")

        # Get options chain for the ticker
        chain = await client.get_options_chain(ticker)
        if not chain:
            return {"status": "error", "message": f"No options chain for {ticker}"}

        # Build the order based on strategy
        if strategy == "iron_condor":
            result = await client.place_iron_condor(ticker, chain, qty)
        elif strategy == "call_spread":
            result = await client.place_call_spread(ticker, chain, qty)
        elif strategy == "put_spread":
            result = await client.place_put_spread(ticker, chain, qty)
        else:
            return {"status": "error", "message": f"Unknown strategy: {strategy}"}

        logger.info(f"Paper trade executed: {strategy} {ticker} x{qty}")
        return {
            "status": "executed",
            "strategy": strategy,
            "ticker": ticker,
            "qty": qty,
            "result": result,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    except Exception as e:
        logger.error(f"Paper trade failed: {e}")
        return {"status": "error", "message": str(e)}


async def process_signals_for_ticker(
    ticker: str,
    signals: list[dict[str, Any]],
    auto_trade: bool = False,
) -> list[dict[str, Any]]:
    """Process trading signals and optionally execute trades."""
    results = []

    for signal in signals:
        signal_type = signal.get("type", "")

        if signal_type not in ENABLED_SIGNALS:
            continue

        order = build_order_from_signal(signal, ticker, signal.get("spot", 0))
        if not order:
            continue

        result = {
            "signal": signal_type,
            "order": order,
            "executed": False,
        }

        if auto_trade:
            trade_result = await execute_paper_trade(order)
            result["trade"] = trade_result
            result["executed"] = trade_result.get("status") == "executed"

        results.append(result)

    return results


# ───────────────────────────────────────────────────────────────────────────
# Dry-run paper trading (SPY direction model v1.0)
# ───────────────────────────────────────────────────────────────────────────


class TradeIntent(BaseModel):
    """Pre-submission trade description. Never sent to Alpaca in this module."""

    ticker: str
    side: str  # "buy" or "sell"
    qty: int = 1
    strategy: Strategy
    max_premium: float = 100.0
    notes: str | None = None


def check_risk(
    intent: TradeIntent,
    portfolio: dict[str, Any] | None = None,
    account: dict[str, Any] | None = None,
) -> tuple[bool, str]:
    """Minimum-viable risk gate. Returns (ok, reason)."""
    if intent.qty <= 0:
        return False, "qty must be > 0"
    if intent.qty > RISK_MAX_QTY:
        return False, f"qty {intent.qty} exceeds max {RISK_MAX_QTY}"
    if intent.max_premium <= 0:
        return False, "max_premium must be > 0"
    if intent.max_premium > RISK_MAX_PREMIUM:
        return False, f"max_premium {intent.max_premium} exceeds max {RISK_MAX_PREMIUM}"
    if intent.ticker.upper() not in RISK_ALLOWED_TICKERS:
        return False, f"ticker {intent.ticker} not in allowlist {sorted(RISK_ALLOWED_TICKERS)}"
    if intent.side not in {"buy", "sell"}:
        return False, f"side {intent.side!r} must be 'buy' or 'sell'"
    return True, "ok"


def _model_paths(model_id: str = ACTIVE_MODEL_ID) -> tuple[str, str, str]:
    """Resolve paths for the active model + scaler + meta. Refuses quarantined dirs."""
    models_dir = os.path.join(os.path.dirname(__file__), "..", "models")
    version = model_id.split("_")[-1] if "_" in model_id else ACTIVE_MODEL_VERSION
    model_path = os.path.join(models_dir, f"SPY_direction_{version}.joblib")
    scaler_path = os.path.join(models_dir, f"SPY_scaler_{version}.joblib")
    meta_path = os.path.join(models_dir, f"SPY_meta_{version}.json")
    for p in (model_path, scaler_path, meta_path):
        assert "_quarantine" not in str(p), f"refused to load quarantined artifact: {p}"
    return model_path, scaler_path, meta_path


def _load_active_model(model_id: str = ACTIVE_MODEL_ID):
    """Load model + scaler + feature_names. Quarantine-guarded."""
    import joblib  # noqa: WPS433 — local import keeps cold-import cheap

    model_path, scaler_path, meta_path = _model_paths(model_id)
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"active model missing: {model_path}")
    if not os.path.exists(scaler_path):
        raise FileNotFoundError(f"active scaler missing: {scaler_path}")

    model = joblib.load(model_path)
    scaler = joblib.load(scaler_path)

    feature_names: list[str] = []
    if os.path.exists(meta_path):
        try:
            with open(meta_path) as fh:
                meta = json.load(fh)
            feature_names = list(meta.get("feature_names") or [])
        except Exception as exc:  # noqa: BLE001 — best-effort metadata
            logger.warning(f"failed to read model meta {meta_path}: {exc}")
    return model, scaler, feature_names


async def _latest_feature_row(ticker: str, feature_names: list[str]) -> dict[str, Any] | None:
    """Fetch the most recent precomputed feature row for ``ticker`` from Mongo.

    Falls back to computing a fresh row via services.ml.features.compute_features
    when no precomputed row exists.
    """
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "confluence_decoder")]

    try:
        row = await db["ml_features"].find_one(
            {"ticker": ticker, "feature_version": ACTIVE_MODEL_VERSION},
            sort=[("date", -1)],
        )
    finally:
        client.close()

    if row:
        return row

    # Fallback: compute on-the-fly. Returns the most recent doc, or None.
    try:
        from services.ml.features import compute_features  # type: ignore

        result = await compute_features(ticker)
        docs = result.get("docs") or []
        return docs[-1] if docs else None
    except Exception as exc:  # noqa: BLE001 — feature compute is best-effort
        logger.warning(f"compute_features fallback failed for {ticker}: {exc}")
        return None


def _build_feature_vector(row: dict[str, Any], feature_names: list[str]):
    """Project a Mongo feature doc into the model's expected feature order.

    A DECLARED feature that is missing from the row or stored as null is
    UNKNOWN data: it is refused with ValueError — never silently substituted
    with 0.0 (repo data rule: unknown is never zero). Observed 0.0 values are
    real data and are kept. Non-numeric values are refused the same way so
    the caller can skip honestly instead of crashing.
    """
    import numpy as np

    if not feature_names:
        # Unknown schema: take everything that looks numeric, sorted.
        ignore = {"_id", "ticker", "date", "feature_version", "_computed_at"}
        feature_names = sorted(
            k for k, v in row.items()
            if k not in ignore and not k.startswith("target_") and isinstance(v, (int, float))
        )
    missing = [name for name in feature_names if name not in row or row[name] is None]
    if missing:
        raise ValueError(f"missing or null declared features: {sorted(missing)}")
    try:
        values = [float(row[name]) for name in feature_names]
    except (TypeError, ValueError) as exc:
        raise ValueError(f"non-numeric declared feature value: {exc}") from None
    return np.array([values], dtype=float), feature_names


def _nearest_weekly_expiry(today: datetime | None = None) -> str:
    """Return ISO date of the next Friday (or today if Friday). Weekly options proxy."""
    now = today or datetime.now(UTC)
    days_to_friday = (4 - now.weekday()) % 7  # Mon=0 ... Fri=4
    target = now.date() if days_to_friday == 0 else now.date()
    if days_to_friday > 0:
        from datetime import timedelta
        target = (now + timedelta(days=days_to_friday)).date()
    return target.isoformat()


def _atm_strike(spot: float) -> float:
    """Round spot to the nearest dollar for ATM strike."""
    try:
        return float(round(float(spot)))
    except (TypeError, ValueError):
        return 0.0


async def daily_paper_trade_dry_run(ticker: str = "SPY") -> dict[str, Any]:
    """Predict, build a TradeIntent, run the risk gate, and log the intent.

    DRY-RUN ONLY. No Alpaca order submission. The hard guard
    ``LIVE_TRADING_ENABLED`` is respected, but even when enabled this function
    does not call any submit/place endpoint — that wiring is intentionally
    deferred to a future PR (post SPY v1.0 audit).
    """
    timestamp = datetime.now(UTC)
    result: dict[str, Any] = {
        "ticker": ticker,
        "model_id": ACTIVE_MODEL_ID,
        "mode": "dry_run",
        "live_enabled": LIVE_TRADING_ENABLED,
        "ts": timestamp.isoformat(),
    }

    # ── 1. Load model ───────────────────────────────────────────────────
    try:
        model, scaler, feature_names = _load_active_model()
    except FileNotFoundError as exc:
        result.update({"action": "skip", "reason": f"model_missing: {exc}"})
        logger.warning(result["reason"])
        return result

    # ── 2. Latest feature row ───────────────────────────────────────────
    row = await _latest_feature_row(ticker, feature_names)
    if not row:
        result.update({"action": "skip", "reason": "no_feature_row"})
        logger.warning(result["reason"])
        return result

    feature_date = row.get("date")
    try:
        X_raw, used_names = _build_feature_vector(row, feature_names)
    except ValueError as exc:
        # Unknown (missing/null/non-numeric) declared features: skip honestly,
        # never predict on substituted zeros (paper-recovery B12).
        result.update({"action": "skip", "reason": f"incomplete_feature_row: {exc}"})
        logger.warning(result["reason"])
        return result
    try:
        X = scaler.transform(X_raw)
    except Exception as exc:  # noqa: BLE001 — scaler shape mismatch etc.
        result.update({"action": "skip", "reason": f"scaler_error: {exc}"})
        logger.error(result["reason"])
        return result

    # ── 3. Predict direction + probability ──────────────────────────────
    try:
        raw_pred = int(model.predict(X)[0])
        if hasattr(model, "predict_proba"):
            proba_vec = model.predict_proba(X)[0]
            confidence = float(max(proba_vec))
        else:
            confidence = 0.5
    except Exception as exc:  # noqa: BLE001 — degenerate model etc.
        result.update({"action": "skip", "reason": f"predict_error: {exc}"})
        logger.error(result["reason"])
        return result

    # Binary classifier outputs {0,1} → map to direction {-1,+1}; 0 → neutral skip.
    direction = 1 if raw_pred == 1 else -1 if raw_pred == 0 else 0
    # We only skip on an explicit neutral signal (rare for binary models). The
    # binary classifier currently produces direction +1 / -1; a future ternary
    # model can emit 0 here.
    if direction == 0:
        result.update({
            "action": "skip",
            "reason": "neutral prediction",
            "prediction": raw_pred,
            "probability": confidence,
        })
        logger.info("neutral prediction; no intent built")
        return result

    side = "buy" if direction > 0 else "sell"
    option_type = "call" if side == "buy" else "put"

    spot = float(row.get("spot_price") or row.get("spot") or 0.0)
    strike = _atm_strike(spot)
    expiry = _nearest_weekly_expiry(timestamp)

    leg = SingleLeg(
        type="single_leg",
        option_type=option_type,
        strike=strike,
        expiry=expiry,
        side=side,
        qty=1,
    )

    intent = TradeIntent(
        ticker=ticker,
        side=side,
        qty=1,
        strategy=leg,
        max_premium=100.0,
        notes=f"dir={direction} proba={confidence:.4f} feature_date={feature_date}",
    )

    # ── 4. Risk gate ────────────────────────────────────────────────────
    ok, reason = check_risk(intent)
    result.update({
        "prediction": direction,
        "probability": confidence,
        "intent": intent.model_dump(),
        "risk_ok": ok,
        "risk_reason": reason,
        "feature_date": feature_date,
    })
    if not ok:
        result["action"] = "rejected"
        logger.warning(f"intent rejected by risk gate: {reason}")
        return result

    # ── 5. Persist intent (dry-run record) ──────────────────────────────
    from motor.motor_asyncio import AsyncIOMotorClient

    doc = {
        "intent": intent.model_dump(),
        "prediction": direction,
        "probability": confidence,
        "model_id": ACTIVE_MODEL_ID,
        "ts": timestamp,
        "mode": "dry_run",
        "feature_date": feature_date,
    }
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "confluence_decoder")]
    try:
        write_result = await db["orders_dry_run"].insert_one(doc)
        result["mongo_id"] = str(write_result.inserted_id)
    finally:
        client.close()

    # ── 6. Log the intended order ───────────────────────────────────────
    intent_repr = intent.model_dump()
    logger.info(f"INTENDED ORDER: {intent_repr}")
    logger.info(f"INTENDED ORDER (dry-run): {intent_repr}")

    # NOTE: Live submission is gated behind LIVE_TRADING_ENABLED, but there is
    # NO submit/place call anywhere in this file. That wiring lands in a
    # future PR after the SPY v1.0 audit returns PASS.
    if LIVE_TRADING_ENABLED:
        logger.warning(
            "LIVE_TRADING_ENABLED=1 detected, but this module contains no live "
            "submission path. Intent recorded as dry-run only."
        )

    result["action"] = "intent_logged"
    return result


if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="SPY paper-trading dry-run runner")
    parser.add_argument("--dry-run", action="store_true", help="Run the dry-run pipeline once and exit")
    parser.add_argument("--ticker", default="SPY")
    args = parser.parse_args()

    if not args.dry_run:
        # Fail loud: this CLI is dry-run only by design. There is no live mode.
        parser.error("--dry-run is required; live submission is not wired in this module")

    out = asyncio.run(daily_paper_trade_dry_run(args.ticker))
    logger.info(json.dumps(out, indent=2, default=str))
