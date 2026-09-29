"""S4 recorder health: durability and capture state are different facts (Spark).

A durable store with no capture worker must not be described as either
"healthy" or "needs time". These pin the three distinct worker states, the
disabled-by-default activation, and the stop/recovery contract.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

duckdb = pytest.importorskip("duckdb")

from services import recorder_health as rh  # noqa: E402


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv(rh.WORKER_ENV_FLAG, raising=False)
    rh._STOP.clear()
    rh._THREAD = None
    rh._CAPTURE = None
    rh._STATS.update({
        "worker_state": "absent", "last_capture_at": None, "last_error_at": None,
        "last_error": None, "captures": 0, "errors": 0, "gaps": 0,
    })
    yield
    rh._STOP.set()
    if rh._THREAD is not None and rh._THREAD.is_alive():
        rh._THREAD.join(timeout=2.0)
    rh._THREAD = None
    rh._CAPTURE = None


def test_memory_store_is_not_durable(tmp_path):
    mem = duckdb.connect(":memory:")
    try:
        health = rh.recorder_health(mem)
    finally:
        mem.close()
    assert health["durable"] is False
    assert health["store"]["mode"] in ("memory", "file")
    assert health["store"]["backing"] == "memory"


def test_file_store_with_tables_is_durable(tmp_path):
    path = tmp_path / "health.duckdb"
    conn = duckdb.connect(str(path))
    try:
        from services.heatmap_history import ensure_tables

        ensure_tables(conn)
        health = rh.recorder_health(conn)
    finally:
        conn.close()
    assert health["durable"] is True
    assert health["store"]["backing"] == "file"


def test_absent_worker_is_not_the_same_as_a_disabled_worker(monkeypatch):
    first = rh.start_worker()
    assert first["started"] is False
    assert first["worker_state"] == "absent", "no capture registered anywhere = absent"
    health = rh.recorder_health()
    assert health["worker_state"] == "absent"
    assert health["capture_registered"] is False

    rh.register_capture(lambda: {"snapshot_id": "x"})
    health2 = rh.recorder_health()
    assert health2["worker_state"] == "wired_off", (
        "a registered capture with the flag unset is OFF, not absent"
    )
    assert health2["worker_enabled"] is False
    assert health2["capture_registered"] is True


def test_worker_starts_only_with_the_explicit_flag(monkeypatch):
    rh.register_capture(lambda: {"snapshot_id": "x"})
    assert rh.start_worker()["started"] is False
    assert rh.recorder_health()["worker_state"] == "wired_off"

    monkeypatch.setenv(rh.WORKER_ENV_FLAG, "0")
    assert rh.start_worker()["started"] is False
    monkeypatch.setenv(rh.WORKER_ENV_FLAG, "1")
    started = rh.start_worker()
    assert started["started"] is True
    assert rh.recorder_health()["worker_state"] == "active"
    assert rh.stop_worker()["worker_state"] == "wired_off"
    assert rh.stop_worker()["stopped"] is True, "stop is idempotent"


def test_failures_and_gaps_are_counted_separately_from_successes(monkeypatch):
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            return None                     # a real attempt, no observation
        if calls["n"] == 2:
            raise RuntimeError("provider down")
        return {"snapshot_id": "s1"}

    rh.register_capture(flaky)
    monkeypatch.setenv(rh.WORKER_ENV_FLAG, "1")
    monkeypatch.setattr(rh, "WORKER_INTERVAL_S", 0.01)
    assert rh.start_worker()["started"] is True
    deadline = time.time() + 3.0
    while time.time() < deadline:
        health = rh.recorder_health()
        if health["captures"] and health["gaps"] and health["errors"]:
            break
        time.sleep(0.02)
    rh.stop_worker()
    health = rh.recorder_health()
    assert health["gaps"] == 1
    assert health["errors"] == 1
    assert "RuntimeError" in (health["last_error"] or "")
    assert health["captures"] >= 1
    assert health["last_capture_at"] is not None
    assert health["last_capture_age_s"] is not None
    assert health["durable"] is False  # no store was passed: separate facts


def test_stop_recovery_instructions_are_present_on_every_packet():
    for _ in range(2):
        health = rh.recorder_health()
        assert set(health["stop_recovery"]) == {"stop", "recovery", "note"}
        assert "stop_worker()" in health["stop_recovery"]["stop"]
        assert "activation is an explicit operator act" in health["stop_recovery"]["note"]
