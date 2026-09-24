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
from datetime import UTC, datetime
from typing import Any

log = logging.getLogger(__name__)

SCHEMA_VERSION = "2"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def snapshot_digest(payload: dict[str, Any]) -> str:
    """Recorder identity = canonical content digest (P02/R4-01, R4-13).

    Same content re-recorded is the same snapshot (idempotent); changed
    exposure always digests differently. Observation time lives in the row,
    not the digest.
    """
    from services.heatmap_snapshot import content_digest
    return content_digest(payload)


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
    "outcome_labels_v1": """
        CREATE TABLE IF NOT EXISTS outcome_labels_v1 (
            decision_id VARCHAR, ticker VARCHAR, horizon_s INTEGER, label VARCHAR,
            label_version VARCHAR, at_ts VARCHAR, censored BOOLEAN, detail VARCHAR
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
    try:
        conn.execute("ALTER TABLE heatmap_snapshots_v2 ADD COLUMN IF NOT EXISTS coverage_json VARCHAR")
    except Exception as e:
        log.warning("heatmap_history migrate coverage_json failed: %s", e)


def recorder_status(conn, path: str | None = None) -> dict[str, Any]:
    """Honest durability status (R4-13/P07): :memory: is never durable.

    Disk failure / unusable path must never claim durable recording.
    """
    try:
        import os as _os
        p = path if path is not None else _os.environ.get("DUCKDB_PATH", ":memory:")
        durable = bool(p) and p != ":memory:"
        tables: list[str] = []
        if conn is not None:
            try:
                rows = conn.execute("SHOW TABLES").fetchall()
                tables = [str(r[0]) for r in (rows or [])]
            except Exception:
                tables = []
        else:
            durable = False
        return {"durable": durable and len(tables) > 0,
                "mode": "file" if durable else "memory",
                "path": p, "tables": tables,
                "note": "memory mode is not crash-safe durable storage"}
    except Exception as e:
        return {"durable": False, "mode": "unknown", "error": str(e)}


def record_capability(conn, ticker: str, operation: str,
                      requested: int | None = None, returned: int | None = None,
                      usable: int | None = None, truncated: bool = False,
                      detail: dict | None = None) -> None:
    """Production capability/coverage writer (R4-18/P07): nonzero linked records."""
    try:
        ensure_tables(conn)
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


def record_snapshot(conn, payload: dict[str, Any], query_key: str = "",
                    snapshot_id: str | None = None) -> str | None:
    """Record one heatmap payload + its contracts. Returns snapshot_id or None.

    R4-13/P07 atomicity: header + contracts commit in one transaction; a
    crash between them leaves no half-record. Retry of the same snapshot_id
    completes missing contracts instead of skipping via dedup. Coverage
    (requested/returned/usable/truncated) is explicit — no silent 2,000-row
    truncation. Never stores repeated cache hits as new events: caller must
    only invoke on fresh builds, not stale-serve paths.
    """
    try:
        ensure_tables(conn)
        sid = snapshot_id or f"snap_{snapshot_digest(payload)}"
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
        # Idempotent but verifying: header exists AND contracts complete →
        # skip; header exists with missing contracts (crash) → rewrite.
        try:
            n = conn.execute(
                "SELECT COUNT(*) FROM heatmap_snapshots_v2 WHERE snapshot_id = "
                + _esc(sid)).fetchone()
            if n and n[0] > 0:
                try:
                    m = conn.execute(
                        "SELECT COUNT(*) FROM contract_observations_v2 WHERE snapshot_id = "
                        + _esc(sid)).fetchone()
                    if m and m[0] >= len(contracts):
                        return sid
                except Exception:
                    pass
                # Partial record: remove header + partial contracts, re-insert below.
                try:
                    conn.execute("DELETE FROM contract_observations_v2 WHERE snapshot_id = "
                                 + _esc(sid))
                    conn.execute("DELETE FROM heatmap_snapshots_v2 WHERE snapshot_id = "
                                 + _esc(sid))
                except Exception as del_e:
                    log.debug("partial cleanup failed: %s", del_e)
        except Exception as dedup_e:
            log.debug("dedup check failed, proceeding to insert (idempotent PK): %s", dedup_e)
        import contextlib as _ctxlib
        with _ctxlib.suppress(Exception):
            conn.execute("BEGIN")
        try:
            try:
                cols = [d[1] for d in
                        conn.execute("PRAGMA table_info(heatmap_snapshots_v2)").fetchall()]
            except Exception:
                cols = []
            if "coverage_json" in cols:
                conn.execute(
                    "INSERT INTO heatmap_snapshots_v2 VALUES ("
                    + ",".join([_esc(sid), _esc(payload.get("ticker")), _esc(query_key),
                                _esc(json.dumps(payload.get("expiries_used", []))),
                                _esc(payload.get("spot")), _esc(payload.get("data_source")),
                                _esc(payload.get("exposure_basis")), _esc(payload.get("formula_version")),
                                _esc(payload.get("asof")), _esc(payload.get("source_received_at")),
                                _esc(len(contracts)), _esc(usable),
                                _esc(snapshot_digest(payload)),
                                _esc(json.dumps(strikes[:500], default=str)),
                                _esc(json.dumps(walls, default=str)),
                                _esc(json.dumps(coverage, default=str))]) + ")")
            else:
                conn.execute(
                    "INSERT INTO heatmap_snapshots_v2 VALUES ("
                    + ",".join([_esc(sid), _esc(payload.get("ticker")), _esc(query_key),
                                _esc(json.dumps(payload.get("expiries_used", []))),
                                _esc(payload.get("spot")), _esc(payload.get("data_source")),
                                _esc(payload.get("exposure_basis")), _esc(payload.get("formula_version")),
                                _esc(payload.get("asof")), _esc(payload.get("source_received_at")),
                                _esc(len(contracts)), _esc(usable),
                                _esc(snapshot_digest(payload)),
                                _esc(json.dumps(strikes[:500], default=str)),
                                _esc(json.dumps(walls, default=str))]) + ")")
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
            import contextlib as _ctxlib2
            with _ctxlib2.suppress(Exception):
                conn.execute("COMMIT")
        except Exception:
            import contextlib as _ctxlib3
            with _ctxlib3.suppress(Exception):
                conn.execute("ROLLBACK")
            raise
        return sid
    except Exception as e:
        log.warning("heatmap_history record failed (non-fatal): %s", e)
        return None


def record_wall_event(conn, wall_id: str, ticker: str, event: str,
                      snapshot_id: str, evidence: dict | None = None,
                      scope: str = "") -> None:
    try:
        ensure_tables(conn)
        conn.execute("INSERT INTO wall_events_v1 VALUES ("
                     + ",".join([_esc(wall_id), _esc(ticker), _esc(event), _esc(_now_iso()),
                                 _esc(snapshot_id), _esc(json.dumps(evidence or {}, default=str)),
                                 _esc(scope)]) + ")")
    except Exception as e:
        log.warning("wall event record failed: %s", e)


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
                 "beyond_side": ev.get("beyond_side")}
        return state
    except Exception as e:
        log.debug("latest_wall_state failed: %s", e)
        return None


def record_decision(conn, decision: dict[str, Any]) -> str:
    """Record scenario decision incl. no-trade with all features known then."""
    import uuid
    did = decision.get("decision_id") or f"dec_{uuid.uuid4().hex[:12]}"
    try:
        ensure_tables(conn)
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


def record_outcome(conn, decision_id: str, ticker: str, horizon_s: int,
                   label: str, label_version: str = "outcome.v1",
                   censored: bool = False, detail: dict | None = None) -> None:
    try:
        ensure_tables(conn)
        conn.execute("INSERT INTO outcome_labels_v1 VALUES ("
                     + ",".join([_esc(decision_id), _esc(ticker), _esc(horizon_s),
                                 _esc(label), _esc(label_version), _esc(_now_iso()),
                                 _esc(1 if censored else 0),
                                 _esc(json.dumps(detail or {}, default=str))]) + ")")
    except Exception as e:
        log.warning("outcome record failed: %s", e)


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
            "contracts": obs.to_dict("records") if obs is not None else [],
            "replay_note": "available-at join: only rows with this snapshot_id; "
                           "later revisions excluded",
        }
    except Exception as e:
        log.warning("replay failed for %s: %s", snapshot_id, e)
        return None


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
