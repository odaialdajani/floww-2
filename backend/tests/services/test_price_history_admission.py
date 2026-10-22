"""History admission is observable; identical concurrent reads share one slot."""
import asyncio
import sys
from datetime import UTC, datetime
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
    args = dict(ticker="SPY",days=5,query_key=None,interval_minutes=30,include_metric_lines=False,contract_symbol=None,sessions="regular",
                include_envelopes=False,opening_minutes=60,tick_size=0.01,units="usd",entitlement="delayed-15m",max_delay_seconds=900)
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


# R21-03/04 route supplier: the history read can emit the committed admission
# envelopes alongside its own bars — every envelope computed from THIS read's
# recorded rows with explicit cursor (the read's own recorded receipt), and
# explicit instrument/capability/delay parameters carried from the request.
# Missing sources never become invented totals: they stay named unavailability
# in the exact contract vocabulary. Emmission is opt-in.
IB_BARS = [
    {"t":"2026-09-10T13:30:00Z","o":100.0,"h":101.0,"l":99.0,"c":100.5,"v":10},
    {"t":"2026-09-10T14:00:00Z","o":100.5,"h":102.0,"l":100.0,"c":101.5,"v":10},
]


class FixedUTCNow(datetime):
    """Deterministic route clock: the read's recorded receipt lands inside the
    fixture's own session (2026-09-10 10:35 NY), after the opening bars."""

    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 9, 10, 14, 35, tzinfo=UTC)


@pytest.mark.asyncio
async def test_envelopes_are_absent_unless_opted_in(isolated,monkeypatch):
    async def bars(*a,**kw):
        return [BAR]
    monkeypatch.setattr("services.public_budget.budget",PublicBudget())
    monkeypatch.setattr("services.public_api_adapter.fetch_bars_by_interval",bars)
    result = await read()
    assert result["price_status"]=="available"
    assert "envelopes" not in result


@pytest.mark.asyncio
async def test_opt_in_envelope_supply_admits_real_opening_and_names_every_missing_source(isolated,monkeypatch):
    async def bars(*a,**kw):
        return list(IB_BARS)
    monkeypatch.setattr("services.public_budget.budget",PublicBudget())
    monkeypatch.setattr("services.public_api_adapter.fetch_bars_by_interval",bars)
    monkeypatch.setattr(route,"datetime",FixedUTCNow)
    result = await read(include_envelopes=True)
    env = result["envelopes"]
    assert env["session"]["date"]=="2026-09-10"
    ib = env["initial_balance"]
    assert ib["status"]=="available"
    assert ib["bounds"]=={"low":99.0,"high":102.0}
    assert ib["coverage"]["complete"] is True
    assert ib["opening_minutes"]==60
    assert ib["instrument"]=={"ticker":"SPY","tick_size":0.01,"units":"usd","entitlement":"delayed-15m"}
    # The cursor is the read's own recorded receipt (10:35 NY), never a
    # candle-derived clock.
    assert ib["cursor"]==datetime(2026,9,10,14,35,tzinfo=UTC).timestamp()
    # No recorded option-flow tape exists at this source yet: the envelope
    # stays honestly unavailable in the committed vocabulary, never totals.
    assert env["flow"]["status"]=="unavailable"
    assert env["flow"]["reason"]=="no admitted rows for this flow bucket"
    assert env["naked"]["status"]=="not_requested"
    # No classified-size source rides this read: the capability stays
    # undeclared and the delta envelope refuses in the committed vocabulary.
    assert env["delta"]["status"]=="refused"
    assert env["delta"]["reason"]=="capability-not-declared: classified_sizes"
    assert env["darkpool"]["status"]=="unavailable"
    assert env["darkpool"]["reason"]=="no eligible dark-pool prints"


@pytest.mark.asyncio
async def test_opt_in_envelope_on_a_closed_day_refuses_instead_of_inventing(isolated,monkeypatch):
    async def bars(*a,**kw):
        return [{**BAR,"t":"2026-09-12T14:00:00Z"}]
    monkeypatch.setattr("services.public_budget.budget",PublicBudget())
    monkeypatch.setattr("services.public_api_adapter.fetch_bars_by_interval",bars)
    result = await read(include_envelopes=True)
    env = result["envelopes"]
    assert env["session"]["date"]=="2026-09-12"
    # The receipt's own live day carries no bars in this read: the supplier
    # never fabricates an initial balance for a day it cannot receipt-bind.
    ib = env["initial_balance"]
    assert ib["status"]=="not_requested"
    assert env["flow"]["status"] in {"refused","unavailable"}
    assert env["flow"]["status"]!="available"
