"""Red safety regressions: the isolated runner has no trusted admission seam.

These tests intentionally expose the current bypass; do not mark xfail or
inject an unconditional approval to obtain a green run. All state is fake Mongo
in memory. Policy acceptance below is an explicit synthetic fixture, not an
application account or production approval. The missing production composition
must obtain trusted source frames and independently verified trade-risk evidence,
then fund/persist assessment begin + actual observation + resolution before it
can replace the raw stage/fill calls. A model/caller-provided risk result is not
an implementation of that contract.
"""
from __future__ import annotations

import copy
import sys
import uuid
from datetime import timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_agent_paper_runner import NOW, POLICY, QUOTE, RULE, _fresh_repo  # noqa: E402

from services.agent.paper.policy import create_policy, prepare_policy_change  # noqa: E402
from services.agent.paper.repository import PaperConflict, operation_id  # noqa: E402
from services.agent.paper.runner import PaperRunner  # noqa: E402


async def persisted_synthetic_policy(repo, owner, account, *, per_trade="500", version=1):
    """Use actual policy preparation + commit over isolated fake collections."""
    current = await repo.read(owner, account)
    body = copy.deepcopy(POLICY["body"])
    body["limits"]["per_trade_max_loss"] = per_trade
    prior = current["state"].get("risk_policy")
    policy = create_policy(
        {key: current[key] for key in ("owner", "account_id", "venue", "epoch")},
        body, policy_id=prior["policy_id"] if prior else str(uuid.uuid4()),
        policy_version=version, effective_at=NOW, accepted_at=NOW,
        accepted_by=owner, acceptance_evidence=["synthetic-owner-choice-only"],
        now=NOW, verify_acceptance=lambda _: True,
    )
    state, event = prepare_policy_change(
        current, policy, expected_version=current["version"],
        expected_policy_digest=prior["digest"] if prior else None, now=NOW,
    )
    await repo.commit(owner, account,
                      operation_id(current["version"], epoch=current["epoch"]),
                      {"kind": "synthetic_policy_fixture", "digest": policy["digest"]},
                      state, event)
    return policy


async def started_runner(*, per_trade="500", clock=None):
    repo, owner, account = await _fresh_repo()
    policy = await persisted_synthetic_policy(repo, owner, account, per_trade=per_trade)
    runner = PaperRunner(repo, quote_reader=lambda: dict(QUOTE), clock=clock or (lambda: NOW))
    await runner.start(owner, account, RULE, policy)
    return repo, owner, account, runner


@pytest.mark.asyncio
async def test_entry_refuses_zero_persisted_loss_limit_without_trusted_admission():
    repo, owner, account, runner = await started_runner(per_trade="0")
    before = copy.deepcopy(await repo.read(owner, account))
    with pytest.raises(PaperConflict, match="risk|policy|admission|valuation"):
        await runner.enter(owner, account, QUOTE)
    assert await repo.read(owner, account) == before


@pytest.mark.asyncio
async def test_fill_rechecks_current_policy_lowered_after_staging():
    repo, owner, account, runner = await started_runner()
    entry, created = await runner.enter(owner, account, QUOTE)
    assert created is True
    await persisted_synthetic_policy(repo, owner, account, per_trade="0", version=2)
    before = copy.deepcopy(await repo.read(owner, account))
    with pytest.raises(PaperConflict, match="risk|policy|admission|valuation"):
        await runner.enter_fill(owner, account, entry["order_id"], QUOTE)
    after = await repo.read(owner, account)
    assert after == before
    assert after["state"]["cash"] == "1000"


@pytest.mark.asyncio
async def test_fill_refuses_unknown_full_valuation_even_with_well_formed_policy():
    repo, owner, account, runner = await started_runner()
    entry, _ = await runner.enter(owner, account, QUOTE)
    assert "valuation" not in (await repo.read(owner, account))["state"]
    before = copy.deepcopy(await repo.read(owner, account))
    with pytest.raises(PaperConflict, match="risk|policy|admission|valuation"):
        await runner.enter_fill(owner, account, entry["order_id"], QUOTE)
    assert await repo.read(owner, account) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("size", [None, 0])
@pytest.mark.parametrize("action", ["stage", "fill"])
async def test_existing_zero_and_unknown_size_controls_preserve_the_book(size, action):
    repo, owner, account, runner = await started_runner()
    order = None
    if action == "fill":
        order, _ = await runner.enter(owner, account, QUOTE)
    before = copy.deepcopy(await repo.read(owner, account))
    unknown = {**QUOTE, "ask_size": size}
    with pytest.raises(ValueError, match="size|whole count"):
        if action == "stage":
            await runner.enter(owner, account, unknown)
        else:
            await runner.enter_fill(owner, account, order["order_id"], unknown)
    assert await repo.read(owner, account) == before


@pytest.mark.asyncio
async def test_existing_expired_order_control_preserves_cash_and_receipts():
    clock = [NOW]
    repo, owner, account, runner = await started_runner(clock=lambda: clock[0])
    entry, _ = await runner.enter(owner, account, QUOTE)
    clock[0] = NOW + timedelta(minutes=11)
    quote = {**QUOTE, "source_id": "after-expiry", "observed_at": clock[0].isoformat(),
             "received_at": clock[0].isoformat()}
    before = copy.deepcopy(await repo.read(owner, account))
    with pytest.raises(PaperConflict, match="expired"):
        await runner.enter_fill(owner, account, entry["order_id"], quote)
    assert await repo.read(owner, account) == before
