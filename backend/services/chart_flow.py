"""B20 flow buckets: call up/put down, hash equality, explicit unknowns.

R21-03 admission contract (shared row gates live here for B21-B23): an
admitted bucket is derived from recorded rows, never claimed by a hash.
Rows carry their own instrument, event clock and recorded receipt clock;
the interval comes from the owning chart/source (R21-01 bar_seconds set);
eligibility = receipt <= cursor AND event_time inside the selected bar's
own window; filters are applied for real; every exclusion is reported in
named gaps; zero admitted rows stays "unavailable"; and locally generated
matching hashes alone can never certify a bucket.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

SUPPORTED_BAR_SECONDS = (60, 300, 900, 1800, 3600)
WINDOW_KEYS = {60: "1m", 300: "5m", 900: "15m", 1800: "30m", 3600: "1h"}
SESSION_TZ = ZoneInfo("America/New_York")
# Published NYSE schedule, checked statically (no provider reads): days the
# equity markets were closed and days with a 1:00 p.m. early close for
# 2025-2028 (2025-2026 verified against NYSE/ICE, Nasdaq and FINRA pages;
# 2027-2028 transcribed from the NYSE hours-calendars table, including its
# observed-holiday and New-Year-2028 "no holiday observed" rulings). Dates
# outside the table get plain weekday behavior and no schedule claim is
# made for them.
_NYSE_CLOSED = frozenset({
    "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18",
    "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27",
    "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
    "2028-01-17", "2028-02-21", "2028-04-14", "2028-05-29", "2028-06-19",
    "2028-07-04", "2028-09-04", "2028-11-23", "2028-12-25",
})
_NYSE_EARLY_CLOSE_HOUR = {
    "2025-07-03": 13, "2025-11-28": 13, "2025-12-24": 13,
    "2026-11-27": 13, "2026-12-24": 13,
    "2027-11-26": 13, "2028-07-03": 13, "2028-11-24": 13,
}
_NY_SCHEDULE_COVERAGE = ("2025", "2026", "2027", "2028")
_FILTER_KEYS = ("min_premium", "max_premium", "side")
_INSTRUMENT_KEYS = ("ticker", "instrument", "symbol")
_GAPS = ("malformed_row", "foreign_instrument", "late_receipt", "missing_receipt",
         "previous_session", "future_event", "stale_event")


def bucket_hash(bar_id, window, filters) -> str:
    """Equal filter/cursor hash for drilldown and totals."""
    raw = json.dumps({"bar": bar_id, "window": window, "filters": filters or {}}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def bucketize(trades: list[dict]):
    """Sum call premium above zero, put below; unknown classifications explicit."""
    call = sum(t.get("premium", 0) for t in (trades or []) if t.get("side") == "call")
    put = sum(t.get("premium", 0) for t in (trades or []) if t.get("side") == "put")
    unknown = [t for t in (trades or []) if t.get("side") not in ("call", "put")]
    return {"call_premium": call, "put_premium": -abs(put), "count": len(trades or []),
            "unknown": len(unknown), "top": sorted(trades or [], key=lambda t: t.get("premium", 0), reverse=True)[:3]}


def session_bounds_for_date(ny_date) -> dict | None:
    """Bounds for a selected NY date: full 09:30-16:00 session, 1:00 p.m.
    close on published early-close days, and None on weekends or published
    closed days (static 2025-2028 schedule; later dates make no claim)."""
    key = ny_date.strftime("%Y-%m-%d")
    if ny_date.weekday() >= 5 or key in _NYSE_CLOSED:
        return None
    open_dt = datetime(ny_date.year, ny_date.month, ny_date.day, 9, 30, tzinfo=SESSION_TZ)
    close_dt = datetime(ny_date.year, ny_date.month, ny_date.day,
                        _NYSE_EARLY_CLOSE_HOUR.get(key, 16), 0, tzinfo=SESSION_TZ)
    return {"start": open_dt.timestamp(), "end": close_dt.timestamp(),
            "tz": "America/New_York", "date": key}


def session_bounds(cursor) -> dict | None:
    """Regular session bounds for a cursor: the America/New_York wall-clock
    date must be a published trading day (2025-2028 closed/early-close
    schedule included) and the moment must fall inside its open/close.
    Returns None when the cursor cannot name such a moment."""
    try:
        moment = datetime.fromtimestamp(float(cursor), tz=UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    ny = moment.astimezone(SESSION_TZ)
    bounds = session_bounds_for_date(ny)
    if bounds is None:
        return None
    unless_ = moment.timestamp()
    if not (bounds["start"] <= unless_ < bounds["end"]):
        return None
    return bounds


def resolve_epoch(value) -> float | None:
    """Numbers and ISO timestamps both resolve to epoch seconds (naive
    strings are treated as UTC); anything else is unresolvable."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            out = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if math.isnan(out) or math.isinf(out):
            return None
        return out
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.timestamp()
    return None


