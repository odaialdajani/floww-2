"""Isolated internal paper runner CLI — Task 3.

Runs a synthetic paper lifecycle against an isolated Mongo database
(prefix floww_paper_run_*) and writes a JSON report/receipt. Composes the
guarded paper sequence through PaperRunner over injected quote observations.
No broker import and no broker order method anywhere in this module.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient

from scripts.paper_synthetic_fixture import SyntheticPaperAdapter, persist_synthetic_policy
from services.agent.paper.admission import PaperExecutionAuthority
from services.agent.paper.execution import new_book
from services.agent.paper.guarded_repository import GuardedPaperRepository
from services.agent.paper.runner import PaperRunner
from services.execution_lease import acquire_lease, release_lease

PREFIX = "floww_paper_run_"

NOW = datetime.now(UTC)

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


def check(value, label):
    if not value:
        raise AssertionError(label)


def client():
    return AsyncIOMotorClient("mongodb://127.0.0.1:27017/?directConnection=true",
                              serverSelectionTimeoutMS=2000, socketTimeoutMS=5000, tz_aware=True)


def test_database(name):
    if not re.fullmatch(PREFIX + r"[a-f0-9]{32}", name):
        raise ValueError("Only an isolated synthetic run database is allowed")
    return name


async def execute(args):
    connection = client()
    lease_directory = tempfile.TemporaryDirectory(prefix="floww-paper-synthetic-")
    lease_path = str(Path(lease_directory.name) / "executor.lease")
    lease = acquire_lease(lease_path, "isolated-synthetic-cli")
    if not lease.get("ok"):
        connection.close()
        lease_directory.cleanup()
        raise ValueError("Isolated paper executor lease unavailable")
    try:
        await connection.admin.command("ping")
        report_path = Path(args.report)
        if report_path.exists():
            raise ValueError("Refuse to overwrite earlier verification evidence")
        name = test_database(PREFIX + uuid.uuid4().hex)
        check(name not in await connection.list_database_names(), "fresh isolated database")
        repo = GuardedPaperRepository(connection[name])
        await repo.initialize()
        owner, account = str(uuid.uuid4()), str(uuid.uuid4())
        await repo.create(owner, account, new_book("1000", currency="USD"))
        policy = await persist_synthetic_policy(repo, owner, account, POLICY["body"], now=NOW)
        adapter = SyntheticPaperAdapter(repo, clock=lambda: datetime.now(UTC))
        authority = PaperExecutionAuthority(lease_path, lease["token"], lambda: "running")
        runner = PaperRunner(repo, quote_reader=lambda: dict(QUOTE), clock=lambda: datetime.now(UTC),
                             admission_adapter=adapter, execution_authority=authority)
        started = await runner.start(owner, account, RULE, policy)
        check(started["rule_digest"] == RULE["rule_digest"], "runner started with frozen rule")
        entry_receipt, created = await runner.enter(owner, account, QUOTE)
        check(created, "entry staged")
        check(entry_receipt["kind"] == "paper_order_staged", "staged entry receipt")
        fill_receipt, changed = await runner.enter_fill(
            owner, account, entry_receipt["order_id"], QUOTE,
        )
        check(changed, "entry filled")
        report = await runner.reconcile(owner, account)
        check(report["cash"] == "794.35", "reconciled cash")
        check(report["realized_result"] == "0", "reconciled realized result")
        check(len(report["positions"]) == 1, "reconciled position")
        check(report["positions"][0]["quantity"] == 1, "position quantity")
        check(len(report["working_orders"]) == 0, "no working orders after fill")
        check(len(report["fills"]) == 1, "one reconciled fill")
        check(report["fills"][0]["order_id"] == entry_receipt["order_id"], "fill ties to order")
        result = dict(status="pass", database=name, owner=owner, account=account,
                      started=started, entry=entry_receipt, fill=fill_receipt,
                      reconciliation=report, python=sys.version, broker_orders=0,
                      limitation="Synthetic isolated run; no broker or production account access")
        report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
    finally:
        release_lease(lease_path, lease["token"])
        lease_directory.cleanup()
        connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--report")
    args = parser.parse_args()
    if not args.run:
        print(json.dumps({"status": "reachable", "broker_orders": 0}, indent=2))
        sys.exit(0)
    if not args.report:
        raise ValueError("--report is required with --run")
    print(json.dumps(asyncio.run(execute(args)), indent=2))
