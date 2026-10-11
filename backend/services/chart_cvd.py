"""BVC-estimated CVD from OHLCV+volume (Easley/Lopez de Prado/O'Hara 2012).

Pure function over bar history. No trade tape, no vendor recompute, no
interpolation: unknown bars are honest gaps (delta/cvd None), never zero.

Rule set (see BVC_CVD_IMPLEMENTATION_SPEC.md; deviations from its section 6
are documented in tests/services/test_chart_cvd.py):
- Session-anchored at each New York regular-session date: the first bar of a
  session is a gap (no prior close) and the overnight move never enters sigma.
- Sigma is the population std of the trailing up-to-W simple returns ending
  at the bar, session-local. Zero variance with no price move is a balanced
  split (delta 0); zero variance with a real move takes the full side.
- Missing, non-finite, negative or zero volume is a gap (nothing to split).
"""
from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

VERSION = "bvc-cvd.v1"
DEFAULT_WINDOW = 20
CVD_LABEL = ("CVD estimated via bulk volume classification "
             "(Easley, Lopez de Prado & O'Hara 2012); "
             "\u224880% bar accuracy on equities \u2014 directional, not exact. "
             "Unknown \u2260 zero; gaps are honest.")

_NY = "America/New_York"


def _epoch(value: Any) -> float | None:
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not math.isfinite(value):
                return None
            seconds = float(value) / 1000 if value >= 100_000_000_000 else float(value)
            datetime.fromtimestamp(seconds, UTC)
            return seconds
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return None
        return dt.timestamp()
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _positive(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _volume(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    # A measured zero carries no flow to split; absent/negative/non-finite
    # stays absent. A fabricated 0 would read as "balanced flow" on the pane.
    return number if math.isfinite(number) and number > 0 else None


def _session_key(at: float) -> str:
    try:
        return datetime.fromtimestamp(at, UTC).astimezone(
            ZoneInfo(_NY)).date().isoformat()
    except Exception:
        return datetime.fromtimestamp(at, UTC).date().isoformat()


def _phi(z: float) -> float:
    if math.isinf(z):
        return 1.0 if z > 0 else 0.0
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def estimate_cvd_from_bars(bars: list[dict[str, Any]],
                           window: int = DEFAULT_WINDOW) -> list[dict[str, Any]]:
    """Bulk-volume-classification CVD per bar, session-anchored.

    Returns one row per time-parseable bar: {time (epoch s), delta, cvd}.
    Unknown rows carry None for both delta and cvd (honest gaps).
    """
    window = max(1, int(window))
    parsed: list[tuple[float, float | None, float | None]] = []
    for bar in bars or []:
        if not isinstance(bar, dict):
            continue
        at = _epoch(bar.get("t", bar.get("time")))
        if at is None:
            continue
        raw_close = bar.get("c", bar.get("close"))
        close = _positive(raw_close)
        volume = _volume(bar.get("v", bar.get("volume")))
        parsed.append((at, close, volume))
    parsed.sort(key=lambda row: row[0])

    out: list[dict[str, Any]] = []
    session = object()  # sentinel: first row always opens a session
    prior_close: float | None = None
    returns: list[float] = []
    running: float | None = None
    for at, close, volume in parsed:
        key = _session_key(at)
        if key != session:
            session = key
            prior_close = None
            returns = []
            running = None
        if close is None:
            out.append({"time": at, "delta": None, "cvd": None})
            continue
        if prior_close is None:
            prior_close = close
            out.append({"time": at, "delta": None, "cvd": None})
            continue
        ret = (close - prior_close) / prior_close
        prior_close = close
        returns.append(ret)
        recent = returns[-window:]
        mean = sum(recent) / len(recent)
        var = sum((r - mean) ** 2 for r in recent) / len(recent)
        sigma = math.sqrt(var) if var > 0 else 0.0
        if volume is None:
            out.append({"time": at, "delta": None, "cvd": None})
            continue
        if ret == 0.0:
            delta = 0.0
        elif sigma == 0.0:
            delta = volume if ret > 0 else -volume
        else:
            delta = volume * (2.0 * _phi(ret / sigma) - 1.0)
        running = delta if running is None else running + delta
        out.append({"time": at, "delta": delta, "cvd": running})
    return out
