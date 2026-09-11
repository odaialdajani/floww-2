from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services import public_api_adapter as adapter
from services.agent.reads import ResearchReads


def test_naive_quote_time_does_not_gain_a_timezone():
    assert adapter._quote_ts_utc(SimpleNamespace(timestamp="2026-09-11T20:00:00")) is None


@pytest.mark.parametrize("now,expected", [
    ("2026-07-03T21:00:00+00:00","2026-07-02T20:00:00+00:00"),
    ("2026-11-27T19:00:00+00:00","2026-11-27T18:00:00+00:00"),
])
def test_quote_staleness_uses_actual_exchange_close(now,expected):
    assert adapter._last_us_close_utc(datetime.fromisoformat(now)).isoformat() == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("bid,ask", [(0,100),(-1,100),(110,100),(1,100),(float("nan"),100)])
async def test_batch_quotes_reject_invalid_midpoints(bid, ask):
    from services.public_api import Quote
    now = datetime.now(UTC).isoformat()
    quote = Quote(symbol="SPY", instrument_type="EQUITY", bid=bid, ask=ask, last=99,
                  timestamp=now, bid_timestamp=now, ask_timestamp=now)
    broker = SimpleNamespace(get_trading_account=lambda:SimpleNamespace(account_id="test"),
                             get_quotes=AsyncMock(return_value=[quote]))
    with patch.object(adapter,"_get_broker",AsyncMock(return_value=broker)), patch.object(adapter,"_record_call") as record:
        result = await adapter.fetch_quotes_from_public_api(["SPY"])
    assert result is None
    record.assert_not_called()


@pytest.mark.asyncio
async def test_price_has_own_source_and_time_without_freshening_chain():
    now = datetime.now(UTC)
    raw = dict(
        spot=500,
        data_source="public_api",
        event_time=None,
        spot_source="yfinance-fallback",
        spot_event_time=None,
        spot_fetched_at=now.isoformat(),
        fetched_at=now.isoformat(),
        contracts=[],
    )
    reads = ResearchReads(lambda *_: raw, lambda *_: None, lambda *_: [])
    first = await reads.snapshot("SPY", "all", now=now)
    price = next(f for f in first["facts"] if f["metric"] == "Underlying price")
    assert price["source"] == "yfinance-fallback"
    assert price["event_time"] is None and price["status"] == "degraded"
    raw.update(spot_source="public-mid", spot_event_time=now.isoformat())
    second = await reads.snapshot("SPY", "all", now=now)
    price = next(f for f in second["facts"] if f["metric"] == "Underlying price")
    assert price["source"] == "public-mid" and price["status"] == "ok"
    assert second["snapshot_id"] != first["snapshot_id"]
    assert next(f for f in second["facts"] if f["metric"] == "Available contracts")["status"] == "degraded"


def test_cached_age_advances_without_inventing_source_time():
    stamp = (datetime.now(UTC) - timedelta(seconds=300)).isoformat()
    result = adapter._cached_copy(dict(fetched_at=stamp, event_time=None), stale=True)
    assert result["cache_age_s"] >= 300
    assert result["event_time"] is None and result["stale"]


def test_heatmap_cache_preserves_original_age_and_copy():
    from services.market_provenance import cached_market_copy

    original = {"stale_age_s": 600, "stale": True, "event_time": None, "grid": {"value": 4}}
    result = cached_market_copy(original, 10)
    assert result["stale_age_s"] == 610 and result["stale"] and result["event_time"] is None
    result["grid"]["value"] = 100
    assert original["grid"]["value"] == 4 and original["stale_age_s"] == 600
    assert cached_market_copy({"event_time": None}, 10)["stale_age_s"] is None


def test_public_peek_is_copy_only_without_refresh(monkeypatch):
    monkeypatch.setattr(
        adapter,
        "_CHAIN_CACHE",
        {
            ("SPY", 4): (
                0,
                None,
                {
                    "spot": 500,
                    "spot_source": "public-mid",
                    "fetched_at": datetime.now(UTC).isoformat(),
                    "contracts": [{"strike": 500}],
                    "event_time": None,
                },
            )
        },
    )
    result = adapter.peek_chain_from_public_api("SPY")
    assert result["requested_expiry_count"] == 4 and result["event_time"] is None
    result["contracts"][0]["strike"] = 123
    assert adapter.peek_chain_from_public_api("SPY")["contracts"][0]["strike"] == 500


