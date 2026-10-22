"""B22 CVD/delta/footprint: actual classified sizes, session resets.

R21-04 admission contract: a declared classified_sizes capability is
required and never defaulted; the admitted stream is instrument-
homogeneous recorded bars knowable at the cursor (foreign/future/previous-
session/late rows are named gaps, never silent); a later corrected
restatement replaces its original statement; unclassified volume stays
its own number; and the running series re-zeroes on session boundaries.
"""
from __future__ import annotations

from services.chart_flow import (
    SUPPORTED_BAR_SECONDS,
    explicit_instrument,
    gate_recorded_rows,
    refused,
    session_bounds,
)


def session_cvd(bars: list[dict]):
    """Running buy-minus-sell; period opens at zero; missing bar => no candle."""
    running = 0
    out = []
    for b in (bars or []):
        if b is None or b.get("buy") is None or b.get("sell") is None:
            continue
        buy, sell = b["buy"], b["sell"]
        if not all(isinstance(v, (int, float)) for v in (buy, sell)):
            continue
        prev = running
        running += buy - sell
        out.append({"open": prev, "close": running, "delta": buy - sell,
                    "unclassified": b.get("unclassified", 0)})
    return out


def _finite(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    out = float(value)
    if out != out or out in (float("inf"), float("-inf")):
        return None
    return out


def admit_delta(bars, *, ticker, cursor, bar_seconds, capabilities, tick_size, units,
                entitlement) -> dict:
    """Admit a classified-delta read at the owning chart cursor (R21-04)."""
    try:
        instrument = explicit_instrument(ticker, tick_size, units, entitlement)
    except ValueError as err:
        return refused(str(err))
    if not isinstance(capabilities, dict) or capabilities.get("classified_sizes") is not True:
        return refused("capability-not-declared: classified_sizes")
    if bar_seconds not in SUPPORTED_BAR_SECONDS:
        return refused("unsupported-bar-seconds")
    session = session_bounds(cursor)
    if session is None:
        return refused("cursor-not-in-regular-session")
    window_end = float(cursor) + float(bar_seconds)
    admitted, gaps = gate_recorded_rows(bars, ticker=instrument["ticker"], cursor=cursor,
                                        window_start=session["start"],
                                        window_end=window_end, session=session)
    gaps.update({"superseded_by_correction": 0, "unclassified_bar": 0})
    corrected_times = {row["event_epoch"] for row in admitted if row.get("corrected") is True}
    stream = []
    for row in admitted:
        if row["event_epoch"] in corrected_times and row.get("corrected") is not True:
            gaps["superseded_by_correction"] += 1
            continue
        if _finite(row.get("buy")) is None or _finite(row.get("sell")) is None:
            # A bar whose classified sizes are unknown but which carries
            # knowable unclassified volume keeps its volume counted; a bar
            # with nothing parseable stays a named gap.
            if _finite(row.get("unclassified")) is not None:
                stream.append({**row, "buy": 0.0, "sell": 0.0})
            else:
                gaps["unclassified_bar"] += 1
            continue
        stream.append(row)
    envelope = {"ticker": instrument["ticker"], "cursor": float(cursor),
                "bar_seconds": bar_seconds,
                "window": {"start": session["start"], "end": window_end},
                "session": session, "instrument": instrument,
                "capabilities": {"classified_sizes": True},
                "admitted_count": 0,
                "excluded_count": sum(gaps.values()), "gaps": gaps,
                "certification": {"basis": "classified bar sizes knowable at the cursor; "
                                           "corrections replace originals",
                                  "certified_by_hash": False}}
    if not stream:
        envelope.update({"status": "unavailable", "reason": "no eligible classified bars",
                         "totals": None, "rows": []})
        return envelope
    stream.sort(key=lambda row: (row["event_epoch"], row["receipt_epoch"]))
    running = 0.0
    classified = 0.0
    unclassed = 0.0
    rows_out = []
    for row in stream:
        if row.get("session_reset") is True:
            running = 0.0
        opened = running
        running += row["buy"] - row["sell"]
        clean_unclassed = _finite(row.get("unclassified"))
        unclassed += clean_unclassed if clean_unclassed is not None else 0.0
        classified += row["buy"] + row["sell"]
        rows_out.append({"time": row["event_epoch"], "open": opened, "close": running,
                         "delta": row["buy"] - row["sell"],
                         "unclassified": clean_unclassed if clean_unclassed is not None else 0.0})
    envelope.update({"status": "available", "rows": rows_out, "admitted_count": len(rows_out),
                     "totals": {"delta": running, "classified_volume": classified,
                                "unclassified_volume": unclassed}})
    return envelope
