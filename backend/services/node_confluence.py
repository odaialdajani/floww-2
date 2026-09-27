"""Roadmap #4 + #5: per-strike confluence overlay and flow-at-node.

Two gaps from the Skylit comparison, both wiring jobs over code that
already exists:

#4  `services/agent/confluence.py::score()` had ZERO production callers —
    the deterministic confluence scorer was reachable only from the agent
    copilot, never from the mounted heatmap. This module feeds it real
    per-strike inputs so the score lands where the trader is looking.

#5  Flow confirmation at a level existed (flow_alerts read-alert-feed) but
    had no strike-scoped entry point, so confirming a wall meant
    tab-switching. This returns the prints near the selected strike.

Honesty rules, both load-bearing:
  * A dimension with no real input is reported as "missing" and
    remains unknown — never a default that reads as signal.
  * structure is a MAGNITUDE (how big is this strike's gamma). It is not
    a direction, so it is passed as unsigned context, never folded into
    the signed total as if it implied buying. Direction comes from
    fresh declared alert bias only; put/call volume skew is context.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = "node_confluence.v1"

# A strike is "near" the selected level within this band (absolute price
# units), matching the flow-confirmation window the desk already uses.
NEAR_STRIKE_TOL = 2.0

# Volumes below this are treated as no-signal (thin tape), not as a
# bearish or bullish read. Absence of flow is not flow.
MIN_VOLUME_FOR_SKEW = 50.0


def _safe_f(v: Any, default: float = 0.0) -> float:
    if isinstance(v, bool):
        return default
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f != f or f in (float("inf"), float("-inf")):
        return default
    return f


def _clamp(x: float) -> float:
    return max(-1.0, min(1.0, x))


def structure_magnitude(strikes: list[dict[str, Any]]) -> tuple[float, str]:
    """Unsigned gamma magnitude of the largest |GEX| strike, normalized to the
    payload's own king node (so 1.0 == the board's structural center).

    Returns (value in [0,1], status). Unsigned on purpose — magnitude is
    not a direction and must not be mistaken for one. "missing" when the
    payload carries no usable strike at all.
    """
    best = 0.0
    seen = False
    for s in strikes or []:
        if not isinstance(s, dict):
            continue
        g = abs(_safe_f(s.get("gex")))
        if g > 0:
            seen = True
        best = max(best, g)
    if not seen or best <= 0:
        return 0.0, "missing"
    return 1.0, "ok"  # the king itself is 1.0 by construction


def microstructure_skew(strike_row: dict[str, Any]) -> tuple[float, str]:
    """Signed volume skew in [-1,1]: call-heavy positive, put-heavy negative.

    (call_volume - put_volume) / total_volume is an option-type activity
    balance only. It does not reveal buys, sells, or price direction.
    """
    if not isinstance(strike_row, dict):
        return 0.0, "missing"
    call_v = _safe_f(strike_row.get("call_volume"), -1)
    put_v = _safe_f(strike_row.get("put_volume"), -1)
    if call_v < 0 or put_v < 0:
        return 0.0, "missing"
    total = call_v + put_v
    if total < MIN_VOLUME_FOR_SKEW:
        # Thin tape: report missing, never a fabricated lean.
        return 0.0, "missing"
    return _clamp((call_v - put_v) / total), "ok"


def _near_strikes(strikes: list[dict[str, Any]], strike: float,
                  tol: float = NEAR_STRIKE_TOL) -> list[dict[str, Any]]:
    out = []
    for s in strikes or []:
        if not isinstance(s, dict):
            continue
        try:
            k = float(s.get("strike"))
        except (TypeError, ValueError):
            continue
        if abs(k - float(strike)) <= tol:
            out.append(s)
    return out


def flow_at_strike(flow_rows: list[dict[str, Any]] | None, strike: float,
                   tol: float = NEAR_STRIKE_TOL) -> dict[str, Any]:
    """Match saved alert records by contract strike, never option price/premium.

    These records are alerts, not executions. Only fresh, explicitly directional
    alert bias contributes to the separate alert-agreement reading. Cumulative
    snapshots, unknown times and unclassified sides cannot imply neutral flow.
    """
    rows: list[dict[str, Any]] = []
    unpriced = 0
    for r in flow_rows or []:
        if not isinstance(r, dict):
            continue
        price = _safe_f(r.get("strike"), -1)
        if price <= 0:
            unpriced += 1
            continue
        if abs(price - float(strike)) <= tol:
            rows.append(r)
    call_like = sum(str(r.get("type", "")).lower() in {"call", "c"} for r in rows)
    put_like = sum(str(r.get("type", "")).lower() in {"put", "p"} for r in rows)
    directional: list[float] = []
    direction_signs: list[int] = []
    now = datetime.now(UTC)
    for r in rows:
        context = r.get("context") or r.get("context_json") or {}
        if isinstance(context, str):
            try:
                context = json.loads(context)
            except (TypeError, ValueError):
                context = {}
        if not isinstance(context, dict):
            context = {}
        if (r.get("activity_basis") == "cumulative_snapshot"
                or context.get("activity_basis") == "cumulative_snapshot"
                or str(r.get("side", "")).upper() in {"FLOW", "STRATEGY"}):
            continue
        bias = str(r.get("bias") or "").lower()
        conviction = _safe_f(r.get("conviction"), -1)
        if bias not in {"bullish", "bearish"} or not 0 <= conviction <= 100:
            continue
        try:
            at = datetime.fromisoformat(str(r.get("asof_ts") or "").replace("Z", "+00:00"))
            if at.tzinfo is None or not 0 <= (now - at).total_seconds() <= 900:
                continue
        except (ValueError, TypeError):
            continue
        sign = 1 if bias == "bullish" else -1
        direction_signs.append(sign)
        directional.append(sign * conviction / 100)
    return {
        "strike": float(strike), "window": tol,
        "count": len(rows), "call_side": call_like, "put_side": put_like,
        "direction_net": sum(direction_signs) if directional else None,
        "direction_status": "ok" if directional else "unavailable",
        "direction_basis": "fresh_alert_bias",
        "directional_count": len(directional),
        "signed_alert_bias": sum(directional) / len(directional) if directional else None,
        "prints": rows[:50],  # legacy key; these are explicitly alert records
        "records": rows[:50], "record_basis": "saved_alerts",
        "unpriced_rows": unpriced,
        "status": "ok" if rows else "no_prints",
    }


def _flow_skew(flow_summary: dict[str, Any]) -> tuple[float, str]:
    if flow_summary.get("direction_status") != "ok":
        return 0.0, "missing"
    return _clamp(flow_summary["signed_alert_bias"]), "ok"


def node_brief(ticker: str, strikes: list[dict[str, Any]], *,
               flow_rows: list[dict[str, Any]] | None = None,
               limit: int = 12) -> dict[str, Any]:
    """Per-strike confluence brief for the top-|GEX| levels.

    Ranks by |GEX| (the structural significance a trader reads off the
    grid), then attaches microstructure skew, flow-at-strike, and the
    fused confluence total with an honest per-dimension status map.
    """
    from services.agent.confluence import score as confluence_score

    rows = [s for s in (strikes or []) if isinstance(s, dict)]
    # Keep any strike that carries a real strike price. Do NOT drop on
    # gex == 0: a perfectly hedged call/put pair nets to exactly zero GEX,
    # which is a meaningful structural fact (a pin), not a missing value.
    def _has_strike(s: dict[str, Any]) -> bool:
        try:
            return _safe_f(s.get("strike")) > 0
        except (TypeError, ValueError):
            return False

    rows = [s for s in rows if _has_strike(s)]
    rows.sort(key=lambda s: -abs(_safe_f(s.get("gex"))))

    out_rows: list[dict[str, Any]] = []
    for s in rows[: max(1, int(limit))]:
        strike = _safe_f(s.get("strike"))
        micro_v, micro_status = microstructure_skew(s)
        if micro_status == "ok":
            micro_status = "context_only"
        flow_sum = flow_at_strike(flow_rows, strike)
        flow_v, flow_status = _flow_skew(flow_sum)

        inputs = {
            "flow": flow_v,
            "structure": 0.0,  # unsigned context; never signed
            "microstructure": micro_v,
            "ml": 0.0,         # no per-strike ML input exists
            "vol": 0.0,        # no per-strike vol input exists
            "time_delta": 0.0,  # no per-strike time-delta input exists
        }
        inputs_status = {
            "flow": flow_status,
            "structure": "context_only",
            "microstructure": micro_status,
            "ml": "missing",
            "vol": "missing",
            "time_delta": "missing",
        }
        fused = confluence_score({**inputs, "inputs_status": inputs_status})
        out_rows.append({
            "strike": strike,
            "gex": _safe_f(s.get("gex"), None),
            "total_oi": _safe_f(s.get("total_oi"), None),
            "lifecycle": s.get("lifecycle"),
            "taps": s.get("taps"),
            "tap_prob": s.get("tap_prob"),
            "microstructure_skew": micro_v,
            "microstructure_status": micro_status,
            "flow": flow_sum,
            "confluence": fused,
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "ticker": str(ticker or "").upper(),
        "strikes_considered": len(rows),
        "rows": out_rows,
        "notes": [
            "structure is unsigned context: gamma magnitude, not direction",
            "dimensions with no real per-strike input are reported "
            "missing; call/put volume is context, and flow uses only fresh declared alert bias",
        ],
    }
