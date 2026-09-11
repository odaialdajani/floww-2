"""
backend/services/flow_trade_bridge.py

Signal-to-trade bridge: converts qualifying institutional flow alerts
(from services.flow_alerts, persisted in flow_alerts_daily) into
(1) paper-trading orders compatible with PaperTradingEngine.submit_order,
(2) journal seed entries matching the frontend's floww_trades_v2 schema.

Eligibility gates (all must pass):
  tier in {SILVER, GOLD}          — conviction floor (configurable)
  side == "BUY"                   — directional claims only; FLOW/STRATEGY
                                    never auto-trade (desk rule: never claim
                                    a side you can't defend)
  dte >= min_dte (default 2)      — architect mandate: skip same-day 0DTE;
                                    take the forward-dated contracts
  est_entry is a positive number  — BS-priced entry required for sizing

Position sizing: fixed-fraction risk — notional = RISK_PCT * equity, so
quantity = floor(risk_notional / (est_entry * 100)), minimum 1 contract.

Pure logic only; the route layer handles persistence and engine calls.
"""

from __future__ import annotations

import math
from typing import Any

_TIER_RANK = {"GOLD": 0, "SILVER": 1, "BRONZE": 2}

RISK_PCT_PER_TRADE = 0.02   # 2% of account equity per position
DEFAULT_MIN_DTE = 2         # skip same-day + next-day expiries

# C3 Kelly caps (Agent C, 2026-09-05): quarter-Kelly of the calibrated edge,
# hard-capped per name; earnings-protocol alerts (C5) size to the blackout
# fraction. p_method values that count as calibrated (staged) — anything
# else (None/"uncalibrated*"/"calibration_error"/"missing_features") takes
# the legacy flat schedule.
KELLY_FRACTION = 0.25       # quarter-Kelly: parameter-uncertain edges
SINGLE_NAME_CAP = 0.05      # 5% equity risk per name, hard
EARNINGS_RISK_CAP = 0.01    # earnings-protocol blackout sizing
STAGED_METHODS = frozenset({"decile", "logistic", "logistic+isotonic"})


def eligible_for_auto_trade(alert: dict, *, min_tier: str = "SILVER",
                            min_dte: int = DEFAULT_MIN_DTE) -> bool:
    """All gates must pass for an alert to become an auto paper-trade."""
    if not isinstance(alert, dict):
        return False
    tier = str(alert.get("tier") or "").upper()
    min_rank = _TIER_RANK.get(min_tier.upper(), _TIER_RANK["SILVER"])
    if _TIER_RANK.get(tier, 99) > min_rank:
        return False
    if str(alert.get("side") or "").upper() != "BUY":
        return False
    dte = alert.get("dte")
    if not isinstance(dte, (int, float)) or isinstance(dte, bool) or dte < min_dte:
        return False
    entry = alert.get("est_entry")
    if not isinstance(entry, (int, float)) or isinstance(entry, bool):
        return False
    return entry > 0


def _position_size(est_entry: float, account_equity: float,
                   conviction: int | None = None) -> int:
    """Fixed-fraction base (2% of equity) scaled by Blademap-style
    conviction: ≥75 conviction takes full size, 60–75 takes 75%, below
    60 takes half. Min 1 contract. Conviction is the ranked 0-100
    score from flow_alerts.score_conviction (None → full size)."""
    scale = 1.0
    if isinstance(conviction, (int, float)) and not isinstance(conviction, bool):
        if conviction >= 75:
            scale = 1.0
        elif conviction >= 60:
            scale = 0.75
        else:
            scale = 0.5
    risk_notional = max(account_equity, 0.0) * RISK_PCT_PER_TRADE * scale
    per_contract = max(est_entry, 0.01) * 100.0
    qty = int(math.floor(risk_notional / per_contract)) if per_contract > 0 else 0
    return max(qty, 1)


def _payoff_ratio(key_levels: dict | None) -> float | None:
    """Reward:risk from key levels: (target-entry)/(entry-invalidation)."""
    try:
        kl = key_levels or {}
        entry, inv, tgt = float(kl["entry"]), float(kl["invalidation"]), float(kl["target"])
    except (TypeError, ValueError, KeyError):
        return None
    risk = entry - inv
    if risk <= 0 or tgt <= entry:
        return None
    return (tgt - entry) / risk


