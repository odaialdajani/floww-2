# ruff: noqa: I001
"""
backend/tests/services/test_agentfield_hub.py

Unit tests for services/agentfield_hub.py — the AgentField Integration Hub.

Strategy: The `agentfield` SDK is not installed in the test venv, so we mock
agentfield.Agent, AgentRouter, AIConfig, and CostTracker at the module level
before importing agentfield_hub. From there we test:
  - AgentFieldHub.__init__ sets correct defaults
  - get_hub() singleton behavior
  - init() wires up the Agent with the right config and registers reasoners
  - init() is idempotent (double-call is a no-op)
  - Reasoner registration: correct count, paths, tags
  - classify_regime reasoner: deterministic BULLISH/BEARISH/NEUTRAL outputs
  - execution_health reasoner: returns cost tracker fields
  - Error boundary: reasoners that raise return {"status": "error", ...}
  - AGENTFIELD_MODEL env var overrides default model
  - router.prefix and router.tags

No network, no DB, no file I/O. Pure unit tests with mocked SDK.
Run with:
    cd backend && .venv/bin/python3 -m pytest tests/services/test_agentfield_hub.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── Bootstrap: mock the agentfield SDK before importing agentfield_hub ──────
# All stdlib/third-party imports are above this line (ruff I001 compliant).
# sys.path.insert + local import come after.

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class FakeCostTracker:
    def __init__(self):
        self.total_cost_usd = 0.0
        self.total_tokens = 0


class FakeAIConfig:
    def __init__(self, model: str = "anthropic/claude-sonnet-4-20250514"):
        self.model = model


class FakeAgent:
    def __init__(
        self,
        node_id: str,
        version: str,
        ai_config=None,
        dev_mode: bool = False,
    ):
        self.node_id = node_id
        self.version = version
        self.ai_config = ai_config
        self.dev_mode = dev_mode
        self.router = None

    def include_router(self, router):
        self.router = router


class FakeRouter:
    def __init__(self, prefix: str = "", tags: list[str] | None = None):
        self.prefix = prefix
        self.tags = tags or []
        self.reasoners: list[dict] = []

    def reasoner(self, path: str = "", tags: list[str] | None = None):
        """Decorator that registers a reasoner function."""

        def decorator(func):
            self.reasoners.append({
                "func": func,
                "path": path,
                "tags": tags or [],
            })
            return func

        return decorator


# Inject the fake agentfield module
fake_agentfield = MagicMock()
fake_agentfield.Agent = FakeAgent
fake_agentfield.AgentRouter = FakeRouter
fake_agentfield.AIConfig = FakeAIConfig
fake_agentfield.CostTracker = FakeCostTracker
sys.modules["agentfield"] = fake_agentfield

# Now safe to import the module under test
from services.agentfield_hub import AgentFieldHub, get_hub, init_hub  # noqa: E402


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the global _hub singleton before each test."""
    import services.agentfield_hub as mod

    mod._hub = None
    yield
    mod._hub = None


@pytest.fixture
def hub():
    """Return a fresh AgentFieldHub (not initialized)."""
    return AgentFieldHub()


# ── AgentFieldHub.__init__ ──────────────────────────────────────────────────


class TestAgentFieldHubInit:
    def test_default_state(self, hub):
        assert hub.agent is None
        assert hub._initialized is False
        assert isinstance(hub.cost_tracker, FakeCostTracker)
        assert isinstance(hub.router, FakeRouter)

    def test_router_prefix(self, hub):
        assert hub.router.prefix == "/agentfield/v1"

    def test_router_tags(self, hub):
        assert hub.router.tags == ["trading"]

    def test_cost_tracker_initial_values(self, hub):
        assert hub.cost_tracker.total_cost_usd == 0.0
        assert hub.cost_tracker.total_tokens == 0


# ── get_hub() singleton ─────────────────────────────────────────────────────


class TestGetHub:
    def test_creates_on_first_call(self):
        h = get_hub()
        assert isinstance(h, AgentFieldHub)

    def test_returns_same_instance(self):
        h1 = get_hub()
        h2 = get_hub()
        assert h1 is h2

    def test_returns_none_before_first_call(self):
        import services.agentfield_hub as mod

        assert mod._hub is None


