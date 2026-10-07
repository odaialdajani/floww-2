"""Bounded immutable research values and a deliberately constrained answer grammar."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from datetime import UTC, date, datetime

from services.agent.access.horizon import normalize_horizon


def canonical(value):
    def dates(item):
        if isinstance(item, datetime):
            return instant(item)
        if isinstance(item, date):
            return item.isoformat()
        raise TypeError("Unsupported evidence value")

    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=dates)


def instant(value):
    if value is None:
        return None
    try:
        dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return None
        return dt.astimezone(UTC).isoformat()
    except (ValueError, TypeError):
        return None


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def fact(
    metric,
    value,
    unit,
    *,
    ticker,
    source,
    snapshot_id,
    event_time=None,
    received_at=None,
    horizon="all",
    contract=None,
    status="ok",
    reason=None,
    version="research-1",
    parents=None,
):
    values = value if isinstance(value, list) else [value]
    if len(values) > 512 or any(isinstance(v, (dict, list, tuple)) for v in values):
        raise ValueError("Fact must be scalar or a bounded series")
    canonical(value)  # Reject NaN/Infinity rather than laundering them into zero.
    observed = instant(event_time)
    if status == "ok" and observed is None:
        status, reason = "degraded", "Source observation time is unknown"
    result = dict(
        metric=metric,
        value=copy.deepcopy(value),
        unit=unit,
        ticker=ticker,
        source=source,
        snapshot_id=snapshot_id,
        event_time=observed,
        received_at=instant(received_at),
        horizon=horizon,
        contract=contract,
        status=status,
        reason=reason,
        version=version,
        parents=parents or [],
    )
    result["id"] = "ev" + hashlib.sha256(canonical(result).encode()).hexdigest()
    return result


def is_price_lookup(question, tickers):
    """Optimize only an explicit spot/underlying lookup; ambiguous prices stay research."""
    if len(tickers) != 1:
        return False
    text = re.sub(r"\$?\b" + re.escape(tickers[0]) + r"\b(?:['’]s)?", "", question, flags=re.IGNORECASE)
    text = " ".join(text.lower().strip(" ?.!").split())
    text = re.sub(r" (?:of|for)$", "", text)
    return bool(
        re.fullmatch(
            r"(?:(?:what is|what's|show|show me) )?(?:the )?(?:(?:current|cached|latest) )?(?:spot|underlying) price",
            text,
        )
    )


def validate_screen_context(screen):
    """Compatible v2 selector validation; numeric client values are never evidence."""
    version = screen.get("contextVersion", 1)
    if type(version) is not int or version not in (1, 2):
        raise ValueError("Unsupported screen context version")
    if version == 1:
        return
    if screen.get("page") == "flowseeker-pro":
        if screen.get("bridgeVersion") != "tidehunter-public-review.v1":
            raise ValueError("Unsupported v2 Tidehunter bridge owner")
    elif screen.get("page") not in {"heatseeker", "trinity"}:
        raise ValueError("Unsupported v2 screen context owner")
    for field in ("snapshotId", "provider", "formula", "activePane"):
        value = screen.get(field)
        if not isinstance(value, str) or not value or len(value) > 128:
            raise ValueError(f"Incomplete screen context: {field}")
    if screen["activePane"] not in {"gex", "vex", "charm", "delta", "raw", "adjusted"}:
        raise ValueError("Unknown context pane")
    expiries = screen.get("mapExpiries")
    if (not isinstance(expiries, list) or not 1 <= len(expiries) <= 24
            or any(not isinstance(e, str) for e in expiries) or len(set(expiries)) != len(expiries)):
        raise ValueError("Incomplete context expiry population")
    try:
        for expiry in expiries:
            if not isinstance(expiry, str) or date.fromisoformat(expiry).isoformat() != expiry:
                raise ValueError("Invalid context expiry")
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid context expiry") from exc
    if not isinstance(screen.get("mapQuery"), dict) or instant(screen.get("mapVersion")) is None:
        raise ValueError("Incomplete context observation query/version")
    if screen.get("selectedExpiry") is not None and screen["selectedExpiry"] not in expiries:
        raise ValueError("Selected contract/cell is outside context scope")
    wall = screen.get("selectedWall")
    if wall is not None and (not isinstance(wall, str) or not wall or len(wall) > 128):
        raise ValueError("Invalid context wall")
    contract = screen.get("selectedContract")
    if contract is not None:
        from services.contract_identity import contract_identity

        if not isinstance(contract, dict) or contract_identity(contract) is None:
            raise ValueError("Invalid exact contract context")


def _specific_history_matches(question):
    """A named date/time cannot silently become the latest saved comparison."""
    dates = r"(?:\d{4}-\d{2}-\d{2}|\d{1,4}/\d{1,2}(?:/\d{1,4})?)"
    months = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
              r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+\d{1,2}\b")
    weekdays = r"(?:(?:last|this)\s+)?(?:mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b"
    clocks = (r"(?:(?:today|yesterday)(?:['’]s)?(?:\s+at)?\s+)?"
              r"(?:\d{1,2}:\d{2}(?::\d{2})?(?:\s*[ap]\.?m\.?)?|\d{1,2}\s*[ap]\.?m\.?)\b")
    sessions = r"(?:(?:the|today's|today’s|this)\s+)?(?:market open|open|morning|afternoon|noon)\b"
    explicit_comparison = bool(re.search(
        r"\b(?:chang(?:e|ed|es)|compar(?:e|ed|ing|ison)|history|historical|saved|previous|prior|earlier)\b", question, re.I))
    introducers = (r"\b(?:since|from|after|for|with|to|versus|before|on|at)\s+(?:(?:the|an?|my|saved|earlier)\s+){0,3}"
                   if explicit_comparison else r"\b(?:since|from)\s+")
    pattern = introducers + "(?P<baseline>" + "|".join((dates, months, weekdays, clocks, sessions)) + ")"
    result = []
    for match in re.finditer(pattern, question, re.I):
        # Calendar expiry selection is separate from the comparison baseline.
        if re.search(r"\b(?:expiry|expiration|expiring|expires)\s+$", question[:match.start()], re.I):
            continue
        result.append(match)
    return result



def specific_history_baseline(question):
    """Retain the existing detector for callers that only need a yes/no result."""
    return bool(_specific_history_matches(question))


def validate_history_baseline(value):
    if value is None:
        return None
    message = "Choose one saved-history date with the date picker or YYYY-MM-DD"
    if (not isinstance(value, dict) or set(value) != {"date"} or not isinstance(value["date"], str)
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value["date"])):
        raise ValueError(message)
    try:
        if date.fromisoformat(value["date"]).isoformat() != value["date"]:
            raise ValueError(message)
    except ValueError:
        raise ValueError(message) from None
    return {"date": value["date"]}


def parse_history_baseline(question, value=None):
    """Keep a fully specified calendar day, never guess a year or clock cutoff."""
    from services.agent.answer_sections import history_excluded, requests_history

    supplied = validate_history_baseline(value)
    if history_excluded(question):
        positive_dated_price = any(
            not history_excluded(clause)
            and re.search(r"\bprices?\b", clause, re.I)
            and re.search(r"\b(?:on|as of|for|from|since|at)\s+\d{1,4}[-/]\d{1,2}", clause, re.I)
            for clause in re.split(r"[;!?]|\.(?:\s+|$)", question)
        )
        if supplied is not None or positive_dated_price:
            raise ValueError("The requested history date conflicts with the request not to use saved history")
        return None
    matches = _specific_history_matches(question)
    dated_price = bool(re.search(r"\b(?:spot|underlying|stock|share)?\s*prices?\b", question, re.I)
                       and re.search(r"\b(?:on|as of|for|from|since|at)\s+\d{1,4}[-/]\d{1,2}", question, re.I))
    context = supplied is not None or bool(matches) or requests_history(question) or dated_price
    if not context:
        return None
    message = "Specific history comparisons need the date picker or YYYY-MM-DD; incomplete dates and exact clocks are unsupported"
    if any(not re.fullmatch(r"\d{4}-\d{2}-\d{2}", match.group("baseline")) for match in matches):
        raise ValueError(message)
    dates = []
    for match in re.finditer(r"\b\d{4}-\d{1,2}-\d{1,3}\b", question):
        if re.search(r"\b(?:expiry|expiration|expiring|expires)(?:\s+on)?\s+$", question[:match.start()], re.I):
            continue
        dates.append(match.group())
    dates = list(dict.fromkeys(dates))
    clock = r"\b(?:\d{1,2}:\d{2}(?::\d{2})?(?:\s*[ap]\.?m\.?)?|\d{1,2}\s*[ap]\.?m\.?)\b"
    if re.search(clock, question, re.I) or re.search(r"\d{4}-\d{2}-\d{2}T\d{1,2}:\d{2}", question):
        raise ValueError(message)
    if len(dates) > 1:
        raise ValueError("Choose one saved-history date with the date picker or YYYY-MM-DD")
    if dates:
        parsed = validate_history_baseline({"date": dates[0]})
        if supplied is not None and parsed != supplied:
            raise ValueError("The selected history date differs from the date in the question")
        return parsed
    if supplied is not None:
        return supplied
    # A bare month/day or weekday in a history question is still not a known day.
    ambiguous = (r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
                 r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+\d{1,2}\b|"
                 r"\b(?:mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b|"
                 r"\b\d{1,4}[-/]\d{1,2}(?:[-/]\d{1,4})?\b")
    if requests_history(question) and re.search(ambiguous, question, re.I):
        raise ValueError(message)
    return None


_MARKET_SCOPE = re.compile(
    r"\b(?:(?:whole|entire|full)\s+(?:stock\s+)?market|market[- ]wide|"
    r"(?:all|every|each)\s+(?:the\s+)?(?:(?:eligible|available|possible|accessible|supported)\s+)*"
    r"(?:stocks?|tickers?|symbols?|names|funds?|etfs?))\b", re.I
)


_MARKET_DATA = re.compile(r"\bacross\s+all\s+(?:available\s+)?data\b", re.I)
_MARKET_NEGATION = re.compile(
    r"\b(?:not|never|no|do\s+not|don't|dont)(?:\s+(?:scan|check|inspect|research|analy[sz]e|search|include|look\s+at))?"
    r"(?:\s+across)?(?:\s+(?:the|an?|a))?\s*$", re.I
)


def negates_market(question):
    return any(_MARKET_NEGATION.search(question[:match.start()].rstrip())
               for pattern in (_MARKET_SCOPE, _MARKET_DATA) for match in pattern.finditer(question))


def requests_market(question):
    if negates_market(question):
        return False
    if _MARKET_SCOPE.search(question):
        return True
    # Broad data requests without a named stock may inspect the market cache;
    # a question explicitly about SPY's readings remains selected-stock research.
    symbols = re.findall(r"\$[A-Za-z][A-Za-z0-9.-]{0,11}\b|\b[A-Z][A-Z0-9.]{1,11}\b", question)
    symbols = [name for name in symbols if name not in {"AI", "USD", "ETF", "GEX", "VEX", "AND", "OR", "THE", "IV", "OI"}]
    return not symbols and bool(_MARKET_DATA.search(question))


def validate_parent_turn_id(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}", value):
        raise ValueError("Choose a valid completed saved answer for the previous context")
    return value.lower()


def request_spec(body):
    question = body.get("question")
    if not isinstance(question, str) or not question.strip() or len(question) > 2000:
        raise ValueError("Question must contain between one and two thousand characters")
    baseline = parse_history_baseline(question, body.get("history_baseline"))
    baseline_fields = {"history_baseline": baseline} if baseline is not None else {}
    parent_id = validate_parent_turn_id(body.get("parent_turn_id"))
    parent_fields = {"parent_turn_id": parent_id} if parent_id is not None else {}
    screen = copy.deepcopy(body.get("screen") or {})
    if not isinstance(screen, dict) or len(canonical(screen)) > 12000:
        raise ValueError("Invalid screen selection")
    validate_screen_context(screen)
    mode, overlay = screen.get("displayMode", "live"), screen.get("overlayMetric", "raw")
    scope = body.get("scope")
    if scope is not None and scope not in ("selected", "market"):
        raise ValueError("Choose selected-stock or market research")
    if scope == "market" and negates_market(question):
        raise ValueError("Market scope conflicts with the question; choose selected-stock research")
    if scope == "selected" and requests_market(question):
        raise ValueError("Selected-stock scope conflicts with a whole-market question")
    market = scope == "market" or scope is None and requests_market(question)
    if market:
        if baseline is not None:
            raise ValueError("Dated saved history needs selected-stock research; market scans have no saved dated baseline")
        if mode in {"replay", "range-replay"}:
            raise ValueError("Market research cannot mix a recorded chart with current cached scan findings")
        if mode not in (None, "live", "range-live"):
            raise ValueError("Market research needs a supported live view or no chart selection")
        limit = body.get("market_limit", 50)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50:
            raise ValueError("Choose between one and fifty cached scan examples")
        return dict(question=question.strip(), scope="market", tickers=[], ticker=None, horizon="all", screen=screen,
                    context_conflict=False, question_scope=None, price_only=False, market_limit=limit, **parent_fields)
    if baseline is not None and mode in {"replay", "range-replay"}:
        raise ValueError("Dated saved history cannot substitute a different observation for the recorded chart")
    range_replay = mode == "range-replay"
    if range_replay:
        from services.agent.range_replay import validate_selection

        validate_selection(screen)
    elif mode not in (None, "live", "replay") or overlay not in {"raw", "delta", "activity", "session_delta_volume", "window"}:
        raise ValueError("Research for this display is unavailable; unsupported surface or view")
    if (mode == "replay" or overlay != "raw" or isinstance(screen.get("selectedContract"), dict)) and screen.get("contextVersion") != 2:
        raise ValueError("Research for this display is unavailable; exact v2 observation context is required")
    if not range_replay and overlay == "window" and (not isinstance(screen.get("windowBaselineId"), str) or not screen["windowBaselineId"]):
        raise ValueError("Window research is unavailable; a recorded baseline identity is required")
    explicit = re.findall(r"\$([A-Za-z][A-Za-z0-9.-]{0,9})\b", question)
    # Unambiguous uppercase symbols in a market question; ordinary short words excluded.
    if not explicit:
        explicit = [
            s
            for s in re.findall(r"\b[A-Z][A-Z0-9.]{1,5}\b", question)
            if s not in {"AI", "USD", "ETF", "GEX", "VEX", "AND", "OR", "THE", "IV", "OI"}
        ]
    excluded = {
        symbol.upper() for symbol in explicit
        if re.search(
            r"\b(?:not(?:\s+use)?|don't use|except|excluding|exclude|ignore|instead of|rather than)(?:\s+the)?\s+\$?"
            + re.escape(symbol) + r"\b", question, re.IGNORECASE
        )
    }
    explicit = [symbol for symbol in explicit if symbol.upper() not in excluded]
    if excluded and not explicit:
        raise ValueError("Name the ticker you want to use, rather than only the ticker to exclude")
    tickers = list(dict.fromkeys(s.upper() for s in explicit)) or [
        str(body.get("ticker") or screen.get("ticker") or "SPY").upper()
    ]
    if len(tickers) > 3 or any(not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", t) for t in tickers):
        raise ValueError("Choose at most three valid tickers")
    horizon = (f"range:{screen['mapQuery']['min_dte']}:{screen['mapQuery']['max_dte']}" if range_replay else
               normalize_horizon(body.get("horizon") or screen.get("horizon") or screen.get("dte") or "all"))
    question_scope = None
    named_scopes = [
        value
        for pattern, value in (
            (r"\b(?:0dte|same-day expiry|expiring today|expires today|today's expiry|today's expiration)\b", "0dte"),
            (r"\b(?:next trading (?:day|session)|1dte)\b", "1dte"),
            (r"\bnext (?:five|5) (?:trading )?(?:sessions|days)\b", "week"),
            (r"\b(?:next|coming) month\b", "month"),
        )
        if re.search(pattern, question, re.IGNORECASE)
    ]
    if re.search(r"\b(?:earnings|dividend|news|economic release)\b", question, re.IGNORECASE) and not re.search(
        r"\b(?:expir\w*|0dte|1dte)\b", question, re.IGNORECASE
    ):
        named_scopes = []
    expiry_dates = list(
        dict.fromkeys(
            re.findall(
                r"\b(?:expiry|expiration|expiring|expires)(?:\s+on)?\s+(\d{4}-\d{2}-\d{2})\b", question, re.IGNORECASE
            )
        )
    )
    if len(named_scopes) + len(expiry_dates) > 1:
        raise ValueError("Choose one explicit expiry scope per question")
    if expiry_dates:
        expiry = date.fromisoformat(expiry_dates[0]).isoformat()
        horizon, question_scope = "all", {"selected_expiry": expiry}
    elif named_scopes:
        horizon, question_scope = named_scopes[0], {"selected_expiry": None}
    bounds = screen.get("expiryRange")
    if (
        bounds
        and bounds != [None, None]
        and (not explicit or tickers == [screen.get("ticker")])
        and question_scope is None
    ):
        if not isinstance(bounds, list) or len(bounds) != 2:
            raise ValueError("Invalid visible expiry range")
        lo, hi = bounds
        horizon = normalize_horizon(f"range:{0 if lo is None else lo}:{3660 if hi is None else hi}")
    if screen.get("selectedExpiry"):
        date.fromisoformat(screen["selectedExpiry"])
    if mode != "replay" and screen.get("contextVersion") == 2 and (overlay != "raw" or screen.get("selectedContract") is not None) and tickers != [screen.get("ticker")]:
        raise ValueError("Selected surface research must stay within its displayed symbol")
    if screen.get("contextVersion") == 2 and screen.get("selectedContract") is not None and question_scope is not None:
        if question_scope.get("selected_expiry") != screen.get("selectedExpiry"):
            raise ValueError("Selected contract research must stay within its listed expiry scope")
    if range_replay:
        require_scope = (tickers == [screen.get("ticker")] and (question_scope is None or
                         question_scope.get("selected_expiry") == screen.get("selectedExpiry")))
        if not require_scope or (body.get("horizon") is not None and body["horizon"] !=
                                 f"range:{screen['mapQuery']['min_dte']}:{screen['mapQuery']['max_dte']}"):
            raise ValueError("RANGE_SCOPE_MISMATCH: research must stay within the recorded selection")
        horizon = f"range:{screen['mapQuery']['min_dte']}:{screen['mapQuery']['max_dte']}"
    if mode in {"replay", "range-replay"}:
        if tickers != [screen.get("ticker")] or (question_scope is not None and
                question_scope.get("selected_expiry") not in screen.get("mapExpiries", [])):
            raise ValueError("Replay research must stay within its recorded symbol and expiry scope")
    return dict(
        question=question.strip(),
        tickers=tickers,
        ticker=tickers[0],
        horizon=horizon,
        screen=screen,
        context_conflict=bool(screen.get("ticker") and screen["ticker"] not in tickers),
        question_scope=question_scope,
        price_only=baseline is None and mode not in {"replay", "range-replay"} and is_price_lookup(question, tickers),
        **parent_fields,
        **baseline_fields,
    )


# No unrestricted model prose is published. Each interpretation is a reviewed phrase;
# all factual values are rendered by the server from supplied evidence IDs.
INTERPRETATIONS = {
    "descriptive": "These readings describe the available snapshot.",
    "limited": "Missing coverage limits this interpretation.",
    "mixed": "Available readings do not establish a single direction.",
}


def validate_model_answer(answer, ledger):
    if not isinstance(answer, dict) or set(answer) - {"sections", "relationships", "explanations"}:
        raise ValueError("Unexpected answer fields")
    sections = answer.get("sections")
    if not isinstance(sections, list) or not 1 <= len(sections) <= 8:
        raise ValueError("Invalid answer sections")
    for section in sections:
        if not isinstance(section, dict):
            raise ValueError("Invalid section")
        if set(section) - {"name", "fact_ids", "interpretation"}:
            raise ValueError("Unrestricted factual commentary is not accepted")
        if section.get("name") not in {"Market", "Structure", "Flow", "Volatility", "History"}:
            raise ValueError("Unknown section")
        refs = section.get("fact_ids")
        if (
            not isinstance(refs, list)
            or not 1 <= len(refs) <= 12
            or any(not isinstance(r, str) or r not in ledger for r in refs)
        ):
            raise ValueError("Unknown evidence")
        if section.get("interpretation") not in INTERPRETATIONS:
            raise ValueError("Unsupported interpretation")
        if section["interpretation"] != "limited" and any(ledger[r].get("status") != "ok" for r in refs):
            raise ValueError("Limited evidence needs a limited interpretation")
    checked = copy.deepcopy(answer)
    relationships = answer.get("relationships", [])
    if not isinstance(relationships, list) or len(relationships) > 8:
        raise ValueError("Invalid relationships")
    checked["relationship_text"] = [relationship_text(r, ledger) for r in relationships]
    from services.agent.explanations import select_explanations
    checked["explanations"] = select_explanations(answer.get("explanations",[]),list(ledger.values()))
    return checked


def relationship_text(relation, ledger):
    if not isinstance(relation, dict) or set(relation) - {"kind", "fact_id", "other_fact_id"}:
        raise ValueError("Invalid relationship")
    kind, ref = relation.get("kind"), relation.get("fact_id")
    if not isinstance(ref, str) or ref not in ledger:
        raise ValueError("Unknown relationship evidence")
    left = ledger[ref]
    label = f"{left['ticker']} {left['metric']}"
    if kind in {"fresh", "stale", "available", "event_date"}:
        if "other_fact_id" in relation:
            raise ValueError("Unexpected comparison evidence")
        if kind == "fresh" and left.get("status") == "ok" and instant(left.get("event_time")):
            return f"{label} was fresh at the saved observation."
        if kind == "stale" and left.get("status") == "stale":
            return f"{label} was stale at the saved observation."
        if kind == "available" and left.get("value") is not None and left.get("status") in {"ok", "degraded", "stale"}:
            return f"{label} is present in the saved evidence ({left['status']})."
        if kind == "event_date" and left.get("unit") == "date" and isinstance(left.get("value"), str):
            return f"{label}: {date.fromisoformat(left['value']).isoformat()}."
        raise ValueError("Unsupported evidence state")
    other = relation.get("other_fact_id")
    if kind not in {"above", "below", "rising", "falling"} or not isinstance(other, str) or other not in ledger:
        raise ValueError("Unsupported comparison")
    right = ledger[other]
    if any(left.get(k) != right.get(k) for k in ("unit", "ticker", "horizon")):
        raise ValueError("Incompatible comparison scope")
    if (
        left.get("status") != "ok"
        or right.get("status") != "ok"
        or not finite(left.get("value"))
        or not finite(right.get("value"))
    ):
        raise ValueError("Comparison needs healthy scalar evidence")
    left_time, right_time = instant(left.get("event_time")), instant(right.get("event_time"))
    if left_time is None or right_time is None:
        raise ValueError("Comparison source time is unknown")
    left_observed, right_observed = datetime.fromisoformat(left_time), datetime.fromisoformat(right_time)
    if kind in {"rising", "falling"}:
        if (
            left["metric"] != right["metric"]
            or left["source"] != right["source"]
            or left_observed <= right_observed
        ):
            raise ValueError("Trend needs comparable time-ordered observations")
    elif (
        abs((left_observed - right_observed).total_seconds())
        > 120
    ):
        raise ValueError("Comparison observations are too far apart")
    expected = left["value"] > right["value"] if kind in {"above", "rising"} else left["value"] < right["value"]
    if not expected:
        raise ValueError("Comparison contradicts saved values")
    word = {"above": "is above", "below": "is below", "rising": "rose from", "falling": "fell from"}[kind]
    return f"{label} ({left['value']:,.6g} {left['unit']}) {word} {right['metric']} ({right['value']:,.6g} {right['unit']})."
