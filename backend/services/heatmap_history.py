"""
backend/services/heatmap_history.py — Solstice recorder + deterministic replay (T09).

Additive, versioned DuckDB tables. Research history is immutable and separate
from the short Mongo display cache. Replay reconstructs what was AVAILABLE at
the decision time (known-at / received_at), never future information.

Tables:
  contract_observations_v2, heatmap_snapshots_v2, wall_events_v1,
  scenario_decisions_v1, candidate_quotes_v1, execution_events_v1 (disarmed),
  outcome_labels_v1
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from typing import Any

from services.connection_guard import guarded_connection

log = logging.getLogger(__name__)

SCHEMA_VERSION = "2"

# Recorder ordering is nested inside the shared connection guard.
# Reads, writes, commit and rollback hold the same connection lock.
_RECORDER_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def snapshot_digest(payload: dict[str, Any]) -> str:
    """Recorder identity = canonical content digest (P02/R4-01, R4-13).

    Content-addressed storage deduplicates unchanged blobs; every distinct
    usable OBSERVATION still gets its own row (see record_snapshot, which
    keys rows by observation ID = content + asof + ticker). Observation time
    lives in the row, not the digest.
    """
    from services.heatmap_snapshot import content_digest
    return content_digest(payload)


def normalize_stored_contract(row: dict[str, Any]) -> dict[str, Any]:
    """Lossless adapter: DB contract row → canonical contract identity (R5-B/R06).

    The table stores side as `opt_type` and timestamps as `bid_ts/ask_ts/
    last_ts`; producers use `type` and `bid_timestamp/...`. Without this
    adapter record→replay→window matching silently yields zero comparable
    rows. Strikes normalize to exact floats; provenance passes through.
    """
    if not isinstance(row, dict):
        return {}
    out = dict(row)
    out["type"] = row.get("type") or row.get("opt_type")
    out["bid_timestamp"] = row.get("bid_timestamp") or row.get("bid_ts")
    out["ask_timestamp"] = row.get("ask_timestamp") or row.get("ask_ts")
    out["last_timestamp"] = row.get("last_timestamp") or row.get("last_ts")
    try:
        out["strike"] = float(row.get("strike")) if row.get("strike") is not None else None
    except (TypeError, ValueError):
        out["strike"] = None
    return out


def observation_id_for(payload: dict[str, Any]) -> str:
    """One issued observation ID per usable observation (R5-A/R03).

    Content digest + observation time + ticker: identical exposure observed
    twice yields two observation rows (e.g. a volume-only update changes no
    exposure blob but is a new observation with new clocks). A valid cache
    hit reuses the same asof and therefore the same observation ID — it must
    not invent a new market event.
    """
    from services.heatmap_snapshot import snapshot_id_for
    return snapshot_id_for(payload)


DDL = {
    "contract_observations_v2": """
        CREATE TABLE IF NOT EXISTS contract_observations_v2 (
            snapshot_id VARCHAR, ticker VARCHAR, osi VARCHAR, expiry VARCHAR,
            strike DOUBLE, opt_type VARCHAR, multiplier DOUBLE,
            bid DOUBLE, ask DOUBLE, last DOUBLE,
            bid_ts VARCHAR, ask_ts VARCHAR, last_ts VARCHAR, received_at VARCHAR,
            volume DOUBLE, oi DOUBLE, oi_effective_date VARCHAR,
            iv DOUBLE, delta DOUBLE, gamma DOUBLE, theta DOUBLE, vega DOUBLE,
            greeks_source VARCHAR, provider VARCHAR, exposure_basis VARCHAR,
            calculated_at VARCHAR
        )
    """,
    "heatmap_snapshots_v2": """
        CREATE TABLE IF NOT EXISTS heatmap_snapshots_v2 (
            snapshot_id VARCHAR PRIMARY KEY, ticker VARCHAR, query_key VARCHAR,
            expiries VARCHAR, spot DOUBLE, data_source VARCHAR, exposure_basis VARCHAR,
            formula_version VARCHAR, asof_ts VARCHAR, received_at VARCHAR,
            n_contracts INTEGER, n_usable INTEGER, digest VARCHAR,
            strikes_json VARCHAR, walls_json VARCHAR
        )
    """,
    "wall_events_v1": """
        CREATE TABLE IF NOT EXISTS wall_events_v1 (
            wall_id VARCHAR, ticker VARCHAR, event VARCHAR, at_ts VARCHAR,
            snapshot_id VARCHAR, evidence VARCHAR, scope VARCHAR
        )
    """,
    "scenario_decisions_v1": """
        CREATE TABLE IF NOT EXISTS scenario_decisions_v1 (
            decision_id VARCHAR, ticker VARCHAR, at_ts VARCHAR, snapshot_id VARCHAR,
            scenario VARCHAR, side VARCHAR, eligible BOOLEAN, reason_codes VARCHAR,
            features VARCHAR
        )
    """,
    "candidate_quotes_v1": """
        CREATE TABLE IF NOT EXISTS candidate_quotes_v1 (
            decision_id VARCHAR, osi VARCHAR, bid DOUBLE, ask DOUBLE,
            bid_ts VARCHAR, ask_ts VARCHAR, delta DOUBLE, spread_ticks DOUBLE,
            rejected BOOLEAN, reject_reason VARCHAR, at_ts VARCHAR
        )
    """,
    "execution_events_v1": """
        CREATE TABLE IF NOT EXISTS execution_events_v1 (
            intent_id VARCHAR, ticker VARCHAR, at_ts VARCHAR, stage VARCHAR,
            venue VARCHAR, detail VARCHAR
        )
    """,
    "decision_reviews_v1": """
        CREATE TABLE IF NOT EXISTS decision_reviews_v1 (
            decision_id VARCHAR PRIMARY KEY, state VARCHAR,
            reason VARCHAR, note VARCHAR, reviewed_at VARCHAR
        )
    """,
    "outcome_labels_v1": """
        CREATE TABLE IF NOT EXISTS outcome_labels_v1 (
            decision_id VARCHAR, ticker VARCHAR, horizon_s INTEGER, label VARCHAR,
            label_version VARCHAR, at_ts VARCHAR, censored BOOLEAN, detail VARCHAR,
            policy_version VARCHAR
        )
    """,
    "price_paths_v1": """
        CREATE TABLE IF NOT EXISTS price_paths_v1 (
            at_ts DOUBLE, ticker VARCHAR, price DOUBLE, source VARCHAR,
            received_at VARCHAR
        )
    """,
    "capability_observations_v1": """
        CREATE TABLE IF NOT EXISTS capability_observations_v1 (
            at_ts VARCHAR, ticker VARCHAR, operation VARCHAR,
            requested INTEGER, returned INTEGER, usable INTEGER,
            truncated BOOLEAN, detail VARCHAR
        )
    """,
}


@guarded_connection
def ensure_tables(conn) -> None:
    for name, ddl in DDL.items():
        try:
            conn.execute(ddl)
        except Exception as e:
            log.warning("heatmap_history ensure %s failed: %s", name, e)
    # Additive migration for DBs created before strikes/walls capture.
    for col in ("strikes_json", "walls_json"):
        try:
            conn.execute(f"ALTER TABLE heatmap_snapshots_v2 ADD COLUMN IF NOT EXISTS {col} VARCHAR")
        except Exception as e:
            log.warning("heatmap_history migrate %s failed: %s", col, e)
    for col in ("coverage_json", "quality_json", "scenarios_json",
                "interactions_json", "grid_meta_json", "grids_json"):
        try:
            conn.execute(f"ALTER TABLE heatmap_snapshots_v2 ADD COLUMN IF NOT EXISTS {col} VARCHAR")
        except Exception as e:
            log.warning("heatmap_history migrate %s failed: %s", col, e)
    # R7-03: full wall-local metrics + visible context (session/scout/regime/
    # patterns/vanna/moneyness) so replay restores the inspector, not cells.
    for col in ("metrics_full_json", "context_json"):
        try:
            conn.execute(f"ALTER TABLE heatmap_snapshots_v2 ADD COLUMN IF NOT EXISTS {col} VARCHAR")
        except Exception as e:
            log.warning("heatmap_history migrate %s failed: %s", col, e)
    # R8-05: policy_version keys outcome idempotency (decision/horizon/
    # policy/version); price_paths_v1 stores the worker's price observations.
    for col in ("policy_version",):
        try:
            conn.execute(f"ALTER TABLE outcome_labels_v1 ADD COLUMN IF NOT EXISTS {col} VARCHAR")
        except Exception as e:
            log.warning("heatmap_history migrate %s failed: %s", col, e)


@guarded_connection
def recorder_status(conn, path: str | None = None) -> dict[str, Any]:
    """Honest durability status (R4-13/P07, R6-3/B04): inspect the ACTUAL
    database backing — never infer health from a configured path string.

    A :memory: connection (or a memory-backed file-looking path) reports
    mode memory / durable False even when DUCKDB_PATH names a file. Only a
    file-backed connection with tables present reports durable True.
    Disk failure / unusable path must never claim durable recording.
    """
    try:
        import os as _os
        p = path if path is not None else _os.environ.get("DUCKDB_PATH", ":memory:")
        backing = "unknown"
        tables: list[str] = []
        if conn is not None:
            try:
                dblist = conn.execute("PRAGMA database_list").fetchall()
                files = [str(r[2]) for r in (dblist or []) if len(r) > 2 and r[2]]
                backing = "file" if files else "memory"
            except Exception:
                backing = "unknown"
            try:
                rows = conn.execute("SHOW TABLES").fetchall()
                tables = [str(r[0]) for r in (rows or [])]
            except Exception:
                tables = []
        durable = backing == "file" and len(tables) > 0
        return {"durable": durable,
                "mode": backing if backing != "unknown" else ("file" if p != ":memory:" else "memory"),
                "backing": backing, "path": p, "tables": tables,
                "note": "memory mode is not crash-safe durable storage"}
    except Exception as e:
        return {"durable": False, "mode": "unknown", "error": str(e)}


@guarded_connection
def record_capability(conn, ticker: str, operation: str,
                      requested: int | None = None, returned: int | None = None,
                      usable: int | None = None, truncated: bool = False,
                      detail: dict | None = None) -> None:
    """Production capability/coverage writer (R4-18/P07): nonzero linked records.

    R6-3/B04: serialized on the single-writer lock with snapshots, wall
    events, decisions and outcomes — one writer owner for the connection.
    """
    try:
        ensure_tables(conn)
        with _RECORDER_LOCK:
            conn.execute("INSERT INTO capability_observations_v1 VALUES ("
                         + ",".join([_esc(_now_iso()), _esc(ticker), _esc(operation),
                                     _esc(requested), _esc(returned), _esc(usable),
                                     _esc(1 if truncated else 0),
                                     _esc(json.dumps(detail or {}, default=str))]) + ")")
    except Exception as e:
        log.warning("capability record failed: %s", e)


def _esc(v: Any) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v).replace("'", "''")
    return f"'{s}'"


@guarded_connection
def attach_outcomes_to_decisions(conn, results: dict[str, dict[str, Any]]) -> None:
    """After close_episodes, copy outcome labels into decision features.

    R8-05: the review journal (`GET /{ticker}/decisions`) shows the frozen
    episode layout PLUS the latest outcome label. Terminal outcomes are
    idempotent; censored/indeterminate are overwritten on re-processing
    (the close_episodes path already does this in outcome_labels_v1).
    Scalar results keep the outcome_label keys; multi-horizon results
    ({horizon: res}) are stored under outcome_labels.
    """
    try:
        for did, res in results.items():
            if isinstance(res, dict) and "label" not in res and res:
                _labels = {str(h): {"label": r.get("label"),
                                    "censored": bool(r.get("censored", False)),
                                    "detail": r.get("detail")}
                           for h, r in res.items() if isinstance(r, dict)}
                _patch = {"outcome_labels": _labels,
                          "outcome_updated_at": _now_iso()}
            else:
                label = res.get("label") if isinstance(res, dict) else None
                censored = res.get("censored", False) if isinstance(res, dict) else False
                detail = res.get("detail") if isinstance(res, dict) else None
                _patch = {"outcome_label": label,
                          "outcome_censored": censored,
                          "outcome_detail": detail,
                          "outcome_updated_at": _now_iso()}
            try:
                with _RECORDER_LOCK:
                    conn.execute("UPDATE scenario_decisions_v1 SET features = "
                                 + _esc(json.dumps({
                                     **(_parse_features(conn, did)),
                                     **_patch,
                                 }, default=str))
                                 + " WHERE decision_id = " + _esc(did))
            except Exception as _ue:
                log.debug("attach outcome to %s: %s", did, _ue)
    except Exception as e:
        log.debug("attach_outcomes_to_decisions: %s", e)


@guarded_connection
def _parse_features(conn, did: str) -> dict[str, Any]:
    """Read the current features JSON for a decision."""
    try:
        rows = conn.execute("SELECT features FROM scenario_decisions_v1 "
                            "WHERE decision_id = " + _esc(did)).fetchall()
        if rows:
            raw = rows[0][0]
            if isinstance(raw, str):
                return __import__("json").loads(raw)
            return raw or {}
    except Exception as e:
        log.debug("heatmap_history _parse_features failed for %s: %s", did, e)
    return {}


@guarded_connection
def record_snapshot(conn, payload: dict[str, Any], query_key: str = "",
                    snapshot_id: str | None = None) -> str | None:
    """Record one heatmap payload + its contracts. Returns snapshot_id or None.

    R4-13/P07 + R5-B/R07 atomicity and truth: single-writer lock, one
    transaction (BEGIN → dedup-verify → cleanup → header + contracts + full
    cells → COMMIT). A failed COMMIT is never acknowledged: ROLLBACK runs
    and None returns, so zero half-records exist. Retry of the same
    observation ID completes missing contracts instead of skipping via
    dedup. Coverage (requested/returned/usable/truncated) is explicit — no
    silent 2,000-row truncation. Complete versioned cells persist (not just
    metadata), plus quality/scenarios/interactions/grid-meta. Never stores
    repeated cache hits as new events: caller must only invoke on fresh
    builds, not stale-serve paths.

    Concurrency policy: shared connection lock covers the complete operation,
    including reads, commit and rollback; engine writers use the same lock.
    """
    try:
        ensure_tables(conn)
    except Exception as e:
        log.warning("heatmap_history record failed (non-fatal): %s", e)
        return None
    try:
        sid = snapshot_id or observation_id_for(payload)
        contracts = payload.get("contracts") or []
        # Heatmap payloads carry strike rows + grid + walls rather than full
        # contracts; record those (contracts recorded when present).
        strikes = payload.get("strikes") or []
        walls = ((payload.get("metrics") or {}).get("walls")) or []
        usable = sum(1 for c in contracts if isinstance(c, dict) and c.get("strike"))
        cov = payload.get("coverage") or {}
        requested = cov.get("requested", len(contracts))
        returned = cov.get("returned", len(contracts))
        truncated = bool(cov.get("truncated", False))
        coverage = {"requested": requested, "returned": returned,
                    "usable": usable, "truncated": truncated}
    except Exception as e:
        log.warning("heatmap_history record failed (non-fatal): %s", e)
        return None
    try:
        with _RECORDER_LOCK:
            conn.execute("BEGIN")
            try:
                # Idempotent but verifying: header exists AND contracts
                # complete → COMMIT the read-only txn and return; header with
                # missing contracts (crash) → rewrite inside this txn. A
                # failed dedup read falls through to insert (PK guards dups).
                n = conn.execute(
                    "SELECT COUNT(*) FROM heatmap_snapshots_v2 WHERE snapshot_id = "
                    + _esc(sid)).fetchone()
                if n and n[0] > 0:
                    m = conn.execute(
                        "SELECT COUNT(*) FROM contract_observations_v2 WHERE snapshot_id = "
                        + _esc(sid)).fetchone()
                    if m and m[0] >= len(contracts):
                        conn.execute("COMMIT")
                        return sid
                    conn.execute("DELETE FROM contract_observations_v2 WHERE snapshot_id = "
                                 + _esc(sid))
                    conn.execute("DELETE FROM heatmap_snapshots_v2 WHERE snapshot_id = "
                                 + _esc(sid))
            except Exception as dedup_e:
                log.debug("dedup check failed, proceeding to insert: %s", dedup_e)
            try:
                cols = [d[1] for d in
                        conn.execute("PRAGMA table_info(heatmap_snapshots_v2)").fetchall()]
            except Exception:
                cols = []
            # Named-column insert: new payload columns (coverage/quality/
            # scenarios/interactions/grid-meta) persist when the table has
            # them, older DBs without the migration keep working.
            grids = ((payload.get("metrics") or {}).get("grids")) or {}
            grid_meta = {}
            for _gn, _g in grids.items():
                if isinstance(_g, dict):
                    _grid = _g.get("grid") or {}
                    grid_meta[str(_gn)] = {
                        "expiries": sorted(_grid.keys()) if isinstance(_grid, dict) else [],
                        "n_cells": sum(len(v) for v in _grid.values()) if isinstance(_grid, dict) else 0,
                        "status": _g.get("status"), "reason": _g.get("reason"),
                        "missing_delta": _g.get("missing_delta"),
                        "exposure_basis": _g.get("exposure_basis")}
            _extra = {"coverage_json": json.dumps(coverage, default=str),
                      "quality_json": json.dumps(payload.get("quality", {}), default=str),
                      "scenarios_json": json.dumps(payload.get("scenarios", [])[:12], default=str),
                      "interactions_json": json.dumps(payload.get("interactions", [])[:12], default=str),
                      "grid_meta_json": json.dumps(grid_meta, default=str),
                      "grids_json": json.dumps(_full_grids(payload), default=str),
                      # R7-03: wall-local comparison inputs + visible context.
                      # Full metrics (wall_window, wall_metrics, nearest) and
                      # context (session/scout/regime/patterns/vanna/moneyness)
                      # travel with the record so replay restores the
                      # inspector, not just cells.
                      "metrics_full_json": json.dumps(payload.get("metrics", {}), default=str),
                      "context_json": json.dumps({
                          "session": payload.get("session"),
                          "playbook": payload.get("playbook"),
                          "scout": payload.get("scout"),
                          "gamma_regime_v1": payload.get("gamma_regime_v1"),
                          "patterns_v1": payload.get("patterns_v1"),
                          "vanna_v1": payload.get("vanna_v1"),
                          "moneyness": payload.get("moneyness")}, default=str)}
            _base_cols = ["snapshot_id", "ticker", "query_key", "expiries", "spot",
                          "data_source", "exposure_basis", "formula_version",
                          "asof_ts", "received_at", "n_contracts", "n_usable",
                          "digest", "strikes_json", "walls_json"]
            _base_vals = [sid, payload.get("ticker"), query_key,
                          json.dumps(payload.get("expiries_used", [])),
                          payload.get("spot"), payload.get("data_source"),
                          payload.get("exposure_basis"), payload.get("formula_version"),
                          payload.get("asof"), payload.get("source_received_at"),
                          len(contracts), usable,
                          snapshot_digest(payload),
                          json.dumps(strikes[:500], default=str),
                          json.dumps(walls, default=str)]
            _use_cols = list(_base_cols)
            _use_vals = list(_base_vals)
            for _k, _v in _extra.items():
                if _k in cols:
                    _use_cols.append(_k)
                    _use_vals.append(_v)
            conn.execute(
                f"INSERT INTO heatmap_snapshots_v2 ({', '.join(_use_cols)}) VALUES ("
                + ",".join(_esc(v) for v in _use_vals) + ")")
            for c in contracts:
                if not isinstance(c, dict):
                    continue
                conn.execute(
                    "INSERT INTO contract_observations_v2 VALUES ("
                    + ",".join([_esc(sid), _esc(payload.get("ticker")), _esc(c.get("osi")),
                                _esc(c.get("expiry")), _esc(c.get("strike")), _esc(c.get("type")),
                                _esc(c.get("multiplier", 100.0)), _esc(c.get("bid")), _esc(c.get("ask")),
                                _esc(c.get("last")), _esc(c.get("bid_timestamp")),
                                _esc(c.get("ask_timestamp")), _esc(c.get("last_timestamp")),
                                _esc(c.get("received_at")), _esc(c.get("volume")), _esc(c.get("oi")),
                                _esc(c.get("oi_effective_date")), _esc(c.get("iv")), _esc(c.get("delta")),
                                _esc(c.get("gamma")), _esc(c.get("theta")), _esc(c.get("vega")),
                                _esc(c.get("greeks_source")), _esc(c.get("oi_source", "public_api")),
                                _esc(c.get("exposure_basis", payload.get("exposure_basis"))),
                                _esc(payload.get("asof"))]) + ")")
            # Hard COMMIT: a failed commit is never acknowledged — control
            # falls to ROLLBACK + None below, leaving zero half-records.
            conn.execute("COMMIT")
            return sid
    except Exception as e:
        import contextlib as _ctxlib3
        # silent by design: ROLLBACK is best-effort cleanup; the caller still
        # gets None below, never a success ack for a failed write.
        with _ctxlib3.suppress(Exception):
            conn.execute("ROLLBACK")
        log.warning("heatmap_history record failed (non-fatal): %s", e)
        return None


def _full_grids(payload: dict[str, Any]) -> dict[str, Any]:
    """Complete versioned cell maps (R5-B/R05, R6-1 hydration): main grid +
    metric grids WITH axes, basis and status.

    Metadata alone (expiry names, cell counts) cannot reproduce the grid, and
    axes stripped from cells cannot hydrate it. Cells persist as string-keyed
    maps exactly as served; replay returns them verbatim for the same
    components to render. Version key: grids.v1.
    """
    out: dict[str, Any] = {"version": "grids.v1"}
    main = payload.get("grid")
    if isinstance(main, dict):
        section: dict[str, Any] = {"exposure_basis": main.get("exposure_basis", "OI"),
                                   "formula_version": main.get("formula_version", "gex.v2")}
        for k in ("grid", "charm_grid", "vex_grid", "vomma_grid"):
            if isinstance(main.get(k), dict):
                section[k] = main[k]
        _axes(section)
        out["grid"] = section
    grids = ((payload.get("metrics") or {}).get("grids")) or {}
    if isinstance(grids, dict):
        for name, g in grids.items():
            if isinstance(g, dict) and isinstance(g.get("grid"), dict):
                section = {"grid": g["grid"],
                           "exposure_basis": g.get("exposure_basis"),
                           "formula_version": g.get("formula_version", "gex.v2"),
                           "status": g.get("status"), "reason": g.get("reason"),
                           "missing_delta": g.get("missing_delta"),
                           "quarantined": g.get("quarantined")}
                if isinstance(g.get("expiries"), list):
                    section["expiries"] = g["expiries"]
                if isinstance(g.get("strikes"), list):
                    section["strikes"] = g["strikes"]
                _axes(section)
                out[str(name)] = section
    return out


def _axes(section: dict[str, Any]) -> None:
    """Derive missing expiry/strike axes from cell maps in place (R6-1).

    Hydration must not depend on the producer remembering axes: expiry keys
    are authoritative, strike keys parse back to numbers where possible.
    """
    cells = section.get("grid")
    if not isinstance(cells, dict):
        return
    if "expiries" not in section:
        section["expiries"] = sorted(cells.keys())
    if "strikes" not in section:
        seen: list[float] = []
        for col in cells.values():
            if not isinstance(col, dict):
                continue
            for k in col:
                try:
                    f = float(k)
                except (TypeError, ValueError):
                    continue
                if f not in seen:
                    seen.append(f)
        section["strikes"] = sorted(seen)


@guarded_connection
def record_wall_event(conn, wall_id: str, ticker: str, event: str,
                      snapshot_id: str, evidence: dict | None = None,
                      scope: str = "") -> None:
    """R6-3/B04: serialized on the single-writer lock with snapshots."""
    try:
        ensure_tables(conn)
        with _RECORDER_LOCK:
            conn.execute("INSERT INTO wall_events_v1 VALUES ("
                         + ",".join([_esc(wall_id), _esc(ticker), _esc(event), _esc(_now_iso()),
                                     _esc(snapshot_id), _esc(json.dumps(evidence or {}, default=str)),
                                     _esc(scope)]) + ")")
    except Exception as e:
        log.warning("wall event record failed: %s", e)


@guarded_connection
def latest_wall_state(conn, wall_id: str, ticker: str, scope: str = "") -> dict | None:
    """Load the most recent interaction state for a scoped wall ID.

    R4-06/P04 join key: (ticker, scope, wall_id). Returns the stored state
    dict (state/at/approach_side/inside_since/beyond_since/beyond_side) or
    None when no history exists. Never synthesizes across symbols/scopes.
    """
    try:
        ensure_tables(conn)
        rows = conn.execute(
            "SELECT event, at_ts, evidence FROM wall_events_v1 WHERE wall_id = "
            + _esc(wall_id) + " AND ticker = " + _esc(ticker)
            + (" AND scope = " + _esc(scope) if scope else "")
            + " ORDER BY at_ts DESC LIMIT 1").fetchall()
        if not rows:
            return None
        event, at_ts, evidence = rows[0][0], rows[0][1], rows[0][2]
        try:
            ev = json.loads(evidence) if isinstance(evidence, str) else (evidence or {})
        except Exception:
            ev = {}
        if not isinstance(ev, dict):
            ev = {}
        state = {"state": ev.get("state", event), "at": ev.get("at", at_ts),
                 "approach_side": ev.get("approach_side"),
                 "inside_since": ev.get("inside_since"),
                 "beyond_since": ev.get("beyond_since"),
                 "beyond_side": ev.get("beyond_side"),
                 "adverse_side": ev.get("adverse_side"),
                 "reclaim_state": ev.get("reclaim_state"),
                 "data_source": ev.get("data_source")}
        return state
    except Exception as e:
        log.debug("latest_wall_state failed: %s", e)
        return None


@guarded_connection
def record_decision(conn, decision: dict[str, Any]) -> str:
    """Record scenario decision incl. no-trade with all features known then.

    R6-3/B04: serialized on the single-writer lock with snapshots.
    """
    import uuid
    did = decision.get("decision_id") or f"dec_{uuid.uuid4().hex[:12]}"
    try:
        ensure_tables(conn)
        with _RECORDER_LOCK:
            conn.execute("INSERT INTO scenario_decisions_v1 VALUES ("
                         + ",".join([_esc(did), _esc(decision.get("ticker")), _esc(_now_iso()),
                                     _esc(decision.get("snapshot_id")), _esc(decision.get("scenario")),
                                     _esc(decision.get("side")), _esc(1 if decision.get("eligible") else 0),
                                     _esc(json.dumps(decision.get("reason_codes", []))),
                                     _esc(json.dumps(decision.get("features", {}), default=str))]) + ")")
            for q in decision.get("candidate_quotes", []) or []:
                conn.execute("INSERT INTO candidate_quotes_v1 VALUES ("
                             + ",".join([_esc(did), _esc(q.get("osi")), _esc(q.get("bid")),
                                         _esc(q.get("ask")), _esc(q.get("bid_ts")), _esc(q.get("ask_ts")),
                                         _esc(q.get("delta")), _esc(q.get("spread_ticks")),
                                         _esc(1 if q.get("rejected") else 0),
                                         _esc(q.get("reject_reason")), _esc(_now_iso())]) + ")")
    except Exception as e:
        log.warning("decision record failed: %s", e)
    return did


@guarded_connection
def record_outcome(conn, decision_id: str, ticker: str, horizon_s: int,
                   label: str, label_version: str = "outcome.v1",
                   censored: bool = False, detail: dict | None = None,
                   policy_version: str | None = None) -> None:
    """R6-3/B04 + R8-05: serialized on the single-writer lock with snapshots.

    Named-column insert (schema-tolerant); policy_version participates in
    the outcome idempotency key (decision/horizon/policy/version).
    """
    try:
        ensure_tables(conn)
        with _RECORDER_LOCK:
            conn.execute("INSERT INTO outcome_labels_v1 "
                         "(decision_id, ticker, horizon_s, label, label_version, "
                         "at_ts, censored, detail, policy_version) VALUES ("
                         + ",".join([_esc(decision_id), _esc(ticker), _esc(horizon_s),
                                     _esc(label), _esc(label_version), _esc(_now_iso()),
                                     _esc(1 if censored else 0),
                                     _esc(json.dumps(detail or {}, default=str)),
                                     _esc(policy_version)]) + ")")
    except Exception as e:
        log.warning("outcome record failed: %s", e)


@guarded_connection
def record_price_path(conn, ticker: str, at_ts: float, price: float,
                      source: str = "synthetic",
                      received_at: str | None = None) -> bool:
    """Append one price observation for the outcome worker (R8-05).

    Storage never drops points (no dedupe, no ohlc synthesis): ordering,
    gap detection and available-at rules belong to the labeling layer.
    Non-finite inputs are rejected (False). The production scheduled
    recorder is a commissioning item; this is the tested storage seam.
    """
    try:
        import math as _math
        t, p = float(at_ts), float(price)
        if not (_math.isfinite(t) and _math.isfinite(p)):
            return False
        ensure_tables(conn)
        with _RECORDER_LOCK:
            conn.execute("INSERT INTO price_paths_v1 VALUES ("
                         + ",".join([_esc(t), _esc(str(ticker or "").upper()),
                                     _esc(p), _esc(source),
                                     _esc(received_at or _now_iso())]) + ")")
        return True
    except Exception as e:
        log.debug("price path record failed for %s: %s", ticker, e)
        return False


@guarded_connection
def price_paths_since(conn, ticker: str, since_ts: float = 0.0,
                      limit: int = 100000) -> list[tuple[float, float]]:
    """Ordered finite (t, price) observations for a ticker (R8-05)."""
    import math as _math
    try:
        ensure_tables(conn)
        rows = conn.execute(
            "SELECT at_ts, price FROM price_paths_v1 WHERE ticker = "
            + _esc(str(ticker or "").upper()) + " AND at_ts >= " + str(float(since_ts))
            + " ORDER BY at_ts ASC LIMIT " + str(max(1, int(limit)))).fetchall() or []
        out = []
        for r in rows:
            try:
                t, p = float(r[0]), float(r[1])
            except (TypeError, ValueError):
                continue
            if _math.isfinite(t) and _math.isfinite(p):
                out.append((t, p))
        return out
    except Exception as e:
        log.debug("price paths read failed for %s: %s", ticker, e)
        return []


@guarded_connection
def outcome_close_tick(conn, ticker: str | None = None,
                       default_horizon_s: float = 300) -> dict[str, Any]:
    """One deterministic outcome-worker tick (R8-05).

    Pure function of (conn, stored data): gathers open decisions, pulls
    their stored price paths, runs close_episodes, attaches outcomes.
    Restart catch-up falls out of DB state — no cursors to lose, no
    background loop needed to test it. The scheduler hook is
    default-disabled (SOLSTICE_OUTCOME_WORKER=1 to enable); the recorder
    that feeds price_paths_v1 in production is a commissioning item.
    Returns the close_episodes summary plus decisions_seen.
    """
    from services.solstice_labels import close_episodes
    try:
        ensure_tables(conn)
        if ticker:
            decs = conn.execute(
                "SELECT decision_id, ticker FROM scenario_decisions_v1 WHERE ticker = "
                + _esc(str(ticker).upper())).fetchall() or []
        else:
            decs = conn.execute(
                "SELECT decision_id, ticker FROM scenario_decisions_v1").fetchall() or []
    except Exception as e:
        log.debug("outcome tick decision scan failed: %s", e)
        return {"closed": [], "skipped_idempotent": [], "skipped_pending": [],
                "pending_reasons": {}, "results": {}, "decisions_seen": 0,
                "error": str(e)}
    paths: dict[str, list] = {}
    for did, tick in decs or []:
        pts = price_paths_since(conn, str(tick))
        if pts:
            paths[str(did)] = pts
    out = close_episodes(conn, paths, default_horizon_s=default_horizon_s)
    if out.get("closed"):
        try:
            attach_outcomes_to_decisions(conn, out["results"])
        except Exception as _ae:
            log.debug("worker attach failed: %s", _ae)
    out["decisions_seen"] = len(decs or [])
    return out


@guarded_connection
def replay_snapshot(conn, snapshot_id: str) -> dict[str, Any] | None:
    """Reconstruct exactly what was available at decision time (known-at join).

    Returns snapshot row + strike rows + walls + contract rows as recorded;
    late-arriving revisions are separate rows and never merged into this snapshot.
    """
    try:
        snap = conn.execute(
            "SELECT * FROM heatmap_snapshots_v2 WHERE snapshot_id = "
            + _esc(snapshot_id)).fetchdf()
        if snap is None or len(snap) == 0:
            return None
        row = snap.to_dict("records")[0]
        obs = conn.execute(
            "SELECT * FROM contract_observations_v2 WHERE snapshot_id = "
            + _esc(snapshot_id)).fetchdf()

        def _parse(v: Any) -> Any:
            if v is None:
                return None
            try:
                return json.loads(v)
            except (TypeError, ValueError):
                return None

        return {
            "snapshot": row,
            "strikes": _parse(row.get("strikes_json")) or [],
            "walls": _parse(row.get("walls_json")) or [],
            "contracts": [normalize_stored_contract(r) for r in
                          (obs.to_dict("records") if obs is not None else [])],
            "coverage": _parse(row.get("coverage_json")),
            "quality": _parse(row.get("quality_json")),
            "scenarios": _parse(row.get("scenarios_json")) or [],
            "interactions": _parse(row.get("interactions_json")) or [],
            "grid_meta": _parse(row.get("grid_meta_json")),
            "grids": _parse(row.get("grids_json")) or {},
            # R7-03: None on pre-migration records — the adapter marks those
            # explicitly incomplete instead of reconstructing present-day truth.
            "metrics_full": _parse(row.get("metrics_full_json")),
            "context": _parse(row.get("context_json")),
            "replay_note": "available-at join: only rows with this snapshot_id; "
                           "later revisions excluded",
        }
    except Exception as e:
        log.warning("replay failed for %s: %s", snapshot_id, e)
        return None


@guarded_connection
def compare_snapshots(conn, ticker: str, day: str) -> dict[str, Any]:
    """Coarse wall-level change between the last two snapshots of a ticker/day.

    Per-strike gross deltas + added/removed/retained wall identities. This is a
    descriptive comparison, NOT the full spot/IV/time/OI counterfactual
    (solstice_provenance.attribute_change) — that needs contract-level history.
    Fewer than 2 snapshots → history_unavailable (never a one-point trend).
    """
    try:
        ensure_tables(conn)
        rows = conn.execute(
            "SELECT snapshot_id, asof_ts, spot, strikes_json, walls_json "
            "FROM heatmap_snapshots_v2 WHERE ticker = " + _esc(ticker.upper())
            + " AND asof_ts LIKE " + _esc(day + "%")
            + " ORDER BY asof_ts").fetchall()
        if len(rows or []) < 2:
            return {"ticker": ticker.upper(), "day": day, "status": "history_unavailable",
                    "reason": "need 2+ recorded snapshots for comparison"}

        def _parse(v: Any) -> Any:
            try:
                return json.loads(v) if v else None
            except (TypeError, ValueError):
                return None

        (_id0, _asof0, _spot0, sj0, wj0) = rows[-2]
        (_id1, _asof1, _spot1, sj1, wj1) = rows[-1]
        s0 = {float(s.get("strike")): float(s.get("gex", 0) or 0)
              for s in (_parse(sj0) or []) if isinstance(s, dict) and s.get("strike") is not None}
        s1 = {float(s.get("strike")): float(s.get("gex", 0) or 0)
              for s in (_parse(sj1) or []) if isinstance(s, dict) and s.get("strike") is not None}
        deltas = [{"strike": k, "before": s0.get(k, 0.0), "after": v,
                   "delta": v - s0.get(k, 0.0)}
                  for k, v in sorted(s1.items()) if abs(v - s0.get(k, 0.0)) > 0]
        # Window volume deltas per strike (cumulative-volume differences with
        # rebase quarantine — a negative step invalidates the window, it is
        # never negative flow).
        from services.solstice_provenance import check_volume_window
        v0 = {}
        for s in (_parse(sj0) or []):
            if isinstance(s, dict) and s.get("strike") is not None:
                v0[float(s["strike"])] = s.get("total_volume", s.get("volume"))
        v1 = {}
        for s in (_parse(sj1) or []):
            if isinstance(s, dict) and s.get("strike") is not None:
                v1[float(s["strike"])] = s.get("total_volume", s.get("volume"))
        volume_deltas = []
        volume_rebased = []
        for k in sorted(set(v0) | set(v1)):
            chk = check_volume_window(v0.get(k), v1.get(k))
            if chk["valid"]:
                if chk["delta"] and chk["delta"] > 0:
                    volume_deltas.append({"strike": k, "delta_volume": chk["delta"]})
            elif chk["reason"] == "VOLUME_REBASE":
                volume_rebased.append(k)
        volume_deltas.sort(key=lambda d: d["delta_volume"], reverse=True)
        w0 = {w.get("wall_id") for w in (_parse(wj0) or []) if isinstance(w, dict)}
        w1 = {w.get("wall_id") for w in (_parse(wj1) or []) if isinstance(w, dict)}
        return {"ticker": ticker.upper(), "day": day, "status": "ok",
                "from": {"id": _id0, "asof": _asof0, "spot": _spot0},
                "to": {"id": _id1, "asof": _asof1, "spot": _spot1},
                "strike_deltas": sorted(deltas, key=lambda d: abs(d["delta"]), reverse=True)[:20],
                "volume_deltas": volume_deltas[:20],
                "volume_rebased": volume_rebased,
                "walls_added": sorted(w1 - w0), "walls_removed": sorted(w0 - w1),
                "walls_retained": sorted(w0 & w1),
                "note": "coarse wall-level comparison; use attribute_change for "
                        "spot/IV/time/OI decomposition once contract history exists"}
    except Exception as e:
        log.warning("compare failed: %s", e)
        return {"ticker": ticker.upper(), "day": day, "status": "error", "error": str(e)}


@guarded_connection
def session_manifest(conn, ticker: str, day: str,
                     expected_cadence_s: float | None = None) -> dict[str, Any]:
    """Completeness report for a ticker/day: snapshots, gaps, coverage.

    R4-13/P07: heartbeat (first/last asof) plus gap receipts — any interval
    beyond 1.5x the expected cadence is an explicit gap (never silently
    interpolated). Research readiness cannot be claimed from snapshot counts
    alone without gap accounting.
    """
    try:
        rows = conn.execute(
            "SELECT snapshot_id, asof_ts, n_contracts FROM heatmap_snapshots_v2 "
            "WHERE ticker = " + _esc(ticker.upper())
            + " AND asof_ts LIKE " + _esc(day + "%")
            + " ORDER BY asof_ts").fetchall()
        snaps = [{"id": r[0], "asof": r[1], "n": r[2]} for r in (rows or [])]
        gaps: list[dict[str, Any]] = []
        if expected_cadence_s and len(snaps) >= 2:
            from datetime import UTC as _UTC
            from datetime import datetime as _dt

            def _ts(v: Any) -> float | None:
                try:
                    d = _dt.fromisoformat(str(v).replace("Z", "+00:00"))
                    if d.tzinfo is None:
                        d = d.replace(tzinfo=_UTC)
                    return d.timestamp()
                except (TypeError, ValueError):
                    return None

            for a, b in zip(snaps, snaps[1:], strict=False):
                ta, tb = _ts(a["asof"]), _ts(b["asof"])
                if ta is None or tb is None:
                    continue
                gap_s = tb - ta
                if gap_s > expected_cadence_s * 1.5:
                    gaps.append({"from": a["asof"], "to": b["asof"],
                                 "gap_s": round(gap_s, 1),
                                 "missing_beats": max(0, round(gap_s / expected_cadence_s) - 1)})
        return {"ticker": ticker.upper(), "day": day, "n_snapshots": len(snaps),
                "snapshots": snaps, "gaps": gaps,
                "heartbeat": {"first": snaps[0]["asof"] if snaps else None,
                              "last": snaps[-1]["asof"] if snaps else None,
                              "expected_cadence_s": expected_cadence_s}}
    except Exception as e:
        log.warning("manifest failed: %s", e)
        return {"ticker": ticker.upper(), "day": day, "n_snapshots": 0, "error": str(e)}


# ---------------------------------------------------------------------------
# R8-04: review journal — list and annotate saved scenario decisions.
# ---------------------------------------------------------------------------

@guarded_connection
def list_decisions(conn, ticker: str, limit: int = 50, state_filter: str | None = None) -> list[dict[str, Any]]:
    """List saved scenario decisions for a ticker (R8-04 review journal).

    Returns decision rows with frozen features, candidate quotes summary,
    and any attached outcome labels. Read-only — never mutates storage.
    """
    try:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("limit must be an integer from 1 to 1000")
        ensure_tables(conn)
        q = ("SELECT d.decision_id, d.ticker, d.at_ts, d.snapshot_id, "
             "d.scenario, d.side, d.eligible, d.reason_codes, d.features, "
             "COUNT(DISTINCT c.osi) AS n_quotes, "
             "GROUP_CONCAT(DISTINCT o.label) AS outcome_labels, "
             "MAX(r.state) AS review_state "
             "FROM scenario_decisions_v1 d "
             "LEFT JOIN candidate_quotes_v1 c ON c.decision_id = d.decision_id "
             "LEFT JOIN outcome_labels_v1 o ON o.decision_id = d.decision_id "
             "LEFT JOIN decision_reviews_v1 r ON r.decision_id = d.decision_id "
             "WHERE d.ticker = ? ")
        params = [ticker]
        if state_filter is not None:
            q += "AND r.state = ? "
            params.append(state_filter)
        q += "GROUP BY d.decision_id, d.ticker, d.at_ts, d.snapshot_id, "
        q += "d.scenario, d.side, d.eligible, d.reason_codes, d.features "
        q += "ORDER BY d.at_ts DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(q, params).fetchdf()
        if rows is None or len(rows) == 0:
            return []
        out = []
        for _, r in rows.iterrows():
            feats = r.get("features")
            if isinstance(feats, str):
                try:
                    feats = __import__("json").loads(feats)
                except (TypeError, ValueError):
                    feats = {}
            out.append({
                "decision_id": r.get("decision_id"),
                "ticker": r.get("ticker"),
                "at_ts": r.get("at_ts"),
                "snapshot_id": r.get("snapshot_id"),
                "scenario": r.get("scenario"),
                "side": r.get("side"),
                "eligible": bool(r.get("eligible", False)),
                "reason_codes": feats.get("reason_codes", []) if isinstance(feats, dict) else [],
                "features": feats if isinstance(feats, dict) else {},
                "n_quotes": int(r.get("n_quotes", 0) or 0),
                "outcome_labels": (feats.get("outcome_labels") if isinstance(feats, dict) and isinstance(feats.get("outcome_labels"), str)
                                    else (r.get("outcome_labels") or "")),
                # R8-04: include the review state from decision_reviews_v1 so
                # consumers (incl. the frontend) can display it without a second fetch.
                "review_state": r.get("review_state") if r.get("review_state") is not None else None,
            })
        return out
    except Exception as e:
        log.warning("list_decisions failed for %s: %s", ticker, e)
        return []


@guarded_connection
def save_decision_review(conn, decision_id: str, state: str,
                         reason: str | None = None,
                         note: str | None = None, *, ticker: str | None = None) -> str | None:
    """Save a review state on a decision (R8-04).

    States: pending | reviewed | waiting | skipped.
    Persists through the real route/store.
    """
    try:
        ensure_tables(conn)
        with _RECORDER_LOCK:
            if ticker is not None:
                matches = conn.execute(
                    "SELECT ticker FROM scenario_decisions_v1 WHERE decision_id = ?", [decision_id]
                ).fetchall()
                if len(matches) != 1 or str(matches[0][0]).upper() != ticker.upper():
                    return None
            saved_at = _now_iso()
            conn.execute(
                "INSERT OR REPLACE INTO decision_reviews_v1 VALUES ("
                + _esc(decision_id) + ", "
                + _esc(state) + ", "
                + _esc(reason) + ", "
                + _esc(note) + ", "
                + _esc(saved_at) + ")")
        return saved_at
    except Exception as e:
        log.warning("save_decision_review failed for %s: %s", decision_id, e)
        return None
