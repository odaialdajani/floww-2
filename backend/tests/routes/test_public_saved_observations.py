"""Minimal application checks: saved reads cannot admit provider work or alerts."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import flowseeker as routes
from services import public_scanner as scanner


@pytest.fixture
def client(monkeypatch):
    scanner._reset_state()
    monkeypatch.delenv("FLOWW_PUBLIC_UNIVERSE", raising=False)
    monkeypatch.setattr("services.market_catalog.peek_catalog", lambda: dict(available=False, stale=True, asof=None))
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app) as test_client:
        yield test_client
    scanner._reset_state()


def row(name):
    return [name, f"{name}-actual-option", "call", 100, "2026-10-16", 500, 100, None, None, 100]


def test_saved_read_paginates_actual_legacy_rows_without_live_scan_or_alerts(client, monkeypatch):
    received = datetime.now(UTC).timestamp() - 100
    for i in range(125):
        name = f"T{i:03}"
        scanner._recent_findings_store().save(name, received, [row(name)])
    live = AsyncMock(side_effect=AssertionError("saved read cannot start a scan"))
    refresh = AsyncMock(side_effect=AssertionError("saved read cannot fetch a directory"))
    alerts = AsyncMock(side_effect=AssertionError("saved read cannot feed alerts"))
    monkeypatch.setattr(scanner, "scan_next", live)
    monkeypatch.setattr("services.market_catalog.get_catalog", refresh)
    monkeypatch.setattr(routes, "_run_institutional_alerts", alerts)
    first = client.get("/api/flowseeker/scan-public/observations", params={"limit": 100})
    assert first.status_code == 200
    data = first.json()
    assert data["total"] == 125 and data["count"] == 100 and data["next_offset"] == 100
    second = client.get("/api/flowseeker/scan-public/observations", params={"offset": 100, "limit": 100}).json()
    assert second["count"] == 25 and second["next_offset"] is None
    assert len({r[0] for r in data["rows"] + second["rows"]}) == 125
    assert data["quote_truth"] == {}
    evidence = next(iter(data["row_observations"].values()))
    assert evidence["received_at"] == received and evidence["volume_source_time"] is None
    assert evidence["data_status"] == "legacy_limited" and evidence["quote_extras_available"] is False
    assert data["status"] == "partial" and data["coverage"]["universe"] is None
    assert data["live"] is False and data["trade_eligible"] is False
    assert len(data["columns"]) == 10
    filtered = client.get("/api/flowseeker/scan-public/observations", params={"ticker": "T124", "age": "stale"}).json()
    assert filtered["rows"] == [row("T124")]
    live.assert_not_awaited()
    refresh.assert_not_awaited()
    alerts.assert_not_awaited()


@pytest.mark.parametrize("params", [{"limit": 501}, {"offset": -1}, {"age": "live"},
                                     {"expiry": "bad"}, {"contract_type": "stock"}, {"max_age_seconds": 1}, {"order": "live"}])
def test_invalid_saved_filters_are_refused_before_storage(client, monkeypatch, params):
    read = AsyncMock(side_effect=AssertionError("invalid filter reached storage"))
    monkeypatch.setattr(scanner, "saved_observations_page", read)
    assert client.get("/api/flowseeker/scan-public/observations", params=params).status_code == 422
    read.assert_not_called()


def test_storage_failure_is_unavailable_instead_of_false_empty_success(client, monkeypatch):
    monkeypatch.setattr(scanner, "saved_observations_page", lambda **_: (_ for _ in ()).throw(OSError("isolated disk failure")))
    response = client.get("/api/flowseeker/scan-public/observations")
    assert response.status_code == 503
    assert response.json()["detail"] == "Saved observations are unavailable. Fresh checks remain separate."


def test_legacy_read_failure_keeps_rich_evidence_and_reports_partial(client, monkeypatch):
    received = datetime.now(UTC).timestamp() - 10
    original = row("SPY")
    key = scanner.ckey_of(original[0], original[2], original[3], original[4])
    pack = dict(status="ok", received_ts=received, event_time=None, rows=[original],
                extras={key: {"mid": 2.5, "volume_data_received_at": received, "volume_source_time": None}},
                selection={}, history_status="available")
    scanner._dated_observations_store().save("SPY", pack, scope="provider-options:2")
    def unavailable(**_):
        raise OSError("isolated legacy read failure")
    monkeypatch.setattr(scanner._recent_findings_store(), "saved_records", unavailable)
    response = client.get("/api/flowseeker/scan-public/observations")
    assert response.status_code == 200
    result = response.json()
    assert result["rows"] == [original]
    assert result["status"] == "partial" and result["coverage"]["legacy_status"] == "unavailable"
    evidence = result["row_observations"][key]
    assert evidence["received_at"] == received and evidence["volume_clock_status"] == "unknown"
    assert evidence["trade_eligible"] is False


def test_failed_legacy_read_without_rich_evidence_is_unavailable_not_empty(client, monkeypatch):
    def unavailable(**_):
        raise OSError("isolated legacy read failure")
    monkeypatch.setattr(scanner._recent_findings_store(), "saved_records", unavailable)
    response = client.get("/api/flowseeker/scan-public/observations")
    assert response.status_code == 503
    assert response.json()["detail"] == "Saved observations are unavailable. Fresh checks remain separate."
