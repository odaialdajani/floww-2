"""Review regressions over direct service, durable CAS fences and exit budgets."""
from __future__ import annotations

import copy
import sys
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from services.agent.paper.admission import MAX_ARTIFACTS, artifact_liabilities  # noqa: E402
from services.agent.paper.repository import PaperCapacity, PaperConflict, operation_id  # noqa: E402
from services.agent.paper.service import PreparedPaperService  # noqa: E402
from services.execution_lease import acquire_lease, release_lease  # noqa: E402
from test_agent_paper_admission_supervisor import economics, ready  # noqa: E402
from test_agent_paper_runner import NOW, POLICY, QUOTE, RULE, UnadmittedPaperRunner  # noqa: E402


def service_for(runner):
    return PreparedPaperService(runner.repository, admission_adapter=runner.admission.adapter,
                                 execution_authority=runner.admission.authority, clock=runner.clock)


async def key(repo, owner, account):
    current = await repo.read(owner, account)
    return operation_id(current["version"], epoch=current["epoch"])


@pytest.mark.asyncio
@pytest.mark.parametrize("side", ["buy", "sell"])
@pytest.mark.parametrize("phase", ["stage", "fill"])
@pytest.mark.parametrize("field", ["bid_size", "ask_size"])
@pytest.mark.parametrize("invalid", [None, 0, -1, "1", True, "missing"])
async def test_direct_service_requires_positive_whole_two_sided_sizes(side, phase, field, invalid):
    repo, owner, account, runner = await ready()
    service = service_for(runner)
    parameters = runner._stage_parameters(side)
    if side == "sell":
        opened, _ = await runner.enter(owner, account, QUOTE)
        await runner.enter_fill(owner, account, opened["order_id"], QUOTE)
        parameters.update(structure_id=opened["structure_id"], limit="1.80", proposal_digest="c"*64)
    staged = None
    if phase == "fill":
        staged, _ = await service.stage(owner, account, await key(repo, owner, account), parameters, {}, quote=QUOTE)
        if side == "buy":
            await service.admission.replenish(owner, account)
    before = await repo.read(owner, account)
    invalid_quote = copy.deepcopy(QUOTE)
    if invalid == "missing":
        del invalid_quote[field]
    else:
        invalid_quote[field] = invalid
    with pytest.raises((PaperConflict, ValueError), match="size"):
        if phase == "stage":
            await service.stage(owner, account, await key(repo, owner, account), parameters, {}, quote=invalid_quote)
        else:
            await service.quote(owner, account, await key(repo, owner, account), staged["body"]["order_id"], invalid_quote)
    assert await repo.read(owner, account) == before


@pytest.mark.asyncio
async def test_adapter_captured_stage_quote_cannot_omit_opposite_size():
    repo, owner, account, runner = await ready()
    capture = runner.admission.adapter.capture_verified_inputs
    async def unverified_size(**kwargs):
        inputs = await capture(**{**kwargs, "quote": QUOTE})
        return replace(inputs, executable_quote={**QUOTE, "bid_size": None})
    runner.admission.adapter.capture_verified_inputs = unverified_size
    before = await repo.read(owner, account)
    with pytest.raises((PaperConflict, ValueError), match="size"):
        await service_for(runner).stage(owner, account, await key(repo, owner, account),
                                         runner._stage_parameters("buy"), {})
    assert await repo.read(owner, account) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["stage", "fill"])
@pytest.mark.parametrize("fault", ["stopped", "reduce_only", "revoked", "takeover", "expired", "missing"])
async def test_supported_durable_revocation_at_economic_cas_prevents_economic_write(phase, fault):
    repo, owner, account, runner = await ready()
    opened = None
    if phase == "fill":
        opened, _ = await runner.enter(owner, account, QUOTE)
        await runner.admission.replenish(owner, account)
    before = await repo.read(owner, account)
    update = repo.accounts.update_one
    injected = [False]
    async def revoke_before_cas(query, changes):
        event = changes.get("$push", {}).get("pending_events", {}).get("body", {})
        if event.get("risk_decision", {}).get("status") == "pass" and not injected[0]:
            injected[0] = True
            current = await repo.read(owner, account)
            generation = current["execution_control"]["generation"]
            if fault in ("stopped", "reduce_only"):
                await runner.admission.set_execution_mode(owner, account, fault, expected_generation=generation)
            elif fault == "revoked":
                await runner.admission.revoke_execution(owner, account, expected_generation=generation)
                authority = runner.admission.authority
                assert release_lease(authority.lease_path, authority.lease_token)["ok"]
            elif fault == "takeover":
                authority = runner.admission.authority
                assert release_lease(authority.lease_path, authority.lease_token)["ok"]
                acquired = acquire_lease(authority.lease_path, "new-executor")
                assert acquired["ok"]
                runner.admission.authority = replace(authority, lease_token=acquired["token"])
                await runner.admission.bind_execution(owner, account, expected_generation=generation)
            elif fault == "expired":
                repo.accounts.server_clock = lambda: NOW+timedelta(seconds=121)
            else:
                # Storage-corruption/loss probe: no supported API deletes the
                # durable control, and its independent generation stays intact.
                repo.accounts.docs[0].pop("execution_control")
        return await update(query, changes)
    repo.accounts.update_one = revoke_before_cas
    with pytest.raises(PaperConflict):
        if phase == "stage":
            await runner.enter(owner, account, QUOTE)
        else:
            await runner.enter_fill(owner, account, opened["order_id"], QUOTE)
    after = await repo.read(owner, account)
    assert injected[0]
    assert economics(after) == economics(before)
    assert len(after["state"]["risk_control"]["pending"]) == 1