def explicit_instrument(ticker, tick_size=None, units=None, entitlement=None) -> dict:
    """R21-04 contract: instrument tick/units/entitlement are explicit and
    never defaulted. Raises ValueError carrying the refusal code."""
    name = ticker.strip().upper() if isinstance(ticker, str) else ""
    if not (1 <= len(name) <= 12):
        raise ValueError("instrument-not-explicit")
    if isinstance(tick_size, int) and not isinstance(tick_size, bool):
        tick_size = float(tick_size)
    if not isinstance(tick_size, float) or not (tick_size > 0.0 and tick_size == tick_size):
        raise ValueError("instrument-tick-not-explicit")
    if not isinstance(units, str) or not (0 < len(units.strip()) <= 24):
        raise ValueError("instrument-units-not-explicit")
    if not isinstance(entitlement, str) or not (0 < len(entitlement.strip()) <= 64):
        raise ValueError("entitlement-not-explicit")
    return {"ticker": name, "tick_size": tick_size,
            "units": units.strip(), "entitlement": entitlement.strip()}


def gate_recorded_rows(rows, *, ticker, cursor, window_start=None, window_end=None,
                       session=None):
    """Shared recorded-row admission gates for flow/delta/darkpool (R21-03/04).

    Returns (admitted, gaps). Admitted rows are shallow copies enriched with
    event_epoch/receipt_epoch. Foreign instruments, late receipts,
    previous-session, future and stale events stay named counts, never
    silent drops. `window_start`/`window_end` bound the owning bucket;
    `session` enables honest previous-session naming."""
    gaps = {key: 0 for key in _GAPS}
    admitted = []
    want = ticker.strip().upper() if isinstance(ticker, str) else ""
    cursor = resolve_epoch(cursor)
    if not want:
        raise ValueError("instrument-not-explicit")
    if cursor is None:
        raise ValueError("cursor-not-epoch")
    for raw in rows or []:
        if not isinstance(raw, dict):
            gaps["malformed_row"] += 1
            continue
        instrument = None
        for key in _INSTRUMENT_KEYS:
            candidate = raw.get(key)
            if isinstance(candidate, str) and candidate.strip():
                instrument = candidate.strip().upper()
                break
        event = resolve_epoch(raw.get("event_time"))
        receipt = resolve_epoch(raw.get("received_at"))
        if not instrument or event is None:
            gaps["malformed_row"] += 1
            continue
        if instrument != want:
            gaps["foreign_instrument"] += 1
            continue
        if receipt is None:
            gaps["missing_receipt"] += 1
            continue
        if receipt > cursor:
            gaps["late_receipt"] += 1
            continue
        if event > cursor or (window_end is not None and event >= window_end):
            gaps["future_event"] += 1
            continue
        if window_start is not None and event < window_start:
            if session is not None and event < session["start"]:
                gaps["previous_session"] += 1
            else:
                gaps["stale_event"] += 1
            continue
        if session is not None and not (session["start"] <= event < session["end"]):
            gaps["future_event"] += 1
            continue
        row = dict(raw)
        row["event_epoch"] = event
        row["receipt_epoch"] = receipt
        admitted.append(row)
    return admitted, gaps


