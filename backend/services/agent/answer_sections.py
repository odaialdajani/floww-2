"""Server-owned answer sections built only from already saved evidence."""
from __future__ import annotations

import re

from services.agent.contracts import finite
from services.agent.narrative import explain_snapshot

SECTION_NAMES = ("Structure", "Flow", "Levels", "Vol", "Company", "What changed",
                 "Confluence", "Verdict", "Invalidation", "Trade")
METRICS = {
    "Structure": {"Underlying price", "Available contracts", "Available expiry dates",
        "Gamma exposure strikes", "Estimated gamma exposure", "Total estimated gamma exposure",
        "Displayed strikes", "Displayed expiry dates", "Displayed net gamma",
        "Displayed cumulative gamma", "Displayed total gamma", "Selected display cell",
        "Model exposure strikes", "Model gamma exposure", "Total model gamma exposure",
        "Model vanna exposure", "Total model vanna exposure", "Model charm exposure", "Total model charm exposure"},
    "Flow": {"Signed alert reading", "Cached flow regime", "Flow regime"},
    "Levels": {"Underlying price", "Cached map price", "Displayed flip", "Estimated flip levels",
        "Nearest exposure level below", "Nearest exposure level above", "Estimated air pocket lower bounds", "Estimated air pocket upper bounds"},
    "Vol": {"Implied volatility", "Implied move", "Realized volatility", "Implied move estimate",
        "Implied move percent", "Implied move lower bound", "Implied move upper bound",
        "Implied move expiry instant", "At-the-money implied volatility", "Realized daily close volatility",
        "Realized volatility observation dates", "Realized volatility close prices"},
    "Company": set(),
    "What changed": {"Price change", "Underlying price change"},
    "Confluence": {"Weighted directional agreement"},
    "Verdict": set(), "Invalidation": set(), "Trade": set(),
}
UNAVAILABLE = {
    "Structure": "Structure readings are unavailable for this scope.",
    "Flow": "No verified fresh directional flow reading is available.",
    "Levels": "No verified level reading is available for this scope.",
    "Vol": "Verified volatility readings are unavailable for this scope.",
    "Company": "Verified company overview, events and news are unavailable. No event date or news conclusion is inferred.",
    "What changed": "No compatible earlier observation has been supplied for comparison.",
    "Confluence": "Insufficient evidence for agreement across the required dimensions; missing readings are not neutral.",
    "Verdict": "Insufficient evidence for a trade direction. These are descriptive readings, not a prediction.",
    "Invalidation": "No testable prediction or verified trade setup was formed, so a price invalidation is unavailable.",
    "Trade": "No executable trade proposal is available. No order, fill or position was created.",
}
QUICK = {
    "Structure": r"\b(?:structure|positioning|gamma|gex|dealer|map)\b",
    "Flow": r"\b(?:flow|alerts?|buying|selling)\b",
    "Levels": r"\b(?:levels?|flip|support|resistance)\b",
    "Vol": r"\b(?:vol|volatility|iv|implied move|realized)\b",
    "Company": r"\b(?:company|earnings|dividend|news|events?)\b",
    "What changed": r"\b(?:changed?|since|yesterday|previous|prior|history|closing)\b",
    "Confluence": r"\b(?:confluence|agreement)\b",
    "Verdict": r"\b(?:verdict|direction|bullish|bearish)\b",
    "Invalidation": r"\b(?:invalidation|invalidate|stop)\b",
    "Trade": r"\b(?:trade|order|buy|sell|target|probability|chance|odds)\b",
}


def requested_sections(spec):
    if spec.get("price_only"):
        return ("Structure",)
    question = spec.get("question", "")
    selected = [name for name in SECTION_NAMES if re.search(QUICK[name], question, re.I)]
    full = re.search(r"\b(?:full|research|overview|analysis|analyze|analyse|outlook|breakdown|read)\b", question, re.I)
    return SECTION_NAMES if full or not selected else tuple(selected)


def _value_text(value):
    if finite(value):
        return f"{value:,.4g}"
    if isinstance(value, list):
        shown = [_value_text(item) for item in value[:12]]
        return ", ".join(shown) + ("; additional values in evidence" if len(value) > 12 else "")
    return str(value)[:300] if value is not None else "unavailable"


def _reference(item):
    return {"type": "fact_reference", "fact_id": item["id"],
            "ticker": item["ticker"], "horizon": item.get("horizon", "all")}


