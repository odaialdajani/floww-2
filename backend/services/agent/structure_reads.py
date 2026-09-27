"""Copy-only structure estimates using the platform's existing calculators.

VEX here means gex_core's vanna exposure, not gex_vex_calculator's
vomma display scale. The three exposure measures are never added together.
No expiry cutoff is inferred from a date or from a provider's floored T.
"""

from __future__ import annotations

from datetime import datetime

from services.agent.access.horizon import ET, fractional_years
from services.agent.contracts import fact, finite, instant
from services.gex_core import compute_gex_by_strike
from services.heatseeker import calc_air_pockets


def derived_fact(metric, value, unit, parents, context, *, reason=None, degraded=False):
    """Retain all input identities and the weakest input observation quality."""
    times = [instant(p.get("event_time")) for p in parents]
    known = [t for t in times if t]
    status = "stale" if any(p.get("status") == "stale" for p in parents) else "ok"
    if status != "stale" and (degraded or not parents or len(known) != len(times)
                              or any(str(p.get("source") or "unknown") in {"unknown", "cached chain"} for p in parents)
                              or any(p.get("status") != "ok" for p in parents)):
        status = "degraded"
    if known and (datetime.fromisoformat(max(known)) - datetime.fromisoformat(min(known))).total_seconds() > 120:
        if status != "stale":
            status = "degraded"
        reason = reason or "Inputs have different observation times"
    received = [instant(p.get("received_at")) for p in parents]
    return fact(metric, value, unit, **context,
                source="; ".join(sorted({part for p in parents for part in str(p.get("source") or "unknown").split("; ")})),
                event_time=min(known) if known and len(known) == len(times) else None,
                received_at=max(t for t in received if t) if any(received) else None,
                status=status, reason=reason,
                parents=list(dict.fromkeys(p["id"] for p in parents)))


def exact_expiry(contract):
    """Only a supplied product-specific, timezone-aware instant is admissible."""
    stamp = instant(contract.get("expiry_instant"))
    if stamp is None:
        return None
    dt = datetime.fromisoformat(stamp)
    if dt.astimezone(ET).date().isoformat() != str(contract.get("expiry")):
        return None
    return dt


def iv_input_fact(metric, value, observations, coverage, context, now):
    """Actual IV evidence keeps its own oldest time, never chain receipt time."""
    oldest, newest = min(observations), max(observations)
    status = coverage["status"]
    if (now - datetime.fromisoformat(oldest)).total_seconds() > 900:
        status = "stale"
    elif status != "stale" and (
        (datetime.fromisoformat(newest) - datetime.fromisoformat(oldest)).total_seconds() > 120
        or str(coverage.get("source") or "unknown") in {"unknown", "cached chain"}
    ):
        status = "degraded"
    return fact(metric, value, "annualized fraction", **context, source=coverage["source"],
                event_time=oldest, received_at=coverage.get("received_at"), status=status,
                parents=[coverage["id"]], reason="Supplied IV observations; oldest actual input time retained")


def _valid_contract(contract, *, model=False):
    if not isinstance(contract, dict):
        return False
    oi = contract.get("open_interest", contract.get("oi"))
    if not (finite(contract.get("strike")) and contract["strike"] > 0
            and finite(oi) and oi >= 0
            and str(contract.get("type", "")).upper() in {"C", "CALL", "P", "PUT"}):
        return False
    key = "iv" if model else "gamma"
    return finite(contract.get(key)) and (contract[key] > 0 if model else contract[key] >= 0)


