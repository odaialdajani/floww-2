"""Trusted admission, funded risk and recovery over isolated faithful Mongo fakes."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_agent_paper_runner import NOW, POLICY, QUOTE, RULE, _fresh_repo  # noqa: E402

from services.agent.paper.repository import PaperConflict  # noqa: E402
from services.agent.paper.runner import PaperRunner  # noqa: E402


@pytest.mark.asyncio
async def test_missing_trusted_composition_refuses_without_any_write():
    repo, owner, account = await _fresh_repo()
    runner = PaperRunner(repo, quote_reader=lambda: QUOTE, clock=lambda: NOW)
    await runner.start(owner, account, RULE, POLICY)
    before = copy.deepcopy(await repo.read(owner, account))
    with pytest.raises(PaperConflict, match="admission"):
        await runner.enter(owner, account, QUOTE)
    assert await repo.read(owner, account) == before

from dataclasses import replace  # noqa: E402
from datetime import timedelta  # noqa: E402

from test_agent_paper_runner import PaperRunner as admitted_runner  # noqa: E402

from services.agent.paper.repository import PaperCapacity, operation_id  # noqa: E402
from services.agent.paper.service import PreparedPaperService  # noqa: E402
from services.execution_lease import release_lease  # noqa: E402


def economics(account):
    return {key: copy.deepcopy(account["state"][key]) for key in
            ("cash", "realized_result", "orders", "positions", "quotes")}


async def ready():
    repo, owner, account = await _fresh_repo()
    runner = admitted_runner(repo, quote_reader=lambda: QUOTE, clock=lambda: NOW)
    await runner.start(owner, account, RULE, POLICY)
    return repo, owner, account, runner


@pytest.mark.asyncio
async def test_a_boolean_callback_cannot_replace_trusted_sources_or_risk():
    repo, owner, account = await _fresh_repo()
    current = await repo.read(owner, account)
    before = copy.deepcopy(current)
    service = PreparedPaperService(repo, admission_check=lambda *args: True, clock=lambda: NOW)
    with pytest.raises(PaperConflict, match="admission"):
        await service.stage(owner, account, operation_id(current["version"], epoch=current["epoch"]), RULE, {})
    assert await repo.read(owner, account) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", [False, 1, None])
async def test_non_true_independent_confirmation_has_no_account_or_artifact_write(reply):
    repo, owner, account, runner = await ready()
    async def rejected(**kwargs):
        return reply
    runner.admission.adapter.verify_admission = rejected
    before = copy.deepcopy(await repo.read(owner, account))
    with pytest.raises(PaperConflict, match="admission"):
        await runner.enter(owner, account, QUOTE)
    assert await repo.read(owner, account) == before
    assert repo.admissions.docs == []


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["begun", "resolved"])
async def test_lost_ack_restart_recovers_same_parent_without_recapture_or_second_stage(phase):
    repo, owner, account, runner = await ready()
    original = repo.commit
    failed = [False]
    async def lose_reply(*args, **kwargs):
        receipt = await original(*args, **kwargs)
        if args[5].get("assessment_phase") == phase and not failed[0]:
            failed[0] = True
            raise TimeoutError("synthetic commit acknowledgement lost")
        return receipt
    repo.commit = lose_reply
    with pytest.raises(TimeoutError):
        await runner.enter(owner, account, QUOTE)
    old_parent = repo.admissions.docs[0]["parent_operation"]
    assert runner.admission.adapter.capture_count == 1
    # A new process can load the durable parent using the same frozen rule.
    restarted = PaperRunner(repo, quote_reader=lambda: QUOTE, clock=lambda: NOW,
                            admission_adapter=runner.admission.adapter,
                            execution_authority=runner.admission.authority)
    await restarted.start(owner, account, RULE, POLICY)
    receipt, _ = await restarted.enter(owner, account, QUOTE)
    current = await repo.read(owner, account)
    assert receipt["order_id"] in current["state"]["orders"]
    assert len(current["state"]["orders"]) == len(repo.admissions.docs) == 1
    assert repo.admissions.docs[0]["parent_operation"] == old_parent
    assert runner.admission.adapter.capture_count == 1
    assert current["state"]["cash"] == "1000"
    assert not current["state"]["risk_control"]["pending"]


@pytest.mark.asyncio
async def test_lost_fill_ack_restart_returns_original_fill_once():
    repo, owner, account, runner = await ready()
    entry, _ = await runner.enter(owner, account, QUOTE)
    original = repo.commit
    async def lose_fill(*args, **kwargs):
        receipt = await original(*args, **kwargs)
        if args[5].get("kind") == "paper_fill":
            raise TimeoutError("lost fill acknowledgement")
        return receipt
    repo.commit = lose_fill
    with pytest.raises(TimeoutError):
        await runner.enter_fill(owner, account, entry["order_id"], QUOTE)
    repo.commit = original
    restarted = PaperRunner(repo, quote_reader=lambda: QUOTE, clock=lambda: NOW,
                            admission_adapter=runner.admission.adapter,
                            execution_authority=runner.admission.authority)
    await restarted.start(owner, account, RULE, POLICY)
    fill, created = await restarted.enter_fill(owner, account, entry["order_id"], QUOTE)
    assert created is False
    assert fill["quantity"] == 1
    report = await restarted.reconcile(owner, account)
    assert report["cash"] == "794.35"
    assert report["cash_reconciled"] is True
    assert len(report["fills"]) == 1


@pytest.mark.asyncio
async def test_expired_mongo_server_window_refuses_candidate_and_retains_intent():
    repo, owner, account, runner = await ready()
    repo.accounts.server_clock = lambda: NOW + timedelta(minutes=11)
    with pytest.raises(PaperConflict, match="server-time window"):
        await runner.enter(owner, account, QUOTE)
    current = await repo.read(owner, account)
    assert current["state"]["orders"] == {}
    assert current["state"]["cash"] == "1000"
    assert len(current["state"]["risk_control"]["pending"]) == 1


@pytest.mark.asyncio
async def test_failed_projection_cannot_replenish_credits_or_capture_a_fill():
    repo, owner, account, runner = await ready()
    entry, _ = await runner.enter(owner, account, QUOTE)
    before = copy.deepcopy(await repo.read(owner, account))
    async def offline(*args, **kwargs):
        raise OSError("synthetic projection unavailable")
    repo.events.insert_one = offline
    with pytest.raises(OSError, match="projection"):
        await runner.enter_fill(owner, account, entry["order_id"], QUOTE)
    assert await repo.read(owner, account) == before
    assert runner.admission.adapter.capture_count == 1
    assert before["state"]["risk_control"]["entry_credits"] == 0


@pytest.mark.asyncio
async def test_direct_assessment_cannot_silently_reset_exhausted_credits():
    repo, owner, account, runner = await ready()
    entry, _ = await runner.enter(owner, account, QUOTE)
    current = await repo.read(owner, account)
    with pytest.raises(PaperCapacity, match="credits"):
        await runner.admission.execute(owner, account, operation_id(current["version"], epoch=current["epoch"]),
                                       kind="fill", order_id=entry["order_id"], quote=QUOTE)
    assert await repo.read(owner, account) == current


@pytest.mark.asyncio
async def test_lost_lease_refuses_before_any_account_or_artifact_write():
    repo, owner, account, runner = await ready()
    authority = runner.admission.authority
    assert release_lease(authority.lease_path, authority.lease_token)["ok"]
    before = copy.deepcopy(await repo.read(owner, account))
    with pytest.raises(PaperConflict, match="lease"):
        await runner.enter(owner, account, QUOTE)
    assert await repo.read(owner, account) == before
    assert repo.admissions.docs == []


@pytest.mark.asyncio
async def test_reduce_only_stop_preserves_verified_exit_and_restart_barrier():
    repo, owner, account, runner = await ready()
    entry, _ = await runner.enter(owner, account, QUOTE)
    await runner.enter_fill(owner, account, entry["order_id"], QUOTE)
    mode = ["reduce_only"]
    runner.admission.authority = replace(runner.admission.authority, stop_reader=lambda: mode[0])
    close_rule = {**RULE, "structure_id": entry["structure_id"], "quantity": 1,
                  "limit": "1.80", "proposal_digest": "c"*64}
    close, _ = await runner.exit(owner, account, close_rule, QUOTE)
    restarted = PaperRunner(repo, quote_reader=lambda: QUOTE, clock=lambda: NOW,
                            admission_adapter=runner.admission.adapter, execution_authority=runner.admission.authority)
    await restarted.start(owner, account, RULE, POLICY)
    with pytest.raises(PaperConflict, match="Unresolved exit"):
        await restarted.enter(owner, account, QUOTE)
    await restarted.exit_fill(owner, account, close["order_id"], QUOTE)
    report = await restarted.reconcile(owner, account)
    assert report["cash"] == "978.70"
    assert report["realized_result"] == "-21.30"
    assert report["cash_reconciled"] is True
    assert report["positions"] == report["working_orders"] == []


@pytest.mark.asyncio
async def test_refused_complete_observation_preserves_actual_peak_without_new_exposure():
    repo, owner, account, runner = await ready()
    entry, _ = await runner.enter(owner, account, QUOTE)
    await runner.enter_fill(owner, account, entry["order_id"], QUOTE)
    await runner.admission.replenish(owner, account)
    current = await repo.read(owner, account)
    before = economics(current)
    later = NOW + timedelta(seconds=1)
    runner.clock = runner.admission.clock = runner.admission.adapter.clock = lambda: later
    repo.accounts.server_clock = lambda: later
    peak_quote = {**QUOTE, "source_id": "synthetic-peak", "bid": "60.00", "ask": "60.10",
                  "observed_at": later.isoformat(), "received_at": later.isoformat()}
    with pytest.raises(PaperConflict, match="risk admission refused"):
        await runner.admission.execute(owner, account, operation_id(current["version"], epoch=current["epoch"]),
                                       kind="stage", parameters=runner._stage_parameters("buy"), quote=peak_quote,
                                       confirmation={"rule_digest": RULE["rule_digest"]})
    after = await repo.read(owner, account)
    assert economics(after) == before
    assert after["state"]["valuation"]["risk_anchor"]["observed_peak_equity"] == "6794.35"
    assert after["pending_events"][-1]["body"]["assessment_status"] == "refuse"


@pytest.mark.asyncio
async def test_changed_immutable_capture_is_not_replayed():
    repo, owner, account, runner = await ready()
    await runner.enter(owner, account, QUOTE)
    original = repo.admissions.docs[0]["parent_operation"]
    repo.admissions.docs[0]["command"]["parameters"]["quantity"] = 9
    before = copy.deepcopy(await repo.read(owner, account))
    with pytest.raises(PaperConflict, match="artifact changed"):
        await runner.admission.resume(owner, account, original)
    assert await repo.read(owner, account) == before


@pytest.mark.asyncio
async def test_rule_is_frozen_before_a_caller_mutates_its_dictionary():
    repo, owner, account = await _fresh_repo()
    runner = admitted_runner(repo, quote_reader=lambda: QUOTE, clock=lambda: NOW)
    supplied = copy.deepcopy(RULE)
    await runner.start(owner, account, supplied, POLICY)
    supplied["quantity"] = 100
    entry, _ = await runner.enter(owner, account, QUOTE)
    assert (await repo.read(owner, account))["state"]["orders"][entry["order_id"]]["quantity"] == 1


@pytest.mark.asyncio
async def test_stop_during_capture_refuses_before_assessment_or_economic_write():
    repo, owner, account, runner = await ready()
    mode = ["running"]
    runner.admission.authority = replace(runner.admission.authority, stop_reader=lambda: mode[0])
    capture = runner.admission.adapter.capture_verified_inputs
    async def stop_during_capture(**kwargs):
        inputs = await capture(**kwargs)
        mode[0] = "stopped"
        return inputs
    runner.admission.adapter.capture_verified_inputs = stop_during_capture
    before = copy.deepcopy(await repo.read(owner, account))
    with pytest.raises(PaperConflict, match="stopped"):
        await runner.enter(owner, account, QUOTE)
    assert await repo.read(owner, account) == before
    assert repo.admissions.docs == []


@pytest.mark.asyncio
async def test_missing_verified_trade_evidence_refuses_despite_positive_confirmation():
    repo, owner, account, runner = await ready()
    capture = runner.admission.adapter.capture_verified_inputs
    async def missing_evidence(**kwargs):
        return replace(await capture(**kwargs), opening_trade_evidence=None)
    runner.admission.adapter.capture_verified_inputs = missing_evidence
    before = copy.deepcopy(await repo.read(owner, account))
    with pytest.raises(PaperConflict, match="risk admission refused"):
        await runner.enter(owner, account, QUOTE)
    after = await repo.read(owner, account)
    assert economics(after) == economics(before)
    assert after["pending_events"][-1]["body"]["assessment_status"] == "unknown"


@pytest.mark.asyncio
async def test_lease_loss_after_fill_commit_reports_uncertainty_and_reconciles_original_receipt():
    repo, owner, account, runner = await ready()
    entry, _ = await runner.enter(owner, account, QUOTE)
    original = repo.commit
    authority = runner.admission.authority
    async def lose_lease(*args, **kwargs):
        receipt = await original(*args, **kwargs)
        if args[5].get("kind") == "paper_fill":
            release_lease(authority.lease_path, authority.lease_token)
        return receipt
    repo.commit = lose_lease
    with pytest.raises(PaperConflict, match="lease.*lost"):
        await runner.enter_fill(owner, account, entry["order_id"], QUOTE)
    fill, created = await runner.enter_fill(owner, account, entry["order_id"], QUOTE)
    assert created is False and fill["quantity"] == 1
    report = await runner.reconcile(owner, account)
    assert report["cash"] == "794.35"
    assert len(report["fills"]) == 1 and report["cash_reconciled"] is True


@pytest.mark.asyncio
async def test_concurrent_parents_at_one_version_cannot_stage_twice():
    import asyncio

    repo, owner, account, runner = await ready()
    current = await repo.read(owner, account)
    capture = runner.admission.adapter.capture_verified_inputs
    barrier = asyncio.Event()
    calls = [0]
    async def simultaneous(**kwargs):
        inputs = await capture(**kwargs)
        calls[0] += 1
        if calls[0] == 2:
            barrier.set()
        await barrier.wait()
        return inputs
    runner.admission.adapter.capture_verified_inputs = simultaneous
    operations = [operation_id(current["version"], epoch=current["epoch"]) for _ in range(2)]
    results = await asyncio.gather(*[
        runner.admission.execute(owner, account, operation, kind="stage",
                                 parameters=runner._stage_parameters("buy"), quote=QUOTE,
                                 confirmation={"rule_digest": RULE["rule_digest"]})
        for operation in operations], return_exceptions=True)
    assert sum(isinstance(result, PaperConflict) for result in results) == 1
    assert sum(isinstance(result, tuple) for result in results) == 1
    after = await repo.read(owner, account)
    assert len(after["state"]["orders"]) == 1
    assert len(repo.admissions.docs) == 1
    assert after["state"]["cash"] == "1000"


@pytest.mark.asyncio
async def test_source_deadline_refuses_without_funding_or_saving_a_late_capture():
    import asyncio

    repo, owner, account, runner = await ready()
    runner.admission.source_timeout_seconds = 0.001
    async def never_finishes(**kwargs):
        await asyncio.Event().wait()
    runner.admission.adapter.capture_verified_inputs = never_finishes
    before = copy.deepcopy(await repo.read(owner, account))
    with pytest.raises(PaperConflict, match="source.*deadline"):
        await asyncio.wait_for(runner.enter(owner, account, QUOTE), timeout=0.1)
    assert await repo.read(owner, account) == before
    assert repo.admissions.docs == []


@pytest.mark.asyncio
async def test_committed_receipt_survives_quote_expiry_without_recapture():
    repo, owner, account, runner = await ready()
    entry, _ = await runner.enter(owner, account, QUOTE)
    old = copy.deepcopy(await repo.read(owner, account))
    late = NOW + timedelta(minutes=2)
    runner.clock = runner.admission.clock = runner.admission.adapter.clock = lambda: late
    replayed, created = await runner.enter(owner, account, QUOTE)
    assert replayed == entry and created is False
    assert await repo.read(owner, account) == old
    assert runner.admission.adapter.capture_count == 1