def kelly_size(alert: dict, *, account_equity: float = 100_000.0) -> dict[str, Any]:
    """C3 sizing: quarter-Kelly of the calibrated edge, hard-capped.

    Calibrated (p_method staged + valid key levels) → Kelly qty with
    size_basis {method, p, b, f, cap}. Negative edge → qty 0 (refuse).
    Anything else → legacy conviction-scaled flat schedule (min 1).
    """
    entry = alert.get("est_entry")
    try:
        per_contract = max(float(entry), 0.01) * 100.0
    except (TypeError, ValueError):
        per_contract = 0.01 * 100.0
    try:
        flat_entry = float(entry)
    except (TypeError, ValueError):
        flat_entry = 0.01
    flat_qty = _position_size(flat_entry, account_equity, conviction=alert.get("conviction"))

    def _flat(reason: str) -> dict[str, Any]:
        return {"qty": flat_qty,
                "size_basis": {"method": "flat", "reason": reason,
                               "risk_frac": RISK_PCT_PER_TRADE}}

    p, method = alert.get("p_move"), str(alert.get("p_method") or "")
    if p is None or method not in STAGED_METHODS:
        return _flat("uncalibrated" if p is None else f"unstaged:{method or 'none'}")
    try:
        p = float(p)
    except (TypeError, ValueError):
        return _flat("bad_p")
    if not 0.0 < p < 1.0:
        return _flat("p_out_of_range")
    b = _payoff_ratio(alert.get("key_levels") if isinstance(alert.get("key_levels"), dict) else None)
    if b is None:
        return _flat("no_key_levels")
    from domain.position_sizing import kelly_fraction
    f_star = kelly_fraction(p, b)
    f = KELLY_FRACTION * f_star
    cap = EARNINGS_RISK_CAP if alert.get("earnings_protocol") else SINGLE_NAME_CAP
    risk_frac = min(f, cap)
    if risk_frac <= 0:
        return {"qty": 0, "size_basis": {"method": "kelly_capped", "p_move": round(p, 4),
                                         "payoff_ratio": round(b, 4), "kelly_f": round(f, 4),
                                         "risk_frac": 0.0, "cap": cap,
                                         "reason": "no_edge_refused"}}
    qty = max(int(math.floor(max(account_equity, 0.0) * risk_frac / per_contract)), 1)
    return {"qty": qty, "size_basis": {"method": "kelly_capped", "p_move": round(p, 4),
                                       "payoff_ratio": round(b, 4), "kelly_f": round(f, 4),
                                       "risk_frac": round(risk_frac, 4), "cap": cap}}


def alert_to_order(alert: dict, *, account_equity: float = 100_000.0) -> dict[str, Any]:
    """Alert → PaperTradingEngine.submit_order kwargs."""
    entry = float(alert["est_entry"])
    sized = kelly_size(alert, account_equity=account_equity)
    return {
        "symbol": str(alert["under"]).upper(),
        "side": "BUY",
        "quantity": sized["qty"],
        "order_type": "market",
        "metadata": {
            "source": "flowseeker",
            "ckey": alert.get("ckey"),
            "alert_key": alert.get("key"),
            "rule": alert.get("rule"),
            "tier": alert.get("tier"),
            "contract_type": alert.get("type"),
            "strike": alert.get("strike"),
            "expiry": alert.get("exp"),
            "dte": alert.get("dte"),
            "est_entry": entry,
            "under_price": alert.get("under_price"),
            "p_move": alert.get("p_move"),
            "p_method": alert.get("p_method"),
            "size_basis": sized["size_basis"],
            "execution": advise_execution(alert),
        },
    }


def alert_to_journal_entry(alert: dict) -> dict[str, Any]:
    """Alert → floww_trades_v2-shaped seed entry (TradeJournal localStorage
    schema): ticker, type, action, strike, expiry, quantity, entry_price,
    exit_price, entry_date, exit_date, notes, gex_regime, setup, tags."""
    under = str(alert.get("under") or "").upper()
    setup = f"{str(alert.get('rule') or 'flow').lower()} {str(alert.get('tier') or '').lower()}"
    why = str(alert.get("why") or "")
    notes = (
        f"Auto-seeded from Flowseeker Pro ({setup}). "
        f"vol/OI {alert.get('vol_oi')}x, ~${(alert.get('premium') or 0) / 1e6:.1f}M premium, "
        f"{alert.get('dte')} DTE. {why}"
    )
    return {
        "ticker": under,
        "type": str(alert.get("type") or "call").lower(),
        "action": "buy",
        "strike": alert.get("strike"),
        "expiry": alert.get("exp"),
        "quantity": "1",           # journal tracks contracts; sizing lives in paper engine
        "entry_price": alert.get("est_entry"),
        "exit_price": "",
        "entry_date": str(alert.get("asof") or "")[:10],
        "exit_date": "",
        "notes": notes,
        "gex_regime": "",
        "setup": setup,
        "tags": "flowseeker,auto",
    }