@pytest.mark.asyncio
async def test_public_spot_retains_provider_time():
    now = datetime.now(UTC)
    q = SimpleNamespace(symbol="SPY", bid=499.99, ask=500.01, mid_price=500, timestamp=now.isoformat(),
                        bid_timestamp=now.isoformat(), ask_timestamp=now.isoformat())
    pb = SimpleNamespace(get_quotes=AsyncMock(return_value=[q]))
    result = await adapter._resolve_spot_observation(pb, "SPY", "sample", now=now)
    assert result["price"] == 500 and result["source"] == "public-mid"
    assert result["event_time"] == now.isoformat()
    assert result["fetched_at"]


@pytest.mark.asyncio
async def test_midpoint_does_not_borrow_last_trade_time():
    now = datetime.now(UTC)
    q = SimpleNamespace(symbol="SPY", bid=499.99, ask=500.01, mid_price=500, timestamp=now.isoformat())
    pb = SimpleNamespace(get_quotes=AsyncMock(return_value=[q]))
    result = await adapter._resolve_spot_observation(pb, "SPY", "sample", now=now)
    assert result["price"] == 500 and result["event_time"] is None


@pytest.mark.parametrize("bid,ask", [(0, 100), (-1, 100), (100, 0), (float("nan"), 100), (None, 100)])
def test_invalid_book_cannot_publish_positive_midpoint(bid, ask):
    q = SimpleNamespace(bid=bid, ask=ask, mid_price=50, last=100, timestamp=datetime.now(UTC).isoformat())
    price, reason = adapter._public_quote_spot(q)
    assert price is None and reason == "invalid-book"


@pytest.mark.asyncio
async def test_ingestion_never_labels_mock_or_unknown_as_yahoo():
    from unittest.mock import Mock

    from services.ingestion_pipeline import IngestionPipeline

    db = Mock()
    feed = IngestionPipeline(db=db)
    await feed._insert_ticks([{"source": "mock"}, {}])
    rows = db.execute_write_bulk.call_args.args[2]
    assert [r[-2] for r in rows] == ["mock", "unknown"]
    await feed._insert_chains([{"source": "mock"}, {}])
    rows = db.execute_write_bulk.call_args.args[2]
    assert [r[-2] for r in rows] == ["mock", "unknown"]


@pytest.mark.asyncio
async def test_cache_filters_unverifiable_legacy_rows():
    from routes.market_data import _duckdb_fallback

    query = AsyncMock(return_value=[])
    with patch("services.duckdb_engine.db.query_async", query):
        assert await _duckdb_fallback("SPY") is None
    assert "data_source = 'public_api'" in query.call_args.args[0]


@pytest.mark.asyncio
async def test_public_dashboard_shares_sweep_and_never_falls_back(monkeypatch):
    import asyncio

    from routes import flowseeker as routes

    monkeypatch.setenv("FLOWW_MARKET_DATA_PROVIDER", "public")
    monkeypatch.setattr(routes, "_public_dashboard_cache", None)
    monkeypatch.setattr(routes, "_public_dashboard_lock", asyncio.Lock())
    rows = [["SPY", "contract", "call", 500, "2026-09-18", volume] for volume in [100, 2000, 3000]]
    sweep = AsyncMock(return_value={"rows": rows, "source": "public-scan", "coverage": {"max_age_s": 20}})
    monkeypatch.setattr(routes, "public_market_scan", sweep)
    results = await asyncio.gather(*(routes.market_scan(min_volume=1000, limit=1, force=False) for _ in range(3)))
    assert sweep.await_count == 1
    assert all(r["source"] == "public-scan" and r["count"] == 1 and r["truncated"] for r in results)
    assert all(r["cache_age_seconds"] >= 20 for r in results)
    results[0]["rows"][0][0] = "WRONG"
    refreshed = await routes.force_refresh_scan(min_volume=0, limit=3)
    assert refreshed["rows"][1][0] == "SPY" and sweep.await_count == 1
    monkeypatch.setattr(routes, "_public_dashboard_cache", None)
    sweep.side_effect = RuntimeError("Public unavailable")
    with pytest.raises(RuntimeError, match="Public unavailable"):
        await routes.market_scan(min_volume=0, limit=3, force=False)


def test_actual_heatmap_sanitization_keeps_readable_scope():
    from server import _sanitize
    from services.agent.display_map import map_cache_key

    query = {"expiries": 6, "mode": "day", "dte": None, "scalp": False, "withTaps": True, "maxStrikes": 80}
    result = _sanitize({"map_query": query, "stale": False})
    assert type(result["map_query"]["scalp"]) is bool
    assert type(result["map_query"]["withTaps"]) is bool
    assert result["stale"] is False
    assert map_cache_key("SPY", result["map_query"]) == "SPY:6:day:None:False:True:80"
