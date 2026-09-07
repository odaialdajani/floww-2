"""Agent spend budget (plan v3 L3).

AGENT_DAILY_BUDGET_USD default 20. Mongo agent_budget when available,
in-memory fallback otherwise. Past the ceiling the loop degrades to the
free deterministic template and says so.
"""

from __future__ import annotations

import contextlib
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
_mem: dict[str, dict[str, float]] = {}


def daily_budget_usd() -> float:
    try:
        return float(os.environ.get("AGENT_DAILY_BUDGET_USD", "20"))
    except Exception:
        return 20.0


def _today() -> str:
    return datetime.now(ET).date().isoformat()


def get_spend_today(db=None) -> float:
    day = _today()
    if db is not None:
        with contextlib.suppress(Exception):
            doc = db["agent_budget"].find_one({"day": day})
            if doc:
                return float(doc.get("spend_usd", 0.0))
    return float(_mem.get(day, {}).get("spend_usd", 0.0))


def record_spend(amount_usd: float, db=None) -> float:
    day = _today()
    total = get_spend_today(db) + float(amount_usd or 0.0)
    _mem[day] = {"spend_usd": total, "ts": time.time()}
    if db is not None:
        with contextlib.suppress(Exception):
            db["agent_budget"].update_one(
                {"day": day}, {"$set": {"spend_usd": total}}, upsert=True
            )
    return total


def budget_state(db=None) -> dict:
    cap = daily_budget_usd()
    spent = get_spend_today(db)
    return {
        "cap_usd": cap,
        "spent_usd": round(spent, 4),
        "remaining_usd": round(max(0.0, cap - spent), 4),
        "exhausted": spent >= cap,
        "degraded": spent >= cap * 0.8,
        "day": _today(),
    }
