"""
backend/services/exposure_alerts.py

Exposure-change alerts from heatmap grid snapshots (VEX walls + charm pins).

Ported from odaialdajani/floww-2 (gsd/010-exposure-alerts, read-only —
their repo untouched): the pure evaluator is theirs, adapted here to our
C6 alert contract and our grid payloads. Why it matters: VEX walls are
vol-suppression levels dealers defend; charm pins are where delta hedging
concentrates as time decays. A wall forming or breaking usually precedes
a regime shift.

Grid shape (both languages survive JSON round-trips, so strike keys may
be str or float — normalized to float on entry):
  {expiries[], strikes[], grid{}, vex_grid{expiry: {strike: value}},
   charm_grid{expiry: {strike: value}}}

Threshold semantics: an event fires when a cell's |value| crosses ABOVE
threshold * max_abs of its grid between snapshots (strictly greater for
formed; the prior cell must be below). Broken fires when a previously-
above-threshold cell drops below. Charm pins shift when the argmax strike
of charm moves between expiries' snapshots.
"""

from __future__ import annotations

import logging
import math
from typing import Any

log = logging.getLogger(__name__)

# Rule names in OUR feed (their exposure_{kind} collapsed to two rules;
# kind detail rides in `why` so the tape stays readable).
RULE_VEX_WALL = "VEX_WALL"
RULE_CHARM_PIN = "CHARM_PIN"
RULE_TOXIC_FLOW = "TOXIC_FLOW"
RULE_GAMMA_FLIP = "GAMMA_FLIP"
RULE_LIQUIDITY_STRESS = "LIQUIDITY_STRESS"
RULE_VOMMA_WALL = "VOMMA_WALL"

# VPIN toxicity gate (Easley-Lopez de Prado-O'Hara high-toxicity regime).
# vpin_state: {"vpin": float, "cdf": float|None, "n_buckets": int} | None.
TOXIC_VPIN = 0.7
TOXIC_MIN_CDF = 0.5  # skipped when cdf absent (vpin-only gate)
TOXIC_MIN_BUCKETS = 10  # cold engines stay silent

# Gamma-flip proximity (dealer positioning edge): price within ±1% of the
# flip level behaves as support (above, mean-reverting) or resistance
# (below, momentum). One event per evaluation when in band.
FLIP_PROXIMITY_PCT = 0.01

_TTL_S = 4 * 3600  # matches CLUSTER (ticker-level structural, hours-long)

# Last-grid cache per ticker for snapshot diffing (in-memory; a restart
# simply re-baselines to "formed" events — documented, never silent).
_LAST_GRIDS: dict[str, dict[str, Any]] = {}
_LAST_GRIDS_MAX = 64


def _cell_above(value: float, threshold: float) -> bool:
    return value is not None and abs(value) >= threshold


def _max_abs(grid_section: dict) -> float:
    """Max |cell value| across all expiries in a {expiry: {strike: value}} map.

    Non-finite cell values are dropped so the result is always finite (or 0.0
    for an empty/degenerate section) — this keeps downstream threshold and
    magnitude math well-defined even when a bad grid leaks in (D6).
    """
    vals = [
        abs(float(v))
        for row in grid_section.values()
        if isinstance(row, dict)
        for v in row.values()
        if isinstance(v, (int, float)) and math.isfinite(float(v))
    ]
    return max(vals, default=0.0)


def _norm_grid(section: Any) -> dict[str, dict[float, float]]:
    """Normalize one grid section to {expiry: {strike_float: value}}.

    Strike keys arrive as str (JSON) or float (in-process) — normalize so
    old-vs-new lookups compare like with like. Unparseable cells dropped.
    """
    out: dict[str, dict[float, float]] = {}
    if not isinstance(section, dict):
        return out
    for expiry, row in section.items():
        if not isinstance(row, dict):
            continue
        norm_row: dict[float, float] = {}
        for k, v in row.items():
            try:
                fk = float(k)
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(fv):  # D6: never carry NaN/Inf into downstream math
                continue
            norm_row[fk] = fv
        out[str(expiry)] = norm_row
    return out


