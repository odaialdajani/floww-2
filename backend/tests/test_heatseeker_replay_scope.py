"""
backend/tests/test_heatseeker_replay_scope.py

Route-level regression for the Task 6 replay-scope repair: a UTC day of
stored replay rows for one ticker may contain more than one query scope.
The session answer must then either group per scope or explicitly refuse to
certify ONE session — never merge the scopes into a single certified day.

The recorder read is the route's own ``_read_replay_session_rows`` helper
(mocked here), so no live store, provider or service is involved.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routes.heatseeker import STORE_BUSY_MESSAGE  # noqa: E402
from server import app  # noqa: E402
from services.store_executor import StoreBusy  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _row(asof: str, scope: str | None, snap: str) -> dict[str, Any]:
    return {"asof": asof, "query_key": scope, "snapshot_id": snap,
            "n_contracts": 616}


TWO_SCOPES = [
    _row("2026-11-06T14:30:00Z", "q=4exp", "s1"),
    _row("2026-11-06T14:35:00Z", "q=12exp", "s2"),
    _row("2026-11-06T14:40:00Z", "q=4exp", "s3"),
    _row("2026-11-06T14:45:00Z", "q=12exp", "s4"),
]

ONE_SCOPE = [
    _row("2026-11-06T14:30:00Z", "q=4exp", "s1"),
    _row("2026-11-06T14:35:00Z", "q=4exp", "s2"),
    _row("2026-11-06T14:45:00Z", "q=4exp", "s3"),
]


def test_two_scopes_on_one_day_are_not_certified_as_one_session(client):
    with patch(
        "routes.heatseeker._read_replay_session_rows",
        AsyncMock(return_value=TWO_SCOPES),
    ):
        r = client.get("/api/heatseeker/replay-sessions/SPY?day=2026-11-06&cadence_s=300")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ticker"] == "SPY"
    assert d["day"] == "2026-11-06"
    assert d["status"] == "refused"
    assert d["reason"] == "MIXED_QUERY_SCOPES"
    assert d["n_scopes"] == 2
    # Grouped per scope, each keeping its own rows and gap accounting.
    scopes = {s["scope"]: s for s in d["sessions"]}
    assert set(scopes) == {"q=4exp", "q=12exp"}
    assert scopes["q=4exp"]["n_snapshots"] == 2
    assert scopes["q=12exp"]["n_snapshots"] == 2
    # Inside one scope the 10-minute interval is that scope's own gap; the
    # other scope's rows are never bridged into it.
    assert [(g["from"], g["to"]) for g in scopes["q=4exp"]["gaps"]] == [
        ("2026-11-06T14:30:00Z", "2026-11-06T14:40:00Z"),
    ]
    assert [(g["from"], g["to"]) for g in scopes["q=12exp"]["gaps"]] == [
        ("2026-11-06T14:35:00Z", "2026-11-06T14:45:00Z"),
    ]
    # No single certified session is returned for the mixed day.
    assert "session" not in d or d.get("session") is None
    assert "cannot certify" in d["note"]


def test_one_scope_on_one_day_certifies_with_gaps(client):
    with patch(
        "routes.heatseeker._read_replay_session_rows",
        AsyncMock(return_value=ONE_SCOPE),
    ):
        r = client.get("/api/heatseeker/replay-sessions/SPY?day=2026-11-06&cadence_s=300")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "ok"
    assert d["n_scopes"] == 1
    assert d["n_snapshots"] == 3
    session = d["sessions"][0]
    assert session["scope"] == "q=4exp"
    assert len(session["gaps"]) == 1
    assert session["gaps"][0]["gap_s"] == 600.0


def test_empty_day_is_an_empty_state_not_a_session(client):
    """A day with no stored rows is an empty state, never a certified session."""
    with patch(
        "routes.heatseeker._read_replay_session_rows",
        AsyncMock(return_value=[]),
    ):
        r = client.get("/api/heatseeker/replay-sessions/SPY?day=2026-11-06&cadence_s=300")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "empty"
    assert d["n_snapshots"] == 0
    assert d["sessions"] == []


def test_recorder_unavailable_is_disclosed(client):
    with patch(
        "routes.heatseeker._read_replay_session_rows",
        AsyncMock(return_value=None),
    ):
        r = client.get("/api/heatseeker/replay-sessions/SPY?day=2026-11-06&cadence_s=300")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "unavailable"
    assert d["reason"] == "recorder_unavailable"


def test_store_busy_reaches_the_degraded_body(client):
    with patch(
        "routes.heatseeker._read_replay_session_rows",
        AsyncMock(side_effect=StoreBusy()),
    ):
        r = client.get("/api/heatseeker/replay-sessions/SPY?day=2026-11-06&cadence_s=300")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "degraded"
    assert d["error"] == STORE_BUSY_MESSAGE


def test_invalid_day_is_refused_before_any_read(client):
    """A malformed day is refused up front; the store is never consulted."""
    reader = AsyncMock(return_value=ONE_SCOPE)
    with patch("routes.heatseeker._read_replay_session_rows", reader):
        r = client.get("/api/heatseeker/replay-sessions/SPY?day=not-a-day&cadence_s=300")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "refused"
    assert d["reason"] == "INVALID_DAY"
    assert reader.await_count == 0
