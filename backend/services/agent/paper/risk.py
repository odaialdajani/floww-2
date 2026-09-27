"""Pure, unmounted long-only cash risk preparation for staging and later fills.

Passing arithmetic is not order admission. Trusted composition must verify all
source frames, contract/lifecycle evidence and human confirmation, and commit
state plus event under the expected account version. No such route is mounted.
Unknown evidence returns no candidate state. No limit or cost defaults exist.

Required future composition: save trusted ACTUAL pre-action observations and
sampled peaks even when a proposed action is refused. Never save hypothetical
post-refusal fills as actual observations. Coordinate that save with account
versions, without consuming or blocking prepaid risk-reducing exit capacity.
This pure module alone does not implement that durable refusal path.
"""

from __future__ import annotations

import copy
import re
from decimal import Decimal

from services.agent.paper import execution
from services.agent.paper.accounting import derived, exact, exact_context
from services.agent.paper.policy import binding_of, evidence_ids, label, validate_policy, valuation_policy
from services.agent.paper.repository import PaperConflict, canonical, digest, validate_json
from services.agent.paper.valuation import _metadata, book_digest, observe

MAX_EVIDENCE_BYTES = 8192
MAX_RETAINED_RISK_RECORDS = 128
ECONOMIC_KEYS = {"contract_id", "product_kind", "currency", "premium_factor", "side", "quantity", "limit",
                 "fee_per_unit", "slippage_enabled", "slippage_method", "price_increment", "max_quote_age_seconds",
                 "max_spread", "latency_ms", "order_expires_at", "proposal_digest"}
MONEY_KEYS = {"premium_factor", "limit", "fee_per_unit", "price_increment", "max_spread"}


class RiskRefusal(ValueError):
    """Known values fail the explicitly supplied policy."""


def _hash(value):
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("A complete evidence content digest is required")
    return value


def economics(parameters):
    """Freeze the same economic fields in a proposed or already stored order."""
    source = validate_json(parameters)
    if not isinstance(source, dict):
        raise ValueError("Confirmed order economics must be an object")
    if "expires_at" in source:
        source["order_expires_at"] = source["expires_at"]
    if not source.keys() >= ECONOMIC_KEYS:
        raise ValueError("Complete confirmed order economics are required")
    result = {key: source[key] for key in ECONOMIC_KEYS}
    if result["side"] not in ("buy", "sell") or result["product_kind"] not in ("equity", "option"):
        raise ValueError("Only declared long-only cash mechanics are supported")
    if result["currency"] != "USD":
        raise ValueError("Unsupported account currency")
    label(result["contract_id"])
    execution.whole_quantity(result["quantity"])
    for key in MONEY_KEYS:
        result[key] = str(exact(result[key], positive=key in ("premium_factor", "limit"),
                                nonnegative=key not in ("premium_factor", "limit")))
    if result["product_kind"] == "equity" and exact(result["premium_factor"]) != 1:
        raise ValueError("Share price units differ from the declared contract")
    if type(result["slippage_enabled"]) is not bool or result["slippage_method"] not in ("price", "cash"):
        raise ValueError("Explicit supported slippage choices are required")
    if type(result["max_quote_age_seconds"]) is not int or not 1 <= result["max_quote_age_seconds"] <= 300:
        raise ValueError("Explicit supported quote age is required")
    if type(result["latency_ms"]) is not int or not 0 <= result["latency_ms"] <= 60000:
        raise ValueError("Explicit supported latency is required")
    result["order_expires_at"] = execution.instant(result["order_expires_at"]).isoformat()
    _hash(result["proposal_digest"])
    return result


def metadata_digests(item):
    """Bind the exact verified source record and explicit lifecycle content.

    These hashes establish content equality only, never source trust or product
    admission. A refreshed source record requires refreshed risk evidence.
    """
    item = validate_json(item)
    if not isinstance(item, dict):
        raise ValueError("Verified contract metadata is required")
    keys = {"contract_id", "product_kind", "currency", "premium_factor"}
    if item.get("product_kind") == "option":
        keys |= {"underlying", "right", "strike", "adjusted", "exercise_style", "settlement_style",
                 "deliverable", "last_trade_at", "expiry_at", "exercise_cutoff_at", "settlement_at"}
    if not keys <= item.keys():
        raise ValueError("Complete lifecycle content is required")
    return digest(item), digest({key: item[key] for key in keys})