def _wall_events(new_sec: dict, old_sec: dict, threshold_pct: float,
                 formed_kind: str, broken_kind: str) -> list[dict]:
    """Wall formed/broken diff for one grid section (VEX, vomma).

    Extracted verbatim from the VEX inline block: an event fires when a
    cell's |value| crosses ABOVE threshold * max_abs of its grid between
    snapshots (strictly greater for formed; the prior cell must be below).
    Broken fires when a previously-above-threshold cell drops below.
    """
    out: list[dict] = []
    threshold_new = threshold_pct * _max_abs(new_sec)
    if threshold_new > 0:
        for expiry, row in new_sec.items():
            old_row = old_sec.get(expiry, {}) if old_sec else {}
            thr_old = threshold_pct * _max_abs(old_sec) if old_sec else 0.0
            for strike, val in row.items():
                v = float(val)
                was = float(old_row.get(strike, 0) or 0)
                above_now = _cell_above(v, threshold_new)
                # A zero/degenerate old threshold means we can't judge the
                # prior state — treat as below so first snapshots emit "formed".
                above_before = (
                    _cell_above(was, thr_old) and thr_old > 0
                    if old_row else False
                )
                if above_now and not above_before:
                    out.append({
                        "kind": formed_kind, "strike": float(strike),
                        "expiry": expiry, "magnitude": abs(v) if math.isfinite(v) else 0.0,
                    })
                elif above_before:
                    # Wall existed at old threshold; check whether it's gone now.
                    broken_thr = max(thr_old, threshold_new)
                    if not _cell_above(v, broken_thr):
                        out.append({
                            "kind": broken_kind, "strike": float(strike),
                            "expiry": expiry, "magnitude": abs(was) if math.isfinite(was) else 0.0,
                        })
    return out


def evaluate_exposure_events(
    new_grid: dict,
    old_grid: dict | None = None,
    threshold_pct: float = 0.25,
    vpin_state: dict | None = None,
    spot: float | None = None,
    flip_level: float | None = None,
    liquidity_state: dict | None = None,
) -> list[dict]:
    """Compare two heatmap grid payloads and emit exposure events.

    Returns a list of event dicts sorted by |magnitude| descending:
    {"kind": "vex_wall_formed" | "vex_wall_broken"
             | "vomma_wall_formed" | "vomma_wall_broken"
             | "charm_pin_formed" | "charm_pin_shifted" | "toxic_flow"
             | "gamma_flip_approach",
     "strike": float, "expiry": str, "magnitude": float}

    vpin_state (optional): {"vpin": float, "cdf": float|None,
    "n_buckets": int} — toxic gate, see _toxic_flow_event.
    flip_level (optional): gamma-flip price level; with spot set, emits one
    gamma_flip_approach event when |spot - flip| / spot <= FLIP_PROXIMITY_PCT.
    """
    events: list[dict] = []
    if not new_grid:
        return events

    new_vex = _norm_grid(new_grid.get("vex_grid"))
    new_charm = _norm_grid(new_grid.get("charm_grid"))
    new_vomma = _norm_grid(new_grid.get("vomma_grid"))
    old_vex = _norm_grid((old_grid or {}).get("vex_grid"))
    old_charm = _norm_grid((old_grid or {}).get("charm_grid"))
    old_vomma = _norm_grid((old_grid or {}).get("vomma_grid"))

    # --- VEX walls ---
    events.extend(_wall_events(new_vex, old_vex, threshold_pct,
                              "vex_wall_formed", "vex_wall_broken"))
    # --- Vomma walls (vol-convexity concentration, one Greek deeper) ---
    events.extend(_wall_events(new_vomma, old_vomma, threshold_pct,
                              "vomma_wall_formed", "vomma_wall_broken"))
    # --- Charm pins ---
    charm_threshold_new = threshold_pct * _max_abs(new_charm)
    if charm_threshold_new > 0:
        for expiry, row in new_charm.items():
            old_row = old_charm.get(expiry, {}) if old_charm else {}

            def _pin(row_: dict[float, float]):
                best_k, best_v = None, 0.0
                for k, v in (row_ or {}).items():
                    fv = abs(float(v)) if isinstance(v, (int, float)) else 0.0
                    if fv > best_v:
                        best_k, best_v = k, fv
                return best_k, best_v

            new_pin, new_val = _pin(row)
            old_pin, old_val = _pin(old_row)
            if new_pin and _cell_above(new_val, charm_threshold_new):
                if old_pin is None:
                    events.append({
                        "kind": "charm_pin_formed", "strike": float(new_pin),
                        "expiry": expiry, "magnitude": new_val if math.isfinite(new_val) else 0.0,
                    })
                elif str(old_pin) != str(new_pin):
                    events.append({
                        "kind": "charm_pin_shifted",
                        "strike": float(new_pin),
                        "expiry": expiry, "magnitude": new_val if math.isfinite(new_val) else 0.0,
                    })

    # --- Toxic flow (VPIN gate) ---
    events.extend(_toxic_flow_event(vpin_state, spot))

    # --- Gamma-flip proximity ---
    events.extend(_flip_approach_event(flip_level, spot))

    # --- Liquidity stress (Kyle + Amihud agreement) ---
    events.extend(_liquidity_stress_event(liquidity_state, spot))

    events.sort(key=lambda e: e["magnitude"], reverse=True)
    return events


