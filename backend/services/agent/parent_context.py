"""Small projections of owned, completed public evidence; never prior prose or account state."""
from __future__ import annotations

import copy
import hashlib
import re
from datetime import UTC, datetime

from services.agent.answer_sections import METRICS
from services.agent.contracts import canonical, finite, instant

MAX_PARENT_FACTS = 12
MAX_PARENT_BYTES = 8192
_PUBLIC_METRICS = frozenset(name for group in METRICS.values() for name in group) | {
    "Reported daily option volume", "Reported open interest", "Reported volume/open interest ratio",
    "Price change since saved observation", "Total estimated gamma exposure", "Maximum pain estimate",
}
_PUBLIC_SOURCES = frozenset({"public_api", "public-api", "public", "public-mid", "public-last", "public-session-close",
                             "public-regular-close", "cvserver", "cvforge", "yfinance", "yfinance-fallback", "databento",
                             "cached chain", "cached dealer map", "stored alerts", "fixed research weights",
                             "compatible saved observations", "cached public options scan", "recorded-public"})
_FIELDS = {"id", "metric", "value", "unit", "ticker", "source", "snapshot_id", "event_time", "received_at", "horizon",
           "contract", "status", "reason", "version", "parents"}
_PRIVATE = re.compile(r"https?://|\b(?:account|portfolio|password|secret|token|api[_ -]?key|authorization|cookie|balance|cash)\b", re.I)
_SAFE = re.compile(r"[A-Za-z0-9 %/$().:+_-]{1,120}")
_SYMBOL = re.compile(r"[A-Z][A-Z0-9.-]{0,11}")
_ID = re.compile(r"ev[a-f0-9]{64}")


def _public_fact(item):
    if not isinstance(item, dict) or set(item) - _FIELDS or not isinstance(item.get("metric"), str) or item["metric"] not in _PUBLIC_METRICS:
        return False
    if not isinstance(item.get("ticker"), str) or not _SYMBOL.fullmatch(item["ticker"]):
        return False
    identity, source, unit = item.get("id"), item.get("source"), item.get("unit")
    if not isinstance(identity, str) or not _ID.fullmatch(identity):
        return False
    if not isinstance(source, str) or len(source) > 240 or any(part.lower() not in _PUBLIC_SOURCES for part in source.split("; ")):
        return False
    if not isinstance(unit, str) or not _SAFE.fullmatch(unit) or _PRIVATE.search(unit):
        return False
    if not isinstance(item.get("status"), str) or item["status"] not in {"ok", "stale", "degraded", "unavailable", "missing", "unsupported", "error"}:
        return False
    if instant(item.get("event_time")) is None and instant(item.get("received_at")) is None:
        return False
    value = item.get("value")
    values = value if isinstance(value, list) else [value]
    if len(values) > 64 or any(part is not None and not finite(part) for part in values):
        return False
    for key in ("snapshot_id", "horizon", "version"):
        text = item.get(key)
        if not isinstance(text, str) or not _SAFE.fullmatch(text) or _PRIVATE.search(text):
            return False
    reason = item.get("reason")
    if reason is not None and (not isinstance(reason, str) or len(reason) > 400 or _PRIVATE.search(reason)):
        return False
    parents = item.get("parents")
    if not isinstance(parents, list) or len(parents) > 64 or any(not isinstance(value, str) or not _ID.fullmatch(value) for value in parents):
        return False
    contract = item.get("contract")
    if contract is not None:
        if not isinstance(contract, dict) or set(contract) - {"osi", "type", "strike", "expiry"}:
            return False
        for key, value in contract.items():
            if key == "strike":
                if not finite(value) or value <= 0:
                    return False
            elif not isinstance(value, str) or not _SAFE.fullmatch(value) or _PRIVATE.search(value):
                return False
    try:
        expected = "ev" + hashlib.sha256(canonical({key: value for key, value in item.items() if key != "id"}).encode()).hexdigest()
    except (ValueError, TypeError):
        return False
    return identity == expected


def completed_parent_context(parent):
    """Keep original evidence identities/times in a separate, explicitly historical group."""
    answer = parent.get("answer")
    answer = answer if isinstance(answer, dict) else {}
    candidates = answer.get("facts")
    candidates = candidates if isinstance(candidates, list) else []
    created = parent.get("created_at")
    if isinstance(created, datetime) and created.tzinfo is None:
        created = created.replace(tzinfo=UTC)  # Motor returns stored UTC dates without a zone by default.
    context = dict(turn_id=parent["turn_id"], created_at=instant(created), scope="market" if answer.get("scope") == "market" else "selected",
                   usage="prior_saved_only", status="unavailable", facts=[], omitted_facts=len(candidates),
                   fact_limit=MAX_PARENT_FACTS, projection="verified_public_readings")
    seen = set()
    for item in candidates:
        if len(context["facts"]) >= MAX_PARENT_FACTS:
            break
        if not _public_fact(item) or item["id"] in seen:
            continue
        projection = copy.deepcopy(item)
        # The original hash is verified above. Prior commentary is omitted from
        # this historical projection; original readings, IDs and times stay exact.
        if isinstance(projection.get("reason"), str):
            projection.pop("reason")
        proposed = {**context, "facts": context["facts"] + [projection]}
        if len(canonical(proposed).encode()) > MAX_PARENT_BYTES:
            continue
        seen.add(item["id"])
        context["facts"].append(projection)
    context["omitted_facts"] = len(candidates) - len(context["facts"])
    if context["facts"]:
        context["status"] = "prior_saved"
    return context
