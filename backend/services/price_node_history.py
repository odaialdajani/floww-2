"""Historical price candles with only the node state known at the provider candle timestamp.

Missing records remain gaps. Node levels are never backfilled from today's
chain or carried across an overnight/data gap. Scope changes never mix.
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime

MAX_NODE_AGE_SECONDS = 900


def epoch(value) -> float | None:
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not math.isfinite(value):
                return None
            seconds = float(value) / 1000 if value >= 100_000_000_000 else float(value)
            datetime.fromtimestamp(seconds, UTC)  # reject out-of-range numeric dates
            return seconds
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return None  # ambiguous local times cannot support an available-at join
        return dt.timestamp()
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def _positive(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (ValueError, TypeError):
        return None


def recorded_nodes(row: dict) -> list[dict]:
    walls = row.get("walls_json") or []
    if isinstance(walls, str):
        try:
            walls = json.loads(walls)
        except (TypeError, ValueError):
            return []
    if not isinstance(walls, list):
        return []
    result = []
    for wall in walls:
        if not isinstance(wall, dict):
            continue
        level = _positive(wall.get("mid", wall.get("strike")))
        if level is None:
            continue
        result.append({"id": str(wall.get("wall_id") or level), "level": level,
                       "low": _positive(wall.get("low")) or level,
                       "high": _positive(wall.get("high")) or level})
    return result


def scope_id(row):
    """Old recorder keys omitted expiry depth; use the recorded expiries too."""
    expiries = row.get("expiries") or []
    if isinstance(expiries, str):
        try:
            expiries = json.loads(expiries)
        except ValueError:
            expiries = []
    key = str(row.get("query_key") or "")
    if isinstance(expiries, list) and expiries:
        key += "|expiries=" + ",".join(sorted(str(e) for e in expiries))
    return key + "|" + str(row.get("formula_version") or "") + "|" + str(row.get("exposure_basis") or "") if row.get("formula_version") or row.get("exposure_basis") else key


def build_history(ticker: str, bars: list[dict], snapshots: list[dict],
                  query_key: str | None = None) -> dict:
    ticker = ticker.strip().upper()
    known = []
    for row in snapshots:
        if row.get("ticker") != ticker:
            continue
        asof, received = epoch(row.get("asof_ts")), epoch(row.get("received_at"))
        if asof is None or received is None:
            continue
        known.append((max(asof, received), row))
    known.sort(key=lambda pair: (pair[0], str(pair[1].get("snapshot_id", ""))))
    clean = {}
    for bar in bars:
        at = epoch(bar.get("t"))
        prices = [_positive(bar.get(k)) for k in ("o", "h", "l", "c")]
        if at is None or None in prices:
            continue
        o, h, low, c = prices
        if not h >= max(o, low, c) or not low <= min(o, h, c):
            continue
        clean[at] = {"time": datetime.fromtimestamp(at, UTC).isoformat(),
                     "open": o, "high": h, "low": low, "close": c}
    # A later-arriving different view cannot choose this chart's default.
    end = max(clean) if clean else float("-inf")
    known = [(at, row) for at, row in known if at <= end]
    scopes = sorted({scope_id(r) for _, r in known})
    latest = max(known, key=lambda pair: (epoch(pair[1]["asof_ts"]), pair[0]), default=None)
    scope = query_key if query_key is not None else (scope_id(latest[1]) if latest else None)
    known = [(at, r) for at, r in known if scope_id(r) == scope]
    frames = []
    cursor = -1
    chosen = None
    for at, bar in sorted(clean.items()):
        while cursor + 1 < len(known) and known[cursor + 1][0] <= at:
            cursor += 1
            candidate = known[cursor]
            if chosen is None or (epoch(candidate[1]["asof_ts"]), candidate[0]) >= (epoch(chosen[1]["asof_ts"]), chosen[0]):
                chosen = candidate
        row = chosen[1] if chosen else None
        # Age is measured from the observation, not late arrival: a delayed
        # old snapshot must not become fresh merely because it arrived now.
        age = at - epoch(row["asof_ts"]) if row else None
        usable = row is not None and 0 <= age <= MAX_NODE_AGE_SECONDS
        frames.append({**bar, "nodes": recorded_nodes(row) if usable else [],
                       "snapshot_id": row.get("snapshot_id") if usable else None,
                       "nodes_known_at": datetime.fromtimestamp(chosen[0], UTC).isoformat() if usable else None,
                       "node_age_seconds": age if usable else None})
    return {"ticker": ticker, "frames": frames, "query_key": scope,
            "scopes": scopes, "node_max_age_seconds": MAX_NODE_AGE_SECONDS,
            "candles": len(frames),
            "candles_with_recorded_nodes": sum(bool(f["nodes"]) for f in frames),
            "note": "Nodes are shown only when recorded and known at the provider candle timestamp. Gaps mean no recent saved reading."}
