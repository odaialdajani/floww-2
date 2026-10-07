"""Comparison only between owner-saved observations with matching coverage."""

from datetime import UTC, date, datetime, time, timedelta

from pymongo.errors import ExecutionTimeout, PyMongoError

from services.agent.access.horizon import ET, horizon_window, required_close
from services.agent.contracts import fact, finite, instant, validate_history_baseline


def price_fact(snapshot):
    return next((item for item in snapshot.get("facts", []) if item.get("metric") == "Underlying price"), None)


def price_time(snapshot):
    price = price_fact(snapshot) or {}
    return instant(price.get("event_time"))


def baseline_window(baseline, current, closing_only, previous_session):
    if baseline is None:
        closing = (required_close(datetime.fromisoformat(current["captured_at"]), previous_session=previous_session)
                   if closing_only else None)
        return None, None, closing, None
    selected = date.fromisoformat(baseline["date"])
    start = datetime.combine(selected, time.min, ET).astimezone(UTC).isoformat()
    end = datetime.combine(selected + timedelta(days=1), time.min, ET).astimezone(UTC).isoformat()
    closing = None
    if closing_only:
        try:
            window = horizon_window("all", now=datetime.combine(selected, time(12), ET))
            closing = instant(window.get("session_close")) if window.get("is_session") else None
        except Exception:
            closing = None
        if closing is None:
            return start, end, None, f"No verified market close is available for {baseline['date']} in New York market time"
    return start, end, closing, None


def coverage_limit(previous, current):
    text = "Previous observation has different expiry or contract coverage"
    counts = [previous.get("coverage"), current.get("coverage")]
    if all(isinstance(count, int) and not isinstance(count, bool) and count >= 0 for count in counts):
        text += (f"; earlier saved coverage: {counts[0]} contracts; "
                 f"current saved coverage: {counts[1]} contracts")
    return text + f". Earlier source observation: {price_time(previous)}; no price change was calculated."


async def history_facts(repository, owner, current, *, closing_only=False, previous_session=False, history_baseline=None):
    if current.get("range_observation") is not None:
        return [], "Recorded range cell observations are not comparable with current-chain history"
    baseline = validate_history_baseline(history_baseline)
    day = f" for {baseline['date']} in New York market time" if baseline else ""
    before_time = price_time(current)
    after = price_fact(current)
    if (not before_time or not after or not finite(after.get("value"))
            or after.get("status") not in {"ok", "degraded", "stale"}
            or any(after.get(key) != current.get(key) for key in ("ticker", "horizon"))):
        return [], f"Current source observation time or price is unavailable{day}; no saved comparison was calculated"
    if (not isinstance(after.get("source"), str) or not after["source"]
            or not isinstance(after.get("unit"), str) or not after["unit"]
            or not current.get("coverage_id")):
        return [], f"Current price source, units or coverage identity are unverified{day}; no saved comparison was calculated"
    start, end, close_time, refusal = baseline_window(baseline, current, closing_only, previous_session)
    if refusal:
        return [], refusal
    unavailable = (f"No verified closing observation was saved for {close_time}{day}" if closing_only else
                   f"No earlier compatible source observation is available{day}")
    criteria = dict(ticker=current["ticker"], horizon=current["horizon"], before=before_time,
                    start=start, end=end, coverage_id=current["coverage_id"], source=after["source"],
                    unit=after["unit"], close_time=close_time)
    try:
        candidates = await repository.history_candidates(owner, **criteria)
    except ExecutionTimeout:
        return [], f"Saved-history database time limit reached{day}; results are incomplete and no comparison was calculated"
    except PyMongoError:
        return [], f"Saved-history database read is unavailable{day}; results are incomplete and no comparison was calculated"
    for previous in candidates["snapshots"]:
        before = price_fact(previous)
        observed = price_time(previous)
        if (not before or before.get("status") not in {"ok", "degraded", "stale"}
                or not observed or observed >= before_time
                or start is not None and not start <= observed < end
                or any(previous.get(key) != current.get(key) for key in ("ticker", "horizon", "coverage_id"))
                or any(before.get(key) != after.get(key) for key in ("source", "unit", "ticker", "horizon"))
                or not finite(before.get("value"))):
            continue
        if closing_only and (previous.get("anchor_kind") != "close" or observed != close_time
                             or instant(previous.get("window", {}).get("session_close")) != close_time):
            continue
        parents = [before, after]
        status = "stale" if any(parent.get("status") == "stale" for parent in parents) else (
            "degraded" if any(parent.get("status") == "degraded" for parent in parents) else "ok")
        reasons = list(dict.fromkeys(parent["reason"][:300] for parent in parents
                       if parent.get("status") != "ok" and isinstance(parent.get("reason"), str) and parent["reason"]))
        reason = ("; ".join(reasons) or f"Saved price comparison inherits {status} input quality") if status != "ok" else after.get("reason")
        change = fact(
            "Price change since saved observation", after["value"] - before["value"], after["unit"],
            ticker=current["ticker"], source="compatible saved observations", snapshot_id=current["snapshot_id"],
            event_time=before_time, horizon=current["horizon"], parents=[before["id"], after["id"]],
            status=status, reason=reason,
        )
        return [before, change], f"Compared with source observation at {observed}{day}"
    # Missing compatibility still needs the original bounded coverage/source note.
    try:
        diagnostic = await repository.history_candidates(owner, **criteria, compatible=False)
    except ExecutionTimeout:
        return [], f"Saved-history database time limit reached{day}; results are incomplete and no comparison was calculated"
    except PyMongoError:
        return [], f"Saved-history database read is unavailable{day}; results are incomplete and no comparison was calculated"
    if candidates["truncated"] or diagnostic["truncated"]:
        limit = candidates["limit_per_store"]
        return [], f"Saved-history search reached its bounded limit of {limit} observations per store{day}; compatibility could not be established"
    for previous in diagnostic["snapshots"]:
        if previous.get("coverage_id") != current.get("coverage_id"):
            return [], coverage_limit(previous, current) + day
        before = price_fact(previous)
        if before and before.get("status") not in {"ok", "degraded", "stale"}:
            unavailable = f"Previous saved price quality is unavailable{day}; no comparison was calculated"
        elif before and any(before.get(key) != after.get(key) for key in ("source", "unit")):
            unavailable = f"Previous price source or units are not comparable{day}"
    return [], unavailable