# ── init() wiring ──────────────────────────────────────────────────────────


class TestHubInit:
    @pytest.mark.asyncio
    async def test_init_creates_agent(self, hub):
        await hub.init()
        assert hub.agent is not None
        assert isinstance(hub.agent, FakeAgent)

    @pytest.mark.asyncio
    async def test_init_sets_node_id(self, hub):
        await hub.init()
        assert hub.agent.node_id == "floww-trading"

    @pytest.mark.asyncio
    async def test_init_sets_version(self, hub):
        await hub.init()
        assert hub.agent.version == "1.0.0"

    @pytest.mark.asyncio
    async def test_init_sets_dev_mode_true(self, hub):
        await hub.init()
        assert hub.agent.dev_mode is True

    @pytest.mark.asyncio
    async def test_init_default_model(self, hub):
        await hub.init()
        assert hub.agent.ai_config.model == "anthropic/claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_init_custom_model_from_env(self, monkeypatch):
        monkeypatch.setenv("AGENTFIELD_MODEL", "openrouter/owl-alpha")
        import services.agentfield_hub as mod

        mod._hub = None
        h = AgentFieldHub()
        await h.init()
        assert h.agent.ai_config.model == "openrouter/owl-alpha"
        mod._hub = None

    @pytest.mark.asyncio
    async def test_init_idempotent(self, hub):
        await hub.init()
        first_agent = hub.agent
        await hub.init()
        assert hub.agent is first_agent

    @pytest.mark.asyncio
    async def test_init_sets_initialized_flag(self, hub):
        assert hub._initialized is False
        await hub.init()
        assert hub._initialized is True

    @pytest.mark.asyncio
    async def test_init_calls_include_router(self, hub):
        await hub.init()
        assert hub.agent.router is hub.router


# ── init_hub() coroutine ────────────────────────────────────────────────────


class TestInitHub:
    @pytest.mark.asyncio
    async def test_returns_hub(self):
        h = await init_hub()
        assert isinstance(h, AgentFieldHub)

    @pytest.mark.asyncio
    async def test_initializes(self):
        h = await init_hub()
        assert h._initialized is True


# ── Reasoner registration ──────────────────────────────────────────────────


class TestReasonerRegistration:
    @pytest.mark.asyncio
    async def test_reasoners_registered(self, hub):
        await hub.init()
        assert len(hub.router.reasoners) > 0

    @pytest.mark.asyncio
    async def test_total_reasoner_count(self, hub):
        """The hub registers 13 reasoners across 5 categories."""
        await hub.init()
        assert len(hub.router.reasoners) == 13

    @pytest.mark.asyncio
    async def test_signal_reasoners_present(self, hub):
        await hub.init()
        paths = [r["path"] for r in hub.router.reasoners]
        assert "/signals/gex-regime" in paths
        assert "/signals/alerts" in paths
        assert "/signals/vpin" in paths
        assert "/signals/hawkes" in paths

    @pytest.mark.asyncio
    async def test_risk_reasoners_present(self, hub):
        await hub.init()
        paths = [r["path"] for r in hub.router.reasoners]
        assert "/risk/portfolio-greeks" in paths
        assert "/risk/scenario" in paths
        assert "/risk/position-size" in paths

    @pytest.mark.asyncio
    async def test_briefing_reasoners_present(self, hub):
        await hub.init()
        paths = [r["path"] for r in hub.router.reasoners]
        assert "/briefing/build" in paths
        assert "/briefing/classify" in paths

    @pytest.mark.asyncio
    async def test_data_reasoners_present(self, hub):
        await hub.init()
        paths = [r["path"] for r in hub.router.reasoners]
        assert "/data/option-chain" in paths
        assert "/data/vol-surface" in paths

    @pytest.mark.asyncio
    async def test_execution_reasoners_present(self, hub):
        await hub.init()
        paths = [r["path"] for r in hub.router.reasoners]
        assert "/execute/order" in paths
        assert "/execute/health" in paths

    @pytest.mark.asyncio
    async def test_all_reasoners_are_coroutines_or_callable(self, hub):
        await hub.init()
        for r in hub.router.reasoners:
            assert callable(r["func"])

    @pytest.mark.asyncio
    async def test_reasoner_tags_nonempty(self, hub):
        await hub.init()
        for r in hub.router.reasoners:
            assert len(r["tags"]) > 0


