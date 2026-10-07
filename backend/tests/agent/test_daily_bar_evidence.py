"""Public daily-bar evidence is warmed by desktop reads, then copied by research."""
import asyncio
import importlib
from copy import deepcopy
from datetime import UTC, datetime, time, timedelta
from types import SimpleNamespace

import pytest

from services import public_api_adapter as adapter
from services.agent.access.horizon import ET, _calendar
from services.agent.reads import ResearchReads
from services.agent.volatility_reads import volatility_facts

NOW = datetime(2026, 10, 7, 6, tzinfo=UTC)


def seam():
    return importlib.import_module("services.agent.daily_bar_evidence")


def rows(end="2026-10-06", count=35):
    sessions = _calendar().sessions_window(end, -(count - 1))
    return [dict(date=datetime.combine(session.date(), time(), tzinfo=ET).isoformat(),
                 open=100 + i / 3, high=102 + i / 3, low=99 + i / 3,
                 close=101 + i / 3 + (i % 3) / 10, volume=1000,
                 session="regular") for i, session in enumerate(sessions)]


def payload(values=None):
    return {"symbol": "SPY", "regularMarket": {"bars": [dict(row, timestamp=row["date"]) for row in (rows() if values is None else values)]}}


@pytest.fixture
def evidence():
    module = seam()
    module.clear_daily_bar_evidence()
    yield module
    module.clear_daily_bar_evidence()


def test_completed_regular_window_has_20_returns_and_keeps_real_close_clock(evidence):
    result = evidence.build_daily_bar_evidence("SPY", rows(), now=NOW, received_at=NOW)
    assert result["source"] == "public_api"
    assert result["ticker"] == "SPY"
    assert result["interval"] == "1d"
    assert result["price_basis"] == "provider_reported"
    assert result["status"] == "degraded"
    assert result["adjustment_policy"] == "unknown"
    assert result["price_basis_verified"] is False
    assert "adjustment" in result["reason"].lower()
    assert len(result["bars"]) == 21
    assert result["complete"] is True
    assert result["bars"][-1]["date"] == "2026-10-06"
    assert result["event_time"] == "2026-10-06T20:00:00+00:00"
    assert result["received_at"] == NOW.isoformat()
    assert result["event_time"] != result["received_at"]


def test_early_close_is_the_exchange_close_not_midnight_or_receipt(evidence):
    now = datetime(2026, 11, 27, 19, tzinfo=UTC)
    result = evidence.build_daily_bar_evidence("SPY", rows("2026-11-27"), now=now, received_at=now)
    assert result["event_time"] == "2026-11-27T18:00:00+00:00"


@pytest.mark.parametrize("change", [
    "missing", "duplicate", "wrong_ticker", "wrong_source", "wrong_basis", "after", "open",
    "negative", "nan", "boolean", "incoherent", "fill", "bad_date", "non_midnight", "future", "oversized", "short",
])
def test_bad_daily_inputs_cannot_be_laundered_into_a_complete_window(evidence, change):
    values = rows()
    index = -5
    if change == "missing": values.pop(index)
    elif change == "duplicate": values.insert(index, deepcopy(values[index]))
    elif change == "wrong_ticker": values[index]["ticker"] = "QQQ"
    elif change == "wrong_source": values[index]["source"] = "other"
    elif change == "wrong_basis": values[index]["price_basis"] = "adjusted"
    elif change == "after": values[index]["session"] = "after"
    elif change == "open": values[index]["complete"] = False
    elif change == "negative": values[index]["close"] = -1
    elif change == "nan": values[index]["close"] = float("nan")
    elif change == "boolean": values[index]["close"] = True
    elif change == "incoherent": values[index]["high"] = values[index]["close"] - 1
    elif change == "fill": values[index]["leadingFill"] = True
    elif change == "bad_date": values[index]["date"] = "not-a-date"
    elif change == "non_midnight": values[index]["date"] = "2026-09-30T14:30:00-04:00"
    elif change == "future": values.append(dict(values[-1], date="2026-10-08T00:00:00-04:00"))
    elif change == "oversized": values = values * 15
    elif change == "short": values = values[-20:]
    assert evidence.build_daily_bar_evidence("SPY", values, now=NOW, received_at=NOW) is None


def test_current_open_session_bar_is_excluded_before_completed_window(evidence):
    now = datetime(2026, 10, 7, 16, tzinfo=UTC)
    values = rows()
    values.append(dict(values[-1], date="2026-10-07T00:00:00-04:00"))
    result = evidence.build_daily_bar_evidence("SPY", values, now=now, received_at=now)
    assert result["bars"][-1]["date"] == "2026-10-06"
    assert len(result["bars"]) == 21


def test_old_closed_window_remains_stale(evidence):
    result = evidence.build_daily_bar_evidence("SPY", rows("2026-10-05"), now=NOW, received_at=NOW)
    assert result["status"] == "stale"
    assert result["event_time"] == "2026-10-05T20:00:00+00:00"


