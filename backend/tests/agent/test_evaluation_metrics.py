import asyncio
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("mongomock_motor", reason="mongo mock unavailable in this env")
from mongomock_motor import AsyncMongoMockClient

from scripts.research_eval_metrics import (
    CaseTrace,
    MeasuredModel,
    measured_bridge,
    read_metrics,
    saved_progress_metrics,
    usage_evidence,
)
from services.agent.codex_bridge import CodexBridge
from services.agent.codex_model import DEFAULT_SETTINGS, OAuthUsage


@pytest.mark.asyncio
async def test_failed_model_entry_is_counted_without_inventing_dispatch_or_cost():
    class Failed:
        single_attempt = True

        async def once(self, *args, **kwargs):
            raise OSError("private credential detail")

    trace = CaseTrace()
    model = MeasuredModel(Failed(), trace)
    with pytest.raises(OSError):
        await model.once("question", [], "turn")
    result = trace.snapshot()
    assert result["model_invocations"] == 1
    assert result["model_outcomes"] == ["error"]
    assert result["managed_turn_start_attempts"] == 0
    assert result["upstream_model_requests"] is None and result["actual_cost_usd"] is None
    assert "private credential detail" not in str(result)


@pytest.mark.asyncio
async def test_bridge_attempt_write_and_acknowledgment_are_distinct(monkeypatch):
    trace = CaseTrace()

    async def sent(self, message):
        return None

    async def requested(self, method, params):
        await self.send({"method": method, "params": params, "id": 1})
        raise TimeoutError("lost acknowledgment")

    monkeypatch.setattr(CodexBridge, "send", sent)
    monkeypatch.setattr(CodexBridge, "request", requested)
    bridge = measured_bridge(trace)()
    with pytest.raises(TimeoutError):
        await bridge.request("turn/start", {})
    result = trace.snapshot()
    assert result["managed_turn_start_attempts"] == 1
    assert result["managed_turn_start_pipe_writes"] == 1
    assert result["managed_turn_start_acknowledgments"] == 0


def test_old_turn_without_read_record_stays_unmeasured():
    assert read_metrics({"status": "completed"})["reserved"] is None
    assert (
        saved_progress_metrics({"created_at": "2026-09-26T12:00:00Z", "events": [{"type": "progress"}]})[
            "first_progress_recorded_s"
        ]
        is None
    )


def test_saved_progress_time_is_not_client_or_browser_time():
    result = saved_progress_metrics(
        {"created_at": "2026-09-26T12:00:00Z", "events": [{"type": "progress", "recorded_at": "2026-09-26T12:00:02Z"}]}
    )
    assert result["first_progress_recorded_s"] == 2
    assert "client" not in result and "browser" not in result


@pytest.mark.asyncio
async def test_usage_read_uses_durable_reservation_even_when_answer_has_no_usage():
    store = AsyncMongoMockClient().test.usage
    ledger = OAuthUsage(store)
    assert await ledger.reserve("alice", "turn", DEFAULT_SETTINGS)
    evidence = await usage_evidence(store, "alice", "turn")
    assert evidence["reservations"] == 1 and evidence["status"] == "uncertain"
    assert evidence["actual_cost_usd"] is None
    assert (await usage_evidence(store, "bob", "turn"))["reservations"] is None
    assert (await ledger.state())["calls"] == 1


@pytest.mark.asyncio
async def test_failed_measurement_save_cannot_enter_model():
    class Model:
        once = AsyncMock()

    def failed(value):
        raise OSError("private path")

    trace = CaseTrace(sink=failed)
    model = Model()
    with pytest.raises(OSError):
        await MeasuredModel(model, trace).once("q", [], "t")
    model.once.assert_not_awaited()
    assert trace.snapshot()["model_invocations"] == 0
    assert trace.snapshot()["model_outcomes"] == ["not_entered"]


@pytest.mark.asyncio
async def test_buffered_transport_cannot_claim_client_progress_timing():
    import httpx
    from fastapi import FastAPI

    from scripts.research_eval_metrics import observe_progress_stream

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=FastAPI()), base_url="http://localhost") as client:
        with pytest.raises(ValueError, match="real HTTP"):
            await observe_progress_stream(client, "12345678-1234-1234-1234-123456789012", CaseTrace())


@pytest.mark.asyncio
async def test_successful_bridge_ack_is_separate_from_generation_completion(monkeypatch):
    async def sent(self, message):
        return None

    async def requested(self, method, params):
        await self.send({"method": method, "params": params, "id": 1})
        return {"turn": {"id": "accepted", "status": "inProgress"}}

    monkeypatch.setattr(CodexBridge, "send", sent)
    monkeypatch.setattr(CodexBridge, "request", requested)
    trace = CaseTrace()
    bridge = measured_bridge(trace)()
    await bridge.request("thread/start", {})
    assert trace.snapshot()["managed_turn_start_attempts"] == 0
    await bridge.request("turn/start", {})
    result = trace.snapshot()
    assert (
        result["managed_turn_start_attempts"]
        == result["managed_turn_start_pipe_writes"]
        == result["managed_turn_start_acknowledgments"]
        == 1
    )
    assert result["upstream_model_requests"] is None


