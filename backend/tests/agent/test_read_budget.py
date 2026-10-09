import asyncio
import time
import uuid
from datetime import UTC, datetime

import pytest

pytest.importorskip("mongomock_motor", reason="mongo mock unavailable in this env")
from mongomock_motor import AsyncMongoMockClient

from services.agent.read_budget import ReadBudget, ReadDenied, budget_scope
from services.agent.reads import ResearchReads
from services.agent.repository import AgentRepository
from services.agent.research import ResearchService


def identity():
    return f"{int(time.time() * 1000)}-{uuid.uuid4()}"


@pytest.mark.asyncio
async def test_ninth_read_never_enters_and_failures_remain_charged():
    saved, calls = [], []

    async def save(value):
        saved.append(value)
        return True

    budget = ReadBudget(save=save, timeout=10)

    def callback():
        calls.append(1)
        raise ValueError("private detail")

    for _ in range(8):
        with pytest.raises(ValueError):
            await budget.sync("context", "SPY", callback)
    with pytest.raises(ReadDenied):
        await budget.sync("context", "SPY", callback)
    state = budget.close()
    assert len(calls) == state["started"] == state["reserved"] == 8
    assert len(state["denied"]) == 1
    assert all(a["outcome"] == "error" for a in state["attempts"])
    assert "private detail" not in str(saved)
    assert saved[0]["reserved"] == 1 and saved[0]["started"] == 0


@pytest.mark.asyncio
async def test_service_three_ticker_history_uses_context_and_history_not_unrequested_alerts():
    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    calls = []

    def chain(ticker, depth):
        calls.append(("context", ticker))
        return {"spot": 100, "event_time": datetime.now(UTC).isoformat(), "contracts": []}

    def alerts(ticker):
        calls.append(("alerts", ticker))
        return []

    service = ResearchService(repo, ResearchReads(chain, lambda *a: None, alerts))
    spec = {
        "ticker": "XLK",
        "tickers": ["XLK", "XLF", "XLE"],
        "horizon": "all",
        "screen": {},
        "context_conflict": False,
        "question": "What changed since yesterday for XLK XLF XLE?",
    }
    turn = await service.ask("alice", identity(), spec)
    await asyncio.gather(*list(service.tasks.values()))
    saved = await repo.read("alice", turn["turn_id"])
    assert saved["status"] == "completed"
    assert calls == [("context", t) for t in spec["tickers"]]
    activity = saved["read_activity"]
    assert activity["reserved"] == activity["started"] == 6
    assert [a["capability"] for a in activity["attempts"]].count("history") == 3
    assert (await repo.read("bob", turn["turn_id"])) is None
    replay = await service.ask("alice", turn["request_id"], spec)
    assert replay["read_activity"] == activity and not service.tasks


@pytest.mark.asyncio
async def test_price_lookup_is_exactly_one_read():
    budget = ReadBudget(timeout=10)
    with budget_scope(budget, {"question": "SPY price", "price_only": True}):
        result = await ResearchReads(lambda *a: {"spot": 100}, lambda *a: None, lambda *a: []).snapshot(
            "SPY", "all", price_only=True
        )
    assert any(f["metric"] == "Underlying price" for f in result["facts"])
    assert budget.close()["started"] == 1


async def wait_until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0.002)


def basic_spec(question="Explain SPY"):
    return {
        "ticker": "SPY",
        "tickers": ["SPY"],
        "horizon": "all",
        "screen": {},
        "context_conflict": False,
        "question": question,
    }


@pytest.mark.asyncio
async def test_failed_durable_reservation_enters_no_callback():
    from services.agent.read_budget import ReadActivityUnavailable

    calls = []

    async def unavailable(state):
        raise OSError("private database location")

    budget = ReadBudget(save=unavailable)
    with pytest.raises(ReadActivityUnavailable):
        await budget.sync("context", "SPY", lambda: calls.append(1))
    assert not calls
    assert budget.close()["started"] == 0


