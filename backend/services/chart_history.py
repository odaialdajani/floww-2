"""B01 canonical chart contract: strict ingress, legacy compat, temporal bounds.

Preserves legacy price_node_history consumers. New strict parsing lives here;
old _positive callers keep their characterization tests unchanged.
Recorded-only: missing stays unknown, zero stays zero, inferred end never
proves recorded availability.
"""
from __future__ import annotations

import math
import re

_NUMERIC_STR_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")


def _strict_number(value):
    """Return finite float for numbers/strict strings, else None.

    Rejects bool, None, blank, arrays, objects, NaN, Infinity.
    Numeric strings must match explicit grammar after strip.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        text = value.strip()
        if not text or not _NUMERIC_STR_RE.match(text):
            return None
        try:
            number = float(text)
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def parse_price(value):
    """Finite positive price or None. Zero/negative rejected, strings via grammar."""
    number = _strict_number(value)
    if number is None or not math.isfinite(number) or number <= 0:
        return None
    return number


def parse_volume(value):
    """Finite nonnegative volume or None. Preserves genuine zero, None stays None."""
    if value is None:
        return None
    number = _strict_number(value)
    if number is None or not math.isfinite(number) or number < 0:
        return None
    return number


def legacy_close_for_trinity(frame: dict):
    """Old Trinity WallPricePath contract: frames[].close or None, unchanged."""
    if not isinstance(frame, dict):
        return None
    close = frame.get("close")
    if isinstance(close, bool):
        return None
    if isinstance(close, (int, float)) and math.isfinite(close):
        return float(close)
    return None


def vwap_caption(value):
    """Unavailable VWAP caption until qualified source exists."""
    if isinstance(value, bool):
        return "unavailable VWAP"
    if isinstance(value, (int, float)) and math.isfinite(value):
        return f"VWAP {float(value):.2f}"
    return "unavailable VWAP"


def bar_is_complete(end_time, cursor) -> bool:
    """Review completed bars require end_time <= cursor."""
    try:
        return float(end_time) <= float(cursor)
    except (TypeError, ValueError):
        return False


def revision_is_recorded(availability, end_time, cursor) -> bool:
    """Faithful revision needs recorded availability and end_time <= cursor.

    inferred_bar_end is review-only calendar endpoint, never arrival evidence.
    """
    if availability != "recorded":
        return False
    return bar_is_complete(end_time, cursor)
