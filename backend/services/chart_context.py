"""B24 server-resolved chart AI context: bind focus/query/scope/cursor generation.

Client numbers untrusted; no trade recommendations/orders or hidden data.
Pane removal/focus races cannot re-admit stale context.
"""
from __future__ import annotations

from datetime import UTC, datetime

MAX_NODE_AGE_SECONDS = 900
# One recording window back from the cursor: enough to join the freshest
# recorded row and to distinguish stale-but-recorded from missing.
_RECORD_WINDOW_SECONDS = 3600
# Probe-end marker covering the whole local recorded store. The future side is
# classification-only: nothing observed or received after the cursor can be
# admitted, but its presence is what proves "not yet recorded" instead of
# guessing that nothing was ever recorded.
_PROBE_END = "9999-12-31T23:59:59.999999+00:00"


def bind_context(*, focus, query, scope, cursor, generation) -> dict:
    """Create a server-resolvable descriptor; refuses incomplete binding."""
    if not focus or not query or not scope or cursor is None or generation is None:
        return {"status": "refused", "reason": "incomplete binding"}
    return {"status": "bound", "focus": focus, "query": query, "scope": scope,
            "cursor": cursor, "generation": generation}


def resolve_context(descriptor: dict, current: dict) -> dict:
    """Admit only exact generation + compatible scope; stale races refused."""
    if not isinstance(descriptor, dict) or descriptor.get("status") != "bound":
        return {"status": "refused", "reason": "unbound"}
    if descriptor.get("generation") != current.get("generation"):
        return {"status": "refused", "reason": "stale generation"}
    if descriptor.get("scope") != current.get("scope"):
        return {"status": "refused", "reason": "scope mismatch"}
    if current.get("pane_removed"):
        return {"status": "refused", "reason": "pane removed"}
    return {"status": "admitted", "focus": descriptor["focus"]}


def circuit_window(cursor) -> tuple[str, str] | None:
    """Recorded-store probe bracket for one ask cursor.

    Returns the as-of probe start one recording window before the cursor and
    the end of the local recorded store. Eligibility is decided later, at the
    cursor, by resolve_focused_chart: a row recorded after the cursor can
    never become evidence, only classify the scope as not yet knowable.
    """
    try:
        cursor = float(cursor)
    except (TypeError, ValueError):
        return None
    if cursor != cursor or cursor in {float("-inf"), float("inf")} or not 631152000 <= cursor <= 4102444800:
        return None
    return (datetime.fromtimestamp(cursor - _RECORD_WINDOW_SECONDS, UTC).isoformat(), _PROBE_END)


def resolve_focused_chart(rows, *, focus, scope, cursor) -> dict:
    """Server owns the focused-chart facts: recorded availability only.

    Rows are the recorded store's route-shaped rows from the resolver's
    probe bracket. The chosen row is the freshest by (as-of, receipt) that
    was both observed and received at or before the cursor and not older
    than the recorded node age cap. Nothing is knowable before its receipt;
    rows outside the bracket say nothing about eligibility.
    """
    if not isinstance(focus, str) or not isinstance(scope, str) or cursor is None:
        return {"status": "refused", "reason": "incomplete binding"}
    focus = focus.strip().upper()
    if isinstance(cursor, bool) or not isinstance(cursor, (int, float)) or not (0 <= float(cursor) <= 4102444800):
        return {"status": "refused", "reason": "invalid cursor"}
    rows = [row for row in (rows or []) if isinstance(row, dict)]
    if not rows:
        return {"status": "unavailable", "reason": "no recorded rows for this window"}
    if focus not in {str(row.get("ticker") or "").upper() for row in rows}:
        return {"status": "refused", "reason": "focus is not recorded in the saved scope"}
    from services.price_node_history import (
        MAX_NODE_AGE_SECONDS,
        epoch,
        recorded_nodes,
        recorded_strikes,
        scope_id,
    )
    candidates = [row for row in rows if scope_id(row) == scope]
    if not candidates:
        return {"status": "refused", "reason": "scope_not_recorded"}
    ticker_rows = [
        row for row in candidates
        if max(epoch(row.get("asof_ts")), epoch(row.get("received_at"))) <= float(cursor)
        if focus == str(row.get("ticker") or "").upper()
    ]
    if not ticker_rows:
        return {"status": "unavailable",
                "reason": "recorded scope exists but nothing was known at this cursor; not yet recorded"}
    chosen = max(ticker_rows, key=lambda row: (epoch(row["asof_ts"]), epoch(row["received_at"])))
    asof, receipt = epoch(chosen["asof_ts"]), epoch(chosen["received_at"])
    age = float(cursor) - float(asof)
    if age <= -1 or age > MAX_NODE_AGE_SECONDS:
        return {"status": "unavailable",
                "reason": f"recorded observation is out of age at this cursor ({int(age)}s)"}
    gaps: list[str] = []
    nodes = recorded_nodes(chosen)
    if not nodes:
        gaps.append("recorded_without_nodes")
    centre = upper = lower = None
    strikes = recorded_strikes(chosen)
    if strikes:
        from services.chart_exposure_centre import exposure_centre

        band = exposure_centre(strikes)
        centre, upper, lower = band["centre"], band["upper"], band["lower"]
    else:
        gaps.append("recorded_without_strikes")
    return {
        "status": "available", "focus": focus, "scope": scope, "cursor": float(cursor),
        "snapshot_id": chosen.get("snapshot_id"), "asof": chosen.get("asof_ts"),
        "received_at": chosen.get("received_at"),
        "node_known_at": datetime.fromtimestamp(max(asof, receipt), UTC).isoformat(),
        "node_age_seconds": int(age), "nodes": nodes,
        "exposure_centre": centre, "exposure_upper": upper, "exposure_lower": lower,
        "gaps": gaps, "src": "focused-chart",
    }
