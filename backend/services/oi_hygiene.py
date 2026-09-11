"""
backend/services/oi_hygiene.py

ΔOI hygiene for the Tidehunter Pro ledger — correctness gates on the
overnight open-interest join that OICONF (and its client mirror) treat as
"yesterday's flow was real" proof. Three mechanical false-positive classes
are tagged here, once, on the server:

  1. EXPIRING — the contract expires before the next scan snapshot. Its
     next-day OI would read −100% (contracts vanish), and migration into the
     next expiry shows up as a +big% pop there. Both are noise wearing
     conviction's clothes → oiChg must be nulled for these contracts.

  2. ROLLOVER — a strike/type pair whose near-expiry OI collapsed ≥40% while
     the same strike/type at the next expiry grew ≥40% is a position
     migration, not new flow. Both legs are tagged; OICONF skips them.

  3. EARNINGS — Pan-Poteshman ΔOI semantics don't transfer into event
     windows (straddle buyers + premium sellers mix with directionals).
     OICONF still fires (never-remove) but carries an explicit
     why-string tag, a conviction cap below GOLD, and exclusion from the
     calibration set.

Pure functions only — no I/O. The route computes tags once per scan and
ships them on rows; both alert engines gate on identical tags, which
*reduces* drift risk versus mirrored logic.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

# OCC option roots are ≤6 chars (equities); the tail is yyMMdd.
_OCC_TAIL_RE = re.compile(r"^(.{1,6})(\d{6})([CP])(\d{1,8})$")

# Roll-detection thresholds (initial values; the outcome ledger is the tuner).
ROLL_DROP_PCT = -0.40
ROLL_GAIN_PCT = 0.40

# Earnings window: tag alerts fired within this many trading days BEFORE the
# report date (day-of included). Direction ambiguity peaks into the event.
EARNINGS_WINDOW_DAYS = 4


def occ_expiry(occ: str | None) -> date | None:
    """Expiration date parsed from an OCC option symbol (yyMMdd tail), else None."""
    if not occ:
        return None
    m = _OCC_TAIL_RE.match(str(occ).upper())
    if not m:
        return None
    try:
        return datetime.strptime(m.group(2), "%y%m%d").date()
    except ValueError:
        return None


def _strike_key(strike: Any) -> str:
    try:
        return f"{float(strike):g}"
    except (TypeError, ValueError):
        return str(strike)


def oi_hygiene_tags(
    rows: list[dict[str, Any]],
    prev_oi: dict[str, int],
    earnings_dates: dict[str, str] | None = None,
    today: date | None = None,
) -> dict[str, dict[str, Any]]:
    """Tags per row-key (rows' 'ckey'): {expiring, rollover, earnings}.

    rows: normalized scan rows (need ckey, occ, under, type, strike, oi).
    prev_oi: {ckey: prior-session OI} — already re-keyed to ckey by the caller.
    earnings_dates: {underlying: ISO report date} — absent/None means the
        window is UNKNOWN, which is surfaced honestly rather than skipped.
    today: injectable for tests; defaults to the real today.

    Expiring rows get oi_null=True: the caller nulls their oiChg BEFORE any
    ΔOI math (theirs and the next expiry's pop both being artifacts).
    """
    today = today or date.today()
    earnings_dates = earnings_dates or {}
    out: dict[str, dict[str, Any]] = {}

    # Pass 1 — expiring contracts: OI is about to evaporate; ΔOI is meaningless.
    expiring = set()
    for r in rows:
        exp = occ_expiry(r.get("occ")) or (
            _parse_iso(r.get("exp")) if r.get("exp") else None)
        if exp is not None and exp <= today:
            expiring.add(r["ckey"])

    # Pass 2 — roll pairs: same under/type/strike, near expiry bleeding while
    # the next expiry swells. Keyed by (under, type, strike) → expiry buckets.
    by_stem: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for r in rows:
        if r.get("oi") is None:
            continue
        key = (r.get("under") or "", r.get("type") or "", _strike_key(r.get("strike")))
        by_stem.setdefault(key, []).append(r)

    rolled_pairs: set[str] = set()
    for _stem, legs in by_stem.items():
        if len(legs) < 2:
            continue
        legs = sorted(legs, key=lambda x: (x.get("exp") or "", x.get("dte") or 9999))
        for i in range(len(legs) - 1):
            near, nxt = legs[i], legs[i + 1]
            pn = prev_oi.get(near["ckey"])
            px = prev_oi.get(nxt["ckey"])
            if not pn or pn <= 0 or not near.get("oi") or not nxt.get("oi") or px is None:
                continue
            near_chg = (near["oi"] - pn) / pn
            # Next leg's baseline: its own prior OI when we have it, else 0 —
            # new-open at the next expiry only counts as a roll leg if the
            # near leg actually bled (the −40% is the load-bearing test).
            nxt_chg = ((nxt["oi"] - px) / px) if px > 0 else 1.0
            if near_chg <= ROLL_DROP_PCT and nxt_chg >= ROLL_GAIN_PCT:
                rolled_pairs.add(near["ckey"])
                rolled_pairs.add(nxt["ckey"])

    # Pass 3 — earnings windows.
    for r in rows:
        ckey = r["ckey"]
        tag: dict[str, Any] = {"expiring": ckey in expiring,
                               "rollover": ckey in rolled_pairs,
                               "earnings": None}
        rep = earnings_dates.get(r.get("under") or "")
        if rep:
            rdate = _parse_iso(rep)
            if rdate is not None:
                days_out = _trading_days_between(today, rdate)
                if days_out is not None and -1 <= days_out <= EARNINGS_WINDOW_DAYS:
                    tag["earnings"] = {"days_to": days_out}
        elif r.get("under") in earnings_dates or (earnings_dates and r.get("under")):
            # Underlying known but no report date cached → window unknown.
            tag["earnings"] = {"unknown": True}
        out[ckey] = tag
    return out


def oi_hygiene_why_suffix(tag: dict[str, Any] | None) -> str:
    """Plain-English suffix for an alert's why-string. Shared contract: the
    client engine appends the identical text for identical tags."""
    if not tag:
        return ""
    parts: list[str] = []
    if tag.get("rollover"):
        parts.append("rollover detected — position migrated expiries, not new flow")
    if isinstance(tag.get("earnings"), dict):
        if tag["earnings"].get("unknown"):
            parts.append("earnings window unknown — direction ambiguous")
        else:
            d = tag["earnings"].get("days_to")
            parts.append(f"earnings in {d} session(s) — direction ambiguous")
    if not parts:
        return ""
    return " [" + "; ".join(parts) + "]"


def _parse_iso(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _trading_days_between(start: date, end: date) -> int | None:
    """Naive trading-day distance (weekends excluded, holidays not). Negative
    when the report date already passed. Good enough for a ±4-session window
    where the boundary days are what matter."""
    if end < start:
        return -_trading_days_between(end, start)
    n = 0
    d = start
    while d < end:
        d = date.fromordinal(d.toordinal() + 1)
        if d.weekday() < 5:
            n += 1
    return n
