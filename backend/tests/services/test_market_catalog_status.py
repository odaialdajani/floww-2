"""Feed counters read completed observations without requesting more data."""
import time
from datetime import UTC, datetime

import pytest

from routes import market_catalog as routes
from services import market_catalog as catalog
from services import public_scanner as scanner
from services.meta_observability import provider_monitor


def directory(monkeypatch):
    now = time.time()
    monkeypatch.setattr(catalog, "_cache", {"asof": datetime.now(UTC).isoformat(), "instruments": [
        {"symbol": "SPY", "options": True, "sector": None},
        {"symbol": "AMD", "options": True, "sector": "Technology"},
        {"symbol": "NOPT", "options": False, "sector": None},
    ]})
    monkeypatch.setattr(catalog, "_loaded_at", time.monotonic())
    monkeypatch.setattr(catalog, "_retry_at", 0)
    monkeypatch.setattr(provider_monitor, "get_health", lambda: {"providers": {"public_api": {
        "seconds_since_last_success": 4, "window_calls": 5, "consecutive_failures": 0}}})
    return now


@pytest.mark.asyncio
async def test_counted_reads_are_distinct_from_listed_names_and_age_without_scanning(monkeypatch):
    now = directory(monkeypatch)
    monkeypatch.setattr(scanner, "_last_completed_view", {"rows": [], "coverage": {
        "universe": 2, "fresh": 2, "received_at_by_ticker": {"SPY": now - 5, "AMD": now - 400},
        "fresh_window_seconds": 300, "checked_at": now - 5, "attempted": 2, "latest_failed": 0,
        "scope_kind": "provider_option_enabled", "progress": {"attempted_in_pass": 2, "succeeded_in_pass": 2}}})
    async def forbidden(*args, **kwargs):
        raise AssertionError("Status must not start provider work")
    monkeypatch.setattr(catalog, "get_catalog", forbidden)
    monkeypatch.setattr(catalog, "_fetch_instruments", forbidden)
    monkeypatch.setattr(scanner, "scan_next", forbidden)
    result = await routes.market_status()
    assert result["directory"]["total"] == 3
    assert result["directory"]["optionable_total"] == 2
    assert result["directory"]["sectors"] == ["Technology"]
    assert result["directory"]["sector_classified"] == 1
    assert result["options"]["received_recently"] == 1
    assert result["options"]["attempted"] == 2
    assert result["options"]["complete_realtime_market"] is False
    assert 3 <= time.time() - result["provider"]["last_success_at"] <= 5
    assert scanner._last_completed_view["coverage"]["fresh"] == 2


@pytest.mark.asyncio
async def test_no_completed_scan_or_directory_is_unknown_instead_of_zero(monkeypatch):
    monkeypatch.setattr(catalog, "_cache", None)
    monkeypatch.setattr(scanner, "_last_completed_view", None)
    monkeypatch.setattr(provider_monitor, "get_health", lambda: {"providers": {}})
    result = await routes.market_status()
    assert result["status"] == "not_checked"
    assert result["directory"]["total"] is None
    assert result["directory"]["optionable_total"] is None
    assert result["options"]["received_recently"] is None
    assert result["provider"]["last_success_at"] is None


@pytest.mark.asyncio
async def test_empty_successful_receipts_are_zero_while_unknown_receipts_are_unavailable(monkeypatch):
    now = directory(monkeypatch)
    monkeypatch.setattr(scanner, "_last_completed_view", {"rows": [], "coverage": {
        "fresh": 0, "received_at_by_ticker": {}, "fresh_window_seconds": 300, "checked_at": now}})
    assert (await routes.market_status())["options"]["received_recently"] == 0
    monkeypatch.setattr(scanner, "peek_scan_view", lambda **kwargs: {"coverage": {
        "fresh": True, "received_at_by_ticker": {}, "fresh_window_seconds": 300, "checked_at": now}})
    assert (await routes.market_status())["options"]["received_recently"] is None


def test_catalogue_preserves_only_supplied_sector_labels():
    rows = catalog.parse_instruments([
        {"instrument": {"symbol": "AMD", "type": "EQUITY"}, "optionTrading": "BUY_AND_SELL", "sector": " Technology "},
        {"instrument": {"symbol": "SPY", "type": "EQUITY"}, "optionTrading": "BUY_AND_SELL"},
        {"instrument": {"symbol": "NVDA", "type": "EQUITY"}, "sector": True},
    ])
    assert {row["symbol"]: row["sector"] for row in rows} == {"AMD": "Technology", "SPY": None, "NVDA": None}


@pytest.mark.asyncio
async def test_catalogue_filter_keeps_full_count_and_matches_only_supplied_sector(monkeypatch):
    async def fake(*, refresh=False):
        return {"total": 3, "optionable_total": 2, "instruments": [
            {"symbol": "AMD", "options": True, "sector": "Technology"},
            {"symbol": "SPY", "options": True, "sector": None},
            {"symbol": "BOND", "options": False, "sector": "Finance"}]}
    monkeypatch.setattr(catalog, "_catalog_snapshot", fake)
    result = await routes.catalog_page(page=1, limit=30, q="", options_only=True, sector="Technology")
    assert result["total"] == 3 and result["matches"] == 1
    assert [row["symbol"] for row in result["instruments"]] == ["AMD"]


@pytest.mark.asyncio
async def test_large_directory_routes_copy_only_the_page_and_share_refresh(monkeypatch):
    from unittest.mock import AsyncMock

    from routes import market_data

    records = [
        {"instrument": {"symbol": f"X{index:05}", "type": "EQUITY"},
         "optionTrading": "BUY_AND_SELL" if index % 2 else "DISABLED"}
        for index in range(30_000)
    ]
    fetch = AsyncMock(return_value=records)
    monkeypatch.setattr(catalog, "_fetch_instruments", fetch)
    monkeypatch.setattr(catalog, "_cache", None)
    monkeypatch.setattr(catalog, "_loaded_at", 0.0)
    monkeypatch.setattr(catalog, "_retry_at", 0.0)
    deepcopy = catalog.copy.deepcopy
    copy_sizes = []

    def tracked_copy(value):
        if isinstance(value, dict) and "instruments" in value:
            copy_sizes.append(len(value["instruments"]))
        elif isinstance(value, list):
            copy_sizes.append(len(value))
        return deepcopy(value)

    monkeypatch.setattr(catalog.copy, "deepcopy", tracked_copy)
    page = await routes.catalog_page(page=2, limit=100, q=" x ", options_only=True, sector="")
    symbols = await market_data.list_all_tickers(page=3, limit=100, refresh=False)
    assert page["total"] == symbols["total"] == 30_000
    assert page["matches"] == page["optionable_total"] == 15_000
    assert page["asof"] == symbols["asof"] and page["has_more"] and symbols["has_more"]
    assert page["instruments"][0]["symbol"] == "X00201"
    assert symbols["tickers"][0] == "X00200" and len(symbols["tickers"]) == 100
    assert max(copy_sizes, default=0) <= 100
    fetch.assert_awaited_once()

    page["instruments"][0]["symbol"] = "mutated"
    again = await routes.catalog_page(page=2, limit=100, q="X", options_only=True, sector="")
    assert again["instruments"][0]["symbol"] == "X00201"
