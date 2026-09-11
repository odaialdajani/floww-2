"""Keep price observations distinct from chain receipt and calculation times."""

import copy
import math
from datetime import UTC, datetime


def timestamp(value):
    try:
        dt = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return None
        return dt.astimezone(UTC)
    except (ValueError, TypeError, AttributeError):
        return None


def receipt_age(value, now=None):
    dt = timestamp(value)
    if dt is None:
        return None
    return max(0, ((now or datetime.now(UTC)) - dt).total_seconds())


def cached_market_copy(payload, local_age, *, revalidating=False):
    result = copy.deepcopy(payload)
    ages = [receipt_age(payload.get("fetched_at"))]
    original_age = payload.get("stale_age_s", payload.get("cache_age_s"))
    if isinstance(original_age, (int, float)) and math.isfinite(original_age) and original_age >= 0:
        ages.append(original_age + max(0, local_age))
    ages = [age for age in ages if age is not None]
    result["stale_age_s"] = max(ages) if ages else None
    result["stale"] = bool(payload.get("stale") or revalidating)
    result["data_fallback"] = bool(payload.get("data_fallback") or result["stale"])
    return result


def spot_provenance(raw, now, max_age=900):
    # Legacy sources without separate quote metadata may use their own
    # observation time. Explicitly unknown quote times must stay unknown.
    separate = "spot_source" in raw or "spot_event_time" in raw
    source = raw.get("spot_source") if separate else raw.get("source") or raw.get("data_source")
    observed = timestamp(raw.get("spot_event_time") if separate else raw.get("event_time") or raw.get("observed_at"))
    status = "degraded" if observed is None else "ok"
    if observed and not -30 <= (now - observed).total_seconds() <= max_age:
        status = "stale"
    age = receipt_age(raw.get("spot_fetched_at") if separate else raw.get("fetched_at"), now)
    if raw.get("stale") or (age is not None and age > max_age):
        status = "stale"
    return dict(
        source=str(source or "unknown"),
        event_time=observed.isoformat() if observed else None,
        received_at=raw.get("spot_fetched_at") if separate else raw.get("fetched_at"),
        status=status,
    )
