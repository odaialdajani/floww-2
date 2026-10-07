"""Bounded price-chart lines from already stored metric cells, with no live substitute."""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime

from services.price_node_history import MAX_NODE_AGE_SECONDS, epoch, scope_id

MAX_DETAIL_RECORDS = 256
MAX_GRID_CHARS = 131072
MAX_CONTEXT_CHARS = 32768


def _object(value, limit):
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or len(value) > limit:
        return None
    try:
        parsed = json.loads(value, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        return parsed if isinstance(parsed, dict) else None
    except (ValueError, TypeError, RecursionError):
        return None


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def _metric_cells(row, ticker, scope, candle_at):
    from services.agent.display_map import map_cache_key
    from services.agent.metric_replay import metric_evidence

    grids = _object(row.get("grids_json"), MAX_GRID_CHARS)
    context = _object(row.get("context_json"), MAX_CONTEXT_CHARS)
    if (row.get("ticker") != ticker or scope_id(row) != scope or not grids
            or grids.get("version") != "grids.v1" or not context):
        return {}, {}
    main, display = grids.get("grid"), context.get("display")
    if not isinstance(main, dict) or not isinstance(display, dict) or display.get("stale") is not False:
        return {}, {}
    strikes, expiries = main.get("strikes"), main.get("expiries")
    if (not isinstance(strikes, list) or not 1 <= len(strikes) <= 512
            or any(_number(strike) is None or strike <= 0 for strike in strikes)
            or len(set(strikes)) != len(strikes) or not isinstance(expiries, list)
            or not 1 <= len(expiries) <= 24 or any(not isinstance(expiry, str) for expiry in expiries)
            or len(set(expiries)) != len(expiries)):
        return {}, {}
    recorded_expiries = row.get("expiries")
    if isinstance(recorded_expiries, str):
        try:
            recorded_expiries = json.loads(recorded_expiries)
        except (TypeError, ValueError):
            return {}, {}
    try:
        if sorted(recorded_expiries) != sorted(expiries) or map_cache_key(ticker, display.get("map_query")) != row.get("query_key"):
            return {}, {}
    except (TypeError, ValueError):
        return {}, {}
    raw = {**display, "ticker": ticker, "snapshotId": row.get("snapshot_id"),
           "recorded_snapshot_id": row.get("snapshot_id"), "replay": True,
           "formula_version": row.get("formula_version"), "exposure_basis": row.get("exposure_basis"),
           "data_source": row.get("data_source"), "asof": row.get("asof_ts"), "grid": main}
    receipt = epoch(row.get("received_at"))
    available = epoch(row.get("asof_ts"))
    event = epoch(display.get("event_time"))
    if (None in (receipt, available, event) or max(receipt, available) > candle_at
            or not 0 <= candle_at - event < MAX_NODE_AGE_SECONDS):
        return {}, {}
    out, statuses = {}, {}
    for metric in ("vex", "charm"):
        try:
            meta, _ = metric_evidence(raw, {"metric": metric, "snapshotId": row.get("snapshot_id")},
                                      datetime.fromtimestamp(candle_at, UTC))
        except (ValueError, TypeError, KeyError, OverflowError):
            continue
        missing = "missing_vanna_inputs" if metric == "vex" else "missing_charm_inputs"
        if (not meta or meta.get("status") != "ok"
                or any(meta.get(key) != 0 for key in ("quarantined", "invalid_type", missing))):
            continue
        cells = main.get(metric + "_grid")
        if not isinstance(cells, dict) or set(cells) != set(expiries):
            continue
        candidates, complete = [], True
        for expiry in expiries:
            column = cells.get(expiry)
            if not isinstance(column, dict):
                complete = False
                break
            parsed = {}
            for key, value in column.items():
                try:
                    strike = float(key)
                except (TypeError, ValueError):
                    complete = False
                    break
                if not math.isfinite(strike) or strike not in strikes or strike in parsed or _number(value) is None:
                    complete = False
                    break
                parsed[strike] = value
            if not complete or set(parsed) != set(strikes):
                complete = False
                break
            candidates.extend((abs(value), strike, expiry, value) for strike, value in parsed.items())
        if not complete or not candidates:
            continue
        maximum = max(candidate[0] for candidate in candidates)
        statuses[metric] = "zero" if maximum == 0 else "available"
        winners = [candidate for candidate in candidates if candidate[0] == maximum]
        # A huge plateau is readable as a tie, but cannot be a compact unique line.
        if maximum == 0 or len(winners) > 8:
            continue
        out[metric] = [{"id": f"{metric}:{expiry}:{strike}", "metric": metric, "level": strike,
                        "expiry": expiry, "value": value, "unit": meta["unit"], "tied": len(winners) > 1,
                        "label": f"Largest saved {metric.upper()} cell; {expiry}" + ("; tied" if len(winners) > 1 else ""),
                        "known_at": datetime.fromtimestamp(max(receipt, available), UTC).isoformat(),
                        "age_seconds": candle_at - event}
                       for _, strike, expiry, value in winners]
    return out, statuses


def enrich_recorded_levels(history, engine):
    """Only selected owning snapshots are read; large or old fields stay unavailable."""
    result = {**history, "frames": [{**frame, "nodes": list(frame.get("nodes") or [])}
                                   for frame in history.get("frames") or []]}
    identities = list(dict.fromkeys(frame.get("snapshot_id") for frame in reversed(result["frames"])
                                   if isinstance(frame.get("snapshot_id"), str) and frame["snapshot_id"]))
    result["metric_details_truncated"] = len(identities) > MAX_DETAIL_RECORDS
    result["metric_line_coverage"] = {metric: {"checked_candles": 0, "zero_candles": 0}
                                       for metric in ("vex", "charm")}
    if not identities:
        return result
    try:
        columns = {row["name"] for row in engine.query_strict("PRAGMA table_info('heatmap_snapshots_v2')", [])}
        if not {"grids_json", "context_json", "data_source"}.issubset(columns):
            return result
        chosen = identities[:MAX_DETAIL_RECORDS]
        marks = ",".join("?" for _ in chosen)
        rows = engine.query_strict(
            "SELECT snapshot_id, ticker, query_key, expiries, formula_version, exposure_basis, asof_ts, received_at, data_source, "
            "CASE WHEN length(grids_json) <= ? THEN grids_json ELSE NULL END AS grids_json, "
            "CASE WHEN length(context_json) <= ? THEN context_json ELSE NULL END AS context_json "
            "FROM heatmap_snapshots_v2 WHERE ticker = ? AND snapshot_id IN (" + marks + ") "
            "LIMIT 256", [MAX_GRID_CHARS, MAX_CONTEXT_CHARS, history["ticker"], *chosen],
        )
    except Exception:
        result["metric_details_status"] = "unavailable"
        return result
    by_id = {row.get("snapshot_id"): row for row in rows}
    for frame in result["frames"]:
        row = by_id.get(frame.get("snapshot_id"))
        at = epoch(frame.get("time"))
        if row is None or at is None:
            continue
        levels, statuses = _metric_cells(row, history["ticker"], history.get("query_key"), at)
        frame["metric_status"] = statuses
        for metric, status in statuses.items():
            result["metric_line_coverage"][metric]["checked_candles"] += 1
            result["metric_line_coverage"][metric]["zero_candles"] += status == "zero"
        frame["nodes"].extend(node for nodes in levels.values() for node in nodes)
    result["candles_with_recorded_nodes"] = sum(bool(frame["nodes"]) for frame in result["frames"])
    result["metric_details_status"] = "checked"
    return result
