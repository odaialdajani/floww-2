"""Testable underlying-price events, independent of option profits or execution."""

import copy
import hashlib

from services.agent.contracts import canonical, finite, instant

VERSION = "price-path-1"


def claim_seed(
    *, turn_id, ticker, issued_at, deadline, reference, target, invalidation, direction, evidence, trigger=None
):
    issued, end = instant(issued_at), instant(deadline)
    if not issued or not end or issued >= end or direction not in {"up", "down"}:
        raise ValueError("A claim needs ordered times and an explicit direction")
    if not all(finite(v) and v > 0 for v in (reference, target, invalidation)):
        raise ValueError("A claim needs finite underlying-price levels")
    if not (invalidation < reference < target if direction == "up" else target < reference < invalidation):
        raise ValueError("Claim levels contradict its direction")
    if trigger is not None and (not finite(trigger) or trigger <= 0):
        raise ValueError("Invalid trigger")
    if trigger is not None and not (
        reference <= trigger < target if direction == "up" else target < trigger <= reference
    ):
        raise ValueError("Trigger must precede the target in the specified direction")
    if (
        not isinstance(evidence, list)
        or not evidence
        or len(evidence) > 32
        or any(
            not isinstance(f, dict)
            or f.get("ticker") != ticker
            or f.get("status") != "ok"
            or not instant(f.get("event_time"))
            or instant(f.get("event_time")) > issued
            or not instant(f.get("received_at"))
            or instant(f.get("received_at")) > issued
            or not f.get("source")
            or not f.get("snapshot_id")
            for f in evidence
        )
    ):
        raise ValueError("A predictive claim needs healthy ticker-specific evidence")
    for item in evidence:
        content = {key: value for key, value in item.items() if key != "id"}
        if item.get("id") != "ev" + hashlib.sha256(canonical(content).encode()).hexdigest():
            raise ValueError("Evidence content does not match its identity")
    if not any(
        f.get("metric") == "Underlying price"
        and f.get("unit") == "USD"
        and finite(f.get("value"))
        and f["value"] == reference
        for f in evidence
    ):
        raise ValueError("Reference price must match the supplied underlying observation")
    result = dict(
        turn_id=turn_id,
        ticker=ticker,
        issued_at=issued,
        deadline=end,
        reference=reference,
        target=target,
        invalidation=invalidation,
        direction=direction,
        trigger=trigger,
        evidence=copy.deepcopy(evidence),
        confidence_meaning="No calibrated probability supplied",
        version=VERSION,
    )
    result["claim_id"] = hashlib.sha256(canonical(result).encode()).hexdigest()
    return result


def resolve_claim(seed, bars, *, now, source_available=True):
    """Minute/path bars only. No target-first assumption or invented gap fill."""
    if not isinstance(seed, dict) or not isinstance(bars, list):
        return {"status": "malformed", "reason": "Invalid event or path container", "resolver_version": VERSION}
    try:
        rebuilt = claim_seed(
            **{key: value for key, value in seed.items() if key not in {"claim_id", "version", "confidence_meaning"}}
        )
        if canonical(rebuilt) != canonical(seed):
            raise ValueError("Claim content changed")
    except (ValueError, TypeError):
        return {"status": "malformed", "reason": "Invalid or changed saved event", "resolver_version": VERSION}
    end, issued, current = instant(seed.get("deadline")), instant(seed.get("issued_at")), instant(now)
    try:
        digest = hashlib.sha256(canonical(bars).encode()).hexdigest()
    except (ValueError, TypeError):
        return {"status": "malformed", "reason": "Invalid path values", "resolver_version": VERSION}
    base = {"resolver_version": VERSION, "resolved_at": current, "path_digest": digest}

    def result(status, reason):
        return {**base, "status": status, "reason": reason}

    if (
        not end
        or not issued
        or not current
        or issued >= end
        or seed.get("direction") not in {"up", "down"}
        or not all(finite(seed.get(k)) for k in ("reference", "target", "invalidation"))
    ):
        return result("malformed", "Invalid event definition")
    if not source_available:
        return result(
            "open" if current < end else "missing_data", "Historical path unavailable; no backfill was invented"
        )
    if len(bars) > 10000:
        return result("malformed", "Path exceeds the supported bound")
    ordered = []
    for bar in bars:
        if not isinstance(bar, dict):
            return result("malformed", "Invalid source bar")
        if bar.get("ticker") != seed["ticker"] or not bar.get("source"):
            return result("malformed", "Source bar identity does not match the event")
        start, stop = instant(bar.get("start")), instant(bar.get("end"))
        if (
            not start
            or not stop
            or start >= stop
            or not all(finite(bar.get(k)) for k in ("open", "high", "low", "close"))
        ):
            return result("malformed", "Invalid source bar")
        if not bar["low"] <= min(bar["open"], bar["close"]) <= max(bar["open"], bar["close"]) <= bar["high"]:
            return result("malformed", "Source bar prices are inconsistent")
        if stop <= issued or start >= end or stop > current:
            continue
        ordered.append({**bar, "start": start, "end": stop})
    ordered.sort(key=lambda b: (b["start"], b["end"]))
    # Validate the entire supplied overlap set before selecting an outcome.
    # Otherwise an earlier version can win before its correction is inspected.
    for previous, following in zip(ordered, ordered[1:], strict=False):
        if following["start"] < previous["end"]:
            return result("missing_data", "Overlapping or corrected source bars need reconciliation")
    active = seed.get("trigger") is None
    cursor = issued
    up = seed["direction"] == "up"
    for bar in ordered:
        # A straddling issue/deadline bar cannot establish which side of the
        # event boundary contained its extremes.
        if bar["start"] < issued or bar["end"] > end:
            return result("missing_data", "Event boundary falls inside a source bar")
        if bar["start"] != cursor:
            return result("missing_data", "Missing, overlapping or corrected source bars need reconciliation")
        cursor = bar["end"]
        target_hit = bar["high"] >= seed["target"] if up else bar["low"] <= seed["target"]
        stop_hit = bar["low"] <= seed["invalidation"] if up else bar["high"] >= seed["invalidation"]
        if not active:
            triggered = bar["high"] >= seed["trigger"] if up else bar["low"] <= seed["trigger"]
            if not triggered:
                continue
            if target_hit or stop_hit:
                return result("ambiguous", "Trigger and outcome share a bar; event order is unknown")
            active = True
        elif target_hit and stop_hit:
            return result("ambiguous", "Target and invalidation share a bar")
        elif target_hit:
            return result("win", "Underlying target reached before invalidation")
        elif stop_hit:
            return result("loss", "Underlying invalidation reached before target")
    if current < end:
        return result("open", "The event has not reached its deadline")
    if cursor < end:
        return result("missing_data", "Path does not cover the full event interval")
    return result("neither" if active else "untriggered", "Deadline reached without the specified outcome")
