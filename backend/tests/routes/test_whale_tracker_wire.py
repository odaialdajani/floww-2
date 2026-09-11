"""Agent C (P1-7 end-to-end): whale badge endpoint + scan-loop hookup.

GET /api/alerts/whales serves tracked whales; _run_institutional_alerts
bookmarks WHALE-rule fires and updates all tracks from each scan's rows.
"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from routes import flowseeker as fs


@pytest.fixture(scope="module")
def client():
    from server import app
    return TestClient(app)


def test_whales_endpoint_serves_tracks(client):
    tracks = [{"ckey": "SPY|call|700|2026-09-18", "state": "STILL_IN"}]
    with patch("services.journal_store.get_engine"), \
         patch("services.journal_store.init_whale_tables"), \
         patch("services.journal_store.read_whales", return_value=tracks):
        r = client.get("/api/alerts/whales")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True and data["n"] == 1
    assert data["tracks"][0]["state"] == "STILL_IN"


def test_whales_endpoint_empty_is_empty_not_500(client):
    with patch("services.journal_store.get_engine"), \
         patch("services.journal_store.init_whale_tables"), \
         patch("services.journal_store.read_whales", return_value=[]):
        r = client.get("/api/alerts/whales")
    assert r.status_code == 200
    assert r.json()["tracks"] == []


@pytest.mark.asyncio
async def test_scan_loop_bookmarks_whales_and_updates_tracks():
    normed = [{"under": "SPY", "ckey": "SPY|call|700|2026-09-18", "occ": "O1",
               "spot": 770.0, "oi": 5000, "vol": 30000, "dte": 10}]
    eval_out = [{"under": "SPY", "ckey": "SPY|call|700|2026-09-18",
                 "key": "whale|SPY|call|700|2026-09-18", "rule": "WHALE", "tier": "GOLD"}]
    marks, updates = [], {}

    with patch.object(fs, "_volume_baselines", AsyncMock(return_value={})), \
         patch.object(fs, "_prev_contract_oi", AsyncMock(return_value={})), \
         patch.object(fs, "_cached_regimes", return_value=[]), \
         patch.object(fs, "_load_calibration", AsyncMock(return_value=None)), \
         patch.object(fs, "_merged_gex_context", return_value={}), \
         patch.object(fs, "_compute_oi_tags", return_value={}), \
         patch("services.flow_alerts.norm_rows", side_effect=lambda r: normed), \
         patch("services.flow_alerts.eval_institutional", return_value=eval_out), \
         patch("services.flow_alerts.init_flow_alert_tables"), \
         patch("services.flow_desk.desk_pass", side_effect=lambda e, r, a, **k: a), \
         patch("services.flow_alerts.dedup_filter", side_effect=lambda e, a: a), \
         patch("services.flow_alerts.persist_alerts"), \
         patch("services.flow_alerts.update_moves"), \
         patch("services.journal_store.bookmark_whale",
               side_effect=lambda e, a, **k: marks.append(a.get("ckey")) or 1), \
         patch("services.journal_store.update_whales",
               side_effect=lambda e, s: updates.update(s) or {}), \
         patch("services.journal_store.get_engine"), \
         patch("services.journal_store.init_journal_tables"), \
         patch("services.journal_store.journal_lifecycle", return_value=0):
        await fs._run_institutional_alerts([{**normed[0]}])

    assert marks == ["SPY|call|700|2026-09-18"], "WHALE fire must bookmark exactly once"
    assert updates["SPY|call|700|2026-09-18"]["oi"] == 5000