def _liquidity_stress_event(liquidity_state: Any, spot: Any) -> list[dict]:
    """One liquidity_stress event when Kyle AND Amihud both read ILLIQUID.

    Agreement = conviction (either alone is noisy). Absent/mismatched/cold
    state emits nothing. Fail-open: never raises.
    """
    try:
        if not isinstance(liquidity_state, dict):
            return []
        if (str(liquidity_state.get("kyle_label") or "") != "ILLIQUID"
                or str(liquidity_state.get("amihud_label") or "") != "ILLIQUID"):
            return []
        px = float(spot) if spot is not None else 0.0
        strike = px if math.isfinite(px) and px > 0 else 0.0
        return [{"kind": "liquidity_stress", "strike": strike, "expiry": "",
                 "magnitude": 1.0}]
    except (TypeError, ValueError):
        return []


def _flip_approach_event(flip_level: Any, spot: Any) -> list[dict]:
    """One gamma_flip_approach event when spot sits within ±FLIP_PROXIMITY_PCT
    of the flip level, else []. Direction: above = support (mean-reverting
    regime), below = resistance (momentum regime). Fail-open on missing or
    non-numeric inputs; never raises."""
    try:
        if isinstance(flip_level, bool) or isinstance(spot, bool):
            return []
        flip = float(flip_level) if flip_level is not None else 0.0
        px = float(spot) if spot is not None else 0.0
        if (not math.isfinite(flip) or not math.isfinite(px)
                or flip <= 0 or px <= 0):
            return []
        dist = abs(px - flip) / px
        if dist > FLIP_PROXIMITY_PCT:
            return []
        return [{"kind": "gamma_flip_approach", "strike": flip, "expiry": "",
                 "magnitude": dist,
                 "direction": "above" if px >= flip else "below"}]
    except (TypeError, ValueError):
        return []


def _toxic_flow_event(vpin_state: Any, spot: Any) -> list[dict]:
    """One toxic_flow event when VPIN is in the high-toxicity regime, else [].

    Fail-open: non-dict state, non-numeric vpin, cold engines (few buckets),
    or a mediocre CDF tail all yield []. CDF confirmation is skipped only
    when cdf is absent (vpin-only gate).
    """
    try:
        if not isinstance(vpin_state, dict):
            return []
        vpin = vpin_state.get("vpin")
        if isinstance(vpin, bool) or not isinstance(vpin, (int, float)):
            return []
        vpin = float(vpin)
        if not math.isfinite(vpin) or vpin < TOXIC_VPIN:
            return []
        n_buckets = vpin_state.get("n_buckets", 0)
        try:
            if int(n_buckets) < TOXIC_MIN_BUCKETS:
                return []
        except (TypeError, ValueError):
            return []
        cdf = vpin_state.get("cdf", None)
        if cdf is not None:
            try:
                if not math.isfinite(float(cdf)) or float(cdf) < TOXIC_MIN_CDF:
                    return []
            except (TypeError, ValueError):
                return []
        strike = float(spot) if isinstance(spot, (int, float)) and math.isfinite(float(spot)) and float(spot) > 0 else 0.0
        return [{"kind": "toxic_flow", "strike": strike, "expiry": "", "magnitude": vpin}]
    except Exception:
        return []


_WHY = {
    "vex_wall_formed": "VEX wall formed — dealers defending this vol level (suppression)",
    "vex_wall_broken": "VEX wall broken — vol suppression released, regime may shift",
    "charm_pin_formed": "Charm pin formed — delta-hedging concentration into expiry",
    "charm_pin_shifted": "Charm pin migrated — hedging magnet moved strikes",
    "toxic_flow": "Toxic flow — VPIN in the high regime: makers adversely selected, spreads/vol may widen (heuristic, not a direction call)",
    "gamma_flip_approach": "Gamma flip proximity — price pressing dealer flip level (support above / resistance below)",
    "liquidity_stress": "Liquidity stress — Kyle and Amihud agree the tape is illiquid: size moves price, expect slippage (heuristic, not a direction call)",
    "vomma_wall_formed": "Vomma wall formed — vol-convexity concentration: dealer hedging accelerates into vol moves at this strike (heuristic, not a direction call)",
    "vomma_wall_broken": "Vomma wall broken — vol-convexity concentration released, hedging pressure may shift",
}


