"""Only implemented cache-only capabilities are advertised."""

from services.agent.registry import Tool, register

_reads = None


def configure_reads(reads):
    global _reads
    _reads = reads


def _register(name, description, metrics):
    async def read(ticker, horizon="all", **kwargs):
        if _reads is None:
            return {"status": "unavailable", "reason": "Research data source is not connected", "data": None}
        snapshot = await _reads.snapshot(ticker, horizon)
        facts = [f for f in snapshot["facts"] if f["metric"] in metrics]
        return {
            "status": "ok"
            if facts and all(f["status"] == "ok" for f in facts)
            else "degraded"
            if facts
            else "unavailable",
            "data": facts,
            "coverage": snapshot["coverage"],
            "gaps": snapshot["gaps"],
            "snapshot_id": snapshot["snapshot_id"],
        }

    register(
        Tool(
            name=name,
            description=description,
            params={"type": "object", "properties": {"ticker": {"type": "string"}, "horizon": {"type": "string"}}},
            call_style="direct",
            fn=read,
        )
    )


_register("market_context", "Cached price and available contracts", {"Underlying price", "Available contracts"})
_register(
    "gex_profile",
    "Estimated exposure from available contract inputs",
    {"Gamma exposure strikes", "Estimated gamma exposure", "Total estimated gamma exposure"},
)
_register("flip_zones", "Estimated flip levels in the available snapshot", {"Estimated flip levels"})
_register("alerts_feed", "Recent eligible stored directional readings", {"Signed alert reading"})
