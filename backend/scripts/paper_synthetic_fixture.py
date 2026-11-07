"""Explicit synthetic source/confirmation composition for isolated verification.

Never installed by the app. Metadata/costs/session facts here describe only the
fictional cash-settled instrument used by the isolated runner acceptance book.
"""
from __future__ import annotations

import copy
import tempfile
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from services.agent.paper.accounting import exact_context
from services.agent.paper.admission import CapturedInputs, PaperExecutionAuthority
from services.agent.paper.execution import new_book
from services.agent.paper.policy import SEMANTICS, binding_of, create_policy, prepare_policy_change, valuation_policy
from services.agent.paper.repository import PaperConflict, digest, operation_id
from services.agent.paper.risk import create_trade_evidence, economics, metadata_digests
from services.agent.paper.service import PreparedPaperService
from services.execution_lease import acquire_lease, release_lease


async def persist_synthetic_policy(repo, owner, account, body, *, now, version=1, policy_id=None):
    current = await repo.read(owner, account)
    prior = current["state"].get("risk_policy")
    policy = create_policy(binding_of(current), body,
                           policy_id=prior["policy_id"] if prior else policy_id or str(uuid.uuid4()),
                           policy_version=version, effective_at=now, accepted_at=now, accepted_by=owner,
                           acceptance_evidence=["explicit-isolated-synthetic-owner-choice"], now=now,
                           verify_acceptance=lambda record: record["accepted_by"] == owner)
    state, event = prepare_policy_change(current, policy, expected_version=current["version"],
                                         expected_policy_digest=prior["digest"] if prior else None, now=now)
    await repo.commit(owner, account, operation_id(current["version"], epoch=current["epoch"]),
                      dict(kind="synthetic_policy_fixture", digest=policy["digest"]), state, event)
    return policy


class SyntheticPaperAdapter:
    def __init__(self, repository, *, clock, frame_reader=None, quote_reader=None):
        self.repository, self.clock = repository, clock
        self.frame_transform = None
        self.capture_count = 0
        self.frame_reader, self.quote_reader = frame_reader, quote_reader

    async def capture_verified_inputs(self, *, binding, expected_version, action,
                                      frozen_parameters, quote, confirmation_ref):
        self.capture_count += 1
        current = await self.repository.read(binding["owner"], binding["account_id"])
        if binding_of(current) != binding or current["version"] != expected_version:
            raise PaperConflict("Synthetic source account changed")
        terms = economics(frozen_parameters)
        if (terms["contract_id"], terms["product_kind"], terms["premium_factor"]) not in (
                ("synthetic-option", "option", "100"), ("TEST", "equity", "1")):
            raise PaperConflict("Instrument is outside the isolated synthetic source allowlist")
        quote = copy.deepcopy(quote if quote is not None else self.quote_reader())
        now = self.clock()
        opened = now.replace(hour=0, minute=0, second=0, microsecond=0)
        closed = opened + timedelta(days=1)
        verified = opened
        metadata = dict(contract_id="synthetic-option", source_id="synthetic-verified-contract-v1",
                        verified_at=verified.isoformat(), currency="USD", product_kind="option", premium_factor="100",
                        adjusted=False, right="call", strike="100", underlying="SYNTHETIC", exercise_style="european",
                        settlement_style="cash", deliverable=dict(kind="cash", quantity="100", currency="USD"),
                        last_trade_at=(opened+timedelta(days=30)).isoformat(),
                        expiry_at=(opened+timedelta(days=30)).isoformat(),
                        exercise_cutoff_at=(opened+timedelta(days=30,hours=1)).isoformat(),
                        settlement_at=(opened+timedelta(days=31)).isoformat())
        policy = current["state"]["risk_policy"]
        frame = dict(policy=valuation_policy(policy),
                     session=dict(session_id="SYNTHETIC-"+opened.date().isoformat(), calendar_version="synthetic-calendar-v1",
                                  source_id="synthetic-session", opened_at=opened.isoformat(), closed_at=closed.isoformat()),
                     session_open=dict(session_id="SYNTHETIC-"+opened.date().isoformat(), source_id="synthetic-open",
                                       observed_at=opened.isoformat(), equity=current["state"]["initial_cash"]),
                     metadata=[metadata],
                     marks=[dict(contract_id=quote["contract_id"], currency="USD", source_id=quote["source_id"],
                                 observed_at=quote["observed_at"], received_at=quote["received_at"],
                                 bid=quote["bid"], ask=quote["ask"])])
        if self.frame_reader:
            frame = copy.deepcopy(self.frame_reader())
            frame["policy"] = valuation_policy(policy)
            metadata = next(item for item in frame["metadata"] if item["contract_id"] == terms["contract_id"])
        evidence = None
        if action == "entry" and "order_id" not in frozen_parameters:
            with exact_context():
                entry = Decimal(terms["limit"]) * Decimal(terms["premium_factor"]) + Decimal(terms["fee_per_unit"])
                if terms["slippage_enabled"] and terms["slippage_method"] == "cash":
                    entry += Decimal(terms["premium_factor"]) * Decimal(terms["price_increment"])
                exit_cost, lifecycle_cost = ("5.65", "1") if terms["product_kind"] == "option" else ("1", "0")
                maximum = str((entry + Decimal(exit_cost) + Decimal(lifecycle_cost)) * terms["quantity"])
            contract_hash, lifecycle_hash = metadata_digests(metadata)
            costs = dict(exit_cost_per_unit=exit_cost, lifecycle_cost_per_unit=lifecycle_cost, maximum_loss=maximum,
                         maximum_loss_basis="prepaid_long_zero_recovery_plus_costs", cost_basis="linear_per_unit",
                         contract_digest=contract_hash, lifecycle_digest=lifecycle_hash)
            evidence = create_trade_evidence(binding, policy, terms, costs, proposal_version=1,
                                               evidence=["synthetic-contract-v1", "synthetic-cost-schedule-v1"],
                                               verified_at=now, valid_until=now+timedelta(minutes=30),
                                               verifier_version="isolated-fixture-v1", now=now,
                                               verify_evidence=lambda record: record["costs"] == costs
                                               and record["binding"] == binding)
        confirmation = dict(binding=binding, economics_digest=digest(terms),
                            confirmation_ref=confirmation_ref, quote_digest=digest(quote), synthetic=True)
        refs = ["synthetic-source:"+digest(quote), "synthetic-contract:"+digest(metadata)]
        if self.frame_transform:
            frame = self.frame_transform(copy.deepcopy(frame))
        return CapturedInputs(frame, evidence, refs, confirmation)

    async def verify_admission(self, *, owner, current_account, frozen_parameters,
                               confirmation_record, immutable_source_refs):
        # Exact independently registered synthetic ownership/confirmation, not a
        # risk/equity Boolean. Persisted policy arithmetic is always recomputed.
        terms = frozen_parameters
        if terms is None:
            terms = next((order for order in current_account["state"]["orders"].values()
                          if digest(economics(order)) == confirmation_record.get("economics_digest")), None)
        return (owner == current_account["owner"]
                and confirmation_record.get("binding") == binding_of(current_account)
                and confirmation_record.get("synthetic") is True
                and isinstance(terms, dict)
                and confirmation_record.get("economics_digest") == digest(economics(terms))
                and terms.get("contract_id") in ("synthetic-option", "TEST")
                and len(immutable_source_refs) == 2
                and all(ref.startswith("synthetic-") for ref in immutable_source_refs))