def test_peek_copies_without_fetch_or_auth_and_cache_is_bounded(evidence, monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("research copy attempted provider access")
    monkeypatch.setattr(adapter, "_get_broker", forbidden)
    evidence.cache_public_daily_bars("SPY", rows(), now=NOW, received_at=NOW)
    first = evidence.peek_daily_bars("SPY")
    first["bars"][-1]["close"] = 0
    assert evidence.peek_daily_bars("SPY")["bars"][-1]["close"] > 0
    assert evidence.peek_daily_bars("QQQ") is None
    for i in range(129):
        evidence.cache_public_daily_bars(f"T{i}", rows(), now=NOW, received_at=NOW)
    assert evidence.peek_daily_bars("SPY") is None
    assert evidence.peek_daily_bars("T128") is not None
    assert len(evidence._CACHE) <= 128


def test_public_reported_basis_is_degraded_and_not_labeled_unadjusted(evidence):
    envelope = evidence.build_daily_bar_evidence("SPY", rows(), now=NOW, received_at=NOW)
    facts, gaps = volatility_facts([], [], envelope, ticker="SPY", snapshot_id="saved", horizon="all", now=NOW)
    realized = [fact for fact in facts if fact["metric"].startswith("Realized")]
    assert len(realized) == 3
    assert all(fact["status"] == "degraded" for fact in realized)
    assert all(fact["event_time"] == "2026-10-06T20:00:00+00:00" for fact in realized)
    assert all(fact["source"] == "public_api" for fact in realized)
    assert all("unadjusted" not in (fact["reason"] or "") for fact in realized)
    assert "adjustment" in realized[0]["reason"].lower()
    forged = dict(envelope, source="unknown", status="ok")
    assert not volatility_facts([], [], forged, ticker="SPY", snapshot_id="saved", horizon="all", now=NOW)[0]


@pytest.mark.asyncio
async def test_research_consumes_copy_without_ensure_or_provider(evidence, monkeypatch):
    evidence.cache_public_daily_bars("SPY", rows(), now=NOW, received_at=NOW)
    async def forbidden(*args, **kwargs):
        raise AssertionError("research must not warm or fetch daily bars")
    monkeypatch.setattr(evidence, "ensure_public_daily_bars", forbidden)
    monkeypatch.setattr(adapter, "_get_broker", forbidden)
    reads = ResearchReads(lambda *a: {}, lambda *a: None, lambda *a: [], read_daily_bars=evidence.peek_daily_bars)
    snapshot = await reads.snapshot("SPY", "all", now=NOW)
    assert any(f["metric"] == "Realized daily close volatility" for f in snapshot["facts"])


class Budget:
    def __init__(self, refused=False):
        self.calls = []
        self.releases = 0
        self.refused = refused
    async def acquire_n(self, count, provider):
        self.calls.append((count, provider))
        if self.refused:
            raise adapter._public_budget.BudgetExhausted("refused")
    def release(self): self.releases += 1
    def record_ok(self, *args, **kwargs): pass


class Broker:
    def __init__(self, raw=None, failed=False):
        self.raw = payload() if raw is None else raw
        self.calls = []
        self.failed = failed
    def get_trading_account(self):
        return SimpleNamespace(account_id="test-account")
    async def get_bars(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        await asyncio.sleep(0)
        if self.failed: raise TimeoutError("temporary")
        return self.raw


def install(monkeypatch, broker, budget):
    monkeypatch.setattr(adapter, "BROKER", broker)
    monkeypatch.setattr(adapter._public_budget, "budget", budget)
    async def get(): return broker
    monkeypatch.setattr(adapter, "_get_broker", get)


@pytest.mark.asyncio
async def test_desktop_warm_is_single_flight_shared_budget_and_reused_until_next_close(evidence, monkeypatch):
    broker, budget = Broker(), Budget()
    install(monkeypatch, broker, budget)
    values = await asyncio.gather(*(evidence.ensure_public_daily_bars("SPY", now=NOW) for _ in range(8)))
    assert all(value and len(value["bars"]) == 21 for value in values)
    assert len(broker.calls) == 1
    assert budget.calls == [(1, "api.public.com")]
    assert budget.releases == 1
    args, kwargs = broker.calls[0]
    assert args[:2] == ("SPY", "YEAR")
    assert kwargs["aggregation"] == "ONE_DAY"
    assert kwargs["trading_session_toggle"] == "REGULAR_HOURS"
    before_close = datetime(2026, 10, 7, 19, 59, tzinfo=UTC)
    assert await evidence.ensure_public_daily_bars("SPY", now=before_close)
    assert len(broker.calls) == 1
    broker.raw = payload(rows("2026-10-07"))
    after_close = datetime(2026, 10, 7, 20, 1, tzinfo=UTC)
    latest = await evidence.ensure_public_daily_bars("SPY", now=after_close)
    assert len(broker.calls) == 2
    assert latest["bars"][-1]["date"] == "2026-10-07"


@pytest.mark.asyncio
async def test_refused_warm_never_authenticates_or_calls_provider(evidence, monkeypatch):
    budget = Budget(refused=True)
    monkeypatch.setattr(adapter, "BROKER", None)
    monkeypatch.setattr(adapter._public_budget, "budget", budget)
    async def forbidden(): raise AssertionError("refusal must precede auth")
    monkeypatch.setattr(adapter, "_get_broker", forbidden)
    assert await evidence.ensure_public_daily_bars("SPY", now=NOW) is None
    assert budget.calls == [(3, "api.public.com")]
    assert budget.releases == 0


@pytest.mark.asyncio
async def test_failed_warm_has_negative_cooldown_and_keeps_saved_clock(evidence, monkeypatch):
    broker, budget = Broker(failed=True), Budget()
    install(monkeypatch, broker, budget)
    evidence.cache_public_daily_bars("SPY", rows("2026-10-05"), now=NOW, received_at=NOW)
    old = evidence.peek_daily_bars("SPY")
    assert await evidence.ensure_public_daily_bars("SPY", now=NOW) == old
    assert await evidence.ensure_public_daily_bars("SPY", now=NOW + timedelta(seconds=10)) == old
    assert len(broker.calls) == 1
    assert evidence.peek_daily_bars("SPY")["event_time"] == "2026-10-05T20:00:00+00:00"
    assert budget.releases == 1


@pytest.mark.asyncio
async def test_cancellation_releases_budget_and_allows_retry(evidence, monkeypatch):
    started = asyncio.Event()
    broker, budget = Broker(), Budget()
    install(monkeypatch, broker, budget)
    original = broker.get_bars
    async def wait(*args, **kwargs):
        started.set()
        await asyncio.Future()
    broker.get_bars = wait
    task = asyncio.create_task(evidence.ensure_public_daily_bars("SPY", now=NOW))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    assert budget.releases == 1
    broker.get_bars = original
    assert await evidence.ensure_public_daily_bars("SPY", now=NOW)
    assert budget.releases == 2


@pytest.mark.asyncio
async def test_existing_daily_public_read_populates_evidence_but_intraday_does_not(evidence, monkeypatch):
    broker, budget = Broker(), Budget()
    install(monkeypatch, broker, budget)
    monkeypatch.setattr(evidence, "_utc_now", lambda: NOW)
    await adapter.fetch_bars_from_public_api("SPY", timeframe="1Min", limit=35)
    assert evidence.peek_daily_bars("SPY") is None
    await adapter.fetch_bars_from_public_api("SPY", timeframe="1Day", limit=5)
    assert len(evidence.peek_daily_bars("SPY")["bars"]) == 21
    assert evidence.peek_daily_bars("SPY")["price_basis"] == "provider_reported"


@pytest.mark.asyncio
async def test_daily_producer_cannot_hide_duplicate_raw_rows(evidence, monkeypatch):
    values = rows()
    values.insert(-5, deepcopy(values[-5]))
    broker, budget = Broker(payload(values)), Budget()
    install(monkeypatch, broker, budget)
    monkeypatch.setattr(evidence, "_utc_now", lambda: NOW)
    await adapter.fetch_bars_from_public_api("SPY", timeframe="1Day", limit=35)
    assert evidence.peek_daily_bars("SPY") is None


@pytest.mark.asyncio
async def test_interval_daily_read_populates_copy_but_unknown_session_never_does(evidence, monkeypatch):
    broker, budget = Broker(), Budget()
    install(monkeypatch, broker, budget)
    monkeypatch.setattr(evidence, "_utc_now", lambda: NOW)
    await adapter.fetch_bars_by_interval("SPY", interval="daily")
    assert evidence.peek_daily_bars("SPY")
    evidence.clear_daily_bar_evidence()
    broker.raw = {"mysteryMarket": {"bars": rows()}}
    await adapter.fetch_bars_by_interval("SPY", interval="daily", sessions="all")
    assert evidence.peek_daily_bars("SPY") is None


@pytest.mark.asyncio
async def test_wrong_public_payload_symbol_is_not_relabelled(evidence, monkeypatch):
    wrong = payload()
    wrong["symbol"] = "QQQ"
    broker, budget = Broker(wrong), Budget()
    install(monkeypatch, broker, budget)
    assert await evidence.ensure_public_daily_bars("SPY", now=NOW) is None
    assert evidence.peek_daily_bars("SPY") is None


@pytest.mark.parametrize("clock", [None, "not-a-time", "2026-10-06T20:00:01+00:00", "2026-10-06T19:59:59+00:00"])
def test_provider_reported_basis_requires_exact_final_completed_close_clock(evidence, clock):
    envelope = evidence.build_daily_bar_evidence("SPY", rows(), now=NOW, received_at=NOW)
    envelope["event_time"] = clock
    facts, gaps = volatility_facts([], [], envelope, ticker="SPY", snapshot_id="saved", horizon="all", now=NOW)
    assert not any(fact["metric"].startswith("Realized") for fact in facts)
    assert any("Realized volatility is unavailable" in gap for gap in gaps)


def test_top_level_public_leading_fill_is_not_completed_market_history(evidence):
    raw = payload()
    raw["leadingFill"] = {"timestamp": rows()[0]["date"], "close": rows()[0]["close"]}
    assert evidence.cache_public_daily_payload("SPY", raw, now=NOW, received_at=NOW) is None
    assert evidence.peek_daily_bars("SPY") is None
