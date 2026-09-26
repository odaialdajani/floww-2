"""Mixed legacy/new dates must be ordered before retention or display limits."""
from datetime import UTC, datetime, timedelta

import pytest
from mongomock_motor import AsyncMongoMockClient

import server


@pytest.mark.asyncio
async def test_velocity_uses_newest_legacy_row_before_ten_row_limit(monkeypatch):
    db = AsyncMongoMockClient().test_snapshot_order
    monkeypatch.setattr(server, "db", db)
    start = datetime(2026, 9, 1, tzinfo=UTC)
    for i in range(11):
        await db.snapshots.insert_one({"ticker": "SPY", "ts": start + timedelta(minutes=i),
                                      "strikes_compact": [{"strike": 500, "gex": 100}]})
    await db.snapshots.insert_one({"ticker": "SPY", "ts": (start + timedelta(days=1)).isoformat(),
                                  "strikes_compact": [{"strike": 500, "gex": 200}]})
    result = await server.velocity_and_rolling("SPY", {"strikes_compact": [{"strike": 500, "gex": 200}]})
    assert result["velocity_score"] == 0
    assert result["snapshots_count"] == 11


@pytest.mark.asyncio
async def test_retention_keeps_newest_legacy_row(monkeypatch):
    db = AsyncMongoMockClient().test_snapshot_retention
    monkeypatch.setattr(server, "db", db)
    start = datetime(2026, 9, 1, tzinfo=UTC)
    for i in range(50):
        await db.snapshots.insert_one({"ticker": "SPY", "ts": start + timedelta(minutes=i)})
    await db.snapshots.insert_one({"ticker": "SPY", "ts": (start + timedelta(days=1)).isoformat(),
                                  "marker": "newer-legacy"})
    await server.save_snapshot("SPY", {"spot": 500, "nodes": {}, "strikes": []})
    assert await db.snapshots.count_documents({"ticker": "SPY"}) == 50
    assert await db.snapshots.find_one({"marker": "newer-legacy"}) is not None
    assert await db.snapshots.find_one({"ts": start}) is None


@pytest.mark.asyncio
async def test_history_keeps_legacy_dates_and_orders_instants(monkeypatch):
    from routes.analytics import history

    db = AsyncMongoMockClient().test_history_dates
    monkeypatch.setattr(server, "db", db)
    now = datetime.now(UTC)
    await db.snapshots.insert_many([
        {"ticker": "SPY", "ts": now - timedelta(hours=2), "marker": "older"},
        {"ticker": "SPY", "ts": (now - timedelta(hours=1)).isoformat(), "marker": "newer"},
        {"ticker": "SPY", "ts": (now - timedelta(days=2)).isoformat(), "marker": "outside"},
        {"ticker": "QQQ", "ts": now, "marker": "other"},
    ])
    result = await history("SPY", days=1)
    assert [row["marker"] for row in result["snapshots"]] == ["newer", "older"]
    assert result["count"] == 2
