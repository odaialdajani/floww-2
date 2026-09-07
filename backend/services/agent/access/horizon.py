"""Horizon table (plan v3 L0).

No engine endpoint accepts a horizon — they take a count of nearest
expiries. The tool layer slices by expiry so 0DTE means today, not
"nearest expiry". ET everywhere, matching server.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
HORIZONS = ("0dte", "1dte", "week", "month", "all")


def normalize_horizon(h: str | None) -> str:
    h = (h or "all").strip().lower()
    return h if h in HORIZONS else "all"


def is_prep_mode(now: datetime | None = None) -> bool:
    """After 16:00 ET the desk is in prep mode (no 0DTE claims outside RTH)."""
    now = now or datetime.now(ET)
    try:
        return now.hour >= 16
    except Exception:
        return False


def slice_expiries(contracts: list[dict[str, Any]], horizon: str) -> list[dict[str, Any]]:
    """Slice a cached chain to the horizon band.

    Contracts carry 'expiry' (YYYY-MM-DD). Bands:
    0dte = today's expiry (after 16:00 ET -> next session, banner prep mode),
    1dte = next, week = <= 5 sessions, month/all = as far as cached chain reaches.
    Unknown/missing expiry -> keep (never silently drop to empty).
    """
    horizon = normalize_horizon(horizon)
    if horizon in ("month", "all") or not contracts:
        return contracts
    try:
        today = datetime.now(ET).date().isoformat()
        expiries = sorted({str(c.get("expiry", "")) for c in contracts if c.get("expiry")})
        if not expiries:
            return contracts
        if horizon == "0dte":
            if is_prep_mode():
                target = next((e for e in expiries if e > today), expiries[0])
            else:
                target = next((e for e in expiries if e >= today), expiries[0])
            picked = [c for c in contracts if str(c.get("expiry", "")) == target]
            return picked or contracts
        if horizon == "1dte":
            future = [e for e in expiries if e > today]
            if not future:
                return contracts
            # 0DTE target occupies expiries[0] when it equals today
            target = future[0]
            picked = [c for c in contracts if str(c.get("expiry", "")) == target]
            return picked or contracts
        if horizon == "week":
            window = expiries[:5]
            picked = [c for c in contracts if str(c.get("expiry", "")) in window]
            return picked or contracts
    except Exception:
        return contracts
    return contracts