def test_read_metrics_rejects_corrupt_counts_and_preserves_unknown_entry():
    from services.agent.read_budget import ReadBudget

    budget = ReadBudget()
    activity = budget.close()
    assert read_metrics({"read_activity": activity})["entry_count_complete"]
    with pytest.raises(ValueError):
        read_metrics({"read_activity": {**activity, "reserved": 1}})
    with pytest.raises(ValueError):
        read_metrics({"read_activity": {**activity, "reserved": False}})
    unknown = {**activity, "entry_count_complete": False}
    assert read_metrics({"read_activity": unknown})["status"] == "incomplete"


def test_client_marks_do_not_reset_when_stream_replays():
    clock = [10.0]
    trace = CaseTrace(clock=lambda: clock[0])
    clock[0] = 11
    trace.mark("first_stream_progress_received")
    clock[0] = 15
    trace.mark("first_stream_progress_received")
    trace.mark("terminal_stream_received")
    assert trace.snapshot()["timings_s"] == {"first_stream_progress_received": 1, "terminal_stream_received": 5}


@pytest.mark.asyncio
async def test_saved_reservation_is_unknown_after_final_save_failure():
    durable = []
    entered = asyncio.Event()
    release = asyncio.Event()

    class Model:
        async def once(self):
            entered.set()
            await release.wait()
            return {"status": "ok"}

    def sink(value):
        if durable:
            raise OSError("final save failed")
        durable.append(value)

    trace = CaseTrace(sink=sink)
    task = asyncio.create_task(MeasuredModel(Model(), trace).once())
    await entered.wait()
    assert durable[-1]["model_invocations"] is None
    assert durable[-1]["model_invocations_lower_bound"] == 0
    assert not durable[-1]["model_entry_count_complete"]
    assert not durable[-1]["measurement_complete"]
    release.set()
    with pytest.raises(OSError):
        await task
    assert trace.snapshot()["model_invocations"] == 1
    with pytest.raises(ValueError, match="incomplete"):
        trace.finish()
    assert durable[-1]["model_invocations"] is None


@pytest.mark.asyncio
async def test_failed_pipe_measurement_preserves_incomplete_lower_bound(monkeypatch):
    durable, actual_writes = [], []

    def sink(value):
        if value["managed_turn_start_pipe_writes"]:
            raise OSError("save failed after actual write")
        durable.append(value)

    async def sent(self, message):
        actual_writes.append(message)

    async def requested(self, method, params):
        await self.send({"method": method})

    monkeypatch.setattr(CodexBridge, "send", sent)
    monkeypatch.setattr(CodexBridge, "request", requested)
    trace = CaseTrace(sink=sink)
    with pytest.raises(OSError):
        await measured_bridge(trace)().request("turn/start", {})
    assert len(actual_writes) == 1
    assert durable[-1]["managed_turn_start_pipe_writes"] == 0
    assert not durable[-1]["measurement_complete"]
    assert "lower bounds" in durable[-1]["count_interpretation"]
    with pytest.raises(ValueError):
        trace.finish()


def test_new_activity_invalidates_completed_measurement():
    durable = []
    trace = CaseTrace(sink=durable.append)
    trace.finish()
    assert durable[-1]["measurement_complete"]
    trace.mark("answer_lookup_started")
    assert not durable[-1]["measurement_complete"]
    trace.finish()
    assert durable[-1]["measurement_complete"]


@pytest.mark.asyncio
async def test_fixture_setup_failure_restores_environment_and_closes_socket(monkeypatch):
    import os
    import socket

    from scripts import verify_research_eval_metrics as verifier

    original_socket = socket.socket
    sockets = []

    def tracked(*args, **kwargs):
        sock = original_socket(*args, **kwargs)
        sockets.append(sock)
        return sock

    monkeypatch.setenv("FLOWW_AGENT_DEPLOYMENT", "existing-value")
    monkeypatch.delenv("FLOWW_AGENT_ORIGINS", raising=False)
    monkeypatch.setattr(verifier.AgentRepository, "initialize", AsyncMock(side_effect=OSError("setup failed")))
    monkeypatch.setattr(verifier.socket, "socket", tracked)
    with pytest.raises(OSError, match="setup failed"):
        await verifier.verify()
    assert os.environ["FLOWW_AGENT_DEPLOYMENT"] == "existing-value"
    assert "FLOWW_AGENT_ORIGINS" not in os.environ
    assert sockets and all(sock.fileno() == -1 for sock in sockets)
