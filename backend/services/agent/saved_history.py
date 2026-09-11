"""Comparison only between owner-saved observations with matching coverage."""

from services.agent.contracts import fact, finite
from services.agent.repository import utcnow


async def history_facts(repository, owner, current):
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
    previous_snapshots.sort(key=lambda snapshot: snapshot.get("observed_at") or "", reverse=True)
    unavailable = "No earlier compatible source observation was saved"
    for previous in previous_snapshots:
        if previous["ticker"] != current["ticker"] or previous["horizon"] != current["horizon"]:
            continue
        if (
            not previous.get("observed_at")
            or not current.get("observed_at")
            or previous["observed_at"] >= current["observed_at"]
        ):
            continue
        if previous.get("coverage_id") != current.get("coverage_id"):
            unavailable = "Previous observation has different expiry or contract coverage"
            continue
        before = next((f for f in previous["facts"] if f["metric"] == "Underlying price"), None)
        after = next((f for f in current["facts"] if f["metric"] == "Underlying price"), None)
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
            event_time=current["observed_at"],
            horizon=current["horizon"],
            parents=[before["id"], after["id"]],
            status=after["status"],
            reason=after.get("reason"),
        )
        return [before, change], f"Compared with source observation at {previous['observed_at']}"
    return [], unavailable
