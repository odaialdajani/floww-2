"""backend/services/solstice_evidence_inspector.py — C3 read-only evidence/data-sufficiency inspector.

Finite, read-only inspection of an EXPLICIT recorder store. Never imports
server startup, never opens a guessed path, and opens existing files with
``read_only=True`` only — it can never mutate a production DB.

A missing/unreadable/empty store is a useful refusal (named reason), never a
fabricated healthy census. Underlying outcome labels are NOT option P&L:
option fill/fee economics come only from Spark's actual ledger; absent that,
option economics stay UNKNOWN. The five-minute swing price path cannot prove
intraminute 0DTE confirmation, barrier ordering or stops; prospectively fixed
sampling (30–60 sessions) is a collection target, not automatic edge proof.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
from datetime import datetime
from typing import Any

log = logging.getLogger(__name__)

INSPECTOR_VERSION = "recorder-inspector.v1"

_KNOWN_TABLES = (
    "heatmap_snapshots_v2", "contract_observations_v2", "wall_events_v1",
    "scenario_decisions_v1", "candidate_quotes_v1", "execution_events_v1",
    "decision_reviews_v1", "outcome_labels_v1", "price_paths_v1",
    "capability_observations_v1", "range_analytics_envelopes_v1",
)

# Persistent truth — report-only, never a permission or an edge claim.
_LIMITS = [
    "underlying bounce/reject/squeeze/flush labels are not option P&L",
    "option economics require Spark's actual fill/fee account ledger; absent "
    "it they remain UNKNOWN, censored, never zero losses or invented wins",
    "the five-minute swing producer cannot establish intraminute 0DTE "
    "confirmation, barrier ordering or stops",
    "a 30–60-session collection target is a sampling requirement, not "
    "automatic edge proof; synthetic/paper evidence stays separate from real",
]

__all__ = ["INSPECTOR_VERSION", "inspect_recorder_store"]


def _refusal(reason: str, **extra: Any) -> dict[str, Any]:
    return {"version": INSPECTOR_VERSION, "status": "refused",
            "reason": reason, **extra}


def _safe_count(conn, table: str) -> dict[str, Any]:
    try:
        rows = conn.execute(f"SELECT count(*) FROM {table}").fetchall()
        return {"rows": int(rows[0][0])}
    except Exception as e:
        return {"rows": None, "error": str(e)}


def inspect_recorder_store(path: str | None, *, ticker: str | None = None) -> dict[str, Any]:
    """Report backing/durability, schema, populations, clocks, gaps, lineage.

    Requires an explicit store path. Read-only; a DuckDB file is opened with
    read_only=True and closed before returning.
    """
    if not path or not isinstance(path, str) or not path.strip():
        return _refusal("STORE_PATH_REQUIRED")
    p = path.strip()
    if not os.path.exists(p):
        return _refusal("STORE_MISSING", path=p)
    try:
        import duckdb
        conn = duckdb.connect(p, read_only=True)
    except Exception as e:
        return _refusal("STORE_UNREADABLE", path=p, detail=str(e))

    try:
        try:
            dblist = conn.execute("PRAGMA database_list").fetchall()
            files = [str(r[2]) for r in (dblist or []) if len(r) > 2 and r[2]]
            backing = "file" if files else "memory"
        except Exception as e:
            backing = "unknown"
            files = []
            log.warning("inspector database_list failed: %s", e)
        try:
            tables = sorted(str(r[0]) for r in
                            (conn.execute("SHOW TABLES").fetchall() or []))
        except Exception as e:
            tables = []
            return _refusal("SCHEMA_UNREADABLE", path=p, backing=backing,
                            detail=str(e))
        report: dict[str, Any] = {
            "version": INSPECTOR_VERSION,
            "status": "ok",
            "store": {"path": p, "backing": backing,
                      "durable": backing == "file" and len(tables) > 0,
                      "files": files},
            "ticker": ticker.upper() if ticker else None,
            "tables": {name: (_safe_count(conn, name) if name in tables
                              else {"rows": None, "status": "ABSENT"})
                       for name in _KNOWN_TABLES},
            "unknown_tables": [t for t in tables if t not in _KNOWN_TABLES],
            "limits": list(_LIMITS),
        }
        _snapshots_census(conn, report)
        _price_path_cadence(conn, report)
        _lineage_census(conn, report)
        _outcome_sufficiency(conn, report)
        _range_envelope_census(conn, report)
        report.pop("_decision_class", None)  # internal qualification scratch
        return report
    finally:
        with contextlib.suppress(Exception):
            conn.close()


def _is_synthetic_source(value: Any) -> bool | None:
    """Classification rule (honest): known-synthetic markers → True; known
    live capture sources → False; anything else → None (UNKNOWN, not real)."""
    if not isinstance(value, str) or not value:
        return None
    v = value.lower()
    if "synthetic" in v or "fixture" in v or v.startswith(("test", "fake")):
        return True
    if v.startswith(("public", "vendor", "databento")):
        return False
    return None


def _snapshots_census(conn, report: dict[str, Any]) -> None:
    if report["tables"].get("heatmap_snapshots_v2", {}).get("rows") is None:
        report["snapshots"] = {"status": "ABSENT_OR_UNREADABLE"}
        return
    ticker = report.get("ticker")
    sql = ("SELECT ticker, count(*), min(asof_ts), max(asof_ts) "
           "FROM heatmap_snapshots_v2")
    params: list[Any] = []
    if ticker:
        sql += " WHERE ticker = ?"
        params.append(ticker)
    sql += " GROUP BY ticker ORDER BY ticker"
    try:
        rows = conn.execute(sql, params).fetchall()
        report["snapshots"] = {
            "scope": ticker or "ALL",
            "per_ticker": [{"ticker": r[0], "n": int(r[1]),
                            "first_asof": r[2], "last_asof": r[3]} for r in rows],
            "clock_note": "asof_ts is the stored observation clock; the owning "
                          "day key is its timestamp prefix (sessions route)",
        }
    except Exception as e:
        report["snapshots"] = {"status": "QUERY_FAILED", "error": str(e)}


def _price_path_cadence(conn, report: dict[str, Any]) -> None:
    if report["tables"].get("price_paths_v1", {}).get("rows") is None:
        report["price_paths"] = {"status": "ABSENT_OR_UNREADABLE"}
        return
    ticker = report.get("ticker")
    sql = "SELECT ticker, at_ts, source FROM price_paths_v1"
    params: list[Any] = []
    if ticker:
        sql += " WHERE ticker = ?"
        params.append(ticker)
    sql += " ORDER BY ticker, at_ts"
    try:
        rows = conn.execute(sql, params).fetchall()
        per: dict[str, list[float]] = {}
        synth = {"synthetic": 0, "production": 0, "unknown": 0}
        for tk, ts, source in rows:
            cls = _is_synthetic_source(source)
            synth["synthetic" if cls is True else
                  "production" if cls is False else "unknown"] += 1
            try:
                per.setdefault(str(tk), []).append(float(ts))
            except (TypeError, ValueError):
                continue
        cadence: dict[str, Any] = {}
        for tk, stamps in per.items():
            deltas = [b - a for a, b in zip(stamps, stamps[1:], strict=False)]
            deltas = [d for d in deltas if d > 0]
            if deltas:
                deltas.sort()
                median = deltas[len(deltas) // 2]
                gaps = [d for d in deltas if d > 2 * median]
                cadence[tk] = {"n_points": len(stamps), "median_gap_s": median,
                               "n_gaps_gt_2x_median": len(gaps),
                               "max_gap_s": max(deltas)}
            else:
                cadence[tk] = {"n_points": len(stamps), "median_gap_s": None,
                               "n_gaps_gt_2x_median": None, "max_gap_s": None}
        report["price_paths"] = {
            "scope": ticker or "ALL",
            "per_ticker": cadence,
            "classification": synth,
            "classification_note": "synthetic/fixture/test sources are NEVER "
                                   "production; unrecognized sources are UNKNOWN",
            "cadence_note": "scheduled producer is a 5-minute swing-oriented "
                            "source (price-path-producer.v1); it is NOT an "
                            "intraminute 0DTE confirmation/stop tape",
        }
    except Exception as e:
        report["price_paths"] = {"status": "QUERY_FAILED", "error": str(e)}


def _lineage_census(conn, report: dict[str, Any]) -> None:
    """decision → outcome lineage; missing links stay UNKNOWN, never zero.

    C8: ticker-scoped; decisions are classified synthetic/production/unknown
    from their recorded features (never inferred from counts).
    """
    if report["tables"].get("scenario_decisions_v1", {}).get("rows") is None:
        report["lineage"] = {"status": "ABSENT_OR_UNREADABLE"}
        return
    ticker = report.get("ticker")
    t_where = " WHERE ticker = ?" if ticker else ""
    t_params: list[Any] = [ticker] if ticker else []
    try:
        n_dec = conn.execute(
            "SELECT count(*) FROM scenario_decisions_v1" + t_where, t_params
        ).fetchall()[0][0]
        dec_rows = conn.execute(
            "SELECT decision_id, features FROM scenario_decisions_v1" + t_where,
            t_params).fetchall()
    except Exception as e:
        report["lineage"] = {"status": "QUERY_FAILED", "error": str(e)}
        return
    dec_class = {"synthetic": 0, "production": 0, "unknown": 0}
    dec_ids: dict[str, bool | None] = {}
    for did, features in dec_rows:
        cls = None
        try:
            feat = json.loads(features) if features else None
        except (TypeError, ValueError):
            feat = None
        if isinstance(feat, dict):
            if feat.get("synthetic") is True:
                cls = True
            else:
                src = feat.get("source") or feat.get("data_source")
                cls = _is_synthetic_source(src)
        dec_ids[str(did)] = cls
        dec_class["synthetic" if cls is True else
                  "production" if cls is False else "unknown"] += 1
    report["_decision_class"] = dec_ids  # internal: sufficiency qualification
    try:
        o_where = " WHERE ticker = ?" if ticker else ""
        n_labels = conn.execute(
            "SELECT count(*) FROM outcome_labels_v1" + o_where, t_params
        ).fetchall()[0][0]
        unlabelled_sql = (
            "SELECT count(*) FROM scenario_decisions_v1 d WHERE NOT EXISTS ("
            "SELECT 1 FROM outcome_labels_v1 o WHERE o.decision_id = d.decision_id)")
        if ticker:
            unlabelled_sql += " AND d.ticker = ?"
        n_unlabelled = conn.execute(unlabelled_sql, t_params).fetchall()[0][0]
    except Exception:
        n_labels, n_unlabelled = None, None
    report["lineage"] = {
        "scope": ticker or "ALL",
        "n_decisions": int(n_dec),
        "decision_classification": dec_class,
        "n_outcome_labels": (int(n_labels) if n_labels is not None else None),
        "n_decisions_without_outcome": (int(n_unlabelled)
                                        if n_unlabelled is not None else None),
        "note": "decisions without outcome labels are CENSORED/UNKNOWN — "
                "never zero losses and never invented wins; synthetic and "
                "unclassified decisions never qualify as production evidence",
    }



def _outcome_sufficiency(conn, report: dict[str, Any]) -> None:
    """Data-sufficiency verdict: counts vs the 30–60 session target.

    C8: ticker-scoped; only QUALIFIED session days count — an actual NY date,
    non-censored label, lineage-linked to a production-classified decision.
    Synthetic/unknown/unlinked evidence never advances the verdict.
    """
    ticker = report.get("ticker")
    t_params: list[Any] = [ticker] if ticker else []
    try:
        n_labels = conn.execute(
            "SELECT count(*) FROM outcome_labels_v1"
            + (" WHERE ticker = ?" if ticker else ""), t_params).fetchall()[0][0]
        n_censored = conn.execute(
            "SELECT count(*) FROM outcome_labels_v1 WHERE censored"
            + (" AND ticker = ?" if ticker else ""), t_params).fetchall()[0][0]
        classes = [str(r[0]) for r in conn.execute(
            "SELECT DISTINCT label FROM outcome_labels_v1"
            + (" WHERE ticker = ?" if ticker else ""), t_params).fetchall() or []]
        label_rows = conn.execute(
            "SELECT decision_id, at_ts, censored FROM outcome_labels_v1"
            + (" WHERE ticker = ?" if ticker else ""), t_params).fetchall()
    except Exception as e:
        report["outcome_sufficiency"] = {"status": "ABSENT_OR_UNREADABLE",
                                         "error": str(e)}
        return
    # C8 qualification: a session day counts only when at least one label on
    # that ACTUAL NY day is non-censored AND lineage-linked to a decision
    # classified production (synthetic/unknown/unlinked never qualify).
    from zoneinfo import ZoneInfo

    _et = ZoneInfo("America/New_York")
    dec_class = report.get("_decision_class") or {}
    qualified_days: set[str] = set()
    unqualified_days: set[str] = set()
    n_refused_link = 0
    for did, at_ts, censored in label_rows:
        ny_day = None
        try:
            s = str(at_ts).replace("Z", "+00:00")
            ny_day = datetime.fromisoformat(s).astimezone(_et).strftime("%Y-%m-%d")
        except (TypeError, ValueError):
            pass
        if ny_day is None:
            continue
        qualified = (not censored) and dec_class.get(str(did)) is False
        (qualified_days if qualified else unqualified_days).add(ny_day)
        if str(did) not in dec_class:
            n_refused_link += 1
    unqualified_days -= qualified_days
    report["outcome_sufficiency"] = {
        "scope": ticker or "ALL",
        "n_outcome_labels": int(n_labels),
        "n_censored": int(n_censored),
        "n_terminal": int(n_labels) - int(n_censored),
        "label_classes": sorted(classes),
        "n_sessions_observed_ny": len(qualified_days | unqualified_days),
        "n_qualified_sessions": len(qualified_days),
        "n_unqualified_sessions": len(unqualified_days),
        "n_labels_without_decision_link": n_refused_link,
        "collection_target_sessions": "30-60",
        # 30 UNQUALIFIED days never yield sufficiency; only qualified
        # production-linked days count, and even ≥30 is a SAMPLE COUNT — not
        # profitability or option P&L.
        "verdict": ("SAMPLE_TARGET_MET" if len(qualified_days) >= 30
                    else "INSUFFICIENT EVIDENCE"),
        "note": "underlying labels are not option P&L; terminal labels measure "
                "underlying movement vs the frozen protocol, not profitability",
    }


def _range_envelope_census(conn, report: dict[str, Any]) -> None:
    if report["tables"].get("range_analytics_envelopes_v1", {}).get("rows") is None:
        report["range_analytics"] = {"status": "ABSENT"}
        return
    ticker = report.get("ticker")
    sql = ("SELECT ticker, window_min, window_max, asof_date, status, "
           "envelope_json, count(*) FROM range_analytics_envelopes_v1")
    params: list[Any] = []
    if ticker:
        sql += " WHERE ticker = ?"
        params.append(ticker)
    sql += (" GROUP BY ticker, window_min, window_max, asof_date, status, "
            "envelope_json LIMIT 500")
    try:
        rows = conn.execute(sql, params).fetchall()
        envs = []
        classification = {"synthetic": 0, "production": 0, "unknown": 0,
                          "refused_or_corrupt": 0}
        for r in rows:
            try:
                payload = json.loads(r[5]) if r[5] else None
            except (TypeError, ValueError):
                payload = None
            if isinstance(payload, dict):
                syn = payload.get("synthetic")
                key = ("synthetic" if syn is True else
                       "production" if syn is False else "unknown")
            else:
                key = "refused_or_corrupt"
            classification[key] += int(r[6])
            envs.append({"ticker": r[0], "window": [r[1], r[2]],
                         "asof_date": r[3], "status": r[4],
                         "synthetic": payload.get("synthetic")
                         if isinstance(payload, dict) else None,
                         "n": int(r[6])})
        report["range_analytics"] = {
            "scope": ticker or "ALL",
            "envelopes": envs,
            "classification": classification,
            "classification_note": "envelope.synthetic flag; missing/unreadable "
                                   "payload is never counted as production",
        }
    except Exception as e:
        report["range_analytics"] = {"status": "QUERY_FAILED", "error": str(e)}