def refused(reason: str) -> dict:
    return {"status": "refused", "reason": reason}


def _canonical_filters(filters):
    if filters is None:
        return {}
    if not isinstance(filters, dict):
        raise ValueError("unsupported-filter")
    canonical = {}
    for key, raw in filters.items():
        if key not in _FILTER_KEYS:
            raise ValueError("unsupported-filter")
        if key in ("min_premium", "max_premium"):
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValueError("unsupported-filter")
            value = float(raw)
            if math.isnan(value) or math.isinf(value) or value < 0:
                raise ValueError("unsupported-filter")
            canonical[key] = value
        else:
            if raw not in ("call", "put", "all"):
                raise ValueError("unsupported-filter")
            if raw != "all":
                canonical[key] = raw
    return canonical


def admit_flow_bucket(rows, *, ticker, cursor, bar_seconds, filters=None,
                      caller_scope_hash=None) -> dict:
    """Derive the focused flow bucket from recorded rows (R21-03):

    "SPY bucket excludes QQQ, future and previous-session rows; interval
    comes from owning chart/source, filters actually select admitted rows;
    no-data remains unavailable; matching locally generated hashes alone
    cannot certify a bucket."""
    name = ticker.strip().upper() if isinstance(ticker, str) else ""
    if not (1 <= len(name) <= 12):
        return refused("instrument-not-explicit")
    if bar_seconds not in SUPPORTED_BAR_SECONDS:
        return refused("unsupported-bar-seconds")
    try:
        canonical = _canonical_filters(filters)
    except ValueError as err:
        return refused(str(err))
    session = session_bounds(cursor)
    if session is None:
        return refused("cursor-not-in-regular-session")
    cursor_epoch = float(cursor)
    bucket_index = int((cursor_epoch - session["start"]) // bar_seconds)
    window_start = session["start"] + bucket_index * bar_seconds
    window_end = min(window_start + float(bar_seconds), session["end"])
    admitted, gaps = gate_recorded_rows(rows, ticker=name, cursor=cursor_epoch,
                                        window_start=window_start,
                                        window_end=window_end, session=session)
    filtered_out = 0
    selected = []
    for row in admitted:
        premium = row.get("premium")
        if isinstance(premium, bool) or not isinstance(premium, (int, float)):
            premium = None
        if premium is not None and not (0.0 <= float(premium) <= 1e12):
            gaps["anomalous_premium"] = gaps.get("anomalous_premium", 0) + 1
            continue
        if "min_premium" in canonical and (premium is None or premium < canonical["min_premium"]):
            filtered_out += 1
            continue
        if "max_premium" in canonical and (premium is None or premium > canonical["max_premium"]):
            filtered_out += 1
            continue
        if canonical.get("side") and row.get("side") != canonical["side"]:
            filtered_out += 1
            continue
        selected.append(row)
    gaps["filtered_out"] = filtered_out
    scope_hash = bucket_hash(bucket_index, WINDOW_KEYS[bar_seconds], canonical)
    certification = {
        "basis": "row-level eligibility checks over recorded receipt and own-window event clocks",
        "certified_by_hash": False,
        "caller_scope_hash": caller_scope_hash if isinstance(caller_scope_hash, str) else None,
    }
    envelope = {"status": "available", "ticker": name, "cursor": cursor_epoch,
                "bar_seconds": bar_seconds,
                "window": {"start": window_start, "end": window_end},
                "bucket_index": bucket_index, "session": session,
                "totals": bucketize(selected), "admitted_count": len(selected),
                "excluded_count": sum(gaps.values()), "gaps": gaps,
                "filters_applied": canonical, "scope_hash": scope_hash,
                "certification": certification}
    if not selected:
        envelope["status"] = "unavailable"
        envelope["reason"] = "no admitted rows for this flow bucket"
        envelope["totals"] = None
    return envelope