def synthetic_policy_body(*, valuation=None):
    return {**SEMANTICS, "currency": "USD",
            "limits": dict(per_trade_max_loss="500", daily_loss_limit="1000",
                           observed_drawdown_limit="900", max_committed_exposure="5000"),
            "valuation": valuation or dict(mark_method="bid", max_mark_age_seconds=60, max_spread="0.20")}


class SyntheticPaperComposition:
    """Explicit isolated CLI factory. Never imported by an application route."""
    def __init__(self, repository, *, clock, quote_reader, frame_reader=None, body=None, policy_id=None):
        self.repository, self.clock = repository, clock
        self.body, self.policy_id = body or synthetic_policy_body(), policy_id
        self.directory = tempfile.TemporaryDirectory(prefix="floww-paper-fixture-")
        path = str(Path(self.directory.name) / "executor.lease")
        lease = acquire_lease(path, "isolated-cli-synthetic-source")
        if lease.get("ok") is not True:
            self.directory.cleanup()
            raise PaperConflict("Synthetic CLI executor lease unavailable")
        self.authority = PaperExecutionAuthority(path, lease["token"], lambda: "running")
        self.adapter = SyntheticPaperAdapter(repository, clock=clock, frame_reader=frame_reader, quote_reader=quote_reader)
        self.service = PreparedPaperService(repository, admission_adapter=self.adapter,
                                            execution_authority=self.authority, clock=clock)

    async def create(self, owner, account, cash="1000"):
        await self.repository.create(owner, account, new_book(cash, currency="USD"))
        return await persist_synthetic_policy(self.repository, owner, account, self.body,
                                              now=self.clock(), policy_id=self.policy_id)

    async def operation(self, owner, account, *, entry=False):
        current = await self.repository.read(owner, account)
        if entry and current["state"]["risk_control"]["entry_credits"] < 2:
            # This is explicit fixture supervisor work, never a silent reset in
            # the admission service: projection must acknowledge every event.
            await self.service.admission.replenish(owner, account)
            current = await self.repository.read(owner, account)
        return operation_id(current["version"], epoch=current["epoch"])

    def close(self):
        release_lease(self.authority.lease_path, self.authority.lease_token)
        self.directory.cleanup()
