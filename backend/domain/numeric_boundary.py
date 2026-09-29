"""Single numeric boundary for scalar/array/JSON outputs (Command Code C1.6).

Normalize once where appropriate. Valid numbers become plain Python floats.
Missing/invalid/nonfinite values become None and stay missing. This helper
never masks an invalid value as zero and never mutates frozen ML artifacts;
callers decide whether None is unavailable, skipped, or rejected.
"""

from __future__ import annotations

import math
from typing import Any


def coerce_scalar(value: Any) -> float | None:
    """Return a plain float for valid numeric input, else None."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def normalize_array(values: Any) -> list[float | None]:
    """Elementwise boundary normalization; shape preserved, no zero-fill."""
    if values is None:
        return []
    try:
        items = list(values)
    except TypeError:
        return [coerce_scalar(values)]
    return [coerce_scalar(item) for item in items]