# ── classify_regime reasoner (deterministic) ────────────────────────────────


class TestClassifyRegimeReasoner:
    @pytest.mark.asyncio
    async def _get_classify_fn(self, hub):
        await hub.init()
        for r in hub.router.reasoners:
            if r["func"].__name__ == "classify_regime":
                return r["func"]
        pytest.fail("classify_regime reasoner not found")

    @pytest.mark.asyncio
    async def test_bullish_positive_gex_above_flip(self, hub):
        fn = await self._get_classify_fn(hub)
        result = await fn(
            net_gex=1.5e9,
            call_oi=500000,
            put_oi=300000,
            iv_skew=0.005,
            flip_level=450.0,
            spot=452.0,
        )
        assert result["regime"] == "BULLISH"

    @pytest.mark.asyncio
    async def test_bearish_negative_gex_below_flip(self, hub):
        fn = await self._get_classify_fn(hub)
        result = await fn(
            net_gex=-1.5e9,
            call_oi=300000,
            put_oi=500000,
            iv_skew=0.04,
            flip_level=450.0,
            spot=445.0,
        )
        assert result["regime"] == "BEARISH"

    @pytest.mark.asyncio
    async def test_neutral_zero_gex(self, hub):
        fn = await self._get_classify_fn(hub)
        result = await fn(
            net_gex=0.0,
            call_oi=100000,
            put_oi=100000,
            iv_skew=0.0,
            flip_level=450.0,
            spot=450.0,
        )
        assert result["regime"] == "NEUTRAL"

    @pytest.mark.asyncio
    async def test_returns_dict_with_status_ok(self, hub):
        fn = await self._get_classify_fn(hub)
        result = await fn(
            net_gex=1.0e9,
            call_oi=400000,
            put_oi=300000,
            iv_skew=0.01,
            flip_level=450.0,
            spot=451.0,
        )
        assert result["status"] == "ok"
        assert "regime" in result


# ── execution_health reasoner ──────────────────────────────────────────────