def structure_facts(contracts, existing, *, ticker, snapshot_id, horizon, now):
    """Return bounded facts/gaps; contracts have already been expiry-sliced."""
    context = dict(ticker=ticker, snapshot_id=snapshot_id, horizon=horizon)
    by_name = {f["metric"]: f for f in existing}
    spot_fact = by_name.get("Underlying price")
    coverage = by_name.get("Available contracts")
    facts, gaps = [], []
    if not spot_fact or not coverage:
        return facts, ["Combined gamma, vanna and charm estimates are unavailable: price or chain coverage missing"]
    spot = spot_fact["value"]
    if not finite(spot) or spot <= 0:
        return facts, ["Structure estimates are unavailable: underlying price is invalid"]
    parents = [spot_fact, coverage]
    gamma_fact = by_name.get("Estimated gamma exposure")
    strike_fact = by_name.get("Gamma exposure strikes")
    valid = [c for c in contracts if _valid_contract(c)]
    if gamma_fact and strike_fact:
        geometry_parents = [spot_fact, strike_fact, gamma_fact]
        profile = dict(zip(strike_fact["value"], gamma_fact["value"], strict=True))
        levels = [k for k, v in profile.items() if finite(k) and finite(v) and v != 0]
        for side, candidates, choose in (("below", [k for k in levels if k < spot], max),
                                         ("above", [k for k in levels if k > spot], min)):
            if candidates:
                facts.append(derived_fact(f"Nearest exposure level {side}", choose(candidates), "USD",
                                          geometry_parents, context,
                                          reason="Nearest saved nonzero gamma-exposure strike; not a verified support or resistance level"))
            else:
                gaps.append(f"No nonzero saved exposure level {side} the underlying price")
        try:
            pockets = calc_air_pockets(spot, valid)["air_pockets"]
        except (ArithmeticError, ValueError, TypeError, KeyError):
            pockets = None
            gaps.append("Air pocket calculator did not return usable values")
        if pockets is not None and len(pockets) <= 512:
            for bound, key in (("lower", "low"), ("upper", "high")):
                facts.append(derived_fact(f"Estimated air pocket {bound} bounds", [p[key] for p in pockets], "USD",
                                          geometry_parents, context,
                                          reason="Saved gamma estimate: below 20% of local median, minimum span 0.5% of spot"))
        elif pockets is not None:
            gaps.append("Air pocket series exceeds supported size")
    else:
        gaps.append("Nearest exposure levels and air pockets are unavailable: gamma profile missing")

    observation = instant(coverage.get("event_time"))
    if observation is None:
        return facts, gaps + ["Combined gamma, vanna and charm estimates are unavailable: chain observation time is unknown"]
    at = datetime.fromisoformat(observation)
    if at > now:
        return facts, gaps + ["Combined exposure is unavailable: chain observation time is in the future"]
    model_contracts = []
    for c in contracts:
        if not _valid_contract(c, model=True):
            continue
        expiry = exact_expiry(c)
        if expiry is None or expiry <= at:
            continue
        # A specifically supplied IV timestamp may not be replaced by chain time.
        iv_time = instant(c.get("iv_event_time", observation))
        if (iv_time is None or datetime.fromisoformat(iv_time) > now
                or abs((datetime.fromisoformat(iv_time) - at).total_seconds()) > 120):
            continue
        model_contracts.append({**c, "oi": c.get("open_interest", c.get("oi")),
                                "type": "call" if str(c["type"]).upper() in {"C", "CALL"} else "put",
                                "T": fractional_years(expiry, now=at), "_iv_observation": iv_time})
    if not model_contracts:
        return facts, gaps + ["Combined gamma, vanna and charm estimates are unavailable: verified IV and explicit product expiry instants are required"]
    partial = len(model_contracts) != len(contracts)
    if partial:
        gaps.append("Combined exposure excludes contracts without verified IV or explicit expiry instants")
    try:
        rows = compute_gex_by_strike(spot, model_contracts, ticker=ticker)
    except (ArithmeticError, ValueError, TypeError):
        rows = []
    if not rows or any(not all(finite(row.get(k)) for k in ("strike", "gex", "vex", "charm")) for row in rows):
        return facts, gaps + ["Combined exposure calculator did not return usable values"]
    # Keep bounded, real IV values as parents instead of borrowing chain time.
    # A large input is split, not truncated or replaced by a made-up zero.
    iv_parents = []
    for start in range(0, len(model_contracts), 512):
        chunk = model_contracts[start:start + 512]
        metric = "Model implied volatility inputs"
        if len(model_contracts) > 512:
            metric += f" ({start + 1}-{start + len(chunk)})"
        iv_parents.append(iv_input_fact(metric, [c["iv"] for c in chunk],
                                        [c["_iv_observation"] for c in chunk], coverage, context, now))
    facts.extend(iv_parents)
    parents = [*parents, *iv_parents]
    reason = "Model estimate using existing rate/dividend conventions and explicit expiry instants; calls positive, puts negative"
    if len(rows) <= 512:
        strikes = derived_fact("Model exposure strikes", [r["strike"] for r in rows], "USD", parents, context,
                               reason=reason, degraded=partial)
        facts.append(strikes)
        model_parents = [*parents, strikes]
    else:
        gaps.append("Combined exposure series exceeds supported size; only totals are available")
        model_parents = parents
    for label, key, unit in (("gamma", "gex", "USD per 1% underlying move"),
                             ("vanna", "vex", "platform vanna scale: vanna * OI * 100 * spot * 0.01"),
                             ("charm", "charm", "platform charm scale: charm * OI * 100 * spot * 0.01")):
        values = [r[key] for r in rows]
        if len(rows) <= 512:
            facts.append(derived_fact(f"Model {label} exposure", values, unit, model_parents, context,
                                      reason=reason, degraded=partial))
        total = sum(values)
        if finite(total):
            facts.append(derived_fact(f"Total model {label} exposure", total, unit, model_parents, context,
                                      reason=reason, degraded=partial))
        else:
            gaps.append(f"Total model {label} exposure is outside supported numeric range")
    return facts, gaps
