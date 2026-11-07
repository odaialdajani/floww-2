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

import copy
import sys
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pymongo.errors import DuplicateKeyError  # noqa: E402

from scripts.paper_synthetic_fixture import SyntheticPaperAdapter, persist_synthetic_policy  # noqa: E402
from services.agent.paper.admission import PaperExecutionAuthority  # noqa: E402
from services.agent.paper.execution import new_book  # noqa: E402
from services.agent.paper.guarded_repository import GuardedPaperRepository  # noqa: E402
from services.agent.paper.repository import (  # noqa: E402
    PaperConflict,
    operation_id,
)
from services.agent.paper.runner import PaperRunner as UnadmittedPaperRunner  # noqa: E402
from services.execution_lease import acquire_lease  # noqa: E402

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

    def limit(self, count):
        self._rows = self._rows[:count]
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
        self.server_now = NOW
        self.unique_indexes = []

    async def find_one(self, query):
        for doc in self.docs:
            if self.matches(doc, query):
                return copy.deepcopy(doc)
        return None

    def matches(self, doc, query):
        missing = object()
        def field(path):
            value = doc
            for part in path.split("."):
                if not isinstance(value, dict) or part not in value:
                    return missing
                value = value[part]
            return value
        for key, value in query.items():
            if key == "$expr":
                for predicate in value["$and"]:
                    op, operands = next(iter(predicate.items()))
                    left = (self.server_clock() if hasattr(self, "server_clock") else self.server_now) if operands[0] == "$$NOW" else operands[0]
                    right = operands[1]
                    if not ({"$gte": left >= right, "$lt": left < right}[op]):
                        return False
            elif isinstance(value, dict):
                actual = field(key)
                for operator, operand in value.items():
                    if operator == "$exists":
                        if (actual is not missing) != operand:
                            return False
                    elif operator == "$gt":
                        if actual is missing or not actual > operand:
                            return False
                    else:
                        raise AssertionError("Unsupported fake selector: "+operator)
            elif field(key) != value:
                return False
        return True

    def find(self, query, **_kwargs):
        return _FakeCursor([copy.deepcopy(doc) for doc in self.docs if self.matches(doc, query)], query)

    async def insert_one(self, doc):
        if any(item["_id"] == doc["_id"] for item in self.docs):
            raise DuplicateKeyError("isolated duplicate")
        for keys in self.unique_indexes:
            if any(tuple(item.get(key) for key in keys) == tuple(doc.get(key) for key in keys) for item in self.docs):
                raise DuplicateKeyError("isolated compound duplicate")
        self.docs.append(copy.deepcopy(doc))

    async def update_one(self, query, update):
        target = next((doc for doc in self.docs if self.matches(doc, query)), None)
        modified = 0
        if target is not None:
            modified = 1
            for key, value in update.get("$set", {}).items():
                target[key] = value
            for key, value in update.get("$push", {}).items():
                target.setdefault(key, []).append(copy.deepcopy(value))
            for key, value in update.get("$pull", {}).items():
                target[key] = [row for row in target[key] if not all(row.get(k) == v for k, v in value.items())]
        return type("R", (), {"modified_count": modified, "matched_count": modified})()

    async def create_index(self, keys, **kwargs):
        if kwargs.get("unique"):
            self.unique_indexes.append(tuple(key for key, direction in keys))
        return None

    async def count_documents(self, query, **_kwargs):
        return sum(1 for doc in self.docs if self.matches(doc, query))

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


# Acceptance cases explicitly install synthetic provenance and a real local
# executor lease. Production PaperRunner still defaults to denied admission.
def PaperRunner(repo, *, quote_reader, clock):
    lease_dir = tempfile.TemporaryDirectory(prefix="floww-paper-test-")
    acquired = acquire_lease(str(Path(lease_dir.name) / "executor.lease"), "synthetic-owner")
    assert acquired["ok"] is True
    repo.accounts.server_clock = clock
    adapter = SyntheticPaperAdapter(repo, clock=clock)
    authority = PaperExecutionAuthority(str(Path(lease_dir.name) / "executor.lease"), acquired["token"], lambda: "running")
    runner = UnadmittedPaperRunner(repo, quote_reader=quote_reader, clock=clock,
                                   admission_adapter=adapter, execution_authority=authority)
    runner._test_lease_dir = lease_dir
    actual_start = runner.start
    async def trusted_synthetic_start(owner, account, rule, policy):
        current = await repo.read(owner, account)
        if current is not None and "execution_control" not in current:
            await runner.admission.bind_execution(owner, account)
        return await actual_start(owner, account, rule, policy)
    runner.start = trusted_synthetic_start
    return runner


async def _fresh_repo(*, with_policy=True):
    repo = GuardedPaperRepository(_FakeDatabase())
    await repo.initialize()
    owner, account = str(uuid.uuid4()), str(uuid.uuid4())
    await repo.create(owner, account, new_book("1000", currency="USD"))
    if with_policy:
        await persist_synthetic_policy(repo, owner, account, POLICY["body"], now=NOW)
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
        # Retire the unfilled first intent through its real terminal history.
        # Guarded accounts reserve finite recovery storage for each structure.
        await runner.cancel(owner, account, entry_receipt["order_id"])
        await repo.project(owner, account)
        from services.agent.paper.repository import operation_id
        from services.agent.paper.service import PreparedPaperService
        current = await repo.read(owner, account)
        await PreparedPaperService(repo).archive(owner, account,
            operation_id(current["version"], epoch=current["epoch"]), entry_receipt["order_id"])
        # Re-binding clears the stale operation and enables fresh work at the
        # current account version, after explicit history/credit recovery.
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
