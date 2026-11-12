"""Paper mark provenance (`paper-mark-provenance.v1`).

The paper book priced positions from a bare `dict[str, float]` and reported
`mark_source: None` / `mark_time: None`. Nothing said where a mark came from,
how old it was, or whether it was stale. This module gives every mark a
typed record with its provenance and keeps the states apart:

* `ok` — an observed price, including an observed zero (a worthless position
  is real data, not a missing reading);
* `invalid` — a value that cannot be a price (negative, non-numeric,
  non-finite);
* `unavailable` — no mark was supplied, or the fetch produced no observation.

A mark with no declared source is never called fresh: it stays usable but its
provenance is `undeclared`. A stale mark keeps its value and is listed as
stale. Nothing here fetches, writes or invents a price.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

VERSION = "paper-mark-provenance.v1"

MARK_OK = "ok"
MARK_UNAVAILABLE = "unavailable"
MARK_INVALID = "invalid"

REASON_NO_MARKS = "NO_MARKS"
REASON_NO_USABLE_MARKS = "NO_USABLE_MARKS"
REASON_NO_MARK_SUPPLIED = "NO_MARK_SUPPLIED"
REASON_MARK_FETCH_FAILED = "MARK_FETCH_FAILED"
REASON_NOT_A_NUMBER = "NOT_A_NUMBER"
REASON_NEGATIVE_PRICE = "NEGATIVE_PRICE"
REASON_NO_SPOT = "NO_SPOT"
REASON_PARTIAL_MARKS = "PARTIAL_MARKS"


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _clock_text(value: Any) -> str | None:
    """Keep a timestamp as text; a datetime is normalized to UTC."""
    if isinstance(value, datetime):
        dt = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return dt.astimezone(UTC).isoformat()
    return _text(value)


def _as_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    out = float(value)
    return out if math.isfinite(out) else None


def mark_record(symbol: str, price: Any, *, provider: Any = None, source: Any = None,
                fetched_at: Any = None, event_time: Any = None, stale: Any = False,
                age_s: Any = None, reason: Any = None) -> dict[str, Any]:
    """One typed mark with its provenance.

    `price` may be None (no observation), a number (an observed price, zero
    included) or something that cannot be a price (invalid).
    """
    symbol = (_text(symbol) or "").upper()
    source_text = _text(source)
    provider_text = _text(provider)
    record: dict[str, Any] = {
        "symbol": symbol,
        "price": None,
        "status": MARK_UNAVAILABLE,
        "reason": _text(reason) or REASON_NO_MARK_SUPPLIED,
        "provider": provider_text,
        "source": source_text,
        "source_declared": bool(source_text or provider_text),
        "fetched_at": _clock_text(fetched_at),
        "event_time": _clock_text(event_time),
        "age_s": _as_number(age_s),
        "stale": bool(stale),
        "measured_zero": False,
        "unit": "share",
        "contract_multiplier": {"value": 1, "source": "share_quantity"},
    }
    if price is None:
        return record
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        record["status"] = MARK_INVALID
        record["reason"] = REASON_NOT_A_NUMBER
        return record
    value = float(price)
    if not math.isfinite(value):
        record["status"] = MARK_INVALID
        record["reason"] = REASON_NOT_A_NUMBER
        return record
    if value < 0:
        record["status"] = MARK_INVALID
        record["reason"] = REASON_NEGATIVE_PRICE
        return record
    record["price"] = value
    record["measured_zero"] = value == 0.0
    record["status"] = MARK_OK
    record["reason"] = None
    return record


def normalize_mark(symbol: str, value: Any) -> dict[str, Any]:
    """Accept a raw price or an existing mark record."""
    if isinstance(value, dict):
        record = mark_record(
            symbol, value.get("price"),
            provider=value.get("provider"),
            source=value.get("source"),
            fetched_at=value.get("fetched_at"),
            event_time=value.get("event_time"),
            stale=value.get("stale"),
            age_s=value.get("age_s"),
            reason=value.get("reason"),
        )
        # An invalid reading stays invalid: a missing price must not demote a
        # rejected value into an ordinary "no observation".
        if value.get("status") == MARK_INVALID and record["status"] != MARK_OK:
            record["status"] = MARK_INVALID
        return record
    return mark_record(symbol, value)


def normalize_marks(current_prices: dict[str, Any] | None = None,
                    marks: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Normalize the legacy price map and typed marks into one record map.

    The legacy `current_prices` map stays supported; its marks carry no
    source, so their provenance is explicitly `undeclared`.
    """
    source = marks if marks else current_prices
    out: dict[str, dict[str, Any]] = {}
    for symbol, value in (source or {}).items():
        key = (_text(symbol) or "").upper()
        if not key:
            continue
        out[key] = normalize_mark(key, value)
    return out


