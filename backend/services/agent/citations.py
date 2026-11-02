"""Owner-scoped citation index over saved research answers.

A saved answer keeps an evidence ledger (`answer.facts`) and its sections
reference those facts by id. This module turns that stored ledger into a
re-readable index:

* every citation has a stable id (`cit_...`) built from the owner, the turn
  and the fact id, so the same evidence saved in two turns stays two
  citations;
* the reading keeps its own source, snapshot, event clock, receipt clock,
  status and reason — the index never restates a value with different
  provenance;
* a fact that no section referenced is still listed, with `cited: false`;
* nothing is fetched, priced or rewritten here.

The index is owner-scoped by construction: it is built from the owner's own
saved turns.
"""

from __future__ import annotations

import hashlib
from typing import Any

CITATION_INDEX_VERSION = "agent-citation-index.v1"

_CITATION_FIELDS = (
    "metric", "value", "unit", "status", "reason", "source", "snapshot_id",
    "event_time", "received_at", "horizon", "ticker", "contract", "parents",
    "version",
)


def citation_id(owner: str, turn_id: str, fact_id: str) -> str:
    """A stable citation id for one fact inside one saved answer."""
    payload = "|".join([str(owner or ""), str(turn_id or ""), str(fact_id or "")])
    return "cit_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _referenced_facts(answer: dict[str, Any]) -> dict[str, list[str]]:
    """Map each referenced fact id to the sections that referenced it."""
    referenced: dict[str, list[str]] = {}
    for section in answer.get("sections") or []:
        if not isinstance(section, dict):
            continue
        name = section.get("name")
        for segment in section.get("segments") or []:
            if not isinstance(segment, dict):
                continue
            if segment.get("type") != "fact_reference":
                continue
            fact_id = segment.get("fact_id")
            if not fact_id:
                continue
            names = referenced.setdefault(str(fact_id), [])
            if name and name not in names:
                names.append(str(name))
    return referenced


def citations_from_turn(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """The citations of one saved turn."""
    if not isinstance(doc, dict):
        return []
    answer = doc.get("answer")
    if not isinstance(answer, dict):
        return []
    referenced = _referenced_facts(answer)
    owner = doc.get("owner") or ""
    turn_id = doc.get("turn_id") or ""
    rows: list[dict[str, Any]] = []
    for item in answer.get("facts") or []:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        fact_id = str(item["id"])
        row = {
            "citation_id": citation_id(owner, turn_id, fact_id),
            "turn_id": turn_id,
            "fact_id": fact_id,
        }
        for field in _CITATION_FIELDS:
            row[field] = item.get(field)
        row["cited"] = fact_id in referenced
        row["sections"] = sorted(referenced.get(fact_id, ()))
        rows.append(row)
    return rows


def build_index(docs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build the citation index over saved answers."""
    citations: list[dict[str, Any]] = []
    turns: list[str] = []
    scanned = 0
    for doc in docs or []:
        if not isinstance(doc, dict):
            continue
        scanned += 1
        rows = citations_from_turn(doc)
        if not rows:
            continue
        turn_id = doc.get("turn_id")
        if turn_id:
            turns.append(str(turn_id))
        citations.extend(rows)
    sources: dict[str, int] = {}
    for row in citations:
        source = row.get("source") or "unknown"
        sources[source] = sources.get(source, 0) + 1
    return {
        "version": CITATION_INDEX_VERSION,
        "n_turns": len(turns),
        "n_citations": len(citations),
        "turns": turns,
        "citations": citations,
        "sources": [{"source": source, "n": count}
                    for source, count in sorted(sources.items())],
        "coverage": {"turns_scanned": scanned, "turns_indexed": len(turns)},
        "note": ("Citations are read from the owner's saved answers. A citation "
                 "keeps the source, clocks and status of the reading it "
                 "points at; nothing here is recomputed or re-fetched."),
    }


def filter_index(index: dict[str, Any], *, turn_id: str | None = None,
                 metric: str | None = None) -> dict[str, Any]:
    """Narrow the index to one turn and/or one metric."""
    rows = list(index.get("citations") or [])
    if turn_id:
        rows = [row for row in rows if row.get("turn_id") == turn_id]
    if metric:
        rows = [row for row in rows if row.get("metric") == metric]
    sources: dict[str, int] = {}
    for row in rows:
        source = row.get("source") or "unknown"
        sources[source] = sources.get(source, 0) + 1
    turns = []
    for row in rows:
        turn = row.get("turn_id")
        if turn and turn not in turns:
            turns.append(turn)
    return {
        **index,
        "n_turns": len(turns),
        "n_citations": len(rows),
        "turns": turns,
        "citations": rows,
        "sources": [{"source": source, "n": count}
                    for source, count in sorted(sources.items())],
        "coverage": {**index.get("coverage", {}), "n_filtered": len(rows)},
    }


__all__ = [
    "CITATION_INDEX_VERSION",
    "build_index",
    "citation_id",
    "citations_from_turn",
    "filter_index",
]