class TestExecutionHealthReasoner:
    @pytest.mark.asyncio
    async def _get_health_fn(self, hub):
        await hub.init()
        for r in hub.router.reasoners:
            if r["func"].__name__ == "execution_health":
                return r["func"]
        pytest.fail("execution_health reasoner not found")

    @pytest.mark.asyncio
    async def test_status_ok(self, hub):
        fn = await self._get_health_fn(hub)
        result = await fn()
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_node_id(self, hub):
        fn = await self._get_health_fn(hub)
        result = await fn()
        assert result["agent_node_id"] == "floww-trading"

    @pytest.mark.asyncio
    async def test_version(self, hub):
        fn = await self._get_health_fn(hub)
        result = await fn()
        assert result["agent_version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_cost_fields_present(self, hub):
        fn = await self._get_health_fn(hub)
        result = await fn()
        assert "cost_total_usd" in result
        assert "cost_total_tokens" in result


# ── Error boundary in reasoners ────────────────────────────────────────────


class TestReasonerErrorHandling:
    @pytest.mark.asyncio
    async def _get_gex_regime_fn(self, hub):
        await hub.init()
        for r in hub.router.reasoners:
            if r["func"].__name__ == "gex_regime":
                return r["func"]
        pytest.fail("gex_regime reasoner not found")

    @pytest.mark.asyncio
    async def test_gex_regime_returns_error_on_exception(self, hub, monkeypatch):
        """If compute_gex_profile raises, gex_regime returns status=error."""

        async def fake_compute(ticker):
            raise RuntimeError("backend unavailable")

        fake_heatseeker = MagicMock()
        fake_heatseeker.compute_gex_profile = fake_compute
        monkeypatch.setitem(sys.modules, "services.heatseeker", fake_heatseeker)

        fn = await self._get_gex_regime_fn(hub)
        result = await fn(ticker="SPY")
        assert result["status"] == "error"
        assert "backend unavailable" in result["error"]
        assert result["ticker"] == "SPY"


# ── AsyncMock-based reasoner tests for signal reasoners ────────────────────


class TestSignalReasonersAsync:
    """Test that each signal reasoner calls the right underlying service."""

    @pytest.mark.asyncio
    async def test_gex_regime_calls_compute_gex_profile(self, hub, monkeypatch):
        fake_profile = {"regime": "bullish", "flip": 450.0}
        fake_heatseeker = MagicMock()
        fake_heatseeker.compute_gex_profile = AsyncMock(return_value=fake_profile)
        monkeypatch.setitem(sys.modules, "services.heatseeker", fake_heatseeker)

        await hub.init()
        gex_fn = None
        for r in hub.router.reasoners:
            if r["func"].__name__ == "gex_regime":
                gex_fn = r["func"]
                break

        result = await gex_fn(ticker="SPY")
        assert result["status"] == "ok"
        assert result["ticker"] == "SPY"
        assert result["regime"] == "bullish"

    @pytest.mark.asyncio
    async def test_vpin_returns_value(self, hub, monkeypatch):
        mock_engine = MagicMock()
        mock_engine.compute_vpin = MagicMock(return_value=0.73)
        mock_module = MagicMock()
        mock_module.VpinEngine = MagicMock(return_value=mock_engine)
        monkeypatch.setitem(sys.modules, "services.vpin_engine", mock_module)

        await hub.init()
        vpin_fn = None
        for r in hub.router.reasoners:
            if r["func"].__name__ == "vpin_signal":
                vpin_fn = r["func"]
                break

        result = await vpin_fn(ticker="QQQ")
        assert result["status"] == "ok"
        assert result["vpin"] == 0.73
        assert result["ticker"] == "QQQ"

    @pytest.mark.asyncio
    async def test_hawkes_returns_state(self, hub, monkeypatch):
        fake_state = {"mu": 1.0, "alpha": 0.5, "beta": 1.0}
        fake_hp = MagicMock()
        fake_hp.HawkesProcess = MagicMock(
            return_value=MagicMock(get_state=MagicMock(return_value=fake_state))
        )
        monkeypatch.setitem(sys.modules, "services.hawkes_process", fake_hp)

        await hub.init()
        hawkes_fn = None
        for r in hub.router.reasoners:
            if r["func"].__name__ == "hawkes_intensity":
                hawkes_fn = r["func"]
                break

        result = await hawkes_fn(ticker="SPY")
        assert result["status"] == "ok"
        assert result["hawkes"] == fake_state


# ── Ticker normalization ────────────────────────────────────────────────────


class TestTickerNormalization:
    @pytest.mark.asyncio
    async def test_gex_regime_uppercases_ticker(self, hub, monkeypatch):
        fake_heatseeker = MagicMock()
        fake_heatseeker.compute_gex_profile = AsyncMock(return_value={})
        monkeypatch.setitem(sys.modules, "services.heatseeker", fake_heatseeker)

        await hub.init()
        gex_fn = None
        for r in hub.router.reasoners:
            if r["func"].__name__ == "gex_regime":
                gex_fn = r["func"]
                break

        result = await gex_fn(ticker="spy")
        assert result["ticker"] == "SPY"

    @pytest.mark.asyncio
    async def test_vpin_uppercases_ticker(self, hub, monkeypatch):
        mock_engine = MagicMock()
        mock_engine.compute_vpin = MagicMock(return_value=0.5)
        mock_module = MagicMock()
        mock_module.VpinEngine = MagicMock(return_value=mock_engine)
        monkeypatch.setitem(sys.modules, "services.vpin_engine", mock_module)

        await hub.init()
        vpin_fn = None
        for r in hub.router.reasoners:
            if r["func"].__name__ == "vpin_signal":
                vpin_fn = r["func"]
                break

        result = await vpin_fn(ticker="qqq")
        assert result["ticker"] == "QQQ"