def mark_from_chain_payload(symbol: str, payload: Any) -> dict[str, Any]:
    """Build a mark record from an existing chain payload.

    The chain's spot carries its own source, receipt clock and event clock.
    A missing or non-positive spot is the source's "no observation"
    convention, not a measured zero, so it stays unavailable with a reason.
    """
    payload = payload if isinstance(payload, dict) else {}
    spot = payload.get("spot")
    age = payload.get("cache_age_s")
    if age is None:
        age = payload.get("stale_age_s")
    record = mark_record(
        symbol, spot,
        provider=payload.get("data_source"),
        source=payload.get("spot_source"),
        fetched_at=payload.get("spot_fetched_at") or payload.get("fetched_at"),
        event_time=payload.get("spot_event_time") or payload.get("event_time"),
        stale=payload.get("stale"),
        age_s=age,
    )
    if record["status"] == MARK_OK and record["price"] == 0.0:
        # The chain reports "no spot" as 0.0; that is an absent observation,
        # not a worthless stock.
        record["status"] = MARK_UNAVAILABLE
        record["price"] = None
        record["measured_zero"] = False
        record["reason"] = REASON_NO_SPOT
    return record


def _latest_clock(values: list[str]) -> str | None:
    """The newest clock among ISO texts, compared as instants."""
    best: tuple[float, str] | None = None
    for value in values:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        if parsed.tzinfo is None:
            continue
        stamp = parsed.astimezone(UTC).timestamp()
        if best is None or stamp > best[0]:
            best = (stamp, str(value))
    return best[1] if best else None


def build_mark_envelope(marks: dict[str, dict[str, Any]] | None = None,
                        requested: list[str] | None = None) -> dict[str, Any]:
    """One envelope over the supplied marks.

    The envelope states what was asked for, what was priced, what was not and
    why, which marks are stale, and the newest receipt clock among them.
    """
    items: dict[str, dict[str, Any]] = {}
    for symbol, record in (marks or {}).items():
        key = (_text(symbol) or "").upper()
        if key and isinstance(record, dict):
            items[key] = record
    priced = sorted(s for s, r in items.items() if r.get("status") == MARK_OK)
    unavailable = [{"symbol": s, "reason": r.get("reason") or "MARK_UNAVAILABLE"}
                   for s, r in sorted(items.items()) if r.get("status") != MARK_OK]
    stale_symbols = sorted(s for s, r in items.items() if r.get("stale"))
    providers = {r.get("provider") for s, r in items.items()
                 if r.get("status") == MARK_OK and r.get("provider")}
    source = next(iter(providers)) if len(providers) == 1 else None
    declared = bool(priced) and all(
        items[s].get("source_declared") for s in priced)
    if not items:
        status, reason = MARK_UNAVAILABLE, REASON_NO_MARKS
    elif not priced:
        status, reason = MARK_UNAVAILABLE, REASON_NO_USABLE_MARKS
    elif unavailable:
        status, reason = "partial", REASON_PARTIAL_MARKS
    else:
        status, reason = MARK_OK, None
    return {
        "version": VERSION,
        "status": status,
        "reason": reason,
        "provenance": "declared" if declared else "undeclared",
        "source": source,
        "as_of": _latest_clock([r.get("fetched_at") for r in items.values()
                                if r.get("fetched_at")]),
        "requested": sorted({(_text(s) or "").upper() for s in (requested or []) if s}),
        "priced": priced,
        "unavailable": unavailable,
        "stale_symbols": stale_symbols,
        "items": items,
    }


__all__ = [
    "MARK_INVALID",
    "MARK_OK",
    "MARK_UNAVAILABLE",
    "REASON_MARK_FETCH_FAILED",
    "REASON_NO_MARK_SUPPLIED",
    "REASON_NO_MARKS",
    "VERSION",
    "build_mark_envelope",
    "mark_from_chain_payload",
    "mark_record",
    "normalize_mark",
    "normalize_marks",
]