# C4 execution advisor (Agent C, 2026-09-05): Almgren-Chriss direction —
# patient limit vs urgent take from Kyle-lambda + spread + velocity.
# Thresholds are provisional desk parameters (named, tested, ledger-noted),
# not measured fits: λ bands reuse kyle_lambda's published labels;
# spread/velocity cuts are starting points for the Sync-3 kill/keep read.
ADVISE_SPREAD_TIGHT_BPS = 50.0    # pay the spread below this
ADVISE_SPREAD_XWIDE_BPS = 200.0   # untradable above this when illiquid
ADVISE_LIQ_LAMBDA = 0.001         # kyle LABEL_LIQUID boundary
ADVISE_ILLIQ_LAMBDA = 0.005       # kyle LABEL_ILLIQUID boundary
ADVISE_HOT_VELOCITY = 10.0        # prints/min: urgency trigger (provisional)
ADVISE_IMPACT_SLICE = 0.25        # our slice of a fully-imbalanced λ move


def advise_execution(alert: dict | None, *, kyle_lambda: float | None = None,
                     spread_bps: float | None = None,
                     velocity: float | None = None,
                     toxic: bool | None = None) -> dict[str, Any]:
    """TAKE (pay spread) vs WORK (patient limit) vs SKIP + slippage estimate.

    Reads explicit kwargs first, alert-embedded fields second
    (kyle_lambda / spread_bps / velocity_per_min / toxic). Fail-open:
    no inputs → WORK with slippage None (patient default, never a
    fabricated estimate).
    """
    a = alert if isinstance(alert, dict) else {}
    lam = kyle_lambda if kyle_lambda is not None else a.get("kyle_lambda")
    spr = spread_bps if spread_bps is not None else a.get("spread_bps")
    vel = velocity if velocity is not None else a.get("velocity_per_min")
    tox = toxic if toxic is not None else a.get("toxic")
    try:
        lam = float(lam) if lam is not None else None
    except (TypeError, ValueError):
        lam = None
    try:
        spr = float(spr) if spr is not None else None
    except (TypeError, ValueError):
        spr = None
    try:
        vel = float(vel) if vel is not None else None
    except (TypeError, ValueError):
        vel = None

    slip = None
    if spr is not None or lam is not None:
        slip = round((spr or 0.0) / 2.0 + ADVISE_IMPACT_SLICE * (lam or 0.0) * 10000.0, 1)

    if tox:
        return {"action": "SKIP", "slippage_bps_est": slip,
                "reason": "toxic tape — stand down"}
    if (lam is not None and lam >= ADVISE_ILLIQ_LAMBDA
            and spr is not None and spr >= ADVISE_SPREAD_XWIDE_BPS):
        return {"action": "SKIP", "slippage_bps_est": slip,
                "reason": "illiquid + untradable spread — no exit"}
    hot = (vel is not None and vel >= ADVISE_HOT_VELOCITY)
    tight = (spr is not None and spr <= ADVISE_SPREAD_TIGHT_BPS)
    deep = (lam is not None and lam < ADVISE_LIQ_LAMBDA)
    if hot and tight and deep:
        return {"action": "TAKE", "slippage_bps_est": slip,
                "reason": "hot + tight + deep — pay the spread"}
    if spr is None and lam is None and vel is None:
        return {"action": "WORK", "slippage_bps_est": None,
                "reason": "no urgency inputs — patient default"}
    return {"action": "WORK", "slippage_bps_est": slip,
            "reason": "no urgency edge — work a limit"}


def dedupe_alerts(alerts: list[dict]) -> list[dict]:
    """One trade per contract key — first occurrence wins (alerts arrive
    tier-ranked, strongest-first)."""
    seen: set[str] = set()
    out: list[dict] = []
    for a in alerts:
        ckey = a.get("ckey")
        if not ckey or ckey in seen:
            continue
        seen.add(ckey)
        out.append(a)
    return out


def build_auto_trades(alerts: list[dict], *, account_equity: float = 100_000.0,
                      min_tier: str = "SILVER",
                      min_dte: int = DEFAULT_MIN_DTE) -> list[dict]:
    """Full pipeline: filter → dedupe → shape. Returns dicts with both the
    order payload and the journal seed so one call feeds both consumers."""
    out: list[dict] = []
    for a in dedupe_alerts(list(alerts or [])):
        if not eligible_for_auto_trade(a, min_tier=min_tier, min_dte=min_dte):
            continue
        out.append({
            "order": alert_to_order(a, account_equity=account_equity),
            "journal_entry": alert_to_journal_entry(a),
            "ckey": a.get("ckey"),
            "tier": a.get("tier"),
            "under": a.get("under"),
        })
    return out
