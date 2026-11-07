"""Acceptance pins for the isolated internal paper runner (Task 3).

The runner composes the guarded paper sequence over an injected quote reader
and injected repository. It must:

- refuse to start without an explicit frozen rule and policy,
- refuse to start a restored account while recovery_pending,
- refuse duplicate submissions,
- refuse pre-latency quotes,
- keep missing / stale / short-size / malformed quotes distinct,
- block new entries while an exit is unresolved,
- preserve risk-reducing exits,
- require restart/re-bind after recovery, refusing stale-epoch operations,
- reconcile the durable journal to cash, positions, working orders, fills and P&L,
- never import PublicBroker or any broker order method (runner and CLI).

These pins run OFFLINE over the real GuardedPaperRepository and execution
transitions against fake in-memory Mongo collections (no Mongo, no network, no
broker). They are invariant pins: every failure here is a real defect.
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.agent.paper.execution import new_book  # noqa: E402
from services.agent.paper.guarded_repository import GuardedPaperRepository  # noqa: E402
from services.agent.paper.repository import (  # noqa: E402
    PaperConflict,
    operation_id,
)
from services.agent.paper.runner import PaperRunner  # noqa: E402

OWNER = str(uuid.uuid4())
ACCOUNT = str(uuid.uuid4())
NOW = datetime(2026, 11, 6, 14, tzinfo=UTC)

# --- minimal frozen rule and explicit policy used by every case -------------

RULE = {
    "rule_id": "frozen-synthetic-rule",
    "rule_digest": "b" * 64,
    "contract_id": "synthetic-option",
    "product_kind": "option",
    "premium_factor": "100",
    "side": "buy",
    "quantity": 1,
    "limit": "2.10",
    "fee_per_unit": "0.65",
    "slippage_enabled": True,
    "slippage_method": "price",
    "price_increment": "0.05",
    "max_quote_age_seconds": 60,
    "max_spread": "0.20",
    "latency_ms": 0,
    "order_expires_at": (NOW + timedelta(minutes=10)).isoformat(),
    "proposal_digest": "a" * 64,
    "currency": "USD",
}

POLICY = {
    "policy_id": "frozen-synthetic-policy",
    "policy_version": 1,
    "body": {
        "currency": "USD",
        "account_mode": "long_only_cash",
        "exposure_basis": "marked_holdings_pending_debits_and_cost_buffers",
        "loss_boundary": "strict_less_than",
        "exposure_boundary": "less_than_or_equal",
        "peak_coverage": "sampled_only",
        "breach_behavior": "current_observation_only",
        "risk_reduction": "allow_verified_reduction_with_known_costs",
        "buffer_basis": "linear_per_unit",
        "closing_reservation": "included_in_exit_cost_buffer",
        "limits": {
            "per_trade_max_loss": "500",
            "daily_loss_limit": "1000",
            "observed_drawdown_limit": "900",
            "max_committed_exposure": "5000",
        },
        "valuation": {
            "mark_method": "bid",
            "max_mark_age_seconds": 60,
            "max_spread": "0.20",
        },
    },
}

QUOTE = {
    "source_id": "synthetic-quote",
    "contract_id": "synthetic-option",
    "size_unit": "contracts",
    "bid": "1.90",
    "ask": "2.00",
    "bid_size": 10,
    "ask_size": 1,
    "observed_at": NOW.isoformat(),
    "received_at": NOW.isoformat(),
}

LATE_QUOTE = {**QUOTE, "observed_at": (NOW - timedelta(seconds=121)).isoformat()}


# --- fake in-memory Mongo collections ---------------------------------------

class _FakeCursor:
    def __init__(self, docs, query=None):
        self._rows = list(docs)
        self._query = query or {}
        self._i = 0

    def sort(self, _key, _direction):
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._i >= len(self._rows):
            raise StopAsyncIteration
        row = self._rows[self._i]
        self._i += 1
        return row


class _FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []
        self.write_concern = None

    async def find_one(self, query):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return doc
        return None

    def find(self, query, **_kwargs):
        return _FakeCursor(self.docs, query)

    async def insert_one(self, doc):
        self.docs.append(doc)

    async def update_one(self, query, update):
        target = await self.find_one(query)
        modified = 0
        if target is not None:
            modified = 1
            for key, value in update.get("$set", {}).items():
                target[key] = value
            for key, value in update.get("$push", {}).items():
                target.setdefault(key, []).append(value)
        return type("R", (), {"modified_count": modified})()

    async def create_index(self, *args, **kwargs):
        return None

    async def count_documents(self, query, **_kwargs):
        return sum(1 for doc in self.docs if all(doc.get(k) == v for k, v in query.items()))

    async def delete_one(self, query):
        for i, doc in enumerate(self.docs):
            if all(doc.get(k) == v for k, v in query.items()):
                self.docs.pop(i)
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()


class _FakeDatabase:
    def get_collection(self, name, write_concern=None):
        col = _FakeCollection()
        col.write_concern = write_concern
        return col


async def _fresh_repo():
    repo = GuardedPaperRepository(_FakeDatabase())
    await repo.initialize()
    owner, account = str(uuid.uuid4()), str(uuid.uuid4())
    await repo.create(owner, account, new_book("1000", currency="USD"))
    return repo, owner, account


async def _recovery_pending_repo():
    repo, owner, account = await _fresh_repo()
    doc = repo.accounts.docs[0]
    doc["state"]["recovery_pending"] = True
    return repo, owner, account


def _quote_changes():
    return dict(QUOTE)


class TestPaperRunnerAcceptance:
    @pytest.mark.asyncio
    async def test_positive_latency_uses_staged_order_time_for_entry_and_exit(self):
        repo, owner, account = await _fresh_repo()
        clock = [NOW]
        runner = PaperRunner(repo, quote_reader=_quote_changes, clock=lambda: clock[0])
        await runner.start(owner, account, {**RULE, "latency_ms": 1000}, POLICY)
        entry, created = await runner.enter(owner, account, QUOTE)
        assert created is True
        clock[0] = NOW + timedelta(milliseconds=500)
        early = {**QUOTE, "source_id": "early", "observed_at": clock[0].isoformat(),
                 "received_at": clock[0].isoformat()}
        with pytest.raises(PaperConflict, match="latency"):
            await runner.enter_fill(owner, account, entry["order_id"], early)
        clock[0] = NOW + timedelta(seconds=1)
        with pytest.raises(PaperConflict, match="latency"):
            await runner.enter_fill(owner, account, entry["order_id"], QUOTE)
        fresh = {**QUOTE, "source_id": "entry-ready", "observed_at": clock[0].isoformat(),
                 "received_at": clock[0].isoformat()}
        _, filled = await runner.enter_fill(owner, account, entry["order_id"], fresh)
        assert filled is True
        exit_rule = {**RULE, "structure_id": entry["structure_id"], "limit": "1.80",
                     "proposal_digest": "c" * 64}
        exit_order, staged = await runner.exit(owner, account, exit_rule, fresh)
        assert staged is True
        clock[0] = NOW + timedelta(seconds=2)
        closing = {**fresh, "source_id": "exit-ready", "observed_at": clock[0].isoformat(),
                   "received_at": clock[0].isoformat()}
        _, closed = await runner.exit_fill(owner, account, exit_order["order_id"], closing)
        assert closed is True
        report = await runner.reconcile(owner, account)
        assert report["cash_reconciled"] is True
        assert report["positions"] == report["working_orders"] == []
        assert len(report["fills"]) == 2

    @pytest.mark.asyncio
    async def test_missing_frozen_rule_refused(self):
        repo, owner, account = await _fresh_repo()
        runner = PaperRunner(repo, quote_reader=lambda: _quote_changes(), clock=lambda: NOW)
        with pytest.raises(ValueError, match="frozen rule"):
            await runner.start(owner, account, None, POLICY)

    @pytest.mark.asyncio
    async def test_missing_policy_refused(self):
        repo, owner, account = await _fresh_repo()
        runner = PaperRunner(repo, quote_reader=lambda: _quote_changes(), clock=lambda: NOW)
        with pytest.raises(ValueError, match="policy"):
            await runner.start(owner, account, RULE, None)

    @pytest.mark.asyncio
    async def test_pre_latency_quote_refused(self):
        repo, owner, account = await _fresh_repo()
        runner = PaperRunner(repo, quote_reader=lambda: _quote_changes(), clock=lambda: NOW)
        slow_rule = {**RULE, "latency_ms": 1000}
        await runner.start(owner, account, slow_rule, POLICY)
        quote = {**QUOTE, "observed_at": NOW.isoformat(), "received_at": NOW.isoformat()}
        staged, created = await runner.enter(owner, account, quote)
        assert created is True
        with pytest.raises(PaperConflict, match="latency"):
            await runner.enter_fill(owner, account, staged["order_id"], quote)

    @pytest.mark.asyncio
    async def test_stale_quote_refused(self):
        repo, owner, account = await _fresh_repo()
        runner = PaperRunner(repo, quote_reader=lambda: _quote_changes(), clock=lambda: NOW)
        await runner.start(owner, account, RULE, POLICY)
        with pytest.raises((PaperConflict, ValueError), match="stale"):
            await runner.enter(owner, account, LATE_QUOTE)

    @pytest.mark.asyncio
    async def test_zero_size_refused(self):
        repo, owner, account = await _fresh_repo()
        runner = PaperRunner(repo, quote_reader=lambda: _quote_changes(), clock=lambda: NOW)
        await runner.start(owner, account, RULE, POLICY)
        quote = {**QUOTE, "bid_size": 0, "ask_size": 0}
        with pytest.raises((PaperConflict, ValueError), match="size"):
            await runner.enter(owner, account, quote)

    @pytest.mark.asyncio
    async def test_duplicate_submission_refused(self):
        repo, owner, account = await _fresh_repo()
        runner = PaperRunner(repo, quote_reader=lambda: _quote_changes(), clock=lambda: NOW)
        await runner.start(owner, account, RULE, POLICY)
        receipt1, created1 = await runner.enter(owner, account, QUOTE)
        assert created1 is True
        receipt2, created2 = await runner.enter(owner, account, QUOTE)
        assert created2 is False
        assert receipt2 == receipt1

    @pytest.mark.asyncio
    async def test_unresolved_exit_blocks_new_entries(self):
        repo, owner, account = await _fresh_repo()
        runner = PaperRunner(repo, quote_reader=lambda: _quote_changes(), clock=lambda: NOW)
        await runner.start(owner, account, RULE, POLICY)
        entry_receipt, _ = await runner.enter(owner, account, QUOTE)
        order_id = entry_receipt["order_id"]
        structure_id = entry_receipt["structure_id"]
        await runner.enter_fill(owner, account, order_id, QUOTE)

        close_rule = {**RULE, "side": "sell", "structure_id": structure_id,
                      "quantity": 1, "proposal_digest": "c" * 64}
        close_receipt, _ = await runner.exit(owner, account, close_rule, QUOTE)
        assert close_receipt["status"] == "working"

        second_entry = {**RULE, "proposal_digest": "d" * 64}
        with pytest.raises(PaperConflict, match="(?i)unresolved"):
            await runner.enter(owner, account, second_entry)

    @pytest.mark.asyncio
    async def test_risk_reducing_exit_preserved(self):
        repo, owner, account = await _fresh_repo()
        runner = PaperRunner(repo, quote_reader=lambda: _quote_changes(), clock=lambda: NOW)
        await runner.start(owner, account, RULE, POLICY)
        entry_receipt, _ = await runner.enter(owner, account, QUOTE)
        order_id = entry_receipt["order_id"]
        structure_id = entry_receipt["structure_id"]
        await runner.enter_fill(owner, account, order_id, QUOTE)

        close_rule = {**RULE, "side": "sell", "structure_id": structure_id,
                      "quantity": 1, "proposal_digest": "c" * 64}
        close_receipt, created = await runner.exit(owner, account, close_rule, QUOTE)
        assert created is True
        assert close_receipt["kind"] == "paper_order_staged"
        assert close_receipt["status"] == "working"
        # A risk-reducing close stages while the entry position is held.
        report = await runner.reconcile(owner, account)
        working = [o for o in report["working_orders"] if o["side"] == "sell"]
        assert len(working) == 1

    @pytest.mark.asyncio
    async def test_no_public_broker_in_import_graph(self):
        import services.agent.paper.runner as runner_module
        source = Path(runner_module.__file__).read_text(encoding="utf-8")
        assert "PublicBroker" not in source
        assert "place_order" not in source

    @pytest.mark.asyncio
    async def test_journal_reconciles_to_cash_positions_orders_fills_pnl(self):
        repo, owner, account = await _fresh_repo()
        runner = PaperRunner(repo, quote_reader=lambda: _quote_changes(), clock=lambda: NOW)
        await runner.start(owner, account, RULE, POLICY)
        entry_receipt, _ = await runner.enter(owner, account, QUOTE)
        order_id = entry_receipt["order_id"]
        fill_receipt, changed = await runner.enter_fill(owner, account, order_id, QUOTE)
        assert changed is True

        report = await runner.reconcile(owner, account)
        assert report["cash"] == "794.35"
        assert report["realized_result"] == "0"
        assert len(report["positions"]) == 1
        assert report["positions"][0]["quantity"] == 1
        assert len(report["working_orders"]) == 0
        assert len(report["fills"]) == 1
        assert report["fills"][0]["order_id"] == order_id
        assert report["cash_reconciled"] is True, \
            "journal fill cash and realized P&L must reconcile to the account"

    @pytest.mark.asyncio
    async def test_start_refuses_recovery_pending_account(self):
        repo, owner, account = await _recovery_pending_repo()
        runner = PaperRunner(repo, quote_reader=lambda: _quote_changes(), clock=lambda: NOW)
        with pytest.raises(PaperConflict, match="recovery_pending"):
            await runner.start(owner, account, RULE, POLICY)

    @pytest.mark.asyncio
    async def test_restart_requires_rebind_before_reuse(self):
        repo, owner, account = await _fresh_repo()
        runner = PaperRunner(repo, quote_reader=lambda: _quote_changes(), clock=lambda: NOW)
        await runner.start(owner, account, RULE, POLICY)
        entry_receipt, created = await runner.enter(owner, account, QUOTE)
        assert created is True
        # Simulate a restart: the prior entry operation is stale and must not
        # be reused without an explicit re-bind.
        runner._start_op = None
        with pytest.raises(ValueError, match="restarted|rebind"):
            await runner.enter(owner, account, QUOTE)
        # Re-binding clears the stale operation and enables fresh work at the
        # current account version.
        await runner._rebind(owner, account)
        again, created2 = await runner.enter(owner, account, QUOTE)
        assert created2 is True, "rebind must allow fresh work at the current version"
        assert again["order_id"] != entry_receipt["order_id"], \
            "a restarted runner must not replay the pre-restart entry receipt"

    @pytest.mark.asyncio
    async def test_recovery_epoch_stale_operation_refused(self):
        repo, owner, account = await _fresh_repo()
        runner = PaperRunner(repo, quote_reader=lambda: _quote_changes(), clock=lambda: NOW)
        await runner.start(owner, account, RULE, POLICY)
        await runner.enter(owner, account, QUOTE)
        # Advance the account to a new recovery epoch, mimicking a restored
        # copy; the runner's bound epoch/operation is now stale.
        doc = repo.accounts.docs[0]
        doc["epoch"] = str(uuid.uuid4())
        with pytest.raises(PaperConflict, match="epoch|recovery"):
            await runner.enter(owner, account, QUOTE)

    @pytest.mark.asyncio
    async def test_short_size_refused(self):
        repo, owner, account = await _fresh_repo()
        runner = PaperRunner(repo, quote_reader=lambda: _quote_changes(), clock=lambda: NOW)
        await runner.start(owner, account, RULE, POLICY)
        quote = {**QUOTE, "bid_size": -1, "ask_size": 1}
        with pytest.raises(ValueError, match="size"):
            await runner.enter(owner, account, quote)

    @pytest.mark.asyncio
    async def test_non_int_size_refused(self):
        repo, owner, account = await _fresh_repo()
        runner = PaperRunner(repo, quote_reader=lambda: _quote_changes(), clock=lambda: NOW)
        await runner.start(owner, account, RULE, POLICY)
        quote = {**QUOTE, "bid_size": "ten", "ask_size": 1}
        with pytest.raises(ValueError, match="whole count"):
            await runner.enter(owner, account, quote)

    @pytest.mark.asyncio
    async def test_malformed_quote_fields_named_value_error(self):
        repo, owner, account = await _fresh_repo()
        runner = PaperRunner(repo, quote_reader=lambda: _quote_changes(), clock=lambda: NOW)
        await runner.start(owner, account, RULE, POLICY)
        with pytest.raises(ValueError, match="source quote identity"):
            await runner.enter(owner, account, {**QUOTE, "source_id": ""})
        with pytest.raises(ValueError, match="from the future"):
            await runner.enter(owner, account,
                               {**QUOTE, "observed_at": (NOW + timedelta(days=1)).isoformat()})

    @pytest.mark.asyncio
    async def test_naive_datetime_refused(self):
        repo, owner, account = await _fresh_repo()
        runner = PaperRunner(repo, quote_reader=lambda: _quote_changes(), clock=lambda: NOW)
        await runner.start(owner, account, RULE, POLICY)
        naive = {**QUOTE, "observed_at": "2026-11-06T14:00:00", "received_at": NOW.isoformat()}
        with pytest.raises(ValueError, match="timezone"):
            await runner.enter(owner, account, naive)

    @pytest.mark.asyncio
    async def test_no_fill_returns_none_false(self):
        repo, owner, account = await _fresh_repo()
        runner = PaperRunner(repo, quote_reader=lambda: _quote_changes(), clock=lambda: NOW)
        await runner.start(owner, account, RULE, POLICY)
        entry_receipt, _ = await runner.enter(owner, account, QUOTE)
        order_id = entry_receipt["order_id"]
        # A quote priced outside the limit produces no fill: (None, False).
        out_of_limit = {**QUOTE, "ask": "9.99", "bid": "9.90"}
        result, changed = await runner.enter_fill(owner, account, order_id, out_of_limit)
        assert result is None and changed is False, \
            "a quote that does not fill must return (None, False) and consume nothing"
        report = await runner.reconcile(owner, account)
        assert len(report["fills"]) == 0, "no fill may be recorded when nothing filled"
        assert report["cash_reconciled"] is True

    @pytest.mark.asyncio
    async def test_exit_honors_passed_rule_not_entry_rule(self):
        repo, owner, account = await _fresh_repo()
        runner = PaperRunner(repo, quote_reader=lambda: _quote_changes(), clock=lambda: NOW)
        await runner.start(owner, account, RULE, POLICY)
        entry_receipt, _ = await runner.enter(owner, account, QUOTE)
        order_id = entry_receipt["order_id"]
        structure_id = entry_receipt["structure_id"]
        await runner.enter_fill(owner, account, order_id, QUOTE)

        exit_rule = {**RULE, "side": "sell", "structure_id": structure_id, "quantity": 1,
                     "limit": "3.00", "proposal_digest": "c" * 64}
        close_receipt, created = await runner.exit(owner, account, exit_rule, QUOTE)
        assert created is True
        assert close_receipt["status"] == "working"
        report = await runner.reconcile(owner, account)
        working = [o for o in report["working_orders"] if o["side"] == "sell"]
        assert len(working) == 1
        assert working[0]["quantity"] == exit_rule["quantity"], \
            "exit must honor the passed rule quantity, not the entry rule"
        assert working[0]["reserved_cash"] == "0", \
            "a sell exit reserves no buying power"

    @pytest.mark.asyncio
    async def test_runner_and_cli_have_no_broker_import_path(self):
        import services.agent.paper.runner as runner_module
        runner_source = Path(runner_module.__file__).read_text(encoding="utf-8")
        assert "PublicBroker" not in runner_source
        assert "place_order" not in runner_source
        cli_path = Path(__file__).resolve().parents[2] / "scripts" / "run_paper_run.py"
        cli_source = cli_path.read_text(encoding="utf-8")
        assert "PublicBroker" not in cli_source
        assert "place_order" not in cli_source
