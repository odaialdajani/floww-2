"""Prepared account observations; no admission or settlement capability.

Inputs must be verified by trusted composition before persistence. Quotes value
existing holdings; they do not create fills or reapply execution costs. A saved
observation binds the exact book and must become stale after any account change.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import timedelta
from decimal import Decimal

from services.agent.paper.accounting import derived, exact, exact_context
from services.agent.paper.execution import MAX_FILLS_PER_ORDER, MAX_POSITIONS, instant, reserved_cash, whole_quantity
from services.agent.paper.repository import PaperConflict, canonical, digest, identity, scope, validate_json

MAX_INPUT_BYTES = 64 * 1024


def book_digest(state):
    """Exclude only our derived observations; all economic state stays bound."""
    return digest({key: value for key, value in state.items() if key != "valuation"})


def _label(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 200:
        raise ValueError("Bounded source identity required")
    return value


def _index(rows):
    if not isinstance(rows, list) or len(rows) > 64:
        raise ValueError("Bounded observation input list required")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Observation input must be an object")
        key = _label(row.get("contract_id"))
        if key in result:
            raise ValueError("Repeated observation identities are ambiguous")
        result[key] = row
    return result


def _mark_policy(policy):
    _label(policy.get("policy_id"))
    if policy.get("mark_method") not in ("bid", "midpoint"):
        raise ValueError("Choose an explicit account valuation method")
    age = policy.get("max_mark_age_seconds")
    if type(age) is not int or not 1 <= age <= 300:
        raise ValueError("Choose an explicit supported mark age")
    exact(policy.get("max_spread"), nonnegative=True)


def _metadata(position, item, now, currency):
    if not isinstance(item, dict):
        raise ValueError("Verified contract details missing")
    _label(item.get("source_id"))
    verified = instant(item.get("verified_at"))
    if verified > now:
        raise ValueError("Contract details are from the future")
    if (item.get("contract_id") != position["contract_id"] or item.get("currency") != currency
            or item.get("product_kind") != position["product_kind"]
            or exact(item.get("premium_factor"), positive=True) != exact(position["premium_factor"], positive=True)):
        raise ValueError("Contract details differ from the held position")
    if position["product_kind"] == "equity":
        if exact(position["premium_factor"]) != 1:
            raise ValueError("Equity price units are not verified")
        return "equity_preparation"
    if position["product_kind"] != "option":
        raise ValueError("Unsupported held product")
    if item.get("adjusted") is not False:
        raise ValueError("Adjusted or unknown option deliverable is unsupported")
    if item.get("right") not in ("call", "put"):
        raise ValueError("Option right missing")
    exact(item.get("strike"), positive=True)
    _label(item.get("underlying"))
    if item.get("exercise_style") not in ("american", "european"):
        raise ValueError("Option exercise style missing")
    if item.get("settlement_style") not in ("cash", "physical"):
        raise ValueError("Option settlement style missing")
    deliverable = item.get("deliverable")
    if not isinstance(deliverable, dict) or deliverable.get("kind") not in ("cash", "shares"):
        raise ValueError("Verified option deliverable missing")
    exact(deliverable.get("quantity"), positive=True)
    if ((item["settlement_style"] == "cash") != (deliverable["kind"] == "cash")
            or deliverable.get("currency") != currency):
        raise ValueError("Option settlement and deliverable economics disagree")
    if deliverable["kind"] == "shares" and deliverable.get("symbol") != item["underlying"]:
        raise ValueError("Option deliverable identity differs")
    times = [instant(item.get(key)) for key in
             ("last_trade_at", "expiry_at", "exercise_cutoff_at", "settlement_at")]
    if min(times) <= now:
        raise ValueError("Option lifecycle event is due; holdings remain unresolved")
    if times[3] < max(times[:3]):
        raise ValueError("Option settlement precedes required product events")
    return "option_lifecycle_not_implemented"


def _price(mark, position, policy, now, currency):
    if not isinstance(mark, dict):
        raise ValueError("Source price missing")
    _label(mark.get("source_id"))
    if mark.get("contract_id") != position["contract_id"] or mark.get("currency") != currency:
        raise ValueError("Source price identity or currency differs")
    observed, received = instant(mark.get("observed_at")), instant(mark.get("received_at"))
    if observed > received or received > now or (now - observed).total_seconds() > policy["max_mark_age_seconds"]:
        raise ValueError("Source price is stale, future-dated or out of order")
    bid, ask = exact(mark.get("bid"), nonnegative=True), exact(mark.get("ask"), nonnegative=True)
    if ask < bid or ask - bid > exact(policy["max_spread"]):
        raise ValueError("Source price spread is crossed or outside the selected limit")
    return bid if policy["mark_method"] == "bid" else (bid + ask) / 2


def _risk(frame, prior, equity, exposure, now, initial_cash):
    """Observed session loss/peak only; never assert unobserved intraday extrema."""
    policy, session = frame.get("policy") or {}, frame.get("session")
    result = dict(status="unknown", reasons=[], session_id=None, baseline_equity=None,
                  observed_peak_equity=None, loss_from_open=None, observed_drawdown=None,
                  limits_passed=None, observation_coverage="sampled_only")
    try:
        if not isinstance(session, dict):
            raise ValueError("Verified exchange session missing")
        result["session_id"] = _label(session.get("session_id"))
        _label(session.get("calendar_version"))
        _label(session.get("source_id"))
        opened, closed = instant(session.get("opened_at")), instant(session.get("closed_at"))
        if closed <= opened or not opened <= now <= closed:
            raise ValueError("Observation is outside the verified trading session")
        daily = exact(policy.get("daily_loss_limit"), nonnegative=True)
        drawdown = exact(policy.get("drawdown_limit"), nonnegative=True)
        maximum = exact(policy.get("max_gross_exposure"), nonnegative=True)
        result["session_digest"] = digest(session)
        result["policy_digest"] = digest(policy)
        result["initial_cash"] = initial_cash
        same = prior and prior.get("session_id") == result["session_id"]
        if same and (prior.get("session_digest") != result["session_digest"]
                     or prior.get("policy_digest") != result["policy_digest"]
                     or prior.get("initial_cash") != initial_cash):
            raise ValueError("Session evidence, settings or capital changed; risk reconciliation required")
        baseline = frame.get("session_open")
        if same and prior.get("baseline_equity") is not None:
            baseline_value = derived(prior["baseline_equity"])
            result["baseline_source"] = prior["baseline_source"]
            if baseline is not None and digest(baseline) != prior["baseline_source"]:
                raise ValueError("Session opening evidence changed")
        else:
            if not isinstance(baseline, dict) or baseline.get("session_id") != result["session_id"]:
                raise ValueError("Verified session opening equity missing; first request cannot replace it")
            _label(baseline.get("source_id"))
            if instant(baseline.get("observed_at")) != opened:
                raise ValueError("Session opening equity was not measured at the open")
            baseline_value = derived(baseline.get("equity"))
            if baseline_value <= 0:
                raise ValueError("Positive opening equity required")
            result["baseline_source"] = digest(baseline)
        result["baseline_equity"] = str(baseline_value)
        peak = max(baseline_value, derived(prior["observed_peak_equity"])) if (
            same and prior.get("observed_peak_equity") is not None) else baseline_value
        if equity is None:
            result["observed_peak_equity"] = str(peak)
            raise ValueError("Incomplete holdings prevent account risk evaluation")
        peak = max(peak, equity)
        loss, draw = max(Decimal(0), baseline_value - equity), max(Decimal(0), peak - equity)
        result.update(status="observed", observed_peak_equity=str(peak), loss_from_open=str(loss),
                      observed_drawdown=str(draw), limits_passed=loss < daily and draw < drawdown and exposure <= maximum)
        if not result["limits_passed"]:
            result["reasons"].append("Selected account loss or exposure limit reached")
    except (ValueError, KeyError, TypeError) as exc:
        result["reasons"].append(str(exc))
        # Never erase known same-session baseline/peak because a later mark or
        # evidence input failed. They retain their original provenance.
        if prior and prior.get("session_id") == result["session_id"]:
            for key in ("baseline_equity", "baseline_source", "observed_peak_equity", "session_digest",
                        "policy_digest", "initial_cash"):
                if prior.get(key) is not None:
                    result[key] = prior[key]
    return result


def observe(state, frame, *, now, binding, previous=None):
    """Pure snapshot. Caller verifies evidence and uses version-bound storage."""
    state, frame, binding = validate_json(state), validate_json(frame), validate_json(binding)
    if binding != {**scope(binding.get("owner"), binding.get("account_id"), binding.get("venue")),
                   "epoch": identity(binding.get("epoch"))}:
        raise ValueError("Exact owner, account, venue and epoch binding required")
    if state.get("epoch") not in (None, binding["epoch"]):
        raise PaperConflict("Observation belongs to another account recovery")
    if previous and previous.get("binding") != binding:
        raise PaperConflict("Earlier observation belongs to another account or recovery")
    if len(canonical(frame).encode()) > MAX_INPUT_BYTES:
        raise ValueError("Observation inputs exceed the supported size")
    checked = instant(now)
    if state.get("checked_at") is not None and checked < instant(state["checked_at"]):
        raise PaperConflict("Observation clock predates the saved account")
    if previous and checked < instant(previous["observed_at"]):
        raise PaperConflict("Observation clock moved backwards")
    if state.get("book_version") != 1 or len(state.get("positions", {})) > MAX_POSITIONS:
        raise ValueError("Unsupported prepared account book")
    marks, metadata = _index(frame.get("marks", [])), _index(frame.get("metadata", []))
    policy = frame.get("policy") or {}
    policy_error = None
    try:
        _mark_policy(policy)
    except (ValueError, AttributeError) as exc:
        policy_error = str(exc)
    rows, unknown, watermark, deadlines = [], 0, {}, []
    with suppress(TypeError, KeyError, ValueError):
        deadlines.append(instant(frame["session"]["closed_at"]))
    with exact_context():
        cash, known_value, known_basis = derived(state["cash"]), Decimal(0), Decimal(0)
        for structure, position in state["positions"].items():
            if not isinstance(position.get("lots"), list) or not 1 <= len(position["lots"]) <= MAX_FILLS_PER_ORDER:
                raise ValueError("Held structure has an unsupported lot count")
            for lot in position["lots"]:
                whole_quantity(lot["quantity"])
                if derived(lot["cost_per_unit"]) < 0:
                    raise ValueError("Held lot basis cannot be negative")
            quantity = sum(lot["quantity"] for lot in position["lots"])
            whole_quantity(quantity)
            basis = sum((derived(lot["cost_per_unit"]) * lot["quantity"] for lot in position["lots"]), Decimal(0))
            item = dict(structure_id=structure, contract_id=position["contract_id"], quantity=quantity,
                        basis=str(basis), mark=None, value=None, unrealized_result=None,
                        status="unknown", reason=None, lifecycle_status="unknown")
            try:
                if policy_error:
                    raise ValueError(policy_error)
                item["lifecycle_status"] = _metadata(position, metadata.get(position["contract_id"]), checked, state["currency"])
                mark = marks.get(position["contract_id"])
                price = _price(mark, position, policy, checked, state["currency"])
                deadlines.append(instant(mark["observed_at"])+timedelta(seconds=policy["max_mark_age_seconds"]))
                if position["product_kind"] == "option":
                    deadlines.extend(instant(metadata[position["contract_id"]][key]) for key in
                                     ("last_trade_at", "expiry_at", "exercise_cutoff_at", "settlement_at"))
                before = (previous or {}).get("mark_watermarks", {}).get(structure)
                semantic = digest({key: value for key, value in mark.items() if key != "received_at"})
                source_time = instant(mark["observed_at"])
                if before and (source_time < instant(before["observed_at"])
                               or source_time == instant(before["observed_at"]) and semantic != before["digest"]
                               or mark["source_id"] == before["source_id"] and semantic != before["digest"]):
                    raise ValueError("Source mark rewound or changed its recorded identity")
                watermark[structure] = dict(source_id=mark["source_id"], observed_at=source_time.isoformat(), digest=semantic)
                value = quantity * exact(position["premium_factor"], positive=True) * price
                item.update(mark=str(price), value=str(value), unrealized_result=str(value - basis), status="known",
                            mark_source=mark["source_id"], mark_observed_at=instant(mark["observed_at"]).isoformat(),
                            metadata_source=metadata[position["contract_id"]]["source_id"])
                known_value += value
                known_basis += basis
            except (ValueError, TypeError, KeyError) as exc:
                unknown += 1
                item["reason"] = str(exc)
                before = (previous or {}).get("mark_watermarks", {}).get(structure)
                if before:
                    watermark[structure] = before
            rows.append(item)
        if any(derived(order["reserved_cash"]) < 0 for order in state["orders"].values()):
            raise ValueError("Saved buying-power reservation cannot be negative")
        reserved = reserved_cash(state)
        total = cash + known_value if unknown == 0 else None
        prior_risk = (previous or {}).get("risk_anchor") or (previous or {}).get("risk")
        risk = _risk(frame, prior_risk, total, known_value + reserved, checked, state["initial_cash"])
        result = dict(observation_version=1, observed_at=checked.isoformat(), binding=binding,
                      book_digest=book_digest(state), frame_digest=digest(frame), currency=state["currency"],
                      max_mark_age_seconds=policy.get("max_mark_age_seconds") if not policy_error else None,
                      valid_until=min(deadlines).isoformat() if deadlines else None,
                      mark_watermarks=watermark,
                      cash=str(cash), reserved_cash=str(reserved), available_cash=str(cash - reserved),
                      known_holdings_value=str(known_value), equity=str(total) if total is not None else None,
                      realized_result=str(derived(state["realized_result"])),
                      unrealized_result=str(known_value - known_basis) if not unknown else None,
                      unknown_positions=unknown, positions=rows, risk=risk,
                      entry_allowed=False, entry_reason="Paper admission remains disabled; observation is preparation only")
        result["risk_anchor"] = risk if risk.get("baseline_equity") is not None else prior_risk
        result["last_complete"] = (dict(equity=result["equity"], observed_at=result["observed_at"], stale=False)
                                   if total is not None else {**((previous or {}).get("last_complete") or {}), "stale": True})
        result["effective_digest"] = digest({key: value for key, value in result.items()
                                              if key not in ("observed_at", "last_complete", "book_digest")})
        return validate_json(result)


def current_observation(account, *, now):
    """Readiness is never inferred from an old saved frame after a book change."""
    saved = account["state"].get("valuation")
    if saved is None:
        return dict(status="unavailable", observation=None, entry_allowed=False)
    same = (saved.get("saved_version") == account["version"] and saved["book_digest"] == book_digest(account["state"])
            and saved["binding"] == {key: account[key] for key in ("owner", "account_id", "venue", "epoch")})
    checked = instant(now)
    max_age = saved.get("max_mark_age_seconds")
    recent = type(max_age) is int and all(
        0 <= (checked - instant(item["mark_observed_at"])).total_seconds() <= max_age
        for item in saved["positions"] if item["status"] == "known")
    recent = recent and 0 <= (checked - instant(saved["observed_at"])).total_seconds() <= (max_age or 0)
    recent = recent and saved.get("valid_until") is not None and checked < instant(saved["valid_until"])
    return dict(status="current" if same and recent else "stale", observation=validate_json(saved), entry_allowed=False)
