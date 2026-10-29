"""B21 dark-pool: exact single prints, equities only, no direction.

R21-04 admission contract: admitted dark-pool prints are exact single
equity prints from one instrument, knowable at the cursor on the recorded
receipt clock, inside the owning session, with corrections replacing the
prints they correct and aggregates never passing as shapes; the largest-
notional levels keep direction explicitly unknown. An untouchable/naked
claim lives in chart_profiles.naked_levels_claim, where an unknown range
is never proof of untouched. Instrument tick/units/entitlement are
explicit; those apply to every admitted print because foreign rows are
excluded before admission.
"""
from __future__ import annotations

from services.chart_flow import SUPPORTED_BAR_SECONDS, explicit_instrument, gate_recorded_rows, refused, session_bounds


def top_levels(prints: list[dict], top_n=3):
    """Return largest notional single prints with venue/price/size/event/receipt."""
    rows = [p for p in (prints or [])
            if isinstance(p, dict) and p.get("asset_class", "equity") == "equity"
            and all(p.get(k) is not None for k in ("price", "size", "event_time", "venue"))]
    rows.sort(key=lambda p: p["price"] * p["size"], reverse=True)
    return [{"price": p["price"], "size": p["size"], "venue": p["venue"],
             "event_time": p["event_time"], "notional": p["price"] * p["size"],
             "direction": "unknown"} for p in rows[:top_n]]

_REQUIRED_FIELDS = ("price", "size", "event_time", "venue")


def _finite(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    out = float(value)
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def admit_darkpool_prints(rows, *, ticker, cursor, bar_seconds, tick_size, units,
                          entitlement, max_delay_seconds=None, top_n=3) -> dict:
    """Admit dark-pool prints for the level display at the owning cursor."""
    try:
        instrument = explicit_instrument(ticker, tick_size, units, entitlement)
    except ValueError as err:
        return refused(str(err))
    if bar_seconds not in SUPPORTED_BAR_SECONDS:
        return refused("unsupported-bar-seconds")
    session = session_bounds(cursor)
    if session is None:
        return refused("cursor-not-in-regular-session")
    window_end = float(cursor) + float(bar_seconds)
    admitted, gaps = gate_recorded_rows(rows, ticker=instrument["ticker"], cursor=cursor,
                                        window_start=session["start"],
                                        window_end=window_end, session=session)
    gaps.update({"aggregated_row": 0, "non_equity_row": 0,
                 "superseded_by_correction": 0, "delay_unknown_or_over_cap": 0})
    eligible = []
    for row in admitted:
        if row.get("asset_class", "equity") != "equity":
            gaps["non_equity_row"] += 1
            continue
        if row.get("aggregate") is True:
            gaps["aggregated_row"] += 1
            continue
        if any(row.get(key) is None for key in _REQUIRED_FIELDS):
            gaps["malformed_row"] += 1
            continue
        price = _finite(row.get("price"))
        size = _finite(row.get("size"))
        if price is None or size is None or price <= 0.0 or size <= 0.0:
            gaps["malformed_row"] += 1
            continue
        if not isinstance(row.get("venue"), str) or not row["venue"].strip():
            gaps["malformed_row"] += 1
            continue
        if max_delay_seconds is not None:
            delay = _finite(row.get("delay_seconds"))
            if delay is None or delay < 0.0 or delay > max_delay_seconds:
                gaps["delay_unknown_or_over_cap"] += 1
                continue
        eligible.append(row)
    superseded = {row.get("correction_of") for row in eligible
                  if row.get("correction_of") is not None}
    if superseded:
        kept = []
        for row in eligible:
            if row.get("print_id") is not None and row["print_id"] in superseded:
                gaps["superseded_by_correction"] += 1
                continue
            kept.append(row)
        eligible = kept
    levels = [{"price": row["price"], "size": row["size"], "venue": row["venue"],
               "event_time": row["event_time"], "received_at": row["received_at"],
               "notional": row["price"] * row["size"], "direction": "unknown"}
              for row in eligible]
    levels.sort(key=lambda level: level["notional"], reverse=True)
    envelope = {"status": "available", "ticker": instrument["ticker"],
                "cursor": float(cursor), "bar_seconds": bar_seconds,
                "window": {"start": session["start"], "end": window_end},
                "session": session, "instrument": instrument,
                "admitted_count": len(levels),
                "excluded_count": sum(gaps.values()), "gaps": gaps,
                "prints": levels, "top": levels[:top_n],
                "certification": {"basis": "exact single prints with ordered eligibility; "
                                           "no direction claims",
                                  "certified_by_hash": False}}
    if not levels:
        envelope.update({"status": "unavailable", "reason": "no eligible dark-pool prints"})
    return envelope
