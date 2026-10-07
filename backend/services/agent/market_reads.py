"""Bounded public scan inspection. Only injected, already-completed cache views are read."""
from __future__ import annotations

import hashlib
import re
from datetime import UTC, date, datetime

from services.agent.contracts import canonical, fact, finite

MAX_CANDIDATES = 50
MAX_CHART_ACTIONS = 3
_SYMBOL = re.compile(r"[A-Z][A-Z0-9.-]{0,11}")
_REQUIRED = {"underlying_ticker", "ticker", "contract_type", "strike_price", "expiration_date", "day_volume"}
_COUNTERS = ("universe", "attempted", "never_scanned", "latest_failed", "expiries_per_ticker", "rows_per_ticker_cap",
             "ratio_leaders_limit", "volume_leaders_limit", "history_contract_limit", "history_unavailable", "history_capped",
             "eligible_option_tickers", "provider_listed_tickers")


def _counter(value):
    return int(value) if finite(value) and value >= 0 and int(value) == value else None


def _number(value):
    return value if finite(value) and value >= 0 else None


def _receipt(value):
    if not finite(value):
        return None
    try:
        return datetime.fromtimestamp(value, UTC).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def _candidate_rows(rows, index, receipts, basis):
    eligible, conflicts, display_ids = {}, set(), {}
    for row in rows:
        if not isinstance(row, (list, tuple)):
            continue
        def field(name, values=row):
            position = index.get(name)
            return values[position] if position is not None and position < len(values) else None
        ticker, identity, kind = field("underlying_ticker"), field("ticker"), field("contract_type")
        volume, oi, strike = _counter(field("day_volume")), _counter(field("open_interest")), _number(field("strike_price"))
        expiry = field("expiration_date")
        if not isinstance(ticker, str) or ticker not in receipts or not isinstance(identity, str) or not 1 <= len(identity) <= 100:
            continue
        if not isinstance(kind, str) or kind not in {"call", "put"} or strike is None or strike <= 0 or volume is None or volume < 200:
            continue
        if not isinstance(expiry, str) or len(expiry) != 10:
            continue
        try:
            date.fromisoformat(expiry)
        except ValueError:
            continue
        ratio = volume / oi if oi is not None and oi > 0 else None
        if (ratio is None or ratio < 1.0) and volume < 2500:
            continue
        key = (ticker, identity)
        surface = (ticker, kind, strike, expiry)
        other = display_ids.setdefault(surface, key)
        if other != key:
            conflicts.update((key, other))
        candidate = dict(ticker=ticker, contract=identity, contract_type=kind, strike=strike, expiry=expiry,
                         day_volume=volume, open_interest=oi, volume_open_interest_ratio=ratio,
                         received_at=_receipt(receipts[ticker]), source_time=None, status="stale" if basis == "earlier_cached" else "degraded", basis=basis)
        if key in eligible and eligible[key] != candidate:
            conflicts.add(key)
        else:
            eligible[key] = candidate
    candidates = sorted((row for key, row in eligible.items() if key not in conflicts),
                        key=lambda row: (-row["day_volume"], row["ticker"], row["contract"]))
    return candidates, len(conflicts)


