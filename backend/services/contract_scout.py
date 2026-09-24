"""
backend/services/contract_scout.py — read-only 0DTE candidate scout (T10).

Input: confirmed/conditional price scenario (side + target/invalidation), NOT
cell color. Side filtered BEFORE ranking; dwell only among still-valid
candidates. No candidate is a valid result with counters.
"""

from __future__ import annotations

import math
from typing import Any

REJECT_REASONS = (
    "NO_0DTE_LISTING", "WRONG_SIDE", "UNKNOWN_SIDE", "STALE_BID", "STALE_ASK", "GREEKS_MISSING",
    "SPREAD_TOO_WIDE", "DELTA_OUTSIDE_BAND", "INSUFFICIENT_VOLUME",
    "INSUFFICIENT_TIME", "UNSUPPORTED_SERIES",
)

# Research preset (not proven optimum): |delta| 0.40–0.60.
DELTA_BAND = (0.40, 0.60)


def _age_s(ts: str | None, now_s: float | None = None) -> float | None:
    if not ts:
        return None
    try:
        from datetime import UTC, datetime
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        import time
        now = now_s if now_s is not None else time.time()
        return max(0.0, now - dt.timestamp())
    except (ValueError, TypeError):
        return None


def scout_candidates(contracts: list[dict[str, Any]], scenario_side: str,
                     spot: float, max_stale_s: float = 30.0,
                     max_spread_pct: float = 0.25, now_s: float | None = None,
                     session_date: str | None = None,
                     max_skew_s: float = 5.0) -> dict[str, Any]:
    """Filter eligible side first, then rank. Returns candidates + rejections.

    R4-08/P06 contract: finite bid/ask/delta always checked (NaN never
    passes); quote age checked on every candidate when timestamps are
    present (never only-when-already-invalid); bid/ask skew checked;
    same-day (0DTE) membership enforced when session_date is supplied;
    scenario side filtered before ranking (unknown side rejects everything);
    adjusted/nonstandard contracts quarantined as UNSUPPORTED_SERIES. Missing timestamps are allowed
    for backward-compat fixtures but production callers should require them
    (pass session_date + fresh timestamps; unknown age fails closed when
    required by the caller via require path).
    """
    side = str(scenario_side or "").upper()  # CALLS | PUTS
    want_call = side in ("CALL", "CALLS", "BULLISH", "UP")
    want_put = side in ("PUT", "PUTS", "BEARISH", "DOWN")
    # Strict production context: session_date supplied means real session
    # evaluation — unknown quote age is not fresh (R5-D/R12). Fixture mode
    # (session_date None) keeps backward-compat for synthetic tests.
    strict = session_date is not None
    eligible: list[dict[str, Any]] = []
    rejected: dict[str, int] = {}
    reasons: list[dict[str, str]] = []

    def reject(osi: str, reason: str) -> None:
        rejected[reason] = rejected.get(reason, 0) + 1
        reasons.append({"osi": osi, "reason": reason})

    if not want_call and not want_put:
        # Unknown scenario side: nothing is eligible on either side (R5-D).
        for c in contracts or []:
            reject(str((c or {}).get("osi", (c or {}).get("symbol", ""))), "UNKNOWN_SIDE")
        return {
            "side": side,
            "candidates": [],
            "n_eligible": 0,
            "rejected": rejected,
            "rejection_sample": reasons[:20],
            "delta_band": list(DELTA_BAND),
            "no_candidate_is_valid": True,
        }

    for c in contracts or []:
        osi = str(c.get("osi", c.get("symbol", "")))
        # Adjusted/nonstandard contracts need deliverable/payoff metadata the
        # scout does not price — quarantined, never silently ranked (R5-D).
        if c.get("adjusted") or c.get("nonstandard"):
            reject(osi, "UNSUPPORTED_SERIES")
            continue
        is_call = str(c.get("type", "")).lower().startswith("c")
        if want_call and not is_call:
            reject(osi, "WRONG_SIDE")
            continue
        if want_put and is_call:
            reject(osi, "WRONG_SIDE")
            continue
        # 0DTE membership when the session date is known: expiry must be
        # same-day. Skipped when session_date is None (legacy fixtures).
        if session_date is not None:
            exp = str(c.get("expiry", "") or "")
            if exp[:10] != str(session_date)[:10]:
                reject(osi, "NO_0DTE_LISTING")
                continue
        bid, ask = c.get("bid"), c.get("ask")
        try:
            bid_f = float(bid) if bid is not None else None
            ask_f = float(ask) if ask is not None else None
        except (TypeError, ValueError):
            reject(osi, "GREEKS_MISSING")
            continue
        if (bid_f is None or ask_f is None or not math.isfinite(bid_f)
                or not math.isfinite(ask_f) or bid_f <= 0 or ask_f <= 0
                or bid_f > ask_f):
            # Distinguish stale vs crossed/missing via timestamps when present.
            bid_age = _age_s(c.get("bid_timestamp"), now_s)
            ask_age = _age_s(c.get("ask_timestamp"), now_s)
            if bid_age is not None and bid_age > max_stale_s:
                reject(osi, "STALE_BID")
            elif ask_age is not None and ask_age > max_stale_s:
                reject(osi, "STALE_ASK")
            else:
                reject(osi, "SPREAD_TOO_WIDE")
            continue
        # Freshness on every candidate (not only-when-invalid): stale ordinary
        # quotes never rank. Strict production context rejects unknown age;
        # fixture mode allows missing timestamps for synthetic tests.
        bid_age = _age_s(c.get("bid_timestamp"), now_s)
        ask_age = _age_s(c.get("ask_timestamp"), now_s)
        if strict and bid_age is None:
            reject(osi, "STALE_BID")
            continue
        if strict and ask_age is None:
            reject(osi, "STALE_ASK")
            continue
        if bid_age is not None and bid_age > max_stale_s:
            reject(osi, "STALE_BID")
            continue
        if ask_age is not None and ask_age > max_stale_s:
            reject(osi, "STALE_ASK")
            continue
        if bid_age is not None and ask_age is not None:
            if abs(bid_age - ask_age) > max_skew_s:
                reject(osi, "STALE_ASK")
                continue
        mid = (bid_f + ask_f) / 2
        if mid <= 0 or (ask_f - bid_f) / mid > max_spread_pct:
            reject(osi, "SPREAD_TOO_WIDE")
            continue
        delta = c.get("delta")
        try:
            d = abs(float(delta)) if delta is not None else None
        except (TypeError, ValueError):
            d = None
        if d is None or not math.isfinite(d):
            reject(osi, "GREEKS_MISSING")
            continue
        if not (DELTA_BAND[0] <= d <= DELTA_BAND[1]):
            reject(osi, "DELTA_OUTSIDE_BAND")
            continue
        vol = c.get("volume")
        try:
            v = float(vol) if vol is not None else 0
        except (TypeError, ValueError):
            v = 0
        if v <= 0:
            reject(osi, "INSUFFICIENT_VOLUME")
            continue
        T = c.get("T")
        try:
            t = float(T) if T is not None else 0
        except (TypeError, ValueError):
            t = 0
        if t <= 0:
            reject(osi, "INSUFFICIENT_TIME")
            continue
        eligible.append({**c, "_mid": mid, "_delta_abs": d})

    eligible.sort(key=lambda c: abs(float(c.get("_delta_abs", 0.5)) - 0.5))
    return {
        "side": side,
        "candidates": eligible[:5],
        "n_eligible": len(eligible),
        "rejected": rejected,
        "rejection_sample": reasons[:20],
        "delta_band": list(DELTA_BAND),
        "no_candidate_is_valid": len(eligible) == 0,
    }
