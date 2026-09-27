"""Opt-in isolated, synthetic real-store execution proof. No provider or app startup."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from scripts.verify_paper_storage import check, client, refuses, test_database
from services.agent.paper.execution import new_book, reserved_cash
from services.agent.paper.repository import PaperConflict, PaperRepository, operation_id
from services.agent.paper.service import PreparedPaperService

NOW = datetime(2026, 9, 25, 14, tzinfo=UTC)


def parameters(**changes):
    values = dict(contract_id="synthetic-option", product_kind="option", premium_factor="100",
                  side="buy", quantity=2, limit="2.10", fee_per_unit="0.65", slippage_enabled=True,
                  slippage_method="price", price_increment="0.05", max_quote_age_seconds=60,
                  max_spread="0.20", latency_ms=0, order_expires_at=(NOW + timedelta(minutes=10)).isoformat(),
                  proposal_digest="a" * 64, currency="USD")
    return {**values, **changes}


def quote(key="first", **changes):
    values = dict(source_id=key, contract_id="synthetic-option", size_unit="contracts", bid="1.90", ask="2.00",
                  bid_size=10, ask_size=1, observed_at=NOW.isoformat(), received_at=NOW.isoformat())
    return {**values, **changes}


async def synthetic_admission(*_):
    # Test-only approval. Never imported into any application composition.
    return True


async def execute(args):
    connection = client()
    try:
        await connection.admin.command("ping")
        if args.recover:
            info = json.loads(Path(args.recover).read_text(encoding="utf-8"))
            repo = PaperRepository(connection[test_database(info["database"])])
            current = await repo.read(info["owner"], info["account"])
            check(current["version"] == info["version"] and current["state"]["cash"] == info["cash"],
                  "fresh process exact version and cash")
            check(current["state"]["orders"][info["order"]]["filled"] == 1, "partial order recovered")
            await repo.project(info["owner"], info["account"])
            return dict(status="recovered", process=os.getpid())
        if not args.run or not args.report:
            raise ValueError("Explicit --run and a new report path required")
        report = Path(args.report)
        if report.exists():
            raise ValueError("Refuse to replace verification evidence")
        name = test_database("floww_paper_verify_" + uuid.uuid4().hex)
        check(name not in await connection.list_database_names(), "fresh synthetic database")
        repo = PaperRepository(connection[name])
        await repo.initialize()
        owner, account = str(uuid.uuid4()), str(uuid.uuid4())
        await repo.create(owner, account, new_book("1000", currency="USD"))
        service = PreparedPaperService(repo, admission_check=synthetic_admission, clock=lambda: NOW)
        checks = []

        async def key(selected=account, repository=repo):
            current = await repository.read(owner, selected)
            return operation_id(current["version"], epoch=current["epoch"])

        checks.append(await refuses(PreparedPaperService(repo).stage(owner, account, await key(), parameters(), {}),
                                     PaperConflict, "entry disabled without independent admission"))
        stage_key = await key()
        staged, created = await service.stage(owner, account, stage_key, parameters(), {"test_only": True})
        check(created, "stage persisted")
        opening = staged["body"]["order_id"]
        again, created = await service.stage(owner, account, stage_key, parameters(), {"test_only": True})
        check(not created and again == staged, "same stage receipt")
        checks.append("same stage request returns original durable receipt")
        checks.append(await refuses(service.stage(owner, account, stage_key, parameters(quantity=1), {"test_only": True}),
                                     PaperConflict, "changed stage body refused"))
        fill_key = await key()
        results = await asyncio.gather(*(service.quote(owner, account, fill_key, opening, quote()) for _ in range(12)))
        check(sum(created for _, created in results) == 1, "one concurrent fill")
        check(len({receipt["_id"] for receipt, _ in results}) == 1, "same concurrent receipt")
        current = await repo.read(owner, account)
        check(Decimal(current["state"]["cash"]) == Decimal("794.35"), "one partial cash debit")
        checks.append("twelve concurrent identical fills change cash once")
        checks.append(await refuses(service.quote(owner, account, await key(), opening, quote()),
                                     PaperConflict, "fresh request cannot claim an already recorded quote fill"))
        check((await repo.read(owner, account))["version"] == current["version"], "semantic duplicate no new version")
        work = report.with_suffix(".restart.json")
        work.write_text(json.dumps(dict(database=name, owner=owner, account=account, version=current["version"],
                                        cash=current["state"]["cash"], order=opening)), encoding="utf-8")
        child = subprocess.run([sys.executable, "-m", "scripts.verify_paper_execution", "--recover", str(work)],
                               capture_output=True, text=True, timeout=15,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        check(child.returncode == 0, "fresh process recovery: " + child.stderr)
        checks.append("fresh process recovers partial fill, reservation and cash")
        await service.quote(owner, account, await key(), opening, quote("entry2"))
        current = await repo.read(owner, account)
        check(Decimal(current["state"]["cash"]) == Decimal("588.70"), "second partial debit")
        staged, _ = await service.stage(owner, account, await key(),
                                        parameters(side="sell", structure_id=opening, limit="2.30"), {})
        closing = staged["body"]["order_id"]
        await service.quote(owner, account, await key(), closing, quote("close1", bid="2.50", ask="2.60", bid_size=1))
        await service.quote(owner, account, await key(), closing, quote("close2", bid="2.40", ask="2.50", bid_size=1))
        current = await repo.read(owner, account)
        check(Decimal(current["state"]["cash"]) == Decimal("1067.40"), "hand calculated final cash")
        check(Decimal(current["state"]["realized_result"]) == Decimal("67.40"), "hand calculated net result")
        check(not current["state"]["positions"], "closed exact structure")
        checks.append("two partial entries and exits produce exact final cash 1067.40 and result 67.40")
        checks.append(await refuses(service.archive(owner, account, await key(), closing), PaperConflict,
                                     "archive refused before immutable terminal history"))
        await repo.project(owner, account)
        await service.archive(owner, account, await key(), closing)
        await service.archive(owner, account, await key(), opening)
        current = await repo.read(owner, account)
        check(not current["state"]["orders"] and current["reserve_events"] == 0, "terminal capacity released")
        checks.append(await refuses(service.quote(owner, account, await key(), opening, quote("late")),
                                     PaperConflict, "late fill cannot recreate archived order"))
        await repo.project(owner, account)
        saved = await repo.events.find({"scope_id": current["_id"]}).sort("version", 1).to_list(length=100)
        check([item["version"] for item in saved] == list(range(1, current["version"] + 1)), "contiguous journal")
        check(sum(Decimal(item["body"]["accounting"]["cash_change"]) for item in saved
                  if item["body"]["kind"] == "paper_fill") == Decimal("67.40"), "journal cash ties")
        checks.append("immutable journal versions and fill cash reconcile to saved account")

        # Mutation during an await must never replace the already frozen quote.
        selected = str(uuid.uuid4())
        await repo.create(owner, selected, new_book("1000", currency="USD"))
        stage, _ = await service.stage(owner, selected, await key(selected), parameters(quantity=1), {})
        mutable = quote("frozen", ask_size=1)
        original_receipt = repo.receipt

        async def mutate_after_copy(*arguments, **kwargs):
            mutable.update(bid="1.70", ask="1.80")
            return await original_receipt(*arguments, **kwargs)

        repo.receipt = mutate_after_copy
        frozen, _ = await service.quote(owner, selected, await key(selected), stage["body"]["order_id"], mutable)
        repo.receipt = original_receipt
        check(frozen["body"]["accounting"]["fill_price"] == "2.05", "frozen quote price")
        checks.append("quote mutated during await cannot change frozen fill price")

        # Fill a valid outbox to its total pending+reserved cap; exits consume
        # the allowance prepaid by entry and require no added capacity.
        bounded = PaperRepository(connection[name], pending_limit=30)
        selected = str(uuid.uuid4())
        await bounded.create(owner, selected, new_book("1000", currency="USD"))
        bounded_service = PreparedPaperService(bounded, admission_check=synthetic_admission, clock=lambda: NOW)
        stage, _ = await bounded_service.stage(owner, selected, await key(selected, bounded), parameters(quantity=1), {})
        opening = stage["body"]["order_id"]
        await bounded_service.quote(owner, selected, await key(selected, bounded), opening, quote("bounded"))
        while True:
            current = await bounded.read(owner, selected)
            if len(current["pending_events"]) + current["reserve_events"] == 30:
                break
            await bounded.commit(owner, selected, await key(selected, bounded), {"kind": "test_audit"},
                                 current["state"], {"kind": "test_audit"})
        before = current["reserve_events"]
        close, _ = await bounded_service.stage(owner, selected, await key(selected, bounded),
                                               parameters(side="sell", quantity=1, structure_id=opening, limit="1.80"), {})
        await bounded_service.quote(owner, selected, await key(selected, bounded), close["body"]["order_id"], quote("bounded-close"))
        current = await bounded.read(owner, selected)
        check(current["reserve_events"] == before - 2 and not current["state"]["positions"], "reserved exit completes")
        checks.append("at full valid event capacity, close stage and fill consume reserved space")
        checks.append(await refuses(bounded_service.replenish(owner, selected, await key(selected, bounded)),
                                     PaperConflict, "replenishment refused while history pending"))
        await bounded.project(owner, selected)
        checks.append(await refuses(bounded_service.replenish(owner, selected, await key(selected, bounded)),
                                     PaperConflict, "retained close cannot be hidden by replenishment"))
        await bounded_service.archive(owner, selected, await key(selected, bounded), close["body"]["order_id"])
        await bounded.project(owner, selected)
        await bounded_service.replenish(owner, selected, await key(selected, bounded))
        checks.append("capacity replenishes only after history is durable and slot checks pass")

        selected = str(uuid.uuid4())
        created = await repo.create(owner, selected, new_book("500", currency="USD"))
        race = await asyncio.gather(*(service.stage(owner, selected, operation_id(0, epoch=created["epoch"]),
                                                   parameters(), {}) for _ in range(2)), return_exceptions=True)
        check(sum(isinstance(item, PaperConflict) for item in race) == 1, "one competing entry refused")
        current = await repo.read(owner, selected)
        check(len(current["state"]["orders"]) == 1 and reserved_cash(current["state"]) == Decimal("421.30"),
              "one exact cash reservation")
        checks.append("different entry requests cannot both reserve the last buying power")

        selected = str(uuid.uuid4())
        await repo.create(owner, selected, new_book("1000", currency="USD"))
        first, _ = await service.stage(owner, selected, await key(selected), parameters(quantity=1), {})
        second, _ = await service.stage(owner, selected, await key(selected), parameters(quantity=1), {})
        await service.quote(owner, selected, await key(selected), first["body"]["order_id"], quote("retired"))
        await repo.project(owner, selected)
        future = PreparedPaperService(repo, clock=lambda: NOW + timedelta(seconds=301))
        await future.replenish(owner, selected, await key(selected))
        current = await repo.read(owner, selected)
        check(not current["state"]["quotes"], "old liquidity retired")
        checks.append(await refuses(service.quote(owner, selected, await key(selected),
                                                   second["body"]["order_id"], quote("retired")), PaperConflict,
                                     "saved clock watermark prevents retired quote size from returning"))
        check((await repo.read(owner, selected))["state"] == current["state"], "rollback refusal leaves state exact")
        result = dict(status="pass", checks=checks, count=len(checks), database=name,
                      python=sys.version, production_admission=False, provider_calls=0, broker_orders=0,
                      limitation="Synthetic prepared single-leg long lifecycle; no production release or expiry acceptance")
        report.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
    finally:
        connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--report")
    parser.add_argument("--recover")
    print(json.dumps(asyncio.run(execute(parser.parse_args())), indent=2))