def market_answer(view, *, limit=MAX_CANDIDATES, now=None):
    """Produce checked snapshot candidates and server-owned live-chart choices.

    The result limit never changes the published scan's full universe denominator.
    Receipt age is not a verified market observation time or an execution tape.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_CANDIDATES:
        raise ValueError("Choose between one and fifty cached scan examples")
    now = now or datetime.now(UTC)
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("A dated market inspection is required")
    stamp = now.timestamp()
    coverage = {key: None for key in _COUNTERS}
    coverage.update(fresh=0, complete_realtime_market=False, candidates_checked=0, returned_candidates=0,
                    candidates_truncated=False, source="cached-public-scan",
                    roster_status="unknown", membership_verified=False)
    gaps = ["This is a rotating cached scan, not a simultaneous live view of every stock.",
            "Reported daily option volume is cumulative; it does not identify buyers, sellers or executed money.",
            "Only loaded option dates and bounded contract selections are available."]
    result = dict(scope="market", status="unavailable", summary="The cached market scan is unavailable. No provider refresh was started.",
                  sections=[], facts=[], gaps=gaps, candidates=[], current_candidates=[], earlier_candidates=[], actions=[], coverage=coverage,
                  mode="deterministic", model_status="Not requested: cache-only market inspection",
                  claim_status="non-gradeable", claim_reason="Descriptive scan findings are not a trade prediction",
                  requested_tickers=[])
    if not isinstance(view, dict) or not isinstance(view.get("coverage"), dict):
        return result
    raw = view["coverage"]
    for key in _COUNTERS:
        coverage[key] = _counter(raw.get(key))
    for key in ("checked_at", "fresh_window_seconds"):
        value = raw.get(key)
        coverage[key] = value if finite(value) and value >= 0 else None
    for key in ("catalog_stale", "catalog_available", "rows_capped"):
        coverage[key] = raw.get(key) if isinstance(raw.get(key), bool) else None
    coverage["source"] = raw.get("source") if raw.get("source") in ("public-instruments", "custom-universe") else "cached-public-scan"
    coverage["scope_kind"] = raw.get("scope_kind") if raw.get("scope_kind") in ("provider_option_enabled", "explicit_symbols") else None
    progress = raw.get("progress")
    if isinstance(progress, dict):
        coverage["progress"] = {key: _counter(progress.get(key)) for key in
                                ("pass_id", "universe", "pending", "inflight", "deferred", "attempted_in_pass", "succeeded_in_pass", "failed_in_pass")}
        coverage["progress"]["status"] = progress.get("status") if progress.get("status") in ("durable", "memory_only", "unavailable", "awaiting_directory") else "unavailable"
        for key in ("pending_includes_inflight_and_deferred", "pass_complete"):
            coverage["progress"][key] = progress.get(key) if isinstance(progress.get(key), bool) else None
        for key in ("directory_at", "last_complete"):
            value = _number(progress.get(key))
            coverage["progress"][key] = value if value is not None and value <= stamp and _receipt(value) else None
        coverage["progress"]["completion_meaning"] = "Pass completion records attempted names, not fresh market coverage."
    if coverage["source"] == "custom-universe":
        gaps.append("This cached scan uses a configured stock list; full provider-wide coverage is not established.")
    receipts = raw.get("received_at_by_ticker")
    receipts = receipts if isinstance(receipts, dict) else {}
    receipts = {ticker: received for ticker, received in receipts.items()
                if isinstance(ticker, str) and _SYMBOL.fullmatch(ticker) and _receipt(received)}
    total = coverage["universe"]
    published_roster = view.get("tickers")
    roster = None
    inconsistent = False
    if published_roster is not None:
        if not isinstance(published_roster, list) or any(
            not isinstance(ticker, str) or not _SYMBOL.fullmatch(ticker) for ticker in published_roster
        ) or len(set(published_roster)) != len(published_roster):
            inconsistent = True
        else:
            roster = set(published_roster)
    if total is not None:
        inconsistent = inconsistent or len(receipts) > total or (roster is not None and len(roster) > total)
        inconsistent = inconsistent or any(coverage[key] is not None and coverage[key] > total
                                           for key in ("attempted", "never_scanned", "latest_failed"))
        if coverage["attempted"] is not None and coverage["never_scanned"] is not None:
            inconsistent = inconsistent or coverage["attempted"] + coverage["never_scanned"] != total
        if coverage["catalog_available"] is True and (roster is None or len(roster) != total):
            inconsistent = True
    if inconsistent:
        coverage["roster_status"] = "inconsistent"
        gaps.append("The cached scan's published stock list and coverage counts disagree; no candidates or chart choices are offered.")
        result["summary"] = "The cached market scan has inconsistent coverage. No provider refresh was started."
        return result
    if roster is not None and total is not None and len(roster) == total:
        coverage.update(roster_status="complete", membership_verified=True,
                        outside_roster_receipts_excluded=sum(ticker not in roster for ticker in receipts))
        receipts = {ticker: received for ticker, received in receipts.items() if ticker in roster}
    else:
        gaps.append("The full cached stock-list membership is unverified; reported coverage counts do not establish complete coverage.")
        roster = None
    window = coverage["fresh_window_seconds"]
    window = min(60.0, window) if window is not None else 60.0
    fresh = {ticker: received for ticker, received in receipts.items()
             if isinstance(ticker, str) and _SYMBOL.fullmatch(ticker) and _receipt(received)
             and -30 <= stamp - received <= window}
    coverage["fresh"] = len(fresh)
    coverage["max_age_s"] = max((max(0, stamp - value) for value in fresh.values()), default=None)
    columns = view.get("columns")
    if not isinstance(columns, list) or any(not isinstance(name, str) for name in columns) or len(set(columns)) != len(columns):
        gaps.append("The cached scan column mapping is unavailable.")
        return result
    index = {name: position for position, name in enumerate(columns)}
    if not set(index) >= _REQUIRED or not isinstance(view.get("rows"), list):
        gaps.append("The cached scan rows are unavailable.")
        return result
    candidates, conflicts = _candidate_rows(view["rows"], index, fresh, "current_cached")
    coverage["candidates_checked"] = len(candidates)
    leading = {}
    for candidate in candidates:
        leading.setdefault(candidate["ticker"], candidate)
    coverage["stocks_with_candidates"] = len(leading)
    coverage["returned_candidates"] = min(limit, len(leading))
    coverage["candidates_truncated"] = len(leading) > limit
    coverage["conflicting_candidates_excluded"] = conflicts
    current_candidates = list(leading.values())[:limit]
    coverage["candidate_contracts_omitted"] = coverage["candidates_checked"] - len(current_candidates)
    earlier_rows = []
    findings = view.get("recent_findings")
    findings = findings if isinstance(findings, list) else []
    for record in findings[:100]:
        if not isinstance(record, dict):
            continue
        ticker, received, examples = record.get("ticker"), record.get("received_at"), record.get("examples")
        if not isinstance(ticker, str) or not _SYMBOL.fullmatch(ticker) or not _receipt(received) or not isinstance(examples, list):
            continue
        if roster is not None and ticker not in roster:
            continue
        if not -30 <= stamp - received <= 7 * 86400 or received == fresh.get(ticker):
            continue
        examples = [row for row in examples[:3] if isinstance(row, (list, tuple))
                    and len(row) > index["underlying_ticker"] and row[index["underlying_ticker"]] == ticker]
        observed, _ = _candidate_rows(examples, index, {ticker: received}, "earlier_cached")
        earlier_rows.extend(observed)
    earlier_rows.sort(key=lambda row: (-datetime.fromisoformat(row["received_at"]).timestamp(),
                                       -row["day_volume"], row["ticker"], row["contract"]))
    earlier_leading = {}
    for candidate in earlier_rows:
        earlier_leading.setdefault(candidate["ticker"], candidate)
    earlier_candidates = list(earlier_leading.values())[:max(0, limit - len(current_candidates))]
    coverage.update(earlier_findings_inspected=min(100, len(findings)),
                    earlier_candidates_checked=len(earlier_rows), earlier_stocks_with_candidates=len(earlier_leading),
                    earlier_candidates_truncated=len(earlier_leading) > len(earlier_candidates),
                    returned_current_candidates=len(current_candidates), returned_earlier_candidates=len(earlier_candidates))
    candidates = current_candidates + earlier_candidates
    coverage["returned_candidates"] = len(candidates)
    snapshot_id = "scan" + hashlib.sha256(canonical({"coverage": coverage, "candidates": candidates}).encode()).hexdigest()
    result["snapshot_id"] = snapshot_id
    facts, actions, action_tickers = [], [], set()
    for candidate in candidates:
        ids = []
        contract = {"osi": candidate["contract"], "type": candidate["contract_type"],
                    "strike": candidate["strike"], "expiry": candidate["expiry"]}
        for metric, value, unit in (("Reported daily option volume", candidate["day_volume"], "contracts"),
                                    ("Reported open interest", candidate["open_interest"], "contracts"),
                                    ("Reported volume/open interest ratio", candidate["volume_open_interest_ratio"], "ratio")):
            evidence = fact(metric, value, unit, ticker=candidate["ticker"], source="cached Public options scan",
                            snapshot_id=snapshot_id, received_at=candidate["received_at"], contract=contract,
                            status="unavailable" if value is None else candidate["status"],
                            reason="Reading unavailable" if value is None else
                                   "Earlier cached finding; original market observation time is unknown" if candidate["status"] == "stale" else
                                   "Snapshot receipt is known; original market observation time is unknown")
            facts.append(evidence)
            ids.append(evidence["id"])
        candidate["fact_ids"] = ids
        if candidate["ticker"] not in action_tickers and len(actions) < MAX_CHART_ACTIONS:
            action_tickers.add(candidate["ticker"])
            actions.append(dict(kind="open_chart", view="heatseeker", ticker=candidate["ticker"], fact_ids=ids))
    total = coverage["universe"]
    denominator = str(total) if total is not None else "an unknown available universe"
    if not coverage["membership_verified"]:
        denominator += " (full stock-list membership unverified)"
    if current_candidates:
        result["status"] = "degraded"
        names = ", ".join(dict.fromkeys(row["ticker"] for row in current_candidates[:3]))
        result["summary"] = (f"Cached options activity: {names} lead the retained examples by reported daily volume. "
                             f"Showing {len(current_candidates)} current stock examples from {coverage['candidates_checked']} qualifying retained option rows; "
                             f"{coverage['fresh']} recently checked names out of {denominator}.")
    elif earlier_candidates:
        result["status"] = "stale"
        names = ", ".join(row["ticker"] for row in earlier_candidates[:3])
        result["summary"] = (f"Earlier cached activity: {names}. Showing {len(earlier_candidates)} dated stock examples; "
                             f"these are earlier readings, not current activity. Current coverage: "
                             f"{coverage['fresh']} recently checked names out of {denominator}.")
    elif fresh:
        result["status"] = "degraded"
        result["summary"] = (f"No qualifying rows in the current cached view of {len(fresh)} recently checked names "
                             f"out of {denominator}. Older and unchecked names are not ruled out.")
    else:
        gaps.append("No checked names remain within the cached scan's receipt window.")
    if candidates:
        gaps.append("Source observation time for snapshot volume and open interest is unknown; receipt time does not prove current market activity.")
    if earlier_candidates:
        gaps.append("Earlier findings keep their original receipt dates and are never treated as current scan results.")
    if coverage.get("candidate_contracts_omitted"):
        gaps.append("One leading qualifying contract is shown per stock; extra current retained rows were checked but are not repeated here.")
    if coverage["candidates_truncated"] or coverage["earlier_candidates_truncated"]:
        gaps.append(f"At most {limit} current and earlier stock examples are shown in total; the published scan roster was not filtered by this request.")
    sections = []
    if current_candidates or fresh or not earlier_candidates:
        sections.append(dict(name="Flow", status="degraded" if fresh else "unavailable", text=result["summary"],
                             fact_ids=[identity for row in current_candidates for identity in row["fact_ids"]],
                             claim_status="non-gradeable"))
    if earlier_candidates:
        earlier_text = "\n".join(f"{row['ticker']}: {row['day_volume']:,} reported daily contracts; received {row['received_at']} (earlier cached reading)."
                                  for row in earlier_candidates)
        sections.append(dict(name="Earlier cached activity", status="stale", text=earlier_text,
                             fact_ids=[identity for row in earlier_candidates for identity in row["fact_ids"]],
                             claim_status="non-gradeable"))
    result.update(facts=facts, actions=actions, candidates=candidates, current_candidates=current_candidates,
                  earlier_candidates=earlier_candidates, sections=sections)
    return result
