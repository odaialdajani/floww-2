"""Opt-in synthetic observation proof against an isolated local real store."""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts.paper_synthetic_fixture import SyntheticPaperComposition, synthetic_policy_body
from scripts.verify_paper_storage import check, client, refuses, test_database
from services.agent.paper.guarded_repository import GuardedPaperRepository as PaperRepository
from services.agent.paper.observation_service import PreparedObservationService
from services.agent.paper.repository import PaperCapacity, PaperConflict
from services.agent.paper.valuation import current_observation

NOW = datetime.now(UTC)
POLICY_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "floww-isolated-observation-fixture"))
_FRAME_TIMES = {}


async def synthetic_check(*_):
    return True  # Fixture-only; never wired into application composition.


def parameters(**changes):
    result = dict(contract_id="TEST", product_kind="equity", premium_factor="1", side="buy", quantity=2,
                  limit="101", fee_per_unit="1", slippage_enabled=False, slippage_method="price", price_increment="0",
                  max_quote_age_seconds=60, max_spread="2", latency_ms=0,
                  order_expires_at=(NOW+timedelta(hours=1)).isoformat(), proposal_digest="a"*64, currency="USD")
    return {**result, **changes}


def quote(source="fill-one"):
    return dict(contract_id="TEST", source_id=source, size_unit="shares", bid="99", ask="100", bid_size=10, ask_size=10,
                observed_at=NOW.isoformat(), received_at=NOW.isoformat())


def frame(sequence=0):
    opened = NOW-timedelta(minutes=30)
    if sequence not in _FRAME_TIMES:
        _FRAME_TIMES[sequence] = NOW+timedelta(seconds=sequence) if sequence < 0 else datetime.now(UTC)
    observed = _FRAME_TIMES[sequence]
    return dict(marks=[dict(contract_id="TEST", currency="USD", source_id=f"mark-{sequence}", bid="109", ask="111",
                           observed_at=observed.isoformat(),
                           received_at=observed.isoformat())],
                metadata=[dict(contract_id="TEST", product_kind="equity", premium_factor="1", currency="USD",
                               source_id="verified-contract", verified_at=opened.isoformat())],
                policy=dict(policy_id=POLICY_ID+":1", mark_method="midpoint", max_mark_age_seconds=60,
                            max_spread="2", daily_loss_limit="50", drawdown_limit="40", max_gross_exposure="1000"),
                session=dict(session_id="synthetic-session", calendar_version="synthetic-calendar", source_id="session-source",
                             opened_at=opened.isoformat(), closed_at=(NOW+timedelta(hours=6)).isoformat()),
                session_open=dict(session_id="synthetic-session", source_id="synthetic-opening-equity",
                                  observed_at=opened.isoformat(), equity="1000"))