@pytest.mark.asyncio
async def test_control_loss_cannot_reset_the_monotonic_generation():
    repo, owner, account, runner = await ready()
    repo.accounts.docs[0].pop("execution_control")
    before = await repo.read(owner, account)
    with pytest.raises(PaperConflict, match="generation requires recovery"):
        await runner.admission.bind_execution(owner, account, expected_generation=0)
    assert await repo.read(owner, account) == before


@pytest.mark.asyncio
async def test_revocation_after_commit_reconciles_original_receipt_without_new_write():
    repo, owner, account, runner = await ready()
    opened, _ = await runner.enter(owner, account, QUOTE)
    generation = (await repo.read(owner, account))["execution_control"]["generation"]
    await runner.admission.revoke_execution(owner, account, expected_generation=generation)
    before = await repo.read(owner, account)
    again, created = await runner.enter(owner, account, QUOTE)
    assert again == opened and created is False
    assert await repo.read(owner, account) == before


def retained_parents(repo, owner, account, count):
    first = len(repo.admissions.docs)
    repo.admissions.docs.extend(dict(_id="retained-"+str(first+index), owner=owner,
                                     account_id=account, venue="internal") for index in range(count))


@pytest.mark.asyncio
@pytest.mark.parametrize("retained", [102, 126, 127, 128])
async def test_near_cap_entry_refuses_before_surrendering_future_exit_artifacts(retained):
    repo, owner, account, runner = await ready()
    retained_parents(repo, owner, account, retained)
    before = await repo.read(owner, account)
    with pytest.raises(PaperCapacity, match="prepaid fill/exit capacity"):
        await runner.enter(owner, account, QUOTE)
    assert await repo.read(owner, account) == before
    assert len(repo.admissions.docs) == retained


@pytest.mark.asyncio
async def test_full_protected_artifact_budget_keeps_reducing_stage_fill_and_restart_available():
    repo, owner, account, runner = await ready()
    retained_parents(repo, owner, account, 101)
    opened, _ = await runner.enter(owner, account, QUOTE)
    await runner.enter_fill(owner, account, opened["order_id"], QUOTE)
    current = await repo.read(owner, account)
    entries, exits = artifact_liabilities(current["state"])
    assert entries == 0 and exits == 18
    retained_parents(repo, owner, account, MAX_ARTIFACTS-exits-len(repo.admissions.docs))
    assert len(repo.admissions.docs)+exits == MAX_ARTIFACTS
    generation = current["execution_control"]["generation"]
    await runner.admission.set_execution_mode(owner, account, "reduce_only", expected_generation=generation)
    close_rule = {**RULE, "structure_id": opened["structure_id"], "quantity": 1,
                  "limit": "1.80", "proposal_digest": "c"*64}
    close, _ = await runner.exit(owner, account, close_rule, QUOTE)
    original = runner.repository.commit
    async def lost_ack(*args, **kwargs):
        result = await original(*args, **kwargs)
        if args[5].get("kind") == "paper_fill":
            raise TimeoutError("exit reply lost")
        return result
    runner.repository.commit = lost_ack
    with pytest.raises(TimeoutError):
        await runner.exit_fill(owner, account, close["order_id"], QUOTE)
    runner.repository.commit = original
    restarted = UnadmittedPaperRunner(repo, quote_reader=lambda: QUOTE, clock=runner.clock,
                                      admission_adapter=runner.admission.adapter,
                                      execution_authority=runner.admission.authority)
    await restarted.start(owner, account, RULE, POLICY)
    receipt, created = await restarted.exit_fill(owner, account, close["order_id"], QUOTE)
    assert created is False and receipt["quantity"] == 1
    report = await runner.reconcile(owner, account)
    assert report["cash"] == "978.70" and report["realized_result"] == "-21.30"
    assert report["positions"] == report["working_orders"] == []
    assert report["cash_reconciled"] is True
    assert len(repo.admissions.docs)+artifact_liabilities((await repo.read(owner, account))["state"])[1] == MAX_ARTIFACTS