def _unit_reservation(item):
    with exact_context():
        factor, price = exact(item["premium_factor"]), exact(item["limit"])
        friction = exact(item["fee_per_unit"])
        if item["slippage_enabled"] and item["slippage_method"] == "cash":
            friction += factor * exact(item["price_increment"])
        return factor * price + friction if item["side"] == "buy" else max(Decimal(0), friction - factor * price)


def _validate_costs(costs, terms):
    required = {"exit_cost_per_unit", "lifecycle_cost_per_unit", "maximum_loss", "maximum_loss_basis",
                "cost_basis", "contract_digest", "lifecycle_digest"}
    if not isinstance(costs, dict) or set(costs) != required:
        raise ValueError("All verified loss, closing and lifecycle cost evidence is required")
    if (costs["maximum_loss_basis"] != "prepaid_long_zero_recovery_plus_costs"
            or costs["cost_basis"] != "linear_per_unit"):
        raise ValueError("Unsupported maximum-loss or cost formula")
    _hash(costs["contract_digest"])
    _hash(costs["lifecycle_digest"])
    exit_cost = exact(costs["exit_cost_per_unit"], nonnegative=True)
    lifecycle = exact(costs["lifecycle_cost_per_unit"], nonnegative=True)
    maximum = derived(costs["maximum_loss"])
    with exact_context():
        entry = _unit_reservation(terms) * terms["quantity"]
        required_loss = entry + (exit_cost + lifecycle) * terms["quantity"]
        if maximum != required_loss:
            raise ValueError("Verified maximum loss differs from the supported independent cash formula")
    return entry


def create_trade_evidence(binding, policy, parameters, costs, *, proposal_version, evidence,
                          verified_at, valid_until, verifier_version, now, verify_evidence):
    """Retain checked provenance; the trusted checker must establish source truth.

    The supported formula requires independently established zero-recovery
    prepaid-long economics and bounded lifecycle obligations. A digest or this
    function alone does not establish product lifecycle support.
    """
    binding = validate_json(binding)
    if binding != binding_of(binding):
        raise ValueError("Exact risk-evidence ownership binding required")
    policy = validate_policy(policy, binding, now=now)
    terms, costs = economics(parameters), validate_json(costs)
    if terms["side"] != "buy":
        raise ValueError("Opening risk evidence must describe a prepaid long acquisition")
    if type(proposal_version) is not int or not 1 <= proposal_version < 2**63:
        raise ValueError("A positive verified proposal version is required")
    verified, expires, checked = (execution.instant(value) for value in (verified_at, valid_until, now))
    if not verified <= checked < expires or execution.instant(terms["order_expires_at"]) <= checked:
        raise ValueError("Trade evidence or confirmation is not current")
    entry = _validate_costs(costs, terms)
    record = dict(record_version=1, binding=binding, policy_digest=policy["digest"], economics=terms,
                  economics_digest=digest(terms), costs=costs, entry_cost_bound=str(entry),
                  proposal_version=proposal_version, evidence_ids=evidence_ids(evidence),
                  verified_at=verified.isoformat(), valid_until=expires.isoformat(), verifier_version=label(verifier_version))
    if not callable(verify_evidence) or verify_evidence(copy.deepcopy(record)) is not True:
        raise PaperConflict("Independent proposal and lifecycle evidence did not pass")
    record["digest"] = digest(record)
    if len(canonical(record).encode()) > MAX_EVIDENCE_BYTES:
        raise ValueError("Trade risk evidence exceeds its supported size")
    return record


