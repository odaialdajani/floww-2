"""Exact listed facts from an owning observation; selectors are not a quote ledger."""
import hashlib
from datetime import date, datetime

from domain.exposure_metrics import decimal_strike
from services.agent.contracts import canonical, fact, finite, instant
from services.contract_identity import contract_identity, resolve_contract


def contract_facts(raw, screen, ticker, now):
    def refuse(code):
        return [], [code + ": exact contract evidence unavailable; no midpoint or live substitute"]

    sid = screen.get("snapshotId")
    if raw.get("recorded_snapshot_id") != sid or raw.get("replay") is not True:
        return refuse("CONTRACT_RECORD_UNAVAILABLE")
    coverage = raw.get("contract_coverage") or {}
    if (coverage.get("truncated") is not False or coverage.get("requested") != coverage.get("returned")
            or coverage.get("returned") != len(raw.get("contracts") or [])):
        return refuse("CONTRACT_POPULATION_PARTIAL")
    resolved = resolve_contract(raw.get("contracts"), screen.get("selectedContract"), now=now)
    if resolved.get("status") != "ok":
        return refuse("CONTRACT_" + str(resolved.get("reason") or "UNAVAILABLE"))
    identity = resolved["matched_identity"]
    strike = decimal_strike(identity.get("strike"))
    expiry, side = identity.get("expiry"), identity.get("type")
    if (not identity.get("osi") or strike is None or side not in {"call", "put", "c", "p"}
            or not isinstance(expiry, str) or date.fromisoformat(expiry).isoformat() != expiry):
        return refuse("CONTRACT_IDENTITY_INCOMPLETE")
    requested = screen["selectedContract"]
    if requested.get("series") is not None and requested["series"] != identity.get("series"):
        return refuse("CONTRACT_SERIES_CONFLICT")
    if (screen.get("selectedStrike") != float(strike) or screen.get("selectedExpiry") != expiry
            or float(strike) not in screen.get("mapStrikes", []) or expiry not in screen.get("mapExpiries", [])):
        return refuse("CONTRACT_CELL_CONFLICT")
    walls = (raw.get("metrics") or {}).get("walls") or []
    wall = next((w for w in walls if w.get("wall_id") == screen.get("selectedWall")), None)
    if screen.get("selectedWall") and (not wall or not wall.get("low", float(strike)) <= float(strike) <= wall.get("high", float(strike))):
        return refuse("CONTRACT_WALL_CONFLICT")
    row = next(c for c in raw["contracts"] if contract_identity(c) == identity)
    if row.get("snapshot_id") != sid or row.get("ticker") != ticker:
        return refuse("CONTRACT_SNAPSHOT_CONFLICT")
    quote, mult = resolved["quote"], resolved["multiplier"]
    if quote.get("quote_source") != raw.get("data_source"):
        return refuse("CONTRACT_PROVIDER_CONFLICT")
    if mult["status"] not in {"observed", "registered_assumption"} or not mult.get("source"):
        return refuse("CONTRACT_MULTIPLIER_PROVENANCE_UNAVAILABLE")
    recorded, received = instant(raw.get("asof")), instant(row.get("received_at"))
    clocks = {leg: instant(quote["timestamps"][leg]) for leg in ("bid", "ask")}
    if not recorded or not received or not all(clocks.values()):
        return refuse("CONTRACT_QUOTE_CLOCK_UNAVAILABLE")
    if any(datetime.fromisoformat(ts) > min(now, datetime.fromisoformat(received), datetime.fromisoformat(recorded)) for ts in clocks.values()):
        return refuse("CONTRACT_QUOTE_CLOCK_INVALID")
    if datetime.fromisoformat(received) > datetime.fromisoformat(recorded) or datetime.fromisoformat(recorded) > now:
        return refuse("CONTRACT_QUOTE_CLOCK_INVALID")
    if any(not finite(quote[leg]) or quote[leg] < 0 for leg in clocks) or quote["ask"] < quote["bid"]:
        return refuse("CONTRACT_QUOTE_UNAVAILABLE")
    replay = screen.get("displayMode") == "replay"
    stale = quote.get("stale") or any(quote["ages_s"][leg] > 120 for leg in clocks)
    status = "stale" if stale else "degraded" if replay else "ok"
    gaps = ["Recorded listed contract only; quotes do not establish aggressor side, dealer intent or trade direction"]
    if stale:
        gaps.append("Recorded contract quotes are stale; actual source ages are retained")
    contract = canonical(identity)
    scope = hashlib.sha256(canonical([sid, identity, raw.get("map_query"), screen.get("activePane"),
                                      screen.get("metric"), screen.get("overlayMetric"), screen.get("selectedWall"),
                                      screen.get("mapStrikes"), screen.get("mapExpiries")]).encode()).hexdigest()
    facts = []

    def add(label, value, unit, observed=None, reason=None):
        facts.append(fact(label, value, unit, ticker=ticker, source=quote["quote_source"], snapshot_id=sid,
                          event_time=observed or raw.get("event_time"), received_at=received,
                          horizon="contract:" + scope, contract=contract, status=status, reason=reason))

    for label, value, unit in (
        ("OSI", identity["osi"], "listed identity"), ("strike", identity["strike"], "USD exact decimal"),
        ("expiry", expiry, "date"), ("type", side, "option type"),
        ("owning snapshot", sid, "observation identity"), ("multiplier", mult["value"], "contract multiplier"),
        ("multiplier source", mult["source"], "provenance"),
    ):
        add("Exact contract " + label, value, unit)
    if wall and finite(wall.get("low")) and finite(wall.get("high")):
        add("Exact contract selected wall id", wall["wall_id"], "wall identity")
        add("Exact contract selected wall low", wall["low"], "USD")
        add("Exact contract selected wall high", wall["high"], "USD")
    for leg, ts in clocks.items():
        add("Exact contract " + leg, quote[leg], "USD", ts)
        add("Exact contract " + leg + " age", quote["ages_s"][leg], "seconds at research read", ts)
    add("Exact contract spread", quote["spread_absolute"], "USD", min(clocks.values()))
    return facts, gaps
