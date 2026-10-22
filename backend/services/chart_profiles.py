"""B23 profiles/TPO: exact vs approximate, POC ties down, VA up, no future.

R21-04 admission contract: the selected exchange session/open/duration
and its coverage govern an admitted initial balance — America/New_York
with an explicit session date, an opening window the owning bar interval
divides exactly, opening bars knowable at the cursor across the whole
window, and instrument tick/units/entitlement explicit. Truncated or
midday opening history is unavailable or honestly named a first-loaded
range. A naked claim stands only on known low/high coverage plus ordered
event/receipt eligibility; unknown range is never proof of untouched.
"""
from __future__ import annotations

from datetime import datetime

from services.chart_flow import (
    SUPPORTED_BAR_SECONDS,
    explicit_instrument,
    refused,
    resolve_epoch,
    session_bounds,
    session_bounds_for_date,
)


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    out = float(value)
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def _first_number(mapping, keys):
    for key in keys:
        out = _number(mapping.get(key))
        if out is not None:
            return out
    return None


def _first_epoch(mapping, keys):
    for key in keys:
        out = resolve_epoch(mapping.get(key))
        if out is not None:
            return out
    return None


def poc(rows: list[dict]):
    """Point of control: max volume; ties resolve downward (lower price)."""
    if not rows:
        return None
    best = max(r.get("volume", 0) for r in rows)
    cands = [r for r in rows if r.get("volume", 0) == best]
    return min(cands, key=lambda r: r["price"])


def value_area(rows: list[dict], pct=0.70):
    """Expand from POC; equal adjacent-area expansion upward; stop on sparse gaps."""
    if not rows:
        return {"status": "unavailable"}
    ordered = sorted(rows, key=lambda r: r["price"])
    total = sum(r.get("volume", 0) for r in ordered)
    if total <= 0:
        return {"status": "unavailable"}
    target = total * pct
    center = ordered.index(poc(ordered))
    lo = hi = center
    acc = ordered[center].get("volume", 0)
    while acc < target:
        up = ordered[hi + 1].get("volume", 0) if hi + 1 < len(ordered) else None
        dn = ordered[lo - 1].get("volume", 0) if lo - 1 >= 0 else None
        if up is None and dn is None:
            break
        if up is None:
            lo -= 1
            acc += dn
        elif dn is None or up >= dn:
            hi += 1
            acc += up
        else:
            lo -= 1
            acc += dn
        if up == 0 and dn == 0:
            break
    return {"status": "ok", "low": ordered[lo]["price"], "high": ordered[hi]["price"],
            "attained": acc / total}


def naked_levels(prior_levels: list[dict], bars: list[dict]):
    """Historically correct naked levels: a prior level stays visible from the
    next session until the first bar whose range revisits it; unknown gaps are
    never proof of untouched. Each level needs an observed session start."""
    out = []
    for level in (prior_levels or []):
        price = (level or {}).get("price")
        start = (level or {}).get("session_start")
        if not isinstance(price, (int, float)) or not start:
            continue
        end = None
        for bar in (bars or []):
            low, high = (bar or {}).get("low"), (bar or {}).get("high")
            if isinstance(low, (int, float)) and isinstance(high, (int, float)) and low <= price <= high:
                end = bar.get("time")
                break
        out.append({"price": price, "visible_from": start, "visible_until": end,
                    "naked": end is None})
    return out