def _entry(name, snapshot, price_only=False):
    facts = [item for item in snapshot.get("facts", [])
             if item.get("ticker") == snapshot["ticker"]
             and item.get("metric") in ({"Underlying price"} if price_only else METRICS[name])]
    text = "; ".join(
        f"{item['metric']}: {_value_text(item['value'])} {item['unit']} "
        f"({item['status']}; observed {item.get('event_time') or 'time unknown'}; scope {item.get('horizon', 'all')})"
        for item in facts
    )
    segments = [_reference(item) for item in facts]
    note = ""
    if name == "Structure" and not price_only:
        # Preserve existing checked descriptive explanations and their references.
        note = explain_snapshot(snapshot)
        used = {item["id"] for item in facts}
        facts += [item for item in snapshot.get("facts", []) if item["id"] not in used
                  and item.get("ticker") == snapshot["ticker"] and item.get("metric") in METRICS["Levels"] | METRICS["Flow"]]
        segments = [_reference(item) for item in facts]
    if name in {"Confluence", "Verdict"}:
        note = UNAVAILABLE[name]
    elif name == "Flow" and facts:
        note = "Signed alert agreement describes the supplied alerts; it is not a profit probability."
    elif name == "Levels" and facts:
        note = "Displayed map levels retain their own scope; they are not automatically recalculated for the question's expiry range."
        if not any(item["metric"] not in {"Underlying price", "Cached map price"} for item in facts):
            note = "Only the underlying price is available; no level was established for this scope."
    if not text:
        text = UNAVAILABLE[name] if not price_only else "The cached underlying price is unavailable."
    if note and note not in text:
        text += ". " + note
    if note:
        segments.append({"type": "text", "text": note, "claim_status": "non-gradeable"})
    elif not facts:
        segments.append({"type": "text", "text": text, "claim_status": "non-gradeable"})
    window = snapshot.get("window") or {}
    scope = f"{snapshot['ticker']} · {snapshot.get('horizon', 'all')}"
    if window.get("start") and window.get("end"):
        scope += f" · expiries {window['start']} through {window['end']}"
    status = "available" if facts and all(item["status"] == "ok" for item in facts) else "degraded" if facts else "unavailable"
    if name == "Levels" and not any(item["metric"] not in {"Underlying price", "Cached map price"} for item in facts):
        status = "unavailable"
    return {"ticker": snapshot["ticker"], "horizon": snapshot.get("horizon", "all"),
            "window": window, "status": status, "text": f"{scope}: {text}",
            "source_gaps": list(snapshot.get("gaps", [])),
            "segments": segments, "fact_ids": [item["id"] for item in facts],
            "claim_status": "non-gradeable"}


def _section(name, entries):
    states = {entry["status"] for entry in entries}
    status = "available" if states == {"available"} else "unavailable" if states <= {"unavailable"} else "degraded"
    return {"name": name, "status": status, "entries": entries,
            "text": "\n".join(entry["text"] for entry in entries),
            "segments": [segment for entry in entries for segment in entry["segments"]],
            "fact_ids": list(dict.fromkeys(fid for entry in entries for fid in entry["fact_ids"])),
            "claim_status": "non-gradeable"}


def build_answer_sections(snapshots, spec):
    """No reads or model calls: retain each ticker/horizon and every referenced fact."""
    rows = snapshots or [{"ticker": ticker, "horizon": spec.get("horizon", "all"), "facts": []}
                         for ticker in spec.get("tickers", [])]
    return [_section(name, [_entry(name, row, bool(spec.get("price_only"))) for row in rows])
            for name in requested_sections(spec)]


def merge_history_section(answer, ticker, text, facts, horizon="all"):
    """Attach an already validated owned-history comparison without changing evidence."""
    section = next((item for item in answer["sections"] if item["name"] == "What changed"), None)
    entries = list(section.get("entries", [])) if section else []
    entries = [entry for entry in entries if (entry["ticker"], entry["horizon"]) != (ticker, horizon)]
    entries.append({"ticker": ticker, "horizon": horizon, "window": {},
                    "text": f"{ticker} · {horizon}: {text}",
                    "status": "available" if facts and all(f["status"] == "ok" for f in facts) else "degraded" if facts else "unavailable",
                    "fact_ids": [item["id"] for item in facts],
                    "segments": [_reference(item) for item in facts] + [{"type":"text", "text":text, "claim_status":"non-gradeable"}],
                    "claim_status": "non-gradeable"})
    replacement = _section("What changed", entries)
    if section:
        answer["sections"][answer["sections"].index(section)] = replacement
    else:
        answer["sections"].append(replacement)
    answer["sections"].sort(key=lambda item: SECTION_NAMES.index(item["name"]))
