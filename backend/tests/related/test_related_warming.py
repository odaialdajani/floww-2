import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from test_related_price_series import NOW, payload
from test_related_tickers import cat, registry

from routes import related_tickers as routes
from services.public_budget import BudgetExhausted
from services.related_price_series import RelatedSeriesStore, validate_daily_payload, warm_daily_series


@pytest.mark.asyncio
async def test_cache_warm_uses_budget_before_provider_and_coalesces_same_symbol(monkeypatch, tmp_path):
    from services import public_api_adapter as adapter
    from services import public_budget

    calls = []

    class Budget:
        async def acquire_n(self, n, host):
            calls.append(("admit", n))

        def release(self):
            calls.append(("release",))

        def record_ok(self, *args, **kwargs):
            calls.append(("ok",))

    class Broker:
        _token_expires_at = 10**12

        async def get_bars(self, symbol, period, **kwargs):
            calls.append(("bars", symbol, period, kwargs))
            await asyncio.sleep(0.01)
            return payload(symbol)

    broker = Broker()

    async def get_broker():
        calls.append(("broker",))
        return broker

    monkeypatch.setattr(adapter, "BROKER", broker)
    monkeypatch.setattr(adapter, "_get_broker", get_broker)
    monkeypatch.setattr(public_budget, "budget", Budget())
    store = RelatedSeriesStore(tmp_path / "cache.sqlite3")
    one, two = await asyncio.gather(warm_daily_series("AAA", store, now=NOW), warm_daily_series("AAA", store, now=NOW))
    assert {one["status"], two["status"]} == {"fetched", "cached"}
    assert len([call for call in calls if call[0] == "bars"]) == 1
    assert calls[0] == ("admit", 1) and calls[1] == ("broker",)
    bar = next(call for call in calls if call[0] == "bars")
    assert bar[2] == "YEAR" and bar[3] == {"aggregation": "ONE_DAY", "trading_session_toggle": "REGULAR_HOURS"}
    store.close()


@pytest.mark.asyncio
async def test_denied_budget_does_not_authenticate_or_read_a_provider(monkeypatch, tmp_path):
    from services import public_api_adapter as adapter
    from services import public_budget

    called = []

    class Budget:
        async def acquire_n(self, *args):
            raise BudgetExhausted(reason="host_cooldown", retry_after=45)

        def release(self):
            raise AssertionError("No held admission")

    async def forbidden():
        called.append(True)
        raise AssertionError("No authentication on refused admission")

    monkeypatch.setattr(adapter, "BROKER", None)
    monkeypatch.setattr(adapter, "_get_broker", forbidden)
    monkeypatch.setattr(public_budget, "budget", Budget())
    store = RelatedSeriesStore(tmp_path / "cache.sqlite3")
    result = await warm_daily_series("AAA", store, now=NOW)
    assert result["status"] == "deferred" and result["retry_after"] == 45 and not called
    again = await warm_daily_series("AAA", store, now=NOW + timedelta(seconds=1))
    assert again["reason"] == "retry_cooldown"
    store.close()


@pytest.mark.asyncio
async def test_bounded_cursor_covers_all_names_and_persists_after_restart(monkeypatch, tmp_path):
    path = tmp_path / "cache.sqlite3"
    store = RelatedSeriesStore(path)
    seen = []
    names = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III", "JJJ"]

    async def fake(symbol, store, **kwargs):
        seen.append(symbol)
        store.save(validate_daily_payload(symbol, payload(symbol), now=NOW, received_at=NOW), now=NOW)
        return {"symbol": symbol, "status": "fetched", "reserved_calls": 1}

    monkeypatch.setattr(routes, "warm_daily_series", fake)
    monkeypatch.setattr(routes, "provider_read_cost", lambda: 1)
    first = await routes.warm_snapshot(
        "AAA", scope="all", batch_size=8, store=store, catalog=cat(names), now=NOW, registry_path=registry(tmp_path)
    )
    assert first["batch"]["attempted"] == 8 and first["batch"]["reserved_calls"] == 8 and first["batch"]["cursor"] == 8
    store.close()
    store = RelatedSeriesStore(path)
    second = await routes.warm_snapshot(
        "AAA", scope="all", batch_size=8, store=store, catalog=cat(names), now=NOW, registry_path=registry(tmp_path)
    )
    assert second["batch"]["attempted"] == 2 and second["batch"]["done"] is True
    assert len(seen) == len(set(seen)) == 10 and set(seen) == set(names)
    assert second["coverage"]["eligible"] == 9 and second["coverage"]["checked"] == 9
    assert second["coverage"]["complete"] is False
    store.close()