def validate_trade_evidence(record, binding, policy, *, now):
    record = validate_json(record)
    required = {"record_version", "binding", "policy_digest", "economics", "economics_digest", "costs",
                "entry_cost_bound", "proposal_version", "evidence_ids", "verified_at", "valid_until",
                "verifier_version", "digest"}
    if (not isinstance(record, dict) or set(record) != required or type(record["record_version"]) is not int
            or record["record_version"] != 1 or len(canonical(record).encode()) > MAX_EVIDENCE_BYTES):
        raise ValueError("Complete supported trade-risk record required")
    if record["digest"] != digest({key: value for key, value in record.items() if key != "digest"}):
        raise PaperConflict("Trade-risk evidence changed content")
    if record["binding"] != binding or record["policy_digest"] != policy["digest"]:
        raise PaperConflict("Trade evidence belongs to another account, recovery or policy")
    if not execution.instant(record["verified_at"]) <= execution.instant(now) < execution.instant(record["valid_until"]):
        raise ValueError("Trade-risk evidence is expired or from the future")
    terms = economics(record["economics"])
    if terms != record["economics"] or terms["side"] != "buy" or digest(terms) != record["economics_digest"]:
        raise PaperConflict("Frozen trade economics differ")
    if type(record["proposal_version"]) is not int or record["proposal_version"] < 1:
        raise ValueError("Verified proposal version is missing")
    evidence_ids(record["evidence_ids"])
    label(record["verifier_version"])
    if _validate_costs(record["costs"], terms) != derived(record["entry_cost_bound"]):
        raise PaperConflict("Entry debit bound differs from frozen economics")
    return record


def _account(account, expected_version, now):
    account = validate_json(account)
    if (not isinstance(account, dict) or account.get("recovery_pending") or type(expected_version) is not int
            or account.get("version") != expected_version or expected_version < 0):
        raise PaperConflict("Account changed or requires recovery")
    binding = binding_of(account)
    if account["state"].get("epoch") not in (None, binding["epoch"]):
        raise PaperConflict("Book and account recovery differ")
    policy = validate_policy(account["state"].get("risk_policy"), binding, now=now)
    if account["state"].get("currency") != policy["body"]["currency"]:
        raise PaperConflict("Account currency and chosen policy differ")
    if derived(account["state"]["cash"]) < 0:
        raise ValueError("Existing negative cash needs an explicit recovery policy")
    return account, binding, policy


def _totals(state, observation, records, binding, policy, now, frame):
    """Recompute reservations and non-overlapping per-unit cost buffers."""
    if not isinstance(records, dict) or len(records) > MAX_RETAINED_RISK_RECORDS:
        raise ValueError("Risk evidence capacity reached; preserve records for reconciliation")
    active, held, checked_records = {}, {}, {}
    buy_reserve, close_reserve = Decimal(0), Decimal(0)
    for structure, position in state["positions"].items():
        quantity = sum(execution.whole_quantity(lot["quantity"]) for lot in position["lots"])
        execution.whole_quantity(quantity)
        held[structure] = active[structure] = quantity
        record = validate_trade_evidence(records.get(structure), binding, policy, now=now)
        terms = record["economics"]
        if (position["contract_id"] != terms["contract_id"] or position["product_kind"] != terms["product_kind"]
                or exact(position["premium_factor"]) != exact(terms["premium_factor"])):
            raise PaperConflict("Held contract differs from its verified risk record")
        checked_records[structure] = record
    for order in state["orders"].values():
        if order["status"] != "working":
            continue
        terms = economics(order)
        if order.get("risk_economics_digest") != digest(terms):
            raise PaperConflict("Working order has no matching frozen risk economics")
        remaining = execution.whole_quantity(order["remaining"])
        if remaining + order["filled"] != terms["quantity"] or type(order["filled"]) is not int or order["filled"] < 0:
            raise ValueError("Working order quantity is inconsistent")
        reserve = _unit_reservation(terms) * remaining
        if derived(order["reserve_per_unit"]) != _unit_reservation(terms) or derived(order["reserved_cash"]) != reserve:
            raise PaperConflict("Saved reservation differs from remaining confirmed economics")
        structure = order["structure_id"]
        record = validate_trade_evidence(records.get(structure), binding, policy, now=now)
        checked_records[structure] = record
        if terms["side"] == "buy":
            if economics(order) != record["economics"] or structure != order["order_id"]:
                raise PaperConflict("Pending entry differs from its verified risk record")
            buy_reserve += reserve
            active[structure] = active.get(structure, 0) + remaining
        else:
            if structure not in held or remaining > held[structure]:
                raise PaperConflict("Pending exit exceeds known long holdings")
            original = record["economics"]
            if any(terms[key] != original[key] for key in ("contract_id", "product_kind", "currency", "premium_factor")):
                raise PaperConflict("Exit contract differs from the held risk record")
            friction = exact(terms["fee_per_unit"])
            if terms["slippage_enabled"]:
                friction += exact(terms["premium_factor"]) * exact(terms["price_increment"])
            if friction > exact(record["costs"]["exit_cost_per_unit"]):
                raise RiskRefusal("Closing costs exceed the independently verified per-unit bound")
            close_reserve += reserve
    buffers = Decimal(0)
    deadlines = []
    metadata = frame.get("metadata", [])
    for record in checked_records.values():
        terms = record["economics"]
        matches = [item for item in metadata if item.get("contract_id") == terms["contract_id"]]
        if len(matches) != 1:
            raise ValueError("Exactly one verified contract record is required for every pending or held trade")
        item = matches[0]
        _metadata(terms, item, execution.instant(now), policy["body"]["currency"])
        contract_digest, lifecycle_digest = metadata_digests(item)
        if (record["costs"]["contract_digest"] != contract_digest
                or record["costs"]["lifecycle_digest"] != lifecycle_digest):
            raise PaperConflict("Contract or lifecycle content differs from its verified risk evidence")
        deadlines.append(execution.instant(record["valid_until"]))
        if terms["product_kind"] == "option":
            deadlines.extend(execution.instant(item[key]) for key in
                             ("last_trade_at", "expiry_at", "exercise_cutoff_at", "settlement_at"))
    for structure, quantity in active.items():
        record = checked_records[structure]
        if quantity > record["economics"]["quantity"]:
            raise PaperConflict("Held and pending quantity exceeds its verified original trade")
        buffers += quantity * (exact(record["costs"]["exit_cost_per_unit"])
                               + exact(record["costs"]["lifecycle_cost_per_unit"]))
    # Closing shortfall is already covered by the exit buffer, never counted
    # twice or used as expected sale proceeds to finance a new entry.
    if close_reserve > buffers:
        raise RiskRefusal("Known closing cash shortfalls exceed retained cost buffers")
    if execution.reserved_cash(state) != buy_reserve + close_reserve:
        raise PaperConflict("Working reservations do not reconcile")
    value = derived(observation["known_holdings_value"])
    cash = derived(state["cash"])
    return dict(cash=cash, holdings=value, entry_reservations=buy_reserve, closing_reservations=close_reserve,
                cost_buffers=buffers, available_cash=cash-buy_reserve-buffers,
                committed_exposure=value+buy_reserve+buffers, active=active, records=checked_records, deadlines=deadlines)


