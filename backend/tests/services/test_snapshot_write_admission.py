"""Recorder backpressure at the actual fresh-build hook; no provider or live store."""

import ast
import asyncio
from pathlib import Path
from threading import Event

import duckdb
import pytest

from services import duckdb_engine, heatmap_history
from tests.offline_network import deny_external_network  # noqa: F401


def recording_hook(monkeypatch, conn, *, await_recording=False):
    tree = ast.parse((Path(__file__).resolve().parents[2] / "server.py").read_text())
    builder = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_build_heatmap_impl")
    hook = next(n for n in builder.body if isinstance(n, ast.Try) and
                "from services.heatmap_history import" in ast.unparse(n) and
                "RECORDED_STRUCTURE_FIELDS" in ast.unparse(n))
    # Compile the real producer boundary, not a rewritten copy of its scheduling.
    function = ast.AsyncFunctionDef(
        name="record", args=ast.arguments(posonlyargs=[], args=[ast.arg(arg="payload")],
                                          kwonlyargs=[], kw_defaults=[], defaults=[]),
        body=[hook, ast.Return(value=ast.Name(id="payload", ctx=ast.Load()))], decorator_list=[])
    tasks = set()
    namespace = dict(asyncio=asyncio, _background_tasks=tasks, ticker="SPY", mode="day", dte=None,
                     scalp=False, history_query_key="SPY:day:None:False", spot=100, strikes=[], metrics={},
                     requested_map_query={}, scope_selection=None, exposure_basis="OI", raw={"contracts": []},
                     log=__import__("logging").getLogger(__name__), await_recording=await_recording,
                     _SNAPSHOT_ACK_TIMEOUT_S=0.1)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), "<actual-recording-hook>", "exec"), namespace)
    monkeypatch.setattr(duckdb_engine.db, "_conn", conn)
    monkeypatch.setattr(heatmap_history, "record_capability", lambda *args, **kwargs: None)
    return namespace["record"], tasks


def writer_class():
    import importlib.util

    assert importlib.util.find_spec("services.snapshot_writes") is not None, "physical writes need bounded admission and commit receipts"
    from services.snapshot_writes import SnapshotWrites
    return SnapshotWrites


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_release_a_running_physical_write(monkeypatch):
    writer = writer_class()(max_pending=1)
    release = Event()
    started = Event()

    def blocked_write(conn, payload, query_key, snapshot_id=None):
        started.set()
        assert release.wait(5)
        return snapshot_id

    monkeypatch.setattr(heatmap_history, "record_snapshot", blocked_write)
    monkeypatch.setattr(heatmap_history, "record_capability", lambda *args, **kwargs: None)
    try:
        job = writer.submit(object(), {}, "query", "snap_first")
        assert job is not None
        assert await asyncio.to_thread(started.wait, 2)
        waiter = asyncio.create_task(job.wait())
        await asyncio.sleep(0)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert writer.status()["pending"] == 1
        assert writer.submit(object(), {}, "query", "snap_second") is None
        assert writer.status()["refused"] == 1
        release.set()
        assert (await job.wait())["status"] == "committed"
        await writer.drain()
        assert writer.status()["pending"] == 0
        assert writer.status()["committed"] == 1
    finally:
        release.set()
        writer.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("result,reason", [(None, "no_observation_id"), (False, "no_observation_id"), ("snap_wrong", "identity_mismatch")])
async def test_a_write_without_the_expected_identity_is_not_acknowledged(monkeypatch, result, reason):
    writer = writer_class()(max_pending=1)
    monkeypatch.setattr(heatmap_history, "record_snapshot", lambda *args: result)
    try:
        job = writer.submit(object(), {}, "query", "snap_expected")
        receipt = await job.wait()
        assert receipt == {"status": "failed", "reason": reason, "snapshot_id": "snap_expected"}
        await writer.drain()
        assert writer.status()["committed"] == 0
        assert writer.status()["failed"] == 1
    finally:
        writer.shutdown()


@pytest.mark.asyncio
async def test_write_exception_releases_capacity_without_leaking_details(monkeypatch):
    writer = writer_class()(max_pending=1)

    def fail(*args):
        raise RuntimeError("sensitive provider or database detail")

    monkeypatch.setattr(heatmap_history, "record_snapshot", fail)
    try:
        receipt = await writer.submit(object(), {}, "query", "snap_error").wait()
        assert receipt == {"status": "failed", "reason": "write_failed", "snapshot_id": "snap_error"}
        await writer.drain()
        assert writer.status()["pending"] == 0
        assert writer.status()["failed"] == 1
    finally:
        writer.shutdown()


