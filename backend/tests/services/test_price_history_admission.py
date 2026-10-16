"""History admission is observable; identical concurrent reads share one slot."""
import asyncio
import sys
from types import SimpleNamespace

import pytest

from routes import price_history as route
from services.public_budget import BudgetExhausted, PublicBudget

BAR = {"t":"2026-10-06T14:00:00Z","o":100,"h":102,"l":99,"c":101,"v":10}


@pytest.fixture
def isolated(monkeypatch):
    monkeypatch.setitem(sys.modules,"services.duckdb_engine",SimpleNamespace(db=object()))
    monkeypatch.setattr(route,"recording_summary",lambda *a: {"status":"available","durable":False,"count":0})
    monkeypatch.setattr(route,"read_snapshots",lambda *a: [])


async def read(**changes):
    args = dict(ticker="SPY",days=5,query_key=None,interval_minutes=30,include_metric_lines=False,contract_symbol=None,sessions="regular")
    return await route.price_history(**{**args,**changes})


@pytest.mark.asyncio
async def test_same_read_burst_shares_one_admission_instead_of_fabricating_unavailable(isolated,monkeypatch):
    budget = PublicBudget(max_inflight=1)
    calls=[]
    async def bars(ticker,**kwargs):
        calls.append((ticker,kwargs))
        await asyncio.sleep(.02)
        return [BAR]
    monkeypatch.setattr("services.public_budget.budget",budget)
    monkeypatch.setattr("services.public_api_adapter.fetch_bars_by_interval",bars)
    responses = await asyncio.gather(*(read() for _ in range(6)))
    assert all(r["price_status"]=="available" for r in responses)
    assert len(calls)==1
    assert budget.total_limited==0
    assert budget._inflight==0


@pytest.mark.asyncio
@pytest.mark.parametrize("reason",["inflight_cap","host_cooldown","token_bucket"])
async def test_budget_refusal_names_its_actual_reason_and_never_calls_provider(isolated,monkeypatch,reason):
    class Refusal:
        async def acquire(self,host):
            raise BudgetExhausted(retry_after=7,reason=reason)
        def release(self):
            raise AssertionError("Never release an unacquired slot")
    async def no_provider(*a,**kw):
        raise AssertionError("Must not fetch after refusal")
    monkeypatch.setattr("services.public_budget.budget",Refusal())
    monkeypatch.setattr("services.public_api_adapter.fetch_bars_by_interval",no_provider)
    result = await read()
    assert result["price_status"]=="unavailable"
    assert result["price_failure"]=={"reason":reason,"retry_after_seconds":7}
    assert result["prices_received_at"] is None


@pytest.mark.asyncio
async def test_provider_unavailable_is_not_budget_refusal_and_is_not_cached(isolated,monkeypatch):
    budget = PublicBudget()
    calls=[]
    async def bars(*a,**kw):
        calls.append(1)
        return None if len(calls)==1 else [BAR]
    monkeypatch.setattr("services.public_budget.budget",budget)
    monkeypatch.setattr("services.public_api_adapter.fetch_bars_by_interval",bars)
    failed = await read()
    assert failed["price_failure"]["reason"]=="provider_unavailable"
    assert (await read())["price_status"]=="available"
    assert len(calls)==2


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_release_running_provider_slot(isolated,monkeypatch):
    budget = PublicBudget(max_inflight=1)
    entered,finish = asyncio.Event(),asyncio.Event()
    async def bars(*a,**kw):
        entered.set()
        await finish.wait()
        return [BAR]
    monkeypatch.setattr("services.public_budget.budget",budget)
    monkeypatch.setattr("services.public_api_adapter.fetch_bars_by_interval",bars)
    first = asyncio.create_task(read())
    await entered.wait()
    second = asyncio.create_task(read())
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    try:
        assert budget._inflight==1
    finally:
        finish.set()
    assert (await second)["price_status"]=="available"
    assert budget._inflight==0


@pytest.mark.asyncio
async def test_distinct_sessions_and_tickers_do_not_share_reads(isolated,monkeypatch):
    budget = PublicBudget()
    calls=[]
    async def bars(ticker,**kw):
        calls.append((ticker,kw["sessions"]))
        await asyncio.sleep(.01)
        return [BAR]
    monkeypatch.setattr("services.public_budget.budget",budget)
    monkeypatch.setattr("services.public_api_adapter.fetch_bars_by_interval",bars)
    await asyncio.gather(read(),read(ticker="QQQ"),read(sessions="all"))
    assert set(calls)=={("SPY","regular"),("QQQ","regular"),("SPY","all")}


@pytest.mark.asyncio
async def test_bad_provider_bars_have_a_distinct_failure(isolated,monkeypatch):
    async def bars(*a,**kw):
        return [{**BAR,"o":None}]
    monkeypatch.setattr("services.public_budget.budget",PublicBudget())
    monkeypatch.setattr("services.public_api_adapter.fetch_bars_by_interval",bars)
    result = await read()
    assert result["price_failure"]["reason"]=="invalid_price_bars"
    assert result["frames"]==[]
