"""Comparison only between owner-saved observations with matching coverage."""

from datetime import datetime

from services.agent.access.horizon import required_close
from services.agent.contracts import fact, finite, instant
from services.agent.repository import utcnow


async def history_facts(repository, owner, current, *, closing_only=False, previous_session=False):
    close_time = (
        required_close(datetime.fromisoformat(current["captured_at"]), previous_session=previous_session)
        if closing_only
        else None
    )
    cursor = (
        repository.turns.find(
            {"owner": owner, "status": "completed", "answer.snapshots.ticker": current["ticker"]},
            {"answer.snapshots": 1},
        )
        .sort("created_at", -1)
        .limit(30)
    )
    previous_snapshots = []
    async for turn in cursor:
        previous_snapshots.extend(turn.get("answer", {}).get("snapshots", []))
    anchors = (
        repository.snapshots.find(
            {"owner": owner, "ticker": current["ticker"], "expires_at": {"$gt": utcnow()}},
            {"snapshot": 1},
        )
        .sort("created_at", -1)
        .limit(30)
    )
    async for anchor in anchors:
        previous_snapshots.append(anchor["snapshot"])
    def price_time(snapshot):
        price = next((f for f in snapshot.get("facts", []) if f["metric"] == "Underlying price"), {})
        return instant(price.get("event_time"))

    previous_snapshots.sort(key=lambda snapshot: price_time(snapshot) or "", reverse=True)
    unavailable = "No earlier compatible source observation was saved"
    if closing_only:
        unavailable = f"No verified closing observation was saved for {close_time}"
    for previous in previous_snapshots:
        if closing_only and (
            previous.get("anchor_kind") != "close"
            or price_time(previous) != close_time
            or instant(previous.get("window", {}).get("session_close")) != close_time
        ):
            continue
        if previous["ticker"] != current["ticker"] or previous["horizon"] != current["horizon"]:
            continue
        if (
            not price_time(previous)
            or not price_time(current)
            or price_time(previous) >= price_time(current)
        ):
            continue
        if previous.get("coverage_id") != current.get("coverage_id"):
            unavailable = "Previous observation has different expiry or contract coverage"
            continue
        before = next((f for f in previous["facts"] if f["metric"] == "Underlying price"), None)
        after = next((f for f in current["facts"] if f["metric"] == "Underlying price"), None)
        if closing_only and (not before or instant(before.get("event_time")) != close_time):
            continue
        if (
            not before
            or not after
            or before["source"] != after["source"]
            or not finite(before["value"])
            or not finite(after["value"])
        ):
            unavailable = "Previous price source is not comparable"
            continue
        change = fact(
            "Price change since saved observation",
            after["value"] - before["value"],
            "USD",
            ticker=current["ticker"],
            source="compatible saved observations",
            snapshot_id=current["snapshot_id"],
            event_time=price_time(current),
            horizon=current["horizon"],
            parents=[before["id"], after["id"]],
            status=after["status"],
            reason=after.get("reason"),
        )
        return [before, change], f"Compared with source observation at {price_time(previous)}"
    return [], unavailable
