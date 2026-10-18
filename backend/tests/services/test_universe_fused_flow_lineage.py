"""Already-fused flow observations must reach the leaderboard without refusion."""

from copy import deepcopy
from decimal import Decimal
from unittest.mock import AsyncMock

import duckdb
import pytest

from routes import flowseeker
from services import flow_alerts, movers, public_budget, universe_scan
from services.conviction_rank import rank_many, rank_one
from services.duckdb_engine import db
from tests.offline_network import deny_external_network  # noqa: F401

ASOF = "2026-10-16T14:00:00+00:00"


@pytest.mark.asyncio
@pytest.mark.parametrize("flow_score", [0, 20, 100])
async def test_actual_scan_route_preserves_fused_flow_evidence_through_persistence(monkeypatch, flow_score):
    monkeypatch.setattr(flowseeker, "_UNIVERSE_SCAN_CACHE", {"ts": 0.0, "payload": None})
    monkeypatch.setattr(flowseeker, "_UNIVERSE_CURSOR", 0)
    monkeypatch.setattr(flowseeker, "_universe_scan_opportunity", lambda *args: None)
    monkeypatch.setattr(movers, "POPULAR_UNIVERSE", ["SPY"])
    monkeypatch.setattr(movers, "get_movers", AsyncMock(return_value={"results": []}))
    monkeypatch.setattr(public_budget.budget, "peek_available", AsyncMock(return_value=100))
    monkeypatch.setattr(flow_alerts, "read_alert_feed", lambda *args, **kwargs: [
        {"under": "SPY", "conviction": flow_score, "key": "fixture-flow"}])
    real_scan = universe_scan.scan_batch

    async def fake_provider_build(ticker, **kwargs):
        return {"snapshotId": "snap-SPY", "spot": 100.0, "asof": ASOF}

    async def offline_scan(tickers, **kwargs):
        return await real_scan(tickers, build_heatmap_fn=fake_provider_build, **kwargs)

    monkeypatch.setattr(universe_scan, "scan_batch", offline_scan)
    with duckdb.connect(":memory:") as conn:
        monkeypatch.setattr(db, "_conn", conn)
        result = await flowseeker.universe_scan(limit=1, max_expiries=2, dte=None, refresh=True)
        expected = float(Decimal("0.35") * Decimal(flow_score))
        assert len(result["fused"]) == len(result["leaderboard"]) == 1
        for row in (result["fused"][0], result["leaderboard"][0]):
            assert row["conviction"] == expected
            assert row["evidence"]["flow_status"] == "ok"
            assert row["evidence"].get("flow_alert_key") == "fixture-flow"
            assert row["snapshot_id"] == "snap-SPY"
            assert row["asof"] == ASOF
            assert row["rank"] == 1


def test_fused_rows_are_preserved_once_sorted_and_not_aliased():
    originals = []
    for ticker, score in [("WEAK", 20), ("STRONG", 80)]:
        fused = rank_one(ticker, flow={"conviction": score, "key": ticker}, snapshot_id=f"snap-{ticker}", asof=ASOF)
        originals.append({"ticker": ticker, "snapshot_id": f"snap-{ticker}", "asof": ASOF, "conviction": fused})
    before = deepcopy(originals)
    result = rank_many(originals)
    assert [row["ticker"] for row in result] == ["STRONG", "WEAK"]
    assert [row["rank"] for row in result] == [1, 2]
    for row in result:
        source = next(item["conviction"] for item in originals if item["ticker"] == row["ticker"])
        assert {key: value for key, value in row.items() if key != "rank"} == source
    result[0]["evidence"]["flow_alert_key"] = "changed-output"
    assert originals == before


@pytest.mark.parametrize("field,value", [("ticker", "QQQ"), ("snapshot_id", "different-snapshot"),
                                         ("asof", "different-clock"), ("schema_version", "unsupported.v9")])
def test_foreign_fused_identity_is_not_reinterpreted_as_current_scorer(field, value):
    fused = rank_one("SPY", flow={"conviction": 100, "key": "old-flow"}, snapshot_id="snap-SPY", asof=ASOF)
    fused[field] = value
    row = rank_many([{"ticker": "SPY", "snapshot_id": "snap-SPY", "asof": ASOF, "conviction": fused}])[0]
    assert row["evidence"]["flow_status"] == "missing"
    assert "flow_alert_key" not in row["evidence"]
    assert row["conviction"] == 0
