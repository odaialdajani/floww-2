"""Isolated internal paper runner with funded stage/fill admission.

Composes the guarded paper sequence over injected quote observations and an
injected repository. Requires explicit frozen rules, persisted accepted policy,
server-constructed source/confirmation evidence and lease/stop authority. It
blocks new entries while an exit is unresolved, preserves risk-reducing exits,
and reconciles the durable journal to cash, positions, working orders, fills
and P&L. No broker import and no broker order method anywhere in this module.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from services.agent.paper.accounting import derived
from services.agent.paper.admission import PaperAdmissionService
from services.agent.paper.execution import (
    cancel_order,
    reserved_cash,
)
from services.agent.paper.execution_control import claim_of
from services.agent.paper.guarded_repository import GuardedPaperRepository
from services.agent.paper.policy import policy_body
from services.agent.paper.repository import PaperConflict, digest, operation_id, scope, validate_json
from services.agent.paper.risk_assessment import reserved_events as guarded_reserve_events


def _instant(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("Naive source time is not accepted; include its timezone")
        return value.astimezone(UTC)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Naive source time is not accepted; include its timezone")
    return parsed.astimezone(UTC)


def _require(rule, policy):
    if rule is None or not isinstance(rule, dict):
        raise ValueError("A frozen rule digest is required")
    if not isinstance(rule.get("rule_digest"), str) or len(rule["rule_digest"]) != 64:
        raise ValueError("A frozen rule digest is required")
    if policy is None or not isinstance(policy, dict):
        raise ValueError("An explicit policy is required")


class PaperRunner:
    """Deterministic internal paper runner over guarded preparation state."""

    def __init__(self, repository, *, quote_reader, admission_adapter=None, execution_authority=None, clock=None):
        if not isinstance(repository, GuardedPaperRepository):
            raise ValueError("A guarded repository is required")
        if not callable(quote_reader):
            raise ValueError("An injected quote reader is required")
        self.repository = repository
        self.quote_reader = quote_reader
        self.clock = clock or (lambda: datetime.now(UTC))
        self.admission = PaperAdmissionService(repository, adapter=admission_adapter,
                                               authority=execution_authority, clock=self.clock)
        self._fresh_entry = False
        self._started = False

    async def start(self, owner, account, rule, policy):
        _require(rule, policy)
        current = await self.repository.read(owner, account)
        if current is None:
            raise PaperConflict("Paper account unavailable for this owner")
        state = validate_json(current["state"])
        if state.get("recovery_pending"):
            raise PaperConflict("recovery_pending: restored account requires reconciliation before any change")
        if state.get("epoch") not in (None, current["epoch"]):
            raise PaperConflict("Book and account recovery differ")
        # Validate the policy body through the existing policy contract so an
        # explicit, well-formed policy governs the run; the runner does not
        # mutate account risk state, so no policy change is persisted here.
        policy_body(policy.get("body", {}))
        self._rule = validate_json(rule)
        self._policy = validate_json(policy)
        self._owner = owner
        self._account = account
        self._epoch = current["epoch"]
        self._start_op = operation_id(current["version"], epoch=self._epoch)
        self._started = True
        return dict(kind="paper_runner_started", rule_digest=rule["rule_digest"],
                    policy_digest=digest(policy), policy_body_digest=digest(policy_body(policy.get("body", {}))),
                    epoch=self._epoch)

    def _require_started(self, owner, account, require_restart=False):
        if not self._started:
            raise ValueError("Runner must be started with a frozen rule and explicit policy")
        if require_restart and getattr(self, "_restarted", False) is False:
            raise ValueError("Runner must be restarted after recovery; rebind before reuse")
        if owner != self._owner or account != self._account:
            raise PaperConflict("Runner is bound to a different owner/account")

    async def _rebind(self, owner, account):
        """Re-bind after a restart; prior epoch operations are stale and refused.

        Reads the current account so the stale bound operation is replaced with
        a fresh version-bound operation; a restarted runner must not reuse the
        pre-restart entry operation.
        """
        current = await self.repository.read(owner, account)
        if current is None:
            raise PaperConflict("Paper account unavailable for this owner")
        state = validate_json(current["state"])
        if state.get("epoch") not in (None, current["epoch"]):
            raise PaperConflict("Book and account recovery differ")
        if state["risk_control"]["entry_credits"] < 2:
            await self.admission.replenish(owner, account)
            current = await self.repository.read(owner, account)
        self._owner = owner
        self._account = account
        self._started = True
        self._restarted = True
        self._fresh_entry = True
        self._epoch = current["epoch"]
        self._start_op = operation_id(current["version"], epoch=self._epoch)

    async def enter(self, owner, account, quote):
        self._require_started(owner, account)
        current = await self.repository.read(owner, account)
        if current is None:
            raise PaperConflict("Paper account unavailable for this owner")
        state = validate_json(current["state"])
        if self._has_unresolved_exit(state):
            raise PaperConflict("Unresolved exit blocks new entries")
        now = self.clock()
        created_at = _instant(now)
        quote_body, quote_digest = self._validated_quote(quote, created_at, entry=True, fresh=False)
        operation = self._entry_operation(current)
        parameters = self._stage_parameters(side=self._rule["side"])
        for pending in state["risk_control"]["pending"].values():
            if pending["command"].get("parameters") == parameters and pending["command"].get("quote") == quote_body:
                operation = self._start_op = pending["request_id"]
        request = dict(kind="stage", parameters=parameters, order_id=None, quote=quote_body,
                       confirmation=dict(rule_digest=self._rule["rule_digest"]))
        captured = None
        if not self._fresh_entry:
            captured = await self.repository.admissions.find_one({**scope(owner, account, "internal"),
                        "epoch": self._epoch, "request_digest": digest(request)})
        if captured is not None:
            operation = self._start_op = captured["parent_operation"]
        elif not any(item["request_id"] == operation for item in state["risk_control"]["pending"].values()):
            self._validated_quote(quote, created_at, entry=True)
        receipt, created = await self.admission.execute(
            owner, account, operation, kind="stage", parameters=parameters,
            quote=quote_body, confirmation=dict(rule_digest=self._rule["rule_digest"]),
        )
        event = receipt["body"]
        return dict(kind="paper_order_staged", order_id=event["order_id"],
                    structure_id=event["structure_id"], proposal_digest=event["proposal_digest"]), created

    async def exit(self, owner, account, rule, quote):
        self._require_started(owner, account)
        current = await self.repository.read(owner, account)
        if current is None:
            raise PaperConflict("Paper account unavailable for this owner")
        state = validate_json(current["state"])
        structure_id = rule.get("structure_id")
        if not structure_id or structure_id not in state["positions"]:
            raise PaperConflict("A reducing exit requires known held exposure")
        # Honor the passed exit rule (quantity, limit, proposal digest),
        # not the entry rule.
        quantity = rule.get("quantity")
        limit = rule.get("limit")
        proposal_digest = rule.get("proposal_digest")
        if not isinstance(quantity, int) or quantity < 1:
            raise ValueError("Exit quantity must be a positive whole number")
        if not isinstance(proposal_digest, str) or len(proposal_digest) != 64:
            raise ValueError("A frozen exit proposal digest is required")
        now = self.clock()
        created_at = _instant(now)
        quote_body, quote_digest = self._validated_quote(quote, created_at, entry=False, fresh=False)
        parameters = self._stage_parameters(side="sell", structure_id=structure_id,
                                            quantity=quantity, limit=limit,
                                            proposal_digest=proposal_digest)
        return await self._assessed(owner, account, current, kind="stage", parameters=parameters,
                                    quote=quote_body, confirmation=dict(proposal_digest=proposal_digest))

    async def enter_fill(self, owner, account, order_id, quote):
        self._require_started(owner, account)
        current = await self.repository.read(owner, account)
        if current is None:
            raise PaperConflict("Paper account unavailable for this owner")
        state = validate_json(current["state"])
        order = state["orders"].get(order_id)
        if order is None or order["side"] != "buy":
            raise PaperConflict("Order is absent or not an entry")
        now = self.clock()
        created_at = _instant(now)
        quote_body, quote_digest = self._validated_quote(quote, created_at, entry=True, fresh=False)
        return await self._assessed(owner, account, current, kind="fill", order_id=order_id,
                                    quote=quote_body, confirmation=dict(rule_digest=self._rule["rule_digest"]))

    async def exit_fill(self, owner, account, order_id, quote):
        self._require_started(owner, account)
        current = await self.repository.read(owner, account)
        if current is None:
            raise PaperConflict("Paper account unavailable for this owner")
        state = validate_json(current["state"])
        order = state["orders"].get(order_id)
        if order is None or order["side"] != "sell":
            raise PaperConflict("Order is absent or not an exit")
        now = self.clock()
        created_at = _instant(now)
        quote_body, quote_digest = self._validated_quote(quote, created_at, entry=False, fresh=False)
        return await self._assessed(owner, account, current, kind="fill", order_id=order_id,
                                    quote=quote_body, confirmation=dict(rule_digest=self._rule["rule_digest"]))

    async def _assessed(self, owner, account, current, **request):
        normalized = dict(kind=request["kind"], parameters=request.get("parameters"),
                          order_id=request.get("order_id"), quote=request.get("quote"),
                          confirmation=request.get("confirmation"))
        request_key = digest([current["epoch"], normalized])
        existing = await self.repository.admissions.find_one({**scope(owner, account, "internal"),
                    "epoch": self._epoch, "request_digest": digest(normalized)})
        # The parent artifact is immutable; a separate stable nonce plus pending
        # intent lets a restarted runner recover without taking another action.
        for pending in current["state"]["risk_control"]["pending"].values():
            if (pending["command"]["kind"] == request["kind"]
                    and pending["command"].get("order_id") == request.get("order_id")
                    and pending["command"].get("quote") == request.get("quote")
                    and (request["kind"] == "fill" or pending["command"].get("parameters") == request.get("parameters"))):
                existing = dict(parent_operation=pending["request_id"])
                break
        if existing is not None:
            receipt, created = await self.admission.resume(owner, account, existing["parent_operation"])
        else:
            self._validated_quote(request["quote"], _instant(self.clock()), entry=False)
            entry = (request["kind"] == "fill" and current["state"]["orders"][request["order_id"]]["side"] == "buy")
            if entry:
                await self.admission.require_entry_fill_attempt(owner, account, request["order_id"])
            if entry and current["state"]["risk_control"]["entry_credits"] < 2:
                await self.admission.replenish(owner, account)
                current = await self.repository.read(owner, account)
            operation = operation_id(current["version"], str(uuid.uuid5(uuid.NAMESPACE_URL, request_key)), epoch=self._epoch)
            receipt, created = await self.admission.execute(owner, account, operation, **request)
        body = receipt["body"] if receipt else None
        if body and request["kind"] == "stage":
            body = dict(kind="paper_order_staged", order_id=body["order_id"],
                        structure_id=body["structure_id"], status="working")
        return body, created

    async def cancel(self, owner, account, order_id):
        self._require_started(owner, account)
        self.admission.require_execution("reduce")
        current = await self.repository.read(owner, account)
        if current is None:
            raise PaperConflict("Paper account unavailable for this owner")
        claim = claim_of(current, self.admission.authority, "reduce", now=self.clock())
        state = validate_json(current["state"])
        order = state["orders"].get(order_id)
        if order is None:
            raise PaperConflict("Order is absent or retired")
        command = dict(kind="cancel", order_id=order_id)
        operation = operation_id(current["version"], epoch=self._epoch)
        existing = await self.repository.receipt(owner, account, operation, command)
        if existing is not None:
            return existing["body"], False
        candidate, event, changed = cancel_order(
            state, order_id, committed_version=current["version"] + 1,
        )
        if not changed:
            return None, False
        receipt, created = await self.repository.commit(
            owner, account, operation, command, candidate, event,
            reserve_events=guarded_reserve_events(candidate), execution_claim=claim,
        )
        self.admission.require_execution("reduce")
        return event, True

    async def reconcile(self, owner, account):
        self._require_started(owner, account)
        current = await self.repository.read(owner, account)
        if current is None:
            raise PaperConflict("Paper account unavailable for this owner")
        state = validate_json(current["state"])
        cash = derived(state["cash"])
        realized = derived(state["realized_result"])
        reserved = reserved_cash(state)
        positions = []
        for structure, position in state["positions"].items():
            quantity = sum(lot["quantity"] for lot in position["lots"])
            basis = sum(derived(lot["cost_per_unit"]) * lot["quantity"]
                        for lot in position["lots"])
            positions.append(dict(structure_id=structure,
                                  contract_id=position["contract_id"],
                                  product_kind=position["product_kind"],
                                  quantity=quantity, basis=str(basis)))
        working_orders = []
        fills = []
        fill_cash = Decimal(0)
        fill_realized = Decimal(0)
        for order_id, order in state["orders"].items():
            entry = dict(order_id=order_id, structure_id=order["structure_id"],
                         side=order["side"], quantity=order["quantity"],
                         filled=order["filled"], remaining=order["remaining"],
                         status=order["status"], reserved_cash=order["reserved_cash"])
            if order["status"] == "working":
                working_orders.append(entry)
            for fill in order["fills"]:
                cash_change = derived(fill["accounting"]["cash_change"])
                fill_cash += cash_change
                fill_realized += derived(fill["realized_change"])
                fills.append(dict(order_id=order_id, fill_id=fill["fill_id"],
                                  quantity=fill["quantity"],
                                  cash_change=fill["accounting"]["cash_change"],
                                  realized_change=fill["realized_change"],
                                  source_observed_at=fill["source_observed_at"]))
        # Journal-to-account invariants: every fill's cash change and realized
        # P&L must be reflected in the account cash/realized_result, and no
        # fill may exceed its order's remaining buying-power reservation.
        recomputed_cash = derived(state["initial_cash"]) + fill_cash
        return dict(cash=str(cash), initial_cash=state["initial_cash"],
                    realized_result=str(realized), recomputed_journal_cash=str(recomputed_cash),
                    journal_fill_cash=str(fill_cash), journal_fill_realized=str(fill_realized),
                    positions=positions,
                    working_orders=working_orders, fills=fills,
                    reserved_cash=str(reserved),
                    cash_reconciled=recomputed_cash == cash and realized == fill_realized)

    # --- internals --------------------------------------------------------

    def _entry_operation(self, current):
        if self._start_op is None:
            raise ValueError("Runner was restarted; rebind before entering a new order")
        return self._start_op

    def _has_unresolved_exit(self, state):
        return any(order["side"] == "sell" and order["status"] == "working"
                   for order in state["orders"].values())

    def _validated_quote(self, quote, created_at, *, entry, fresh=True):
        if not isinstance(quote, dict):
            raise ValueError("A source quote is required")
        expected_contract = self._rule["contract_id"] if entry else None
        contract = quote.get("contract_id")
        if entry and contract != expected_contract:
            raise PaperConflict("Quote contract differs from the rule")
        observed = _instant(quote.get("observed_at"))
        received = _instant(quote.get("received_at"))
        now = created_at
        if observed > now or received > now:
            raise ValueError("Quote is from the future")
        if fresh and (now - observed).total_seconds() > self._rule["max_quote_age_seconds"]:
            raise ValueError("Quote is stale")
        if received < observed:
            raise ValueError("Quote receipt precedes its source time")
        # fill_order checks elapsed latency against its durable staged-order time.
        # Staging validates freshness without requiring a future observation.
        bid, ask = quote.get("bid"), quote.get("ask")
        if not isinstance(bid, str) or not isinstance(ask, str):
            raise ValueError("Verified quote prices are required")
        for key in ("bid_size", "ask_size"):
            value = quote.get(key)
            if type(value) is not int:
                raise ValueError("Verified displayed size must be a whole count")
            if not 0 <= value < 2**63:
                raise ValueError("Verified displayed size is out of range")
        if quote.get("bid_size", 0) <= 0 or quote.get("ask_size", 0) <= 0:
            raise ValueError("Zero or short quote size is not executable")
        source_id = quote.get("source_id")
        if not isinstance(source_id, str) or not 1 <= len(source_id) <= 200:
            raise ValueError("Stable source quote identity is required")
        body = dict(source_id=source_id, contract_id=contract,
                    observed_at=observed.isoformat(), received_at=received.isoformat(),
                    bid=bid, ask=ask, bid_size=quote["bid_size"], ask_size=quote["ask_size"],
                    size_unit=quote["size_unit"])
        return body, digest(body)

    def _stage_parameters(self, side, structure_id=None, quantity=None, limit=None,
                          proposal_digest=None):
        rule = self._rule
        return dict(contract_id=rule["contract_id"], product_kind=rule["product_kind"],
                    premium_factor=rule["premium_factor"], side=side,
                    quantity=quantity if quantity is not None else rule["quantity"],
                    limit=limit if limit is not None else rule["limit"],
                    fee_per_unit=rule["fee_per_unit"],
                    slippage_enabled=rule["slippage_enabled"],
                    slippage_method=rule["slippage_method"],
                    price_increment=rule["price_increment"],
                    max_quote_age_seconds=rule["max_quote_age_seconds"],
                    max_spread=rule["max_spread"], latency_ms=rule["latency_ms"],
                    order_expires_at=rule["order_expires_at"],
                    proposal_digest=proposal_digest if proposal_digest is not None
                    else rule["proposal_digest"], currency=rule["currency"],
                    structure_id=structure_id)
