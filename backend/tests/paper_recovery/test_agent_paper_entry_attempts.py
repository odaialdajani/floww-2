"""Eight immutable entry-fill parents, including no-fill/refused observations."""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_agent_paper_admission_corrections import retained_parents, service_for  # noqa: E402
from test_agent_paper_admission_supervisor import ready  # noqa: E402
from test_agent_paper_runner import NOW, POLICY, QUOTE, RULE, UnadmittedPaperRunner  # noqa: E402

from services.agent.paper.admission import MAX_ARTIFACTS, artifact_liabilities  # noqa: E402
from services.agent.paper.repository import PaperCapacity, operation_id  # noqa: E402


def advance(repo, runner, seconds, *, source, away=False):
    at = NOW+timedelta(seconds=seconds)
    runner.clock = runner.admission.clock = runner.admission.adapter.clock = lambda: at
    repo.accounts.server_clock = lambda: at
    return {**QUOTE, "source_id": source, "observed_at": at.isoformat(), "received_at": at.isoformat(),
            **({"bid": "2.10", "ask": "2.20"} if away else {})}


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["begun", "resolved"])
async def test_no_fill_at_boundary_then_restart_and_valid_fill_uses_remaining_attempts(phase):
    repo, owner, account, runner = await ready()
    retained_parents(repo, owner, account, 101)
    opened, _ = await runner.enter(owner, account, QUOTE)
    away = advance(repo, runner, 1, source="away-lost-ack", away=True)
    original = repo.commit
    failed = [False]
    async def lose_ack(*args, **kwargs):
        receipt = await original(*args, **kwargs)
        if args[5].get("assessment_phase") == phase and not failed[0]:
            failed[0] = True
            raise TimeoutError("entry attempt reply lost")
        return receipt
    repo.commit = lose_ack
    with pytest.raises(TimeoutError):
        await runner.enter_fill(owner, account, opened["order_id"], away)
    repo.commit = original
    restarted = UnadmittedPaperRunner(repo, quote_reader=lambda: away, clock=runner.clock,
                                      admission_adapter=runner.admission.adapter,
                                      execution_authority=runner.admission.authority)
    await restarted.start(owner, account, RULE, POLICY)
    assert await restarted.enter_fill(owner, account, opened["order_id"], away) == (None, False)
    count = len(repo.admissions.docs)
    assert count+sum(artifact_liabilities((await repo.read(owner, account))["state"])) == MAX_ARTIFACTS
    assert await restarted.enter_fill(owner, account, opened["order_id"], away) == (None, False)
    assert len(repo.admissions.docs) == count
    good = advance(repo, restarted, 2, source="good-after-restart")
    fill, created = await restarted.enter_fill(owner, account, opened["order_id"], good)
    assert created and fill["quantity"] == 1
    current = await repo.read(owner, account)
    assert current["state"]["cash"] == "794.35"
    assert current["state"]["entry_fill_attempts"][opened["order_id"]] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("direct", [False, True])
async def test_eight_unfilled_parents_exhaust_budget_and_exact_retry_is_free(direct):
    repo, owner, account, runner = await ready()
    opened, _ = await runner.enter(owner, account, QUOTE)
    service = service_for(runner)
    for attempt in range(1, 9):
        away = advance(repo, runner, attempt, source="away-"+str(attempt), away=True)
        service.clock = service.admission.clock = runner.clock
        if direct:
            await runner.admission.replenish(owner, account)
            current = await repo.read(owner, account)
            operation = operation_id(current["version"], epoch=current["epoch"])
            assert await service.quote(owner, account, operation, opened["order_id"], away) == (None, False)
            assert await service.quote(owner, account, operation, opened["order_id"], away) == (None, False)
        else:
            assert await runner.enter_fill(owner, account, opened["order_id"], away) == (None, False)
            assert await runner.enter_fill(owner, account, opened["order_id"], away) == (None, False)
    if direct:
        # Explicit observation-credit replenishment must not reset attempts.
        await service.admission.replenish(owner, account)
    before = await repo.read(owner, account)
    retained = len(repo.admissions.docs)
    good = advance(repo, runner, 9, source="ninth-market-able")
    service.clock = service.admission.clock = runner.clock
    with pytest.raises(PaperCapacity, match="eight|Eight|attempt"):
        if direct:
            # Request flags are data only and cannot replenish the allowance.
            await service.admission.execute(owner, account, operation_id(before["version"], epoch=before["epoch"]),
                                              kind="fill", order_id=opened["order_id"], quote=good,
                                              parameters={"entry_fill_attempts": 0})
        else:
            await runner.enter_fill(owner, account, opened["order_id"], good)
    assert await repo.read(owner, account) == before
    assert len(repo.admissions.docs) == retained
    assert before["state"]["cash"] == "1000"
    await runner.cancel(owner, account, opened["order_id"])
    assert (await runner.reconcile(owner, account))["working_orders"] == []