@pytest.mark.asyncio
async def test_two_concurrent_control_writers_cannot_both_advance_one_generation():
    import asyncio

    repo, owner, account, runner = await ready()
    generation = (await repo.read(owner, account))["execution_generation"]
    results = await asyncio.gather(*[
        runner.admission.set_execution_mode(owner, account, mode, expected_generation=generation)
        for mode in ("reduce_only", "stopped")], return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, PaperConflict) for result in results) == 1
    assert (await repo.read(owner, account))["execution_generation"] == generation+1


@pytest.mark.asyncio
async def test_full_artifact_budget_keeps_partial_fills_and_partial_reductions_available():
    repo, owner, account, runner = await ready()
    await runner.start(owner, account, {**RULE, "quantity": 2}, POLICY)
    retained_parents(repo, owner, account, 101)
    opened, _ = await runner.enter(owner, account, QUOTE)
    await runner.enter_fill(owner, account, opened["order_id"], QUOTE)
    assert len(repo.admissions.docs)+sum(artifact_liabilities((await repo.read(owner, account))["state"])) == MAX_ARTIFACTS
    later = NOW+timedelta(seconds=1)
    runner.clock = runner.admission.clock = runner.admission.adapter.clock = lambda: later
    repo.accounts.server_clock = lambda: later
    second = {**QUOTE, "source_id": "second-partial", "observed_at": later.isoformat(), "received_at": later.isoformat()}
    await runner.enter_fill(owner, account, opened["order_id"], second)
    current = await repo.read(owner, account)
    exits = artifact_liabilities(current["state"])[1]
    retained_parents(repo, owner, account, MAX_ARTIFACTS-exits-len(repo.admissions.docs))
    close, _ = await runner.exit(owner, account,
                {**RULE, "structure_id": opened["structure_id"], "quantity": 2, "limit": "1.80", "proposal_digest": "c"*64}, second)
    later = NOW+timedelta(seconds=2)
    first_close = {**QUOTE, "source_id": "first-close-partial", "bid_size": 1,
                   "observed_at": later.isoformat(), "received_at": later.isoformat()}
    await runner.exit_fill(owner, account, close["order_id"], first_close)
    later = NOW+timedelta(seconds=3)
    third = {**QUOTE, "source_id": "last-partial", "bid_size": 1,
             "observed_at": later.isoformat(), "received_at": later.isoformat()}
    await runner.exit_fill(owner, account, close["order_id"], third)
    report = await runner.reconcile(owner, account)
    assert report["cash"] == "957.40" and report["realized_result"] == "-42.60"
    assert report["cash_reconciled"] and report["positions"] == report["working_orders"] == []


@pytest.mark.asyncio
async def test_full_artifact_budget_keeps_cancel_archive_and_verified_exit_retry_available():
    repo, owner, account, runner = await ready()
    retained_parents(repo, owner, account, 101)
    opened, _ = await runner.enter(owner, account, QUOTE)
    await runner.enter_fill(owner, account, opened["order_id"], QUOTE)
    exits = artifact_liabilities((await repo.read(owner, account))["state"])[1]
    retained_parents(repo, owner, account, MAX_ARTIFACTS-exits-len(repo.admissions.docs))
    close_rule = {**RULE, "structure_id": opened["structure_id"], "quantity": 1,
                  "limit": "1.80", "proposal_digest": "c"*64}
    first, _ = await runner.exit(owner, account, close_rule, QUOTE)
    await runner.cancel(owner, account, first["order_id"])
    await repo.project(owner, account)
    service = service_for(runner)
    await service.archive(owner, account, await key(repo, owner, account), first["order_id"])
    await repo.project(owner, account)
    await service.replenish(owner, account, await key(repo, owner, account))
    second, _ = await runner.exit(owner, account, {**close_rule, "proposal_digest": "d"*64}, QUOTE)
    assert second["order_id"] != first["order_id"]
    await runner.exit_fill(owner, account, second["order_id"], QUOTE)
    report = await runner.reconcile(owner, account)
    assert report["cash"] == "978.70" and report["realized_result"] == "-21.30"
    assert report["cash_reconciled"] and report["positions"] == report["working_orders"] == []