def _observations(account, candidate, frame, binding, policy, now):
    frame = validate_json(frame)
    if not isinstance(frame, dict) or frame.get("policy") != valuation_policy(policy):
        raise PaperConflict("Source valuation frame differs from the persisted full policy")
    before = observe(account["state"], frame, now=now, binding=binding, previous=account["state"].get("valuation"))
    after = observe(candidate, frame, now=now, binding=binding, previous=before)
    for reading in (before, after):
        if reading["unknown_positions"] or reading["equity"] is None or reading["risk"]["status"] != "observed":
            raise ValueError("Full current holdings, session and opening equity evidence is required")
        if reading["valid_until"] is None or execution.instant(now) >= execution.instant(reading["valid_until"]):
            raise ValueError("Observation or product/session evidence has reached its deadline")
        # Compute rather than trust saved limits_passed or a stale display value.
        risk = reading["risk"]
        total = derived(reading["equity"])
        with exact_context():
            if (derived(risk["loss_from_open"]) != max(Decimal(0), derived(risk["baseline_equity"])-total)
                    or derived(risk["observed_drawdown"]) != max(Decimal(0), derived(risk["observed_peak_equity"])-total)):
                raise PaperConflict("Observed loss arithmetic does not reconcile")
    return before, after


def _decide(account, candidate, event, target, frame, binding, policy, now, action):
    before, after = _observations(account, candidate, frame, binding, policy, now)
    with exact_context():
        prior = _totals(account["state"], before, account["state"].get("risk_trades", {}), binding, policy, now, frame)
        future = _totals(candidate, after, candidate.get("risk_trades", {}), binding, policy, now, frame)
        limits = {key: exact(value, nonnegative=True) for key, value in policy["body"]["limits"].items()}
        if future["cash"] < 0 or future["available_cash"] < 0:
            raise RiskRefusal("The declared long-only cash policy cannot fund this change and its known cost buffers")
        increasing = target["side"] == "buy"
        if increasing:
            for reading, totals in ((before, prior), (after, future)):
                if (derived(reading["risk"]["loss_from_open"]) >= limits["daily_loss_limit"]
                        or derived(reading["risk"]["observed_drawdown"]) >= limits["observed_drawdown_limit"]
                        or totals["committed_exposure"] > limits["max_committed_exposure"]):
                    raise RiskRefusal("A declared account loss, sampled drawdown or exposure limit is reached")
            if any(derived(record["costs"]["maximum_loss"]) > limits["per_trade_max_loss"]
                   for record in future["records"].values()):
                raise RiskRefusal("A verified trade maximum loss exceeds the declared per-trade limit")
        elif (future["committed_exposure"] > prior["committed_exposure"]
              or any(quantity > prior["active"].get(key, 0) for key, quantity in future["active"].items())):
            raise RiskRefusal("The proposed exit is not a verified reduction of existing exposure")
        deadlines = [execution.instant(before["valid_until"]), execution.instant(after["valid_until"]),
                     execution.instant(target["expires_at"])]
        deadlines.extend(prior["deadlines"] + future["deadlines"])
        if execution.instant(now) >= min(deadlines):
            raise ValueError("Risk decision inputs have expired")
        decision = dict(risk_version=1, status="pass", action=action, evaluated_at=execution.instant(now).isoformat(),
                        valid_until=min(deadlines).isoformat(), freshness_semantics="decision_time_recheck_before_fill",
                        input_account_version=account["version"], binding=binding, policy_digest=policy["digest"],
                        before_book_digest=book_digest(account["state"]), after_book_digest=book_digest(candidate),
                        observation_coverage="sampled_only", admission_allowed=False,
                        trade_evidence={key: record["digest"] for key, record in future["records"].items()},
                        before={key: str(prior[key]) for key in ("cash", "entry_reservations", "closing_reservations",
                                                               "cost_buffers", "available_cash", "committed_exposure")},
                        after={key: str(future[key]) for key in ("cash", "entry_reservations", "closing_reservations",
                                                               "cost_buffers", "available_cash", "committed_exposure")},
                        equity_before=before["equity"], equity_after=after["equity"],
                        loss_from_open=after["risk"]["loss_from_open"], observed_drawdown=after["risk"]["observed_drawdown"])
    after["saved_version"] = account["version"] + 1
    candidate["valuation"] = after
    return dict(status="pass", admission_allowed=False, state=candidate, event={**event, "risk_decision": decision},
                decision=decision, reason="Pure checked preparation; production admission remains disabled")