@pytest.mark.asyncio
async def test_all_eight_marketable_fill_attempts_still_fill_without_risk_limit_changes():
    repo, owner, account, runner = await ready()
    rule = {**RULE, "quantity": 8, "limit": "0.20"}
    await runner.start(owner, account, rule, POLICY)
    first = {**QUOTE, "bid": "0.05", "ask": "0.06"}
    opened, _ = await runner.enter(owner, account, first)
    for attempt in range(1, 9):
        quote = {**advance(repo, runner, attempt, source="cheap-fill-"+str(attempt)), "bid": "0.05", "ask": "0.06"}
        fill, created = await runner.enter_fill(owner, account, opened["order_id"], quote)
        assert created and fill["quantity"] == 1
    current = await repo.read(owner, account)
    order = current["state"]["orders"][opened["order_id"]]
    assert order["filled"] == len(order["fills"]) == 8 and order["status"] == "filled"
    assert current["state"]["cash"] == "906.80"
    assert current["state"]["entry_fill_attempts"][opened["order_id"]] == 8
    retained = len(repo.admissions.docs)
    ninth = {**advance(repo, runner, 9, source="ninth-cheap"), "bid": "0.05", "ask": "0.06"}
    with pytest.raises(PaperCapacity, match="attempt"):
        await runner.enter_fill(owner, account, opened["order_id"], ninth)
    assert len(repo.admissions.docs) == retained
    assert await repo.read(owner, account) == current


@pytest.mark.asyncio
async def test_partial_entry_then_no_fill_preserves_exact_protected_exit_and_cancel():
    repo, owner, account, runner = await ready()
    await runner.start(owner, account, {**RULE, "quantity": 2}, POLICY)
    retained_parents(repo, owner, account, 101)
    opened, _ = await runner.enter(owner, account, QUOTE)
    await runner.enter_fill(owner, account, opened["order_id"], QUOTE)
    away = advance(repo, runner, 1, source="partial-away", away=True)
    assert await runner.enter_fill(owner, account, opened["order_id"], away) == (None, False)
    current = await repo.read(owner, account)
    assert len(repo.admissions.docs)+sum(artifact_liabilities(current["state"])) == MAX_ARTIFACTS
    closing = advance(repo, runner, 2, source="held-exit")
    close, _ = await runner.exit(owner, account, {**RULE, "structure_id": opened["structure_id"],
                     "quantity": 1, "limit": "1.80", "proposal_digest": "c"*64}, closing)
    await runner.exit_fill(owner, account, close["order_id"], closing)
    await runner.cancel(owner, account, opened["order_id"])
    report = await runner.reconcile(owner, account)
    assert report["cash"] == "978.70" and report["realized_result"] == "-21.30"
    assert report["positions"] == report["working_orders"] == [] and report["cash_reconciled"]


@pytest.mark.asyncio
async def test_refused_fill_parent_spends_one_attempt_and_keeps_exit_protection():
    repo, owner, account, runner = await ready()
    await runner.start(owner, account, {**RULE, "quantity": 2}, POLICY)
    retained_parents(repo, owner, account, 101)
    opened, _ = await runner.enter(owner, account, QUOTE)
    await runner.enter_fill(owner, account, opened["order_id"], QUOTE)
    next_quote = advance(repo, runner, 1, source="proposed-risk-refusal")
    def high_verified_mark(frame):
        frame["marks"][0].update(source_id="verified-peak-mark", bid="60.00", ask="60.10")
        return frame
    runner.admission.adapter.frame_transform = high_verified_mark
    from services.agent.paper.repository import PaperConflict
    with pytest.raises(PaperConflict, match="risk admission refused"):
        await runner.enter_fill(owner, account, opened["order_id"], next_quote)
    current = await repo.read(owner, account)
    assert current["state"]["cash"] == "794.35"
    assert current["state"]["orders"][opened["order_id"]]["filled"] == 1
    assert current["state"]["entry_fill_attempts"][opened["order_id"]] == 2
    assert len(repo.admissions.docs)+sum(artifact_liabilities(current["state"])) == MAX_ARTIFACTS
    assert current["state"]["valuation"]["risk_anchor"]["observed_peak_equity"] == "6794.35"
