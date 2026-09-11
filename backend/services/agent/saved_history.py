"""Comparison only between owner-saved observations with matching coverage."""

from services.agent.contracts import fact, finite


async def history_facts(repository, owner, current):
    cursor = (
        repository.turns.find(
            {"owner": owner, "status": "completed", "answer.snapshots.ticker": current["ticker"]},
            {"answer.snapshots": 1},
        )
        .sort("created_at", -1)
        .limit(30)
    )
    async for turn in cursor:
        for previous in turn.get("answer", {}).get("snapshots", []):
            if previous["ticker"] != current["ticker"] or previous["horizon"] != current["horizon"]:
                continue
            if (
                not previous.get("observed_at")
                or not current.get("observed_at")
                or previous["observed_at"] >= current["observed_at"]
            ):
                continue
            if previous.get("coverage_id") != current.get("coverage_id"):
                return [], "Previous observation has different expiry or contract coverage"
            before = next((f for f in previous["facts"] if f["metric"] == "Underlying price"), None)
            after = next((f for f in current["facts"] if f["metric"] == "Underlying price"), None)
            if (
                not before
                or not after
                or before["source"] != after["source"]
                or not finite(before["value"])
                or not finite(after["value"])
            ):
                return [], "Previous price source is not comparable"
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
    return [], "No earlier compatible source observation was saved"