@pytest.mark.asyncio
async def test_cancel_keeps_running_thread_charged_and_terminal_state_immutable():
    import threading

    entered, release, exited = threading.Event(), threading.Event(), threading.Event()

    def alerts(*args):
        entered.set()
        release.wait(3)
        exited.set()
        return []

    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    service = ResearchService(repo, ResearchReads(lambda *a: {"spot": 100}, lambda *a: None, alerts))
    try:
        turn = await service.ask("alice", identity(), basic_spec("Explain SPY flow"))
        await wait_until(entered.is_set)
        result = await service.cancel("alice", turn["turn_id"])
        assert result["status"] == "cancelled" and result["answer"] is None
        activity = result["read_activity"]
        assert activity["reserved"] == activity["started"] == 2
        assert activity["attempts"][-1]["worker_unresolved"]
        release.set()
        await wait_until(exited.is_set)
        await asyncio.gather(*list(service.tasks.values()), return_exceptions=True)
        assert (await repo.read("alice", turn["turn_id"]))["read_activity"] == activity
        assert (await repo.read("alice", turn["turn_id"]))["status"] == "cancelled"
    finally:
        release.set()
        await service.close()


@pytest.mark.asyncio
async def test_blocking_cache_callback_does_not_block_overall_deadline():
    import threading

    entered, release = threading.Event(), threading.Event()

    def chain(*args):
        entered.set()
        release.wait(3)
        return {"spot": 100}

    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    service = ResearchService(repo, ResearchReads(chain, lambda *a: None, lambda *a: []), timeout=0.15)
    start = time.monotonic()
    try:
        turn = await service.ask("alice", identity(), {**basic_spec("SPY price"), "price_only": True})
        await asyncio.gather(*list(service.tasks.values()))
        assert entered.is_set() and time.monotonic() - start < 0.8
        saved = await repo.read("alice", turn["turn_id"])
        assert saved["status"] == "failed"
        assert saved["read_activity"]["started"] == 1
        assert saved["read_activity"]["attempts"][0]["worker_unresolved"]
        release.set()
        await asyncio.sleep(0.02)
        assert (await repo.read("alice", turn["turn_id"])) == saved
    finally:
        release.set()
        await service.close()


@pytest.mark.asyncio
async def test_timeout_does_not_become_success_when_late_worker_returns(monkeypatch):
    import threading

    from services.agent import read_budget

    monkeypatch.setattr(read_budget, "PER_READ_SECONDS", 0.02)
    release = threading.Event()
    budget = ReadBudget(timeout=2)
    try:
        with pytest.raises(TimeoutError):
            await budget.sync("context", "SPY", lambda: release.wait(2))
        release.set()
        await wait_until(lambda: not budget.state()["attempts"][0]["worker_unresolved"])
        result = budget.close()
        assert result["attempts"][0]["outcome"] == "timed_out"
        assert result["started"] == 1
    finally:
        release.set()


@pytest.mark.asyncio
async def test_two_turns_have_independent_allowances_and_durable_counts():
    repos = AgentRepository(AsyncMongoMockClient().test)
    await repos.initialize()
    reads = ResearchReads(lambda *a: {"spot": 100}, lambda *a: None, lambda *a: [])
    service = ResearchService(repos, reads)
    spec = {**basic_spec("Explain gamma structure of SPY QQQ DIA"), "tickers": ["SPY", "QQQ", "DIA"]}
    a, b = await asyncio.gather(service.ask("alice", identity(), spec), service.ask("bob", identity(), spec))
    await asyncio.gather(*list(service.tasks.values()))
    for owner, doc in [("alice", a), ("bob", b)]:
        saved = await repos.read(owner, doc["turn_id"])
        assert saved["status"] == "completed"
        assert saved["read_activity"]["reserved"] == saved["read_activity"]["started"] == 6
        assert not saved["read_activity"]["denied"]


@pytest.mark.asyncio
async def test_exhausted_broad_request_saves_exact_started_count_and_explicit_gaps():
    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    entered = []

    def chain(ticker, *args):
        entered.append(("context", ticker))
        return {"spot": 100}

    def alerts(ticker):
        entered.append(("flow", ticker))
        return []

    def daily(ticker):
        entered.append(("daily_bars", ticker))
        return None

    reads = ResearchReads(chain, lambda *a: None, alerts, read_daily_bars=daily)
    service = ResearchService(repo, reads)
    spec = {**basic_spec("Full research SPY QQQ DIA"), "tickers": ["SPY", "QQQ", "DIA"]}
    turn = await service.ask("alice", identity(), spec)
    await asyncio.gather(*list(service.tasks.values()))
    saved = await repo.read("alice", turn["turn_id"])
    activity = saved["read_activity"]
    assert saved["status"] == "completed"
    assert activity["reserved"] == activity["started"] == 8
    assert activity["denied"]
    assert any("eight-capability limit" in gap for gap in saved["answer"]["gaps"])
    actual_external = [
        (a["capability"], a["ticker"])
        for a in activity["attempts"]
        if a["capability"] in {"context", "flow", "daily_bars"}
    ]
    assert actual_external == entered