def admit_initial_balance(bars, *, ticker, cursor, bar_seconds, session_date,
                          opening_minutes, tick_size, units, entitlement,
                          allow_first_loaded_range=False) -> dict:
    """Admit a session-open initial balance (R21-04): explicit selected
    session (must be a published NY trading day — closed days refuse),
    opening duration the owning interval divides exactly, and full bar
    coverage knowable at the cursor. Truncated history refuses, or — only
    when explicitly allowed — is honestly named a first-loaded range;
    midday history stays unavailable either way."""
    try:
        instrument = explicit_instrument(ticker, tick_size, units, entitlement)
    except ValueError as err:
        return refused(str(err))
    if bar_seconds not in SUPPORTED_BAR_SECONDS:
        return refused("unsupported-bar-seconds")
    if isinstance(opening_minutes, bool) or not isinstance(opening_minutes, int) \
            or opening_minutes <= 0:
        return refused("opening-duration-not-explicit")
    if opening_minutes > 390:
        return refused("opening-duration-exceeds-session")
    if (opening_minutes * 60) % bar_seconds != 0:
        return refused("opening-duration-not-grid-divisible")
    try:
        ny_day = datetime.strptime(str(session_date), "%Y-%m-%d").date()
    except ValueError:
        return refused("unsupported-session-date")
    session = session_bounds_for_date(ny_day)
    if session is None:
        return refused("unsupported-session-date")
    cursor_session = session_bounds(cursor)
    if cursor_session is None or cursor_session["date"] != session["date"]:
        return refused("cursor-not-in-selected-session")
    cursor_epoch = float(cursor)
    opening_end = session["start"] + opening_minutes * 60
    if opening_end > session["end"]:
        return refused("opening-exceeds-session")
    common = {"instrument": instrument, "session": session,
              "opening_minutes": opening_minutes, "cursor": cursor_epoch,
              "bar_seconds": bar_seconds, "approximation": "bar-resolution",
              "certification": {"basis": "recorded opening-window coverage knowable at the cursor",
                                "certified_by_hash": False}}
    if cursor_epoch < opening_end:
        common.update({"status": "unavailable", "reason": "opening-window-incomplete-at-cursor",
                       "coverage": {"covered": 0, "expected_total": 0, "complete": False,
                                    "opening_minutes": opening_minutes}})
        return common
    slots = [session["start"] + i * bar_seconds
             for i in range((opening_minutes * 60) // bar_seconds)]
    expected = [slot for slot in slots if slot + bar_seconds <= cursor_epoch]
    index, gaps = {}, {"malformed_bar": 0, "missing_receipt": 0, "late_receipt": 0,
                       "outside_opening_window": 0}
    for bar in bars or []:
        if not isinstance(bar, dict):
            gaps["malformed_bar"] += 1
            continue
        ts = _first_number(bar, ("time", "ts", "bar_start"))
        high = _number(bar.get("high"))
        low = _number(bar.get("low"))
        if ts is None or high is None or low is None:
            gaps["malformed_bar"] += 1
            continue
        if ts < session["start"] or ts >= opening_end:
            gaps["outside_opening_window"] += 1
            continue
        slot_key = round(ts, 3)
        if slot_key in index:
            gaps["duplicate_bar"] = gaps.get("duplicate_bar", 0) + 1
            continue
        index[slot_key] = {"ts": ts, "high": high, "low": low,
                           "receipt": _first_epoch(bar, ("received_at", "known_at"))}
    usable, covered = [], []
    for slot in expected:
        bar = index.get(round(slot, 3))
        if bar is None:
            usable.append(False)
            continue
        if bar["receipt"] is None:
            gaps["missing_receipt"] += 1
            usable.append(False)
            continue
        if bar["receipt"] > cursor_epoch:
            gaps["late_receipt"] += 1
            usable.append(False)
            continue
        usable.append(True)
        covered.append(bar)
    prefix = 0
    for ok in usable:
        if not ok:
            break
        prefix += 1
    coverage = {"covered": len(covered), "expected_total": len(expected),
                "complete": len(covered) == len(expected), "opening_minutes": opening_minutes}
    envelope = dict(common, coverage=coverage, gaps=gaps)
    if not covered:
        envelope.update({"status": "unavailable", "reason": "opening-history-absent"})
        return envelope
    bounds = {"low": min(bar["low"] for bar in covered),
              "high": max(bar["high"] for bar in covered)}
    bars_used = [{"ts": bar["ts"], "high": bar["high"], "low": bar["low"]} for bar in covered]
    if coverage["complete"]:
        envelope.update({"status": "available", "bounds": bounds, "bars_used": bars_used})
        return envelope
    if prefix == len(covered) and allow_first_loaded_range:
        coverage["honest_name"] = "first loaded bars range"
        envelope.update({"status": "first-loaded-range", "bounds": bounds,
                         "bars_used": bars_used})
        return envelope
    envelope.update({"status": "unavailable",
                     "reason": "opening-history-gapped" if prefix < len(covered)
                               else "opening-history-truncated"})
    return envelope


def naked_levels_claim(levels, bars, *, cursor, coverage=None) -> dict:
    """R21-04 naked claims: a claim stands only on known low/high coverage
    plus ordered event/receipt eligibility; an unknown range is never proof
    of untouched, zero bars knowable at the cursor claim nothing, and bars
    beyond the cursor never close a level."""
    cursor_epoch = resolve_epoch(cursor)
    if cursor_epoch is None:
        return refused("cursor-not-epoch")
    low = coverage.get("low") if isinstance(coverage, dict) else None
    high = coverage.get("high") if isinstance(coverage, dict) else None
    low, high = _number(low), _number(high)
    if low is None or high is None or low > high:
        return {"status": "not-claimable", "reason": "unknown-range-cannot-certify-untouched",
                "claims": [], "cursor": cursor_epoch,
                "certification": {"basis": "known low/high coverage + ordered eligibility",
                                  "certified_by_hash": False}}
    gaps = {"malformed_bar": 0, "malformed_level": 0, "missing_receipt": 0,
            "late_receipt": 0, "future_bar": 0}
    ordered = []
    for bar in bars or []:
        if not isinstance(bar, dict):
            gaps["malformed_bar"] += 1
            continue
        ts = _first_number(bar, ("time", "ts", "bar_start"))
        bar_low = _number(bar.get("low"))
        bar_high = _number(bar.get("high"))
        receipt = _first_epoch(bar, ("received_at", "known_at"))
        if ts is None or bar_low is None or bar_high is None:
            gaps["malformed_bar"] += 1
            continue
        if ts > cursor_epoch:
            gaps["future_bar"] += 1
            continue
        if receipt is None:
            gaps["missing_receipt"] += 1
            continue
        if receipt > cursor_epoch:
            gaps["late_receipt"] += 1
            continue
        ordered.append({"ts": ts, "low": bar_low, "high": bar_high})
    ordered.sort(key=lambda bar: bar["ts"])
    claims = []
    for level in levels or []:
        price = _number((level or {}).get("price"))
        start = (level or {}).get("session_start")
        if price is None or start is None:
            gaps["malformed_level"] += 1
            continue
        touched = None
        for bar in ordered:
            if bar["low"] <= price <= bar["high"]:
                touched = bar["ts"]
                break
        if not (low <= price <= high):
            claims.append({"price": price, "session_start": start, "visible_until": None,
                           "naked": None, "status": "not-claimable",
                           "reason": "level-outside-known-range"})
            continue
        if touched is None and not ordered:
            claims.append({"price": price, "session_start": start, "visible_until": None,
                           "naked": None, "status": "not-claimable",
                           "reason": "no-eligible-bars-known"})
            continue
        claims.append({"price": price, "session_start": start, "visible_until": touched,
                       "naked": touched is None, "status": "claim",
                       "basis": "known-range coverage over ordered, cursor-gated bars"})
    return {"status": "available", "claims": claims, "cursor": cursor_epoch,
            "coverage": {"low": low, "high": high}, "gaps": gaps,
            "certification": {"basis": "known low/high coverage + ordered event/receipt eligibility",
                              "certified_by_hash": False}}