def events_to_alerts(ticker: str, spot: float,
                     events: list[dict]) -> list[dict[str, Any]]:
    """Events → C6-shaped institutional alert dicts (Blademap feed-ready).

    Score is deterministic from magnitude (no invented precision — the WHY
    carries the claim); premium/vol_oi stay None (structure alerts make no
    money claim); ttl 4h like other structural rules.
    """
    out: list[dict[str, Any]] = []
    for e in events or []:
        kind = str(e.get("kind") or "")
        strike = float(e.get("strike") or 0)
        mag = float(e.get("magnitude") or 0)
        if not math.isfinite(mag):
            mag = 0.0
        if kind == "toxic_flow":
            rule = RULE_TOXIC_FLOW
            score = min(99, max(50, int(round(abs(mag) * 100))))
        elif kind == "gamma_flip_approach":
            rule = RULE_GAMMA_FLIP
            score = min(99, max(50, 100 - int(round(abs(mag) * 10000))))
        elif kind == "liquidity_stress":
            rule = RULE_LIQUIDITY_STRESS
            score = 75
        elif kind.startswith("vomma_"):
            rule = RULE_VOMMA_WALL
            score = min(99, max(50, int(abs(mag) / 1e6) + 50))
        else:
            rule = RULE_VEX_WALL if kind.startswith("vex_") else RULE_CHARM_PIN
            score = min(99, max(50, int(abs(mag) / 1e6) + 50))
        out.append({
            "key": f"exposure:{kind}:{ticker.upper()}:{e.get('expiry', '')}:{strike:g}",
            "ckey": f"{ticker.upper()}|exposure|{strike:g}|{e.get('expiry', '')}",
            "rule": rule,
            "tier": "SILVER",
            "side": "FLOW",
            "bias": None,
            "under": ticker.upper(),
            "type": "exposure",
            "strike": strike,
            "exp": str(e.get("expiry", "")),
            "dte": None,
            "score": score,
            "est_entry": None,
            "premium": None,
            "notional": None,
            "vol_oi": None,
            "sigma": None,
            "oi_chg_pct": None,
            "under_price": spot,
            "key_levels": None,
            "context": {"magnitude": mag, "kind": kind},
            "cluster": False,
            "cw_spread": None,
            "why": _WHY.get(kind, kind),
            "ttl_s": _TTL_S,
            "asof": None,
            "premium_truth": False,
            "p_move": None,
            "p_method": "uncalibrated",
            "rel_spread": None,
        })
    return out


def evaluate_ticker(ticker: str, grid_payload: dict | None, spot: float,
                    threshold_pct: float = 0.25,
                    vpin_state: dict | None = None,
                    flip_level: float | None = None,
                    liquidity_state: dict | None = None) -> list[dict[str, Any]]:
    """Diff one ticker's grid vs its last snapshot; cache and return alerts.

    Fail-open by contract: any error returns [] (callers must never let
    exposure evaluation break the heatmap response). First sight emits
    "formed" events only (documented baseline behavior, not a bug).
    vpin_state (optional): {"vpin", "cdf", "n_buckets"} — toxic-flow gate.
    flip_level (optional): gamma-flip price — proximity gate.
    liquidity_state (optional): {"kyle_label", "amihud_label", ...} — stress gate.
    """
    try:
        sym = (ticker or "").strip().upper()
        if not sym or not grid_payload:
            return []
        old = _LAST_GRIDS.get(sym)
        events = evaluate_exposure_events(grid_payload, old, threshold_pct,
                                          vpin_state=vpin_state, spot=spot,
                                          flip_level=flip_level,
                                          liquidity_state=liquidity_state)
        _LAST_GRIDS[sym] = {
            "vex_grid": grid_payload.get("vex_grid") or {},
            "charm_grid": grid_payload.get("charm_grid") or {},
            "vomma_grid": grid_payload.get("vomma_grid") or {},
        }
        if len(_LAST_GRIDS) > _LAST_GRIDS_MAX:
            _LAST_GRIDS.pop(next(iter(_LAST_GRIDS)))
        if not events:
            return []
        from datetime import UTC, datetime

        alerts = events_to_alerts(sym, spot, events)
        asof = datetime.now(UTC).isoformat()
        for a in alerts:
            a["asof"] = asof
        return alerts
    except Exception as e:
        log.warning("exposure eval failed for %s: %s", ticker, e)
        return []
