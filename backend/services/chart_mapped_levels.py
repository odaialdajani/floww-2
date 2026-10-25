"""B09 cross-instrument mapped levels: the source->target RATIO LOCK + typed refusals.

Contract: C2-PRODUCER-CONTRACTS-20261024.json v2, b09_mapped_levels_contract
(sha256 9f8f92ef08d2a28fe75f288125b5caf215667aa03d18f27101e11afa4577727a).

Rules frozen by that contract:
- Supported pairs are the C040 validated equity/index families ONLY. Futures
  pairs (ES/NQ) and the related-futures families stay OUT until a validated
  mapping exists - never guessed, never speculatively enabled.
- Review mode uses an EXPLICIT HORIZONTAL LOCK: the newest eligible ratio
  at-or-before the cursor, held flat; known_at is always <= cursor and a bar
  is knowable at its own close time, so no-lookahead holds by construction.
- Zero on either side refuses (a zero numerator maps every level to zero -
  misleading; a zero denominator is not a ratio). Missing is never zero.
- The C115 SPXW exposure-VWAP board-combine option is a REFUSAL until an
  owner-reviewed combination spec exists; foreign currencies/metric bases are
  never summed.
- Levels are NOT invented here: the producer supplies the locked ratio,
  provenance and shape legend; the level list is empty until a recorded
  source scope supplies real levels (levels_status says so honestly).
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from services.chart_flow import session_bounds_for_date

_NY = ZoneInfo("America/New_York")

SUPPORTED_PAIRS = {
    ("SPXW", "SPY"), ("SPX", "SPY"), ("NDXP", "QQQ"), ("NDX", "QQQ"),
}

LEGEND = {
    "diamond": "Derived level mapped from the source instrument by the locked "
              "ratio (heuristic, not a direction call)",
    "triangle": "Secondary derived marker mapped with the same ratio "
                "provenance (heuristic, not a direction call)",
}


def is_supported_pair(source: str, target: str) -> bool:
    return (source, target) in SUPPORTED_PAIRS


def _refused(reason: str, source: str, target: str, cursor: float, **extra):
    body = {"status": "refused", "reason": reason, "source": source,
            "target": target, "levels": [], "cursor": cursor}
    body.update(extra)
    return body


def _unavailable(reason: str, source: str, target: str, cursor: float, **extra):
    body = {"status": "unavailable", "reason": reason, "source": source,
            "target": target, "levels": [], "cursor": cursor}
    body.update(extra)
    return body


def _finite_close(bar):
    try:
        value = bar.get("c")
    except (TypeError, ValueError):
        return None
    if isinstance(value, bool):
        # H3 V31: bool subclasses int — True must never pass as a close.
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return value


def _bar_time(bar):
    try:
        t = float(bar.get("t"))
    except (TypeError, ValueError):
        return None
    return t


def _ny_date(t: float):
    return datetime.fromtimestamp(t, tz=_NY).date()


def mapped_levels_response(target: str, source: str, cursor: float,
                           source_bars, target_bars, combine: str | None = None):
    """The full typed response for GET /api/heatseeker/mapped-levels/{target}."""
    # 1. Pair validation (C040) - before any provider read or session work.
    if not is_supported_pair(source, target):
        return _refused("unsupported-pair", source, target, cursor,
                        reason_detail="not a validated C040 family mapping")

    # 2. C115: the SPXW board-combine option is a refusal, not a feature.
    if combine:
        return _refused("spxw-board-combination-unavailable", source, target, cursor,
                        reason_detail="the SPXW exposure-VWAP Market-combine option is "
                                      "priced in SPX units and stays unavailable until an "
                                      "owner-reviewed board combination spec exists; "
                                      "foreign currencies/metric bases are never summed")

    # 3. The cursor must sit inside a regular NY session.
    bounds = session_bounds_for_date(_ny_date(cursor))
    if bounds is None or not (bounds["start"] <= cursor < bounds["end"]):
        return _refused("cursor-not-in-regular-session", source, target, cursor)

    # 4. Eligibility at-or-before the cursor (no-lookahead by construction).
    s_bars = [(t, b) for b in (source_bars or [])
              if (t := _bar_time(b)) is not None and t <= cursor]
    t_bars = [(t, b) for b in (target_bars or [])
              if (t := _bar_time(b)) is not None and t <= cursor]
    if not (source_bars or []):
        return _refused("source-not-eligible", source, target, cursor,
                        reason_detail="the source has no recorded bars for this read")
    if not s_bars:
        return _unavailable("no-shared-session", source, target, cursor,
                            reason_detail="every source bar is after the cursor - excluded")
    if not t_bars:
        return _unavailable("no-shared-session", source, target, cursor,
                            reason_detail="the target has no eligible bars at-or-before the cursor")

    s_t, s_new = max(s_bars, key=lambda pair: pair[0])
    t_t, t_new = max(t_bars, key=lambda pair: pair[0])
    if _ny_date(s_t) != _ny_date(t_t):
        return _unavailable("no-shared-session", source, target, cursor,
                            reason_detail="the newest eligible source and target bars "
                                          "sit in different NY sessions")

    s_c, t_c = _finite_close(s_new), _finite_close(t_new)
    if s_c is None or t_c is None or s_c == 0 or t_c == 0:
        return _refused("ratio-unavailable-at-cursor", source, target, cursor,
                        reason_detail="zero or non-finite close on either side "
                                      "is not a ratio")

    known_at = max(s_t, t_t)
    window = {"start": min(s_t, t_t), "end": max(s_t, t_t)}
    return {
        "status": "available",
        "source": source,
        "target": target,
        "ratio": {
            "value": s_c / t_c,
            "provenance": {
                "source_bars_used": len(s_bars),
                "target_bars_used": len(t_bars),
                "window": window,
                "known_at": known_at,
            },
        },
        "levels": [],
        "levels_status": "no recorded source-scope levels at this cursor - "
                         "the caller supplies real levels; none are invented here",
        "legend": LEGEND,
        "cursor": cursor,
        "session": {"date": bounds["date"], "tz": bounds["tz"]},
    }
