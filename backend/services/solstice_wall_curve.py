"""Recorded same-wall curve (`recorded-wall-curve.v1`).

One series owns one raw structural wall inside one declared scope. Every
point is a stored observation of that wall — nothing is recomputed from a
live chain, nothing is forward-filled and no neighbouring wall is borrowed.

The rules come from `docs/RECORDED-PRODUCT-CONTRACTS.md`:

* the series key is ticker + scope + provider + session + formula + raw wall
  id + wall-definition version + metric id;
* the observation id and the content digest stay separate, so the same
  content seen twice is two observations, not one duplicated point;
* wall creation/removal, definition changes and session/scope/provider
  changes break the line and leave an explicit gap;
* missing, invalid, unavailable and a measured zero stay distinct;
* a negative cumulative change stays a retraction — never clamped to zero;
* a point is read only from stored values: there is no provider call, no
  capture and no write in this module.

Only the raw stored families are served. The adjusted/window curve and the
DUO/DVO displays stay design-only: their per-point exclusions and eligible
populations are not stored.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from typing import Any

from domain.exposure_metrics import METRIC_REGISTRY
from services.market_provenance import timestamp
from services.price_node_history import scope_id as recorder_scope_id

CURVE_VERSION = "recorded-wall-curve.v1"

# Stored wall-metric families. Each entry maps a canonical metric id to the
# stored value field plus its usable/missing/invalid counters. An unsupported
# id is refused, never approximated by another family.
WALL_METRIC_FIELDS: dict[str, tuple[str, str, str, str]] = {
    "dadgex_net_v1": ("daddex_net", "daddex_usable", "daddex_missing", "daddex_invalid"),
    "dadgex_gross_v1": ("daddex_gross", "daddex_usable", "daddex_missing", "daddex_invalid"),
    "volume_gamma_v1": ("volume_net", "volume_usable", "volume_missing", "volume_invalid"),
    "session_delta_volume_gamma_v1": (
        "session_delta_volume_net",
        "session_delta_volume_usable",
        "session_delta_volume_missing",
        "session_delta_volume_invalid",
    ),
}

# Families whose stored value is a cumulative change: a negative reading is a
# retraction of activity, not a signed exposure and never a clamped zero.
CUMULATIVE_CHANGE_METRICS = frozenset({"session_delta_volume_gamma_v1"})

# Reason codes. Every one of them is a refusal or an explicit break, never a
# zero.
REASON_NO_MATCHING_OBSERVATIONS = "NO_MATCHING_OBSERVATIONS"
REASON_SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
REASON_SCOPE_UNVERIFIED = "SCOPE_UNVERIFIED"
REASON_WALL_NOT_RECORDED = "WALL_NOT_RECORDED"
REASON_METRIC_NOT_STORED = "METRIC_NOT_STORED"
REASON_METRIC_UNSUPPORTED = "METRIC_UNSUPPORTED"
REASON_VALUE_UNAVAILABLE = "VALUE_UNAVAILABLE"
REASON_SOURCE_CLOCK_UNKNOWN = "SOURCE_CLOCK_UNKNOWN"
REASON_SOURCE_CLOCK_INVALID = "SOURCE_CLOCK_INVALID"
REASON_WALL_NOT_PRESENT = "WALL_NOT_PRESENT"
REASON_WALL_DEFINITION_CHANGED = "WALL_DEFINITION_CHANGED"
REASON_PROVIDER_CHANGED = "PROVIDER_CHANGED"
REASON_SCOPE_CHANGED = "SCOPE_CHANGED"
REASON_SESSION_ROLL = "SESSION_ROLL"
REASON_COVERAGE_TRUNCATED = "COVERAGE_TRUNCATED"
REASON_POPULATION_INCOMPLETE = "POPULATION_INCOMPLETE"
REASON_STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
REASON_DAY_INVALID = "DAY_INVALID"
REASON_CUTOFF_INVALID = "CUTOFF_INVALID"
REASON_LIMIT_OUT_OF_RANGE = "LIMIT_OUT_OF_RANGE"

_COLUMNS = (
    "snapshot_id, asof_ts, received_at, query_key, expiries, data_source, "
    "exposure_basis, formula_version, digest, walls_json, metrics_full_json, "
    "context_json, coverage_json, quality_json"
)

_FALLBACK_COLUMNS = (
    "snapshot_id, asof_ts, received_at, query_key, expiries, data_source, "
    "exposure_basis, formula_version, digest, walls_json"
)


def _loads(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return None


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _session_date(clock: datetime | None) -> str | None:
    """New York session date of a clock. The UTC day can span two sessions."""
    if clock is None:
        return None
    from zoneinfo import ZoneInfo

    return clock.astimezone(ZoneInfo("America/New_York")).date().isoformat()


def _valid_day(day: str | None) -> bool:
    if day is None:
        return True
    try:
        datetime.strptime(str(day), "%Y-%m-%d")
    except (TypeError, ValueError):
        return False
    return True


def _definition_version(wall: dict[str, Any]) -> str:
    """Wall-definition identity derived from the stored wall record.

    The stored `wall_id` hashes symbol, formula and bounds only, so a
    membership change is invisible to it. The definition version adds the
    recorded membership and basis, which is what makes a definition change
    detectable.
    """
    members = wall.get("members") or []
    if isinstance(members, list):
        member_key = ",".join(str(m) for m in members)
    else:
        member_key = str(members)
    payload = "|".join([
        str(wall.get("wall_id") or ""),
        str(wall.get("low") if wall.get("low") is not None else ""),
        str(wall.get("high") if wall.get("high") is not None else ""),
        member_key,
        str(wall.get("exposure_basis") or ""),
        str(wall.get("formula_version") or ""),
    ])
    return "wdv_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _wall_record(walls: Any, wall_id: str) -> dict[str, Any] | None:
    for wall in walls or []:
        if isinstance(wall, dict) and str(wall.get("wall_id")) == str(wall_id):
            return wall
    return None


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {
        "version": CURVE_VERSION,
        "status": "history_unavailable",
        "reason": reason,
        "metric_id": None,
        "series_key": None,
        "wall": None,
        "points": [],
        "gaps": [],
        "coverage": {"n_points": 0, "n_gaps": 0, "n_unavailable": 0, "n_partial": 0},
    }
    out.update(extra)
    return out


def _fetch_rows(conn, ticker: str) -> list[dict[str, Any]]:
    """Stored observations for one ticker, oldest first. Read-only."""
    sql = (f"SELECT {_COLUMNS} FROM heatmap_snapshots_v2 WHERE ticker = ?"
           " ORDER BY asof_ts, received_at, snapshot_id")
    try:
        rows = conn.execute(sql, [ticker]).fetchall()
        names = [name.strip() for name in _COLUMNS.split(",")]
        return [dict(zip(names, row, strict=True)) for row in rows or []]
    except Exception:
        # An older store without the additive columns still answers with the
        # base identity; the metric then reads as not stored, never guessed.
        try:
            rows = conn.execute(
                f"SELECT {_FALLBACK_COLUMNS} FROM heatmap_snapshots_v2 WHERE ticker = ?"
                " ORDER BY asof_ts, received_at, snapshot_id", [ticker]).fetchall()
        except Exception:
            return []
        names = [name.strip() for name in _FALLBACK_COLUMNS.split(",")]
        return [dict(zip(names, row, strict=True)) for row in rows or []]


def wall_curve(conn, ticker: str, *, wall_id: str, metric_id: str = "dadgex_net_v1",
               query_key: str | None = None, as_of: str | None = None,
               day: str | None = None, limit: int = 200) -> dict[str, Any]:
    """Read one recorded wall's curve from stored observations.

    `query_key` is required: an undeclared scope is refused, never widened to
    "the newest scope of the day". `day` is the New York session date and is
    taken from the recorded event clock, never from the UTC day. `as_of` is
    the replay decision cutoff — an observation whose receipt or availability
    clock is later than the cutoff is not known at that cutoff and is
    excluded.
    """
    ticker = (ticker or "").strip().upper()
    if not ticker or not wall_id:
        return _unavailable(REASON_WALL_NOT_RECORDED, metric_id=metric_id)
    if metric_id not in WALL_METRIC_FIELDS:
        return _unavailable(REASON_METRIC_UNSUPPORTED, metric_id=metric_id)
    if not query_key or not str(query_key).strip():
        return _unavailable(REASON_SCOPE_UNVERIFIED, metric_id=metric_id)
    if not _valid_day(day):
        return _unavailable(REASON_DAY_INVALID, metric_id=metric_id)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 2000:
        return _unavailable(REASON_LIMIT_OUT_OF_RANGE, metric_id=metric_id)
    cutoff = timestamp(as_of) if as_of else None
    if as_of and cutoff is None:
        return _unavailable(REASON_CUTOFF_INVALID, metric_id=metric_id)

    value_field, usable_field, missing_field, invalid_field = WALL_METRIC_FIELDS[metric_id]
    registry = METRIC_REGISTRY.get(metric_id) or {}

    rows = [row for row in _fetch_rows(conn, ticker)
            if str(row.get("query_key") or "") == str(query_key)]
    if not rows:
        return _unavailable(REASON_NO_MATCHING_OBSERVATIONS, metric_id=metric_id)

    points: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    last_point_id: str | None = None
    series: dict[str, Any] | None = None

    for row in rows:
        asof = timestamp(row.get("asof_ts"))
        received = timestamp(row.get("received_at"))
        if asof is None or received is None:
            continue
        if cutoff is not None and max(asof, received) > cutoff:
            continue

        observation_id = str(row.get("snapshot_id") or "")
        context = _loads(row.get("context_json"))
        context = context if isinstance(context, dict) else {}
        display = context.get("display")
        display = display if isinstance(display, dict) else {}
        event = timestamp(display.get("event_time") or display.get("observed_at"))
        session = _session_date(event or asof)
        if day and session != day:
            continue

        scope = {
            "query_key": row.get("query_key"),
            "scope_id": recorder_scope_id(row),
            "provider": row.get("data_source"),
            "exposure_basis": row.get("exposure_basis"),
            "formula_version": row.get("formula_version"),
            "session_date": session,
        }
        walls = _loads(row.get("walls_json"))
        wall = _wall_record(walls, wall_id)

        if wall is None:
            gaps.append({
                "after_observation_id": last_point_id,
                "before_observation_id": observation_id,
                "reason": REASON_WALL_NOT_PRESENT,
                "detail": "the requested wall is absent from this stored observation",
            })
            previous = {"observation_id": observation_id, "scope": scope, "wall": None}
            continue

        definition_version = _definition_version(wall)
        break_reason: str | None = None
        break_detail: str | None = None
        if previous is not None and previous.get("wall") is not None:
            previous_scope = previous["scope"]
            if previous_scope.get("provider") != scope.get("provider"):
                break_reason = REASON_PROVIDER_CHANGED
                break_detail = (f"{previous_scope.get('provider')} -> "
                                f"{scope.get('provider')}")
            elif previous_scope.get("scope_id") != scope.get("scope_id"):
                break_reason = REASON_SCOPE_CHANGED
                break_detail = (f"{previous_scope.get('scope_id')} -> "
                                f"{scope.get('scope_id')}")
            elif previous_scope.get("session_date") != scope.get("session_date"):
                break_reason = REASON_SESSION_ROLL
                break_detail = (f"{previous_scope.get('session_date')} -> "
                                f"{scope.get('session_date')}")
            elif previous.get("definition_version") != definition_version:
                break_reason = REASON_WALL_DEFINITION_CHANGED
                break_detail = (f"{previous.get('definition_version')} -> "
                                f"{definition_version}")
            if break_reason is not None:
                gaps.append({
                    "after_observation_id": previous["observation_id"],
                    "before_observation_id": observation_id,
                    "reason": break_reason,
                    "detail": break_detail,
                })

        metrics = _loads(row.get("metrics_full_json"))
        wall_metrics = metrics.get("wall_metrics") if isinstance(metrics, dict) else None
        entry = wall_metrics.get(str(wall_id)) if isinstance(wall_metrics, dict) else None
        coverage_json = _loads(row.get("coverage_json"))
        coverage_json = coverage_json if isinstance(coverage_json, dict) else {}
        quality = _loads(row.get("quality_json"))
        quality = quality if isinstance(quality, dict) else {}

        usable = _num((entry or {}).get(usable_field))
        missing = _num((entry or {}).get(missing_field))
        invalid = _num((entry or {}).get(invalid_field))
        value = _num((entry or {}).get(value_field))

        reason: str | None = None
        if entry is None:
            reason = REASON_METRIC_NOT_STORED
        elif not usable or value is None:
            reason = REASON_VALUE_UNAVAILABLE
        elif event is None:
            reason = REASON_SOURCE_CLOCK_UNKNOWN
        elif event > received or received > asof:
            reason = REASON_SOURCE_CLOCK_INVALID

        excluded = int(missing or 0) + int(invalid or 0)
        if reason is not None:
            status = "unavailable"
        elif excluded:
            status = "partial"
            reason = REASON_POPULATION_INCOMPLETE
        else:
            status = "ok"
        if coverage_json.get("truncated") is True and status == "ok":
            status = "partial"
            reason = REASON_COVERAGE_TRUNCATED

        expiries = _loads(row.get("expiries"))
        if not isinstance(expiries, list):
            expiries = []
        retraction = bool(
            metric_id in CUMULATIVE_CHANGE_METRICS and value is not None and value < 0)

        point = {
            "observation_id": observation_id,
            "content_digest": row.get("digest"),
            "clocks": {
                "event_time": event.isoformat() if event else None,
                "received_at": received.isoformat(),
                "available_at": asof.isoformat(),
            },
            "expiries": [str(e) for e in expiries],
            "scope": scope,
            "wall": {
                "wall_id": str(wall.get("wall_id")),
                "low": wall.get("low"),
                "high": wall.get("high"),
                "mid": wall.get("mid"),
                "members": wall.get("members") or [],
                "definition_version": definition_version,
            },
            "metric": {
                "metric_id": metric_id,
                "basis": registry.get("basis"),
                "formula": registry.get("formula"),
                "formula_version": row.get("formula_version"),
                "units": registry.get("units"),
            },
            "value": value if status != "unavailable" else None,
            "status": status,
            "reason": reason,
            "retraction": retraction,
            "source": row.get("data_source"),
            "quality": quality,
            "coverage": {
                "usable": int(usable or 0),
                "missing": int(missing or 0),
                "invalid": int(invalid or 0),
                "n_contracts": int((entry or {}).get("n_contracts") or 0),
                "unreadable_strike": int((entry or {}).get("unreadable_strike") or 0),
                "not_a_member": int((entry or {}).get("not_a_member") or 0),
                "expiries": (entry or {}).get("expiries") or [],
                "snapshot_requested": coverage_json.get("requested"),
                "snapshot_returned": coverage_json.get("returned"),
                "snapshot_truncated": bool(coverage_json.get("truncated", False)),
            },
            "line": {
                "status": "broken" if break_reason else "continuous",
                "break_reason": break_reason,
            },
        }
        points.append(point)
        last_point_id = observation_id
        if series is None:
            series = {
                "ticker": ticker,
                "query_key": scope.get("query_key"),
                "scope_id": scope.get("scope_id"),
                "provider": scope.get("provider"),
                "session_date": scope.get("session_date"),
                "formula_version": scope.get("formula_version"),
                "wall_id": str(wall.get("wall_id")),
                "wall_definition_version": definition_version,
                "metric_id": metric_id,
                "exposure_basis": scope.get("exposure_basis"),
                "units": registry.get("units"),
            }
        previous = {"observation_id": observation_id, "scope": scope, "wall": wall,
                    "definition_version": definition_version}

    if not points:
        if gaps:
            reason = gaps[0]["reason"]
        elif day:
            reason = REASON_SESSION_NOT_FOUND
        else:
            reason = REASON_NO_MATCHING_OBSERVATIONS
        return _unavailable(reason, metric_id=metric_id, gaps=gaps)

    points = points[:limit]
    n_unavailable = sum(1 for point in points if point["status"] == "unavailable")
    n_partial = sum(1 for point in points if point["status"] == "partial")
    status = "partial" if (gaps or n_partial or n_unavailable) else "ok"
    return {
        "version": CURVE_VERSION,
        "status": status,
        "reason": None,
        "metric_id": metric_id,
        "series_key": series,
        "wall": points[0]["wall"],
        "points": points,
        "gaps": gaps,
        "coverage": {"n_points": len(points), "n_gaps": len(gaps),
                     "n_unavailable": n_unavailable, "n_partial": n_partial},
        "note": ("Stored same-wall readings. Missing, invalid and unavailable stay "
                 "distinct from a measured zero; no live chain is consulted."),
    }


__all__ = [
    "CURVE_VERSION",
    "REASON_COVERAGE_TRUNCATED",
    "REASON_CUTOFF_INVALID",
    "REASON_DAY_INVALID",
    "REASON_LIMIT_OUT_OF_RANGE",
    "REASON_METRIC_NOT_STORED",
    "REASON_METRIC_UNSUPPORTED",
    "REASON_NO_MATCHING_OBSERVATIONS",
    "REASON_POPULATION_INCOMPLETE",
    "REASON_PROVIDER_CHANGED",
    "REASON_SCOPE_CHANGED",
    "REASON_SCOPE_UNVERIFIED",
    "REASON_SESSION_NOT_FOUND",
    "REASON_SESSION_ROLL",
    "REASON_SOURCE_CLOCK_INVALID",
    "REASON_SOURCE_CLOCK_UNKNOWN",
    "REASON_STORE_UNAVAILABLE",
    "REASON_VALUE_UNAVAILABLE",
    "REASON_WALL_DEFINITION_CHANGED",
    "REASON_WALL_NOT_PRESENT",
    "REASON_WALL_NOT_RECORDED",
    "WALL_METRIC_FIELDS",
    "wall_curve",
]
