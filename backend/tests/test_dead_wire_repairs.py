"""Dead-wire repair proofs (Command Code dead-wire hunt).

Five `from X import Y` references named symbols that do not exist. Every one
sat inside a broad `except`, so the feature degraded to "no data" and nothing
reported a failure. These tests pin the repaired behaviour, and each one
asserts something the OLD code got wrong:

  old: alpha-flow        -> market.spy_close == 0.0, fake composite scores
  old: flow-digest       -> invented tickers/regimes it never measured
  old: gex-regime        -> raised ImportError on every call
  old: option-chain      -> returned a generic error on every call
  old: execute/order     -> silent generic error, no declared refusal

NOTE on the hub tests: `services.agentfield_hub` imports the optional
`agentfield` SDK at module scope, which is NOT installed and NOT declared in
requirements. `server.py` documents the hub as an optional feature that is
disabled when the package is missing. The SDK is stubbed here only so the
repaired reasoner bodies can be executed; the stub is not part of any
production path.
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))


def _load_hub():
    """Import the hub with the optional SDK stubbed out.

    The stub must be detected via sys.modules, not find_spec: once a bare
    ModuleType with no __spec__ is installed, a later find_spec raises
    `ValueError: agentfield.__spec__ is None` instead of returning None.
    """
    if "agentfield" not in sys.modules and importlib.util.find_spec("agentfield") is None:
        stub = types.ModuleType("agentfield")

        class _Any:  # noqa: D401 - trivial placeholder double
            def __init__(self, *a, **k):
                pass

            def __call__(self, *a, **k):
                return self

            def __getattr__(self, name):
                return _Any()

        for name in ("Agent", "AgentRouter", "AIConfig", "CostTracker", "Reasoner"):
            setattr(stub, name, _Any)
        sys.modules["agentfield"] = stub
    return importlib.import_module("services.agentfield_hub")



def _client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from routes.alphapod_compat import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestAlphaFlow:
    def test_closes_are_unknown_not_zero(self):
        """0.0 was a fabricated zero print, not a market close."""
        client = _client()
        body = client.get("/api/alpha-flow").json()
        assert body["market"]["spy_close"] is None
        assert body["market"]["vix_close"] is None

    def test_provenance_is_reported(self):
        body = _client().get("/api/alpha-flow").json()
        assert body["top_10_source"] in {
            "flowseeker_live", "degraded_empty", "empty",
            "fallback_stub", "unavailable",
        }
        assert isinstance(body["degraded"], bool)
        assert isinstance(body["prints_seen"], int)

    def test_live_feed_ranks_by_real_premium_without_faked_score(self, monkeypatch):
        import routes.alphapod_compat as mod

        async def fake_meta(*a, **k):
            return {
                "degraded": False,
                "degraded_reason": None,
                "prints": [
                    {"ticker": "SPY", "premium": 5000.0, "classification": "put"},
                    {"ticker": "SPY", "premium": 1500.0, "classification": "put"},
                    {"ticker": "QQQ", "premium": 900.0, "classification": "call"},
                    {"ticker": "IWM", "premium": 700.0, "classification": "call"},
                ],
            }

        monkeypatch.setattr(mod, "fetch_live_flow_with_meta", fake_meta)
        body = _client().get("/api/alpha-flow").json()
        assert body["top_10_source"] == "flowseeker_live"
        assert [row["ticker"] for row in body["top_10"]] == ["SPY", "QQQ", "IWM"]
        assert body["top_10"][0]["premium"] == pytest.approx(6500.0)
        # No composite score exists in this payload, so it must be null rather
        # than a number invented at the call site.
        assert all(row["score"] is None for row in body["top_10"])
        assert body["top_10"][0]["direction"] == "put"


class TestFlowDigest:
    def test_never_prints_measurements_it_did_not_take(self):
        """The old scaffold claimed tickers and regimes it never read."""
        client = _client()
        body = client.get("/api/flow-digest").json()
        lowered = body["body_md"].lower()
        assert "top flow tickers: spy" not in lowered
        assert "vix regime: normal" not in lowered
        assert "gamma regime: positive" not in lowered
        assert "no briefing available" in lowered or body["status"] == "ok"

    def test_status_and_reason_are_explicit(self):
        body = _client().get("/api/flow-digest").json()
        assert body["status"] in {"ok", "unavailable"}
        assert (body["reason"] is None) == (body["status"] == "ok")


class TestExecutionReasoner:
    def test_refuses_without_constructing_a_broker(self, monkeypatch):
        hub = _load_hub()
        import services.paper_broker as broker_mod

        def boom(*a, **k):  # pragma: no cover - must never run
            raise AssertionError("a broker was constructed by the execution reasoner")

        monkeypatch.setattr(broker_mod, "PaperBroker", boom)

        payload = hub.AgentFieldHub._submit_order_refusal_payload()
        assert payload["refused"] is True
        assert payload["status"] == "refused"
        assert payload["reason"] == "EXECUTION_PATH_NOT_APPROVED"
        assert payload["submitted"] is False
        assert "approval" in payload["detail"].lower()


class TestGexProfile:
    def test_missing_coverage_is_none_not_a_zero_profile(self, monkeypatch):
        hub = _load_hub()
        import services.public_api_adapter as adapter

        async def no_chain(*a, **k):
            return None

        monkeypatch.setattr(adapter, "fetch_chain_from_public_api", no_chain)
        out = asyncio.run(hub.AgentFieldHub._canonical_gex_profile("SPY"))
        assert out is None

    def test_no_contracts_is_none(self, monkeypatch):
        hub = _load_hub()
        import services.public_api_adapter as adapter

        async def empty_chain(*a, **k):
            return {"contracts": [], "spot": 0.0}

        monkeypatch.setattr(adapter, "fetch_chain_from_public_api", empty_chain)
        assert asyncio.run(hub.AgentFieldHub._canonical_gex_profile("SPY")) is None

    def test_zero_spot_is_none_not_a_fabricated_profile(self, monkeypatch):
        hub = _load_hub()
        import services.public_api_adapter as adapter

        async def bad_spot(*a, **k):
            return {"contracts": [{"strike": 100, "type": "call", "gamma": 0.01}], "spot": 0.0}

        monkeypatch.setattr(adapter, "fetch_chain_from_public_api", bad_spot)
        assert asyncio.run(hub.AgentFieldHub._canonical_gex_profile("SPY")) is None


def test_gate_is_green_on_this_tree():
    """Standing assertion: the gate must report zero dead wires here."""
    gate_path = REPO_ROOT / "qc" / "audit" / "find_dead_imports.py"
    assert gate_path.is_file()
    spec = importlib.util.spec_from_file_location("find_dead_imports", gate_path)
    gate = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(gate)
    assert gate.find_dead_imports() == []