def _failure(exc):
    return dict(status="refuse" if isinstance(exc, RiskRefusal) else "unknown", admission_allowed=False,
                state=None, event=None, decision=None, reason=str(exc))


def prepare_stage(account, parameters, *, expected_version, trade_evidence, frame, now):
    """Pure candidate only. Never save a refused/unknown result or grant permission."""
    try:
        account, binding, policy = _account(account, expected_version, now)
        parameters = validate_json(parameters)
        candidate, event = execution.stage_order(account["state"], **parameters, epoch=binding["epoch"],
                                                 now=now, committed_version=expected_version+1)
        target = candidate["orders"][event["order_id"]]
        target["risk_economics_digest"] = digest(economics(target))
        records = candidate.setdefault("risk_trades", {})
        if target["side"] == "buy":
            record = validate_trade_evidence(trade_evidence, binding, policy, now=now)
            if record["economics"] != economics(target):
                raise PaperConflict("Confirmed order differs from the verified trade-risk economics")
            records[target["structure_id"]] = record
        elif trade_evidence is not None:
            raise ValueError("A close must retain the original held trade's verified risk record")
        return _decide(account, candidate, event, target, frame, binding, policy, now, "stage")
    except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
        return _failure(exc)


def prepare_fill(account, order_id, quote, *, expected_version, frame, now):
    """Re-evaluate current and actual prospective risk; stage approval is not reused."""
    try:
        account, binding, policy = _account(account, expected_version, now)
        target = account["state"]["orders"][order_id]
        candidate, event, changed = execution.fill_order(account["state"], order_id, validate_json(quote),
                                                         now=now, committed_version=expected_version+1)
        if not changed:
            return dict(status="unchanged", admission_allowed=False, state=None, event=None, decision=None,
                        reason="No new fill; retrieve any original operation receipt")
        return _decide(account, candidate, event, target, frame, binding, policy, now, "fill")
    except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
        return _failure(exc)
