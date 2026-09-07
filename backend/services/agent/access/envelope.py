"""Evidence envelope (plan v3 L0).

Every tool result is wrapped so the model and the panel can tell
ok / degraded / stale / failed apart, plus where it came from and
how old it is. Empty or degraded is never a finding.
"""

from __future__ import annotations

import time
from typing import Any

STATUSES = ("ok", "degraded", "stale", "failed")
STORES = ("durable", "volatile")


def make_envelope(
    *,
    status: str = "ok",
    source: str = "unknown",
    data: Any = None,
    as_of: str | None = None,
    staleness_s: float | None = None,
    n_contracts: int | None = None,
    has_quotes: bool = False,
    coverage: str | None = None,
    truncated: bool = False,
    store: str = "durable",
    volatile_since: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    if status not in STATUSES:
        status = "failed"
    if store not in STORES:
        store = "volatile"
    now = time.time()
    return {
        "status": status,
        "source": source,
        "as_of": as_of,
        "staleness_s": staleness_s,
        "n_contracts": n_contracts,
        "has_quotes": bool(has_quotes),
        "coverage": coverage,
        "truncated": bool(truncated),
        "store": store,
        "volatile_since": volatile_since,
        "data": data,
        "error": error,
        "enveloped_at": now,
    }


def is_usable(env: dict[str, Any]) -> bool:
    """Only ok/degraded/stale may be narrated; failed is barred (plan v3 L2)."""
    try:
        return env.get("status") in ("ok", "degraded", "stale")
    except Exception:
        return False