@pytest.mark.asyncio
async def test_two_panes_do_not_duplicate_same_scope_candidate_calls(monkeypatch, tmp_path):
    store = RelatedSeriesStore(tmp_path / "cache.sqlite3")
    seen = []

    async def fake(symbol, store, **kwargs):
        seen.append(symbol)
        await asyncio.sleep(0.005)
        store.save(validate_daily_payload(symbol, payload(symbol), now=NOW, received_at=NOW), now=NOW)
        return {"symbol": symbol, "status": "fetched", "reserved_calls": 1}

    monkeypatch.setattr(routes, "warm_daily_series", fake)
    monkeypatch.setattr(routes, "provider_read_cost", lambda: 1)
    arguments = dict(
        scope="all",
        batch_size=1,
        store=store,
        catalog=cat(["AAA", "BBB", "CCC"]),
        now=NOW,
        registry_path=registry(tmp_path),
    )
    await asyncio.gather(routes.warm_snapshot("AAA", **arguments), routes.warm_snapshot("AAA", **arguments))
    assert seen == ["AAA", "BBB"]
    store.close()


@pytest.mark.asyncio
async def test_get_is_copy_only_and_post_limits_are_validated_without_server_startup(monkeypatch, tmp_path):
    store = RelatedSeriesStore(tmp_path / "read.sqlite3")
    monkeypatch.setattr(routes, "_store", lambda: store)
    monkeypatch.setattr(routes, "_catalog_snapshot", lambda: cat(["AAA", "BBB"]))
    monkeypatch.setattr(routes, "_REGISTRY", registry(tmp_path))

    async def forbidden(*args, **kwargs):
        raise AssertionError("GET must not warm")

    monkeypatch.setattr(routes, "warm_daily_series", forbidden)
    app = FastAPI()
    app.include_router(routes.router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/related/AAA?window=30&scope=all")
        assert response.status_code == 200 and response.json()["coverage"]["eligible"] == 1
        assert not (tmp_path / "read.sqlite3").exists()
        response = await client.post("/api/related/AAA/warm", json={"window": 30, "scope": "all", "batch_size": 9})
        assert response.status_code == 422
        response = await client.get("/api/related/AAA?window=20")
        assert response.status_code == 422
    store.close()


def test_a_preclose_request_received_after_close_never_admits_its_still_open_bar():
    raw = payload()
    raw["regularMarket"]["bars"].append({"date": "2026-10-07", "open": 100, "high": 102, "low": 99, "close": 101})
    start = NOW.replace(hour=19, minute=59)
    receipt = NOW.replace(hour=20, minute=1)
    result = validate_daily_payload("AAA", raw, now=receipt, received_at=receipt, requested_at=start)
    assert result["bars"][-1]["date"] == "2026-10-06" and result["excluded"]["unclosed"] == 1


@pytest.mark.asyncio
async def test_read_only_storage_refuses_warming_before_any_provider_work(monkeypatch, tmp_path):
    store = RelatedSeriesStore(tmp_path / "blocked.sqlite3")

    def blocked(*args, **kwargs):
        raise PermissionError("blocked")

    async def forbidden(*args, **kwargs):
        raise AssertionError("No upstream work without progress storage")

    monkeypatch.setattr(store, "advance", blocked)
    monkeypatch.setattr(routes, "warm_daily_series", forbidden)
    result = await routes.warm_snapshot(
        "AAA", scope="all", store=store, catalog=cat(["AAA", "BBB"]), now=NOW, registry_path=registry(tmp_path)
    )
    assert result["batch"]["attempted"] == 0 and result["batch"]["reason"] == "cache_storage_unavailable"
    store.close()


@pytest.mark.asyncio
async def test_unknown_scope_warm_still_returns_a_bounded_batch_shape(tmp_path):
    result = await routes.warm_snapshot(
        "^NDX", scope="all", store=RelatedSeriesStore(":memory:"), catalog=cat(["QQQ", "SPY"]), now=NOW
    )
    assert result["status"] == "unavailable" and result["batch"]["attempted"] == 0 and result["batch"]["done"] is True


@pytest.mark.asyncio
async def test_a_late_auth_cost_change_never_exceeds_remaining_batch_admission(monkeypatch, tmp_path):
    from services import public_api_adapter as adapter
    from services import public_budget

    calls = []

    class Budget:
        async def acquire_n(self, *args):
            calls.append("admit")

        def release(self):
            calls.append("release")

    monkeypatch.setattr(adapter, "BROKER", None)
    monkeypatch.setattr(public_budget, "budget", Budget())
    store = RelatedSeriesStore(tmp_path / "cache.sqlite3")
    result = await warm_daily_series("AAA", store, now=NOW, max_reserved_calls=1)
    assert (
        result["status"] == "deferred"
        and result["reason"] == "batch_call_limit"
        and result["reserved_calls"] == 0
        and not calls
    )
    store.close()


@pytest.mark.asyncio
async def test_cached_expired_broker_refresh_retry_is_fully_reserved(monkeypatch, tmp_path):
    from services import public_api_adapter as adapter
    from services import public_budget
    from services.public_api import PublicBroker

    outbound = []
    admissions = []

    class Budget:
        async def acquire_n(self, n, host):
            admissions.append(n)

        def release(self):
            pass

        def record_ok(self, *args, **kwargs):
            pass

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return payload("AAA")

    class Client:
        async def get(self, *args, **kwargs):
            outbound.append("bars")
            return Response()

    broker = PublicBroker.__new__(PublicBroker)
    broker._access_token = "test-token"
    broker._token_expires_at = 0
    broker._client = Client()

    async def auth(*args, **kwargs):
        outbound.append("auth")
        if outbound.count("auth") == 1:
            raise RuntimeError("temporary authentication failure")
        broker._access_token = "test-token"
        broker._token_expires_at = 10**12

    broker.auth = auth
    monkeypatch.setattr(adapter, "BROKER", broker)
    monkeypatch.setattr(public_budget, "budget", Budget())
    store = RelatedSeriesStore(tmp_path / "cache.sqlite3")
    result = await warm_daily_series("AAA", store, now=NOW)
    assert outbound == ["auth", "auth", "bars"] and result["status"] == "fetched"
    assert result["reserved_calls"] >= len(outbound) and admissions[0] >= len(outbound)
    store.close()


@pytest.mark.asyncio
async def test_failure_retry_delay_begins_when_the_provider_read_finishes(monkeypatch, tmp_path):
    from datetime import datetime as RealDateTime

    from services import public_api_adapter as adapter
    from services import public_budget
    from services import related_price_series as module

    clock = [NOW]
    calls = []

    class Clock(RealDateTime):
        @classmethod
        def now(cls, tz=None):
            return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)

    class Budget:
        async def acquire_n(self, *args):
            pass

        def release(self):
            pass

    class Broker:
        _token_expires_at = 10**12

        async def get_bars(self, *args, **kwargs):
            calls.append(True)
            clock[0] += timedelta(seconds=60)
            raise RuntimeError("read failed")

    broker = Broker()

    async def get_broker():
        return broker

    monkeypatch.setattr(module, "datetime", Clock)
    monkeypatch.setattr(adapter, "BROKER", broker)
    monkeypatch.setattr(adapter, "_get_broker", get_broker)
    monkeypatch.setattr(public_budget, "budget", Budget())
    store = RelatedSeriesStore(tmp_path / "cache.sqlite3")
    first = await warm_daily_series("AAA", store)
    second = await warm_daily_series("AAA", store)
    assert first["status"] == "failed" and second["status"] == "deferred" and second["reason"] == "retry_cooldown"
    assert len(calls) == 1
    store.close()