async def execute(args):
    connection = client()
    compositions = []
    try:
        await connection.admin.command("ping")
        if args.recover:
            info = json.loads(Path(args.recover).read_text(encoding="utf-8"))
            repo = PaperRepository(connection[test_database(info["database"])])
            doc = await repo.read(info["owner"], info["account"])
            check(doc["state"]["valuation"] == info["valuation"], "fresh process saved observation exact")
            check(current_observation(doc, now=NOW)["status"] == "current", "fresh process binding current")
            await repo.project(info["owner"], info["account"])
            return dict(status="recovered", process=os.getpid())
        if not args.run or not args.report:
            raise ValueError("Explicit --run and a fresh report path required")
        report = Path(args.report)
        if report.exists():
            raise ValueError("Refuse to replace evidence")
        database = test_database("floww_paper_verify_"+uuid.uuid4().hex)
        check(database not in await connection.list_database_names(), "fresh isolated database")
        repo = PaperRepository(connection[database])
        await repo.initialize()
        owner, account = str(uuid.uuid4()), str(uuid.uuid4())
        checks = []

        async def key(selected=account, repository=repo, *, entry=False):
            fixture = next(item for item in compositions if item.repository is repository
                           and getattr(item, "selected", None) == selected)
            return await fixture.operation(owner, selected, entry=entry)

        async def opened(selected=account, repository=repo, *, initial_frame=None):
            body = synthetic_policy_body(valuation=dict(mark_method="midpoint", max_mark_age_seconds=60, max_spread="2"))
            body["limits"].update(daily_loss_limit="50", observed_drawdown_limit="40", max_committed_exposure="1000")
            # Initial risk uses a separately recorded prior mark. The first
            # manual observation therefore remains a new source observation.
            fixture = SyntheticPaperComposition(repository, clock=lambda: datetime.now(UTC), quote_reader=quote,
                        frame_reader=lambda: initial_frame or frame(-1), body=body, policy_id=POLICY_ID)
            fixture.selected = selected
            compositions.append(fixture)
            await fixture.create(owner, selected)
            fills = fixture.service
            quantity = 3 if selected == account else 2
            staged, _ = await fills.stage(owner, selected, await key(selected, repository), parameters(quantity=quantity), {})
            await fills.quote(owner, selected, await key(selected, repository, entry=True),
                              staged["body"]["order_id"], {**quote(), "ask_size": 2})
            return fills, staged["body"]["order_id"]

        fills, opening = await opened()
        service = PreparedObservationService(repo, evidence_check=synthetic_check, clock=lambda: datetime.now(UTC))
        checks.append(await refuses(PreparedObservationService(repo).record(owner, account, await key(), frame()),
                                     PaperConflict, "default observation admission disabled"))
        checks.append(await refuses(service.record(str(uuid.uuid4()), account, await key(), frame()),
                                     PaperConflict, "another owner cannot observe account"))
        before = await repo.read(owner, account)
        first_key = await key()
        records = await asyncio.gather(*(service.record(owner, account, first_key, frame()) for _ in range(12)))
        check(sum(created for _, created in records) == 1, "one atomic observation")
        current = await repo.read(owner, account)
        saved = current["state"]["valuation"]
        check(saved["equity"] == "1018" and saved["unrealized_result"] == "18", "independent hand account value")
        check(current["reserve_events"] == before["reserve_events"], "observation preserves exit capacity")
        for field in ("cash", "positions", "orders", "exit_capacity", "realized_result"):
            check(current["state"][field] == before["state"][field], "observation preserves "+field)
        checks.append("twelve same requests save one value and leave holdings cash and exit reserves unchanged")
        changed = frame()
        changed["marks"][0]["bid"] = "108"
        checks.append(await refuses(service.record(owner, account, first_key, changed), PaperConflict,
                                     "same operation changed input refused"))
        unchanged = await service.record(owner, account, await key(), frame())
        check(unchanged == (None, False), "unchanged frame does not reserve another receipt")
        check((await repo.read(owner, account))["version"] == current["version"], "unchanged frame saves no extra event")
        checks.append("unchanged new request neither refreshes time nor consumes history capacity")
        work = report.with_suffix(".restart.json")
        work.write_text(json.dumps(dict(database=database, owner=owner, account=account, valuation=saved)), encoding="utf-8")
        child = subprocess.run([sys.executable, "-m", "scripts.verify_paper_observations", "--recover", str(work)],
                               capture_output=True, text=True, timeout=15,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        check(child.returncode == 0, "reopen observation: "+child.stderr)
        checks.append("fresh process reopens exact observation and safely projects pending history")

        # The already confirmed residual share avoids allocating a second
        # protected structure under the unchanged 8MiB reservation bound.
        staged = {"body": {"order_id": opening}}
        fills.admission.adapter.frame_reader = lambda: frame()
        fill_operation = await key(entry=True)
        async def fill_during_observation(*_):
            await fills.quote(owner, account, fill_operation, staged["body"]["order_id"], quote("second-fill"))
            return True
        racing = PreparedObservationService(repo, evidence_check=fill_during_observation, clock=lambda: datetime.now(UTC))
        checks.append(await refuses(racing.record(owner, account, await key(), frame()), PaperConflict,
                                     "a concurrent fill prevents old-book valuation commit"))
        current = await repo.read(owner, account)
        prior_book = {**current, "state": {**current["state"], "valuation": saved}}
        check(current_observation(prior_book, now=datetime.now(UTC))["status"] == "stale", "prior book observation stale after fill")
        check(current_observation(current, now=datetime.now(UTC))["status"] == "current", "new funded risk valuation is current")
        check(current["state"]["cash"] == "697", "fill retained correct cash")
        checks.append("later fill retains its economics and makes earlier observation stale")

        # A trusted checker receives detached inputs. Neither it nor an outside
        # mutation during the await can silently alter the accepted mark body.
        mutable = frame(1)
        async def mutate_during_check(_, doc, inputs):
            mutable["marks"][0]["bid"] = "50"
            inputs["marks"][0]["bid"] = "40"
            doc["state"]["cash"] = "0"
            return True
        frozen_service = PreparedObservationService(repo, evidence_check=mutate_during_check,
                                                    clock=lambda: datetime.now(UTC))
        frozen, _ = await frozen_service.record(owner, account, await key(), mutable)
        check(frozen["body"]["observation"]["equity"] == "1027", "frozen mark inputs")
        checks.append("input or checker mutation cannot change saved prices and cash")

        # Time alone can change readiness with identical source inputs. The
        # deduplication path must retain that transition rather than refreshing
        # or returning the earlier known result.
        selected = str(uuid.uuid4())
        closing_frame = frame()
        closing_frame["session"]["closed_at"] = (NOW+timedelta(seconds=30)).isoformat()
        initial_closing_frame = frame(-1)
        initial_closing_frame["session"] = copy.deepcopy(closing_frame["session"])
        await opened(selected, initial_frame=initial_closing_frame)
        await service.record(owner, selected, await key(selected), closing_frame)
        after_close = PreparedObservationService(repo, evidence_check=synthetic_check,
                                                 clock=lambda: NOW+timedelta(seconds=31))
        doc = await repo.read(owner, selected)
        check(current_observation(doc, now=NOW+timedelta(seconds=31))["status"] == "stale", "session validity deadline")
        changed_status, created = await after_close.record(owner, selected, await key(selected), closing_frame)
        check(created and changed_status["body"]["observation"]["risk"]["limits_passed"] is None,
              "identical sources persist new time-dependent unknown risk")
        checks.append("session close expires saved readiness and identical input saves the unknown transition")

        # Genuine event pressure must not spend entry-prepaid exit capacity.
        bounded = PaperRepository(connection[database], pending_limit=64)
        selected = str(uuid.uuid4())
        bounded_fills, opened_id = await opened(selected, bounded)
        sequence = 0
        while True:
            doc = await bounded.read(owner, selected)
            if len(doc["pending_events"])+doc["reserve_events"] == 64:
                break
            observer = PreparedObservationService(bounded, evidence_check=synthetic_check, clock=lambda: datetime.now(UTC))
            await observer.record(owner, selected, await key(selected, bounded), frame(sequence))
            sequence += 1
        before = copy.deepcopy(doc)
        observer = PreparedObservationService(bounded, evidence_check=synthetic_check,
                                              clock=lambda: datetime.now(UTC))
        checks.append(await refuses(observer.record(owner, selected, await key(selected, bounded), frame(sequence)),
                                     PaperCapacity, "observation cannot consume reserved exit capacity"))
        check(await bounded.read(owner, selected) == before, "capacity failure leaves state exact")
        bounded_fixture = next(item for item in compositions if item.repository is bounded)
        closing_fills = bounded_fixture.service
        closing_fills.clock = closing_fills.admission.clock = closing_fills.admission.adapter.clock = lambda: datetime.now(UTC)
        # Use the exact latest independent observation for the reducing action.
        closing_fills.admission.adapter.frame_reader = lambda: frame(sequence-1)
        closed, _ = await closing_fills.stage(owner, selected, await key(selected, bounded),
                                              parameters(side="sell", structure_id=opened_id, limit="99"), {})
        await closing_fills.quote(owner, selected, await key(selected, bounded), closed["body"]["order_id"], quote("exit"))
        check(not (await bounded.read(owner, selected))["state"]["positions"], "exit survives observation pressure")
        checks.append("close stage and fill succeed at the cap using their previously reserved space")

        selected = str(uuid.uuid4())
        await opened(selected)
        original = await key(selected)
        await repo.accounts.update_one({"owner":owner,"account_id":selected}, {"$set":{"epoch":str(uuid.uuid4())}})
        checks.append(await refuses(service.record(owner, selected, original, frame()), PaperConflict,
                                     "old recovery epoch cannot save an observation"))
        result = dict(status="pass", checks=checks, count=len(checks), database=database, python=sys.version,
                      provider_calls=0, model_calls=0, broker_orders=0, production_admission=False,
                      limitation="Synthetic verified-input observation preparation; no app mount or product lifecycle settlement")
        report.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
    finally:
        for composition in compositions:
            composition.close()
        connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--report")
    parser.add_argument("--recover")
    print(json.dumps(asyncio.run(execute(parser.parse_args())), indent=2))