@pytest.mark.asyncio
async def test_payload_is_frozen_before_a_queued_write_runs(monkeypatch):
    writer = writer_class()(max_pending=2)
    release = Event()
    started = Event()
    seen = []

    def store(conn, payload, query_key, snapshot_id=None):
        if snapshot_id == "snap_blocker":
            started.set()
            assert release.wait(5)
        seen.append(payload)
        return snapshot_id

    monkeypatch.setattr(heatmap_history, "record_snapshot", store)
    try:
        first = writer.submit(object(), {}, "query", "snap_blocker")
        assert await asyncio.to_thread(started.wait, 2)
        payload = {"grid": {"value": 10}}
        second = writer.submit(object(), payload, "query", "snap_frozen")
        payload["grid"]["value"] = 99
        assert second.receipt()["status"] == "queued"
        release.set()
        await first.wait()
        assert (await second.wait())["status"] == "committed"
        assert seen[1]["grid"]["value"] == 10
    finally:
        release.set()
        writer.shutdown()


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_pending_limits_cannot_disable_backpressure(limit):
    with pytest.raises(ValueError):
        writer_class()(max_pending=limit)


@pytest.mark.asyncio
async def test_capability_failure_does_not_erase_a_successful_commit(monkeypatch):
    writer = writer_class()(max_pending=1)
    monkeypatch.setattr(heatmap_history, "record_snapshot", lambda *args: "snap_committed")

    def fail_capability(*args, **kwargs):
        raise RuntimeError("synthetic capability failure")

    monkeypatch.setattr(heatmap_history, "record_capability", fail_capability)
    try:
        job = writer.submit(object(), {"ticker": "SPY"}, "query", "snap_committed", capability={"requested": 1})
        assert (await job.wait())["status"] == "committed"
    finally:
        writer.shutdown()


@pytest.mark.asyncio
async def test_real_file_backed_write_receipt_follows_commit_and_reopens(tmp_path):
    writer = writer_class()(max_pending=1)
    path = tmp_path / "recording.duckdb"
    payload = {"ticker": "SPY", "spot": 100.0, "asof": "2026-10-16T14:00:00+00:00",
               "expiries_used": ["2026-10-19"], "contracts": [], "strikes": [], "grid": {}, "metrics": {}}
    snapshot_id = heatmap_history.observation_id_for(payload)
    try:
        with duckdb.connect(str(path)) as conn:
            receipt = await writer.submit(conn, payload, "SPY:test", snapshot_id).wait()
            assert receipt == {"status": "committed", "snapshot_id": snapshot_id}
            await writer.drain()
        with duckdb.connect(str(path), read_only=True) as reopened:
            saved = heatmap_history.replay_snapshot(reopened, snapshot_id)
            assert saved is not None
            assert saved["snapshot"]["snapshot_id"] == snapshot_id
            assert saved["snapshot"]["ticker"] == "SPY"
    finally:
        writer.shutdown()


@pytest.mark.asyncio
async def test_fresh_builds_bound_pending_snapshot_writes_before_task_creation(monkeypatch):
    release = Event()

    def blocked_write(conn, payload, query_key, snapshot_id=None):
        assert release.wait(5), "test must release its synthetic writer"
        return snapshot_id

    monkeypatch.setattr(heatmap_history, "record_snapshot", blocked_write)
    with duckdb.connect(":memory:") as conn:
        record, tasks = recording_hook(monkeypatch, conn)
        try:
            replies = [await record({"snapshotId": f"snap_{n}"}) for n in range(12)]
            assert len(tasks) <= 8, "fresh builds must not enqueue unbounded recorder tasks"
            refused = [r for r in replies if r.get("recording_receipt", {}).get("status") == "refused"]
            assert len(refused) == 4
            assert all(r["recording_receipt"]["reason"] == "backpressure" for r in refused)
        finally:
            release.set()
            if tasks:
                await asyncio.gather(*list(tasks), return_exceptions=True)


@pytest.mark.asyncio
async def test_ordinary_build_names_queueing_without_claiming_a_commit(monkeypatch):
    release = Event()

    def blocked_write(conn, payload, query_key, snapshot_id=None):
        assert release.wait(5), "test must release its synthetic writer"
        return snapshot_id

    monkeypatch.setattr(heatmap_history, "record_snapshot", blocked_write)
    with duckdb.connect(":memory:") as conn:
        record, tasks = recording_hook(monkeypatch, conn)
        try:
            reply = await record({"snapshotId": "snap_waiting"})
            receipt = reply.get("recording_receipt", {})
            assert receipt.get("status") == "queued", "a returned market-data build is not a COMMIT acknowledgement"
            assert receipt.get("snapshot_id") == "snap_waiting"
        finally:
            release.set()
            if tasks:
                await asyncio.gather(*list(tasks), return_exceptions=True)
