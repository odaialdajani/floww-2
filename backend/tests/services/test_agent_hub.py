"""
backend/tests/services/test_agent_hub.py

Tests for Agent Hub — archetype loading, trigger evaluation, runtime.
"""
from pathlib import Path

import pytest
import yaml

from services.agent_hub import AgentArchetype, AgentHubRuntime

# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def squeeze_config():
    return {
        "name": "squeeze_hunter",
        "description": "Detects gamma squeeze conditions",
        "triggers": [
            {"metric": "vpin_cdf", "op": "gt", "value": 0.6},
            {"metric": "gex_total", "op": "lt", "value": -1000000.0},
        ],
        "logic": "all",
        "action": {"type": "alert", "params": {"severity": "high"}},
        "enabled": True,
    }


@pytest.fixture
def trend_config():
    return {
        "name": "trend_day_confirmer",
        "description": "Confirms trend day",
        "triggers": [
            {"metric": "trinity_score", "op": "gt", "value": 75.0},
            {"metric": "vpin_cdf", "op": "lt", "value": 0.4},
        ],
        "logic": "all",
        "action": {"type": "annotate_chart", "params": {}},
        "enabled": True,
    }


@pytest.fixture
def any_config():
    return {
        "name": "pin_risk_notifier",
        "description": "Pin risk warning",
        "triggers": [
            {"metric": "spot_to_king_node_pct", "op": "lt", "value": 0.005},
            {"metric": "vpin_cdf", "op": "gt", "value": 0.5},
        ],
        "logic": "any",
        "action": {"type": "alert", "params": {}},
        "enabled": True,
    }


def _clean_runtime():
    """Create a runtime with no default archetypes loaded."""
    rt = AgentHubRuntime()
    rt.archetypes = {}
    return rt


# ── AgentArchetype ────────────────────────────────────────────────────────────

class TestAgentArchetype:
    def test_create_from_config(self, squeeze_config):
        a = AgentArchetype(squeeze_config)
        assert a.name == "squeeze_hunter"
        assert a.enabled is True
        assert len(a.triggers) == 2

    def test_evaluate_all_triggers_met(self, squeeze_config):
        a = AgentArchetype(squeeze_config)
        metrics = {"vpin_cdf": 0.7, "gex_total": -2000000.0}
        assert a.evaluate(metrics) is True

    def test_evaluate_not_all_met(self, squeeze_config):
        a = AgentArchetype(squeeze_config)
        metrics = {"vpin_cdf": 0.7, "gex_total": 0.0}
        assert a.evaluate(metrics) is False

    def test_evaluate_disabled(self, squeeze_config):
        a = AgentArchetype(squeeze_config)
        a.enabled = False
        metrics = {"vpin_cdf": 0.7, "gex_total": -2000000.0}
        assert a.evaluate(metrics) is False

    def test_evaluate_any_logic(self, any_config):
        a = AgentArchetype(any_config)
        metrics = {"spot_to_king_node_pct": 0.001, "vpin_cdf": 0.3}
        assert a.evaluate(metrics) is True

    def test_evaluate_any_none_met(self, any_config):
        a = AgentArchetype(any_config)
        metrics = {"spot_to_king_node_pct": 0.01, "vpin_cdf": 0.3}
        assert a.evaluate(metrics) is False

    def test_evaluate_missing_metric(self, squeeze_config):
        a = AgentArchetype(squeeze_config)
        metrics = {"vpin_cdf": 0.7}
        assert a.evaluate(metrics) is False

    def test_evaluate_empty_triggers(self):
        a = AgentArchetype({"name": "empty", "triggers": [], "logic": "all"})
        assert a.evaluate({}) is False

    def test_to_dict(self, squeeze_config):
        a = AgentArchetype(squeeze_config)
        d = a.to_dict()
        assert d["name"] == "squeeze_hunter"
        assert "triggers" in d
        assert "enabled" in d


# ── AgentHubRuntime ───────────────────────────────────────────────────────────

class TestAgentHubRuntime:
    def test_create_runtime(self):
        rt = AgentHubRuntime()
        assert rt.archetypes is not None

    def test_register_archetype(self, squeeze_config):
        rt = _clean_runtime()
        rt.register(squeeze_config)
        assert "squeeze_hunter" in rt.archetypes

    def test_unregister_archetype(self, squeeze_config):
        rt = _clean_runtime()
        rt.register(squeeze_config)
        rt.unregister("squeeze_hunter")
        assert "squeeze_hunter" not in rt.archetypes

    def test_evaluate_all_fires(self, squeeze_config):
        rt = _clean_runtime()
        rt.register(squeeze_config)
        metrics = {"vpin_cdf": 0.7, "gex_total": -2000000.0}
        fired = rt.evaluate_all(metrics)
        assert len(fired) == 1
        assert fired[0]["archetype"] == "squeeze_hunter"

    def test_evaluate_all_no_fire(self, squeeze_config):
        rt = _clean_runtime()
        rt.register(squeeze_config)
        metrics = {"vpin_cdf": 0.3, "gex_total": 0.0}
        fired = rt.evaluate_all(metrics)
        assert len(fired) == 0

    def test_evaluate_multiple_archetypes(self, squeeze_config, trend_config):
        rt = _clean_runtime()
        rt.register(squeeze_config)
        rt.register(trend_config)
        metrics = {
            "vpin_cdf": 0.3,
            "gex_total": -2000000.0,
            "trinity_score": 85.0,
        }
        fired = rt.evaluate_all(metrics)
        assert len(fired) == 1
        assert fired[0]["archetype"] == "trend_day_confirmer"

    def test_get_status(self, squeeze_config):
        rt = _clean_runtime()
        rt.register(squeeze_config)
        status = rt.get_status()
        assert status["total"] >= 1
        assert "archetypes" in status

    def test_disabled_archetype_not_evaluated(self, squeeze_config):
        rt = _clean_runtime()
        squeeze_config["enabled"] = False
        rt.register(squeeze_config)
        metrics = {"vpin_cdf": 0.7, "gex_total": -2000000.0}
        fired = rt.evaluate_all(metrics)
        assert len(fired) == 0


# ── YAML Loading ──────────────────────────────────────────────────────────────

class TestYAMLLLoading:
    def test_archetypes_dir_exists(self):
        d = Path(__file__).parent.parent.parent / "services" / "agent_hub" / "archetypes"
        assert d.exists()

    def test_all_yaml_files_valid(self):
        d = Path(__file__).parent.parent.parent / "services" / "agent_hub" / "archetypes"
        if not d.exists():
            pytest.skip("Archetypes dir not found")
        for yaml_file in d.glob("*.yaml"):
            with open(yaml_file) as f:
                config = yaml.safe_load(f)
            assert config is not None, f"{yaml_file} is empty"
            assert "name" in config, f"{yaml_file} missing 'name'"
            assert "triggers" in config, f"{yaml_file} missing 'triggers'"

    def test_runtime_loads_defaults(self):
        rt = AgentHubRuntime()
        assert len(rt.archetypes) >= 3

    def test_squeeze_hunter_loads(self):
        rt = AgentHubRuntime()
        assert "squeeze_hunter" in rt.archetypes
        a = rt.archetypes["squeeze_hunter"]
        assert a.name == "squeeze_hunter"
        assert a.enabled is True