@pytest.mark.asyncio
async def test_same_history_followup_reuses_frozen_result_and_budget():
    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()

    class Model:
        calls = 0

        async def once(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {"status": "ok", "name": "inspect_history", "data": {"ticker": "SPY"}}
            return {"status": "unavailable", "reason": "Fixture model disabled"}

    model = Model()
    reads = ResearchReads(lambda *a: {"spot": 100}, lambda *a: None, lambda *a: [])
    service = ResearchService(repo, reads, model=model)
    turn = await service.ask("alice", identity(), basic_spec("What changed since yesterday in SPY?"))
    await asyncio.gather(*list(service.tasks.values()))
    saved = await repo.read("alice", turn["turn_id"])
    assert saved["status"] == "completed" and model.calls == 2
    assert [a["capability"] for a in saved["read_activity"]["attempts"]] == ["context", "history"]


@pytest.mark.asyncio
async def test_restart_keeps_reserved_attempt_as_unknown_and_never_reenters():
    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    doc, _ = await repo.admit("alice", identity(), basic_spec())
    await repo.save_read_activity(
        "alice",
        doc["turn_id"],
        {
            "policy": "research-capabilities-1",
            "limit": 8,
            "reserved": 1,
            "started": 0,
            "closed": False,
            "denied": [],
            "attempts": [
                {"id": 1, "capability": "context", "ticker": "SPY", "outcome": "reserved", "started_at": None}
            ],
        },
    )
    await repo.initialize()
    saved = await repo.read("alice", doc["turn_id"])
    assert saved["status"] == "interrupted"
    assert saved["read_activity"]["reserved"] == 1
    assert not saved["read_activity"]["entry_count_complete"]
    assert saved["read_activity"]["attempts"][0]["outcome"] == "interrupted_unknown"


@pytest.mark.asyncio
async def test_reservation_is_visible_to_callback_before_entry():
    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    doc, _ = await repo.admit("alice", identity(), basic_spec())
    seen = []

    async def save(value):
        result = await repo.save_read_activity("alice", doc["turn_id"], value)
        seen.append((await repo.read("alice", doc["turn_id"]))["read_activity"])
        return result

    budget = ReadBudget(save=save)

    def check():
        assert seen[-1]["reserved"] == 1 and seen[-1]["started"] == 0
        return 100

    assert await budget.sync("context", "SPY", check) == 100
    assert seen[-1]["started"] == 1


@pytest.mark.asyncio
async def test_worker_limit_does_not_release_slots_just_because_waiting_turns_cancel():
    import threading

    entered = [threading.Event() for _ in range(4)]
    release = threading.Event()
    budgets = [ReadBudget() for _ in range(5)]

    def slow(index):
        entered[index].set()
        return release.wait(3)

    tasks = [asyncio.create_task(budgets[i].sync("context", "SPY", slow, i)) for i in range(4)]
    try:
        await wait_until(lambda: all(item.is_set() for item in entered))
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        extra = []
        with pytest.raises(ReadDenied, match="still busy"):
            await budgets[4].sync("context", "SPY", lambda: extra.append(1))
        assert not extra and budgets[4].state()["started"] == 0
        assert all(b.state()["attempts"][0]["worker_unresolved"] for b in budgets[:4])
    finally:
        release.set()
        await asyncio.gather(*tasks, return_exceptions=True)
        await wait_until(lambda: all(not b.state()["attempts"][0]["worker_unresolved"] for b in budgets[:4]))


@pytest.mark.asyncio
async def test_legacy_preview_also_shares_one_question_allowance():
    from services.agent.loop import run_turn

    reads = ResearchReads(lambda *a: {"spot": 100}, lambda *a: None, lambda *a: [])
    result = await run_turn(question="Research $SPY $QQQ $DIA", ticker="SPY", reads=reads)
    assert result["saved"] is False
    assert result["read_activity"]["reserved"] == 8
    assert result["read_activity"]["denied"]


@pytest.mark.asyncio
async def test_wrong_owner_cancellation_cannot_freeze_another_turn():
    import threading

    entered, release = threading.Event(), threading.Event()

    def flow(*args):
        entered.set()
        release.wait(3)
        return []

    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    service = ResearchService(repo, ResearchReads(lambda *a: {"spot": 100}, lambda *a: None, flow))
    try:
        turn = await service.ask("alice", identity(), basic_spec("Explain SPY flow and structure"))
        await wait_until(entered.is_set)
        assert await service.cancel("bob", turn["turn_id"]) is None
        release.set()
        await asyncio.gather(*list(service.tasks.values()))
        saved = await repo.read("alice", turn["turn_id"])
        assert saved["status"] == "completed"
        assert [a["capability"] for a in saved["read_activity"]["attempts"]] == [
            "context",
            "flow",
            "structure",
            "volatility",
        ]
        assert not saved["read_activity"]["denied"]
        assert not any("stopped" in g for g in saved["answer"]["gaps"])
    finally:
        release.set()
        await service.close()


@pytest.mark.parametrize(
    "question",
    [
        "Explain SPY flow and expected moves",
        "Explain SPY gamma and implied move",
        "Explain SPY structure and other important readings",
        "Full checklist: what changed in SPY gamma since yesterday?",
    ],
)
def test_single_ticker_complex_wording_keeps_existing_evidence(question):
    from services.agent.read_budget import capability_plan

    assert capability_plan(basic_spec(question)) == {"structure", "volatility", "flow", "map"}


@pytest.mark.parametrize("phrase", ["expected move", "expected moves", "implied move", "implied moves"])
def test_three_ticker_requested_moves_are_not_silently_omitted(phrase):
    from services.agent.read_budget import capability_plan

    spec = {**basic_spec(f"Compare SPY QQQ DIA flow and {phrase}"), "tickers": ["SPY", "QQQ", "DIA"]}
    assert capability_plan(spec) == {"flow", "volatility"}


@pytest.mark.asyncio
async def test_failed_history_is_not_retried_by_followup(monkeypatch):
    from services.agent import research

    calls = []

    async def failed(*args, **kwargs):
        calls.append(1)
        raise OSError("private history failure")

    monkeypatch.setattr(research, "history_facts", failed)
    service = ResearchService(None, None)
    budget = ReadBudget()
    snap = {"ticker": "SPY", "snapshot_id": "same"}
    with budget_scope(budget):
        first = await service._history(None, "alice", snap)
        second = await service._history(None, "alice", snap)
    assert first == second and len(calls) == 1
    assert budget.close()["reserved"] == 1
    assert "private" not in str(first)


@pytest.mark.asyncio
async def test_closed_question_cannot_begin_model_interpretation():
    class Repo:
        async def progress(self, *args):
            return True

    class Model:
        async def once(self, *args, **kwargs):
            raise AssertionError("No model call after cancellation begins")

    service = ResearchService(Repo(), None, model=Model())
    budget = ReadBudget()
    with budget_scope(budget):
        budget.close()
        await service._interpret("alice", "turn", basic_spec(), {"facts": []}, [])


@pytest.mark.asyncio
async def test_failed_cancel_save_stops_work_instead_of_completing_partial_answer(monkeypatch):
    import threading

    entered, release = threading.Event(), threading.Event()

    def flow(*args):
        entered.set()
        release.wait(3)
        return []

    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    service = ResearchService(repo, ResearchReads(lambda *a: {"spot": 100}, lambda *a: None, flow))
    finish = repo.finish

    async def fail_cancel(owner, turn_id, status, **kwargs):
        if status == "cancelled":
            raise OSError("fixture unavailable cancellation save")
        return await finish(owner, turn_id, status, **kwargs)

    monkeypatch.setattr(repo, "finish", fail_cancel)
    try:
        turn = await service.ask("alice", identity(), basic_spec())
        await wait_until(entered.is_set)
        with pytest.raises(OSError):
            await service.cancel("alice", turn["turn_id"])
        release.set()
        await asyncio.gather(*list(service.tasks.values()), return_exceptions=True)
        saved = await repo.read("alice", turn["turn_id"])
        assert saved["status"] == "interrupted" and saved["answer"] is None
        assert saved["read_activity"]["started"] == 2
    finally:
        release.set()
        await service.close()


@pytest.mark.asyncio
async def test_cancellation_before_worker_starts_saves_zero_reads():
    repo = AgentRepository(AsyncMongoMockClient().test)
    await repo.initialize()
    service = ResearchService(repo, ResearchReads(lambda *a: None, lambda *a: None, lambda *a: []))
    turn = await service.ask("alice", identity(), basic_spec())
    saved = await service.cancel("alice", turn["turn_id"])
    assert saved["status"] == "cancelled"
    assert saved["read_activity"]["reserved"] == saved["read_activity"]["started"] == 0
    assert saved["read_activity"]["entry_count_complete"]
    await service.close()
