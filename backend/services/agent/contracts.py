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


def request_spec(body):
    question = body.get("question")
    if not isinstance(question, str) or not question.strip() or len(question) > 2000:
        raise ValueError("Question must contain between one and two thousand characters")
    screen = copy.deepcopy(body.get("screen") or {})
    if not isinstance(screen, dict) or len(canonical(screen)) > 12000:
        raise ValueError("Invalid screen selection")
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
    horizon = normalize_horizon(body.get("horizon") or screen.get("horizon") or screen.get("dte") or "all")
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
    return dict(
        question=question.strip(),
        tickers=tickers,
        ticker=tickers[0],
        horizon=horizon,
        screen=screen,
        context_conflict=bool(screen.get("ticker") and screen["ticker"] not in tickers),
        question_scope=question_scope,
        price_only=is_price_lookup(question, tickers),
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
        if kind == "fresh" and left.get("status") == "ok" and left.get("event_time"):
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
    if not left.get("event_time") or not right.get("event_time"):
        raise ValueError("Comparison source time is unknown")
    if kind in {"rising", "falling"}:
        if (
            left["metric"] != right["metric"]
            or left["source"] != right["source"]
            or left["event_time"] <= right["event_time"]
        ):
            raise ValueError("Trend needs comparable time-ordered observations")
    elif (
        abs((datetime.fromisoformat(left["event_time"]) - datetime.fromisoformat(right["event_time"])).total_seconds())
        > 120
    ):
        raise ValueError("Comparison observations are too far apart")
    expected = left["value"] > right["value"] if kind in {"above", "rising"} else left["value"] < right["value"]
    if not expected:
        raise ValueError("Comparison contradicts saved values")
    word = {"above": "is above", "below": "is below", "rising": "rose from", "falling": "fell from"}[kind]
    return f"{label} ({left['value']:,.6g} {left['unit']}) {word} {right['metric']} ({right['value']:,.6g} {right['unit']})."
