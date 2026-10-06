"""Pure session exposure-weighted level (Command Code C1.2).

Portable math for a session reference level. Route/server code owns the
actual async bar path, session scope proof, and market-VWAP labeling. This
helper takes already-shaped canonical bars and never touches I/O or event
loops.
"""

from __future__ import annotations

import math
from typing import Any

SESSION_LEVEL_VERSION = "session-exposure-level.v1"


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def session_exposure_level(
    bars: list[dict[str, Any]] | None,
    session_date: str,
    session: str = "regular",
) -> dict[str, Any]:
    """Return sum(typical*volume)/sum(volume) for one session date.

    Typical price is (H+L+C)/3. Only rows whose ``session`` matches and
    whose ``date`` starts with ``session_date`` are used. No volume means
    no level: unavailable, never zero and never a fallback price.
    """
    if not bars:
        return {
            "version": SESSION_LEVEL_VERSION,
            "value": None,
            "status": "unavailable",
            "reason": "NO_BARS",
            "bars_used": 0,
            "bars_skipped": 0,
            "source_dates": [],
        }
    total = 0.0
    volume_total = 0.0
    used = 0
    skipped = 0
    dates: list[str] = []
    for row in bars:
        if not isinstance(row, dict):
            skipped += 1
            continue
        if str(row.get("session") or "regular").lower() != session.lower():
            skipped += 1
            continue
        stamp = str(row.get("date") or row.get("timestamp") or "")
        if not stamp.startswith(session_date):
            skipped += 1
            continue
        high, low, close, volume = (
            _num(row.get("high")),
            _num(row.get("low")),
            _num(row.get("close")),
            _num(row.get("volume")),
        )
        if high is None or low is None or close is None or volume is None or volume <= 0:
            skipped += 1
            continue
        total += ((high + low + close) / 3.0) * volume
        volume_total += volume
        used += 1
        dates.append(stamp)
    if used == 0 or volume_total <= 0:
        return {
            "version": SESSION_LEVEL_VERSION,
            "value": None,
            "status": "unavailable",
            "reason": "NO_VOLUME" if bars else "NO_BARS",
            "bars_used": 0,
            "bars_skipped": skipped,
            "source_dates": [],
        }
    return {
        "version": SESSION_LEVEL_VERSION,
        "value": total / volume_total,
        "status": "ok",
        "reason": None,
        "bars_used": used,
        "bars_skipped": skipped,
        "source_dates": dates,
    }
