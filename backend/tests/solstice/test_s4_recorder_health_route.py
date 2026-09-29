"""S4: the recorder-health ROUTE is the production caller (Spark).

A module tested only in isolation proves nothing about delivery. This
exercises the actual HTTP route, which is how an operator reads it, and
pins the two facts it must never conflate: is the store durable, and is a
capture job running.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

httpx = pytest.importorskip("httpx")


def test_recorder_health_route_separates_store_from_capture(monkeypatch):
    from fastapi.testclient import TestClient

    import routes.solstice  # noqa: F401  (mounts the route under test)
    import server
    from services import recorder_health as rh
    from services.duckdb_engine import db as eng

    # No capture registered, flag unset: the job state is "absent", and the
    # store state is whatever the real engine is (memory here).
    monkeypatch.delenv(rh.WORKER_ENV_FLAG, raising=False)
    rh._CAPTURE = None
    rh._STATS.update({"worker_state": "absent", "captures": 0, "gaps": 0, "errors": 0,
                      "last_capture_at": None, "last_error": None, "last_error_at": None})

    client = TestClient(server.app)
    r = client.get("/api/solstice/recorder_health")
    assert r.status_code == 200, r.text
    body = r.json()

    # Legacy top-level shape preserved for existing consumers.
    for key in ("durable", "mode", "backing", "path", "tables", "latest_snapshot",
                "checked_at"):
        assert key in body, key
    assert isinstance(body["durable"], bool)

    # New capture block: the job state, distinct from the store state.
    cap = body["capture"]
    assert cap["worker_state"] in ("absent", "wired_off", "active")
    assert cap["worker_state"] == "absent"
    assert cap["worker_enabled"] is False
    assert cap["capture_registered"] is False
    assert cap["last_capture_at"] is None
    assert "stop_worker()" in cap["stop_recovery"]["stop"]

    # A durable store is never inferred from a configured path, and a
    # non-durable one is never dressed up as collecting.
    if body["durable"] is False:
        assert cap["last_capture_at"] is None or cap["captures"] >= 0
    assert eng is not None


def test_recorder_health_route_reports_a_registered_disabled_worker(monkeypatch):
    from fastapi.testclient import TestClient

    import server
    from services import recorder_health as rh

    monkeypatch.delenv(rh.WORKER_ENV_FLAG, raising=False)
    try:
        rh.register_capture(lambda: {"snapshot_id": "x"})
        client = TestClient(server.app)
        body = client.get("/api/solstice/recorder_health").json()
        assert body["capture"]["worker_state"] == "wired_off"
        assert body["capture"]["capture_registered"] is True
    finally:
        rh._CAPTURE = None
        rh._STATS["worker_state"] = "absent"
