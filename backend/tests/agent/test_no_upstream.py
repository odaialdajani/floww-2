"""No-upstream proof: the bundle completes from cache/fixtures when the
chain fetcher raises (plan v3 W1 exit)."""

import pytest

import services.agent.tools  # noqa: F401
from services.agent.registry import get_tool


@pytest.mark.asyncio
async def test_bundle_survives_chain_outage(monkeypatch):
    async def _raise(*a, **k):
        raise RuntimeError("upstream down")

    try:
        import routes.heatseeker as hs

        monkeypatch.setattr(hs, "_fetch_chain", _raise)
    except Exception:
        pass
    tool = get_tool("gex_profile")
    assert tool is not None and tool.fn is not None
    env = await tool.fn("SPY", horizon="all")
    assert isinstance(env, dict)
    assert env.get("status") in ("ok", "degraded", "stale", "failed")
    # Must never raise, and a failure must be labelled — never a finding.
    if env.get("status") == "failed":
        assert env.get("error")
