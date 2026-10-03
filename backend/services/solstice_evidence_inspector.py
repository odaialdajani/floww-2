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
import logging
import os
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
        return report
    finally:
        with contextlib.suppress(Exception):
            conn.close()


def _snapshots_census(conn, report: dict[str, Any]) -> None:
    if report["tables"].get("heatmap_snapshots_v2", {}).get("rows") is None:
        report["snapshots"] = {"status": "ABSENT_OR_UNREADABLE"}
        return
    try:
        rows = conn.execute(
            "SELECT ticker, count(*), min(asof_ts), max(asof_ts) "
            "FROM heatmap_snapshots_v2 GROUP BY ticker ORDER BY ticker").fetchall()
        report["snapshots"] = {
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
    try:
        rows = conn.execute(
            "SELECT ticker, at_ts FROM price_paths_v1 ORDER BY ticker, at_ts"
        ).fetchall()
        per: dict[str, list[float]] = {}
        for tk, ts in rows:
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
            "per_ticker": cadence,
            "cadence_note": "scheduled producer is a 5-minute swing-oriented "
                            "source (price-path-producer.v1); it is NOT an "
                            "intraminute 0DTE confirmation/stop tape",
        }
    except Exception as e:
        report["price_paths"] = {"status": "QUERY_FAILED", "error": str(e)}


def _lineage_census(conn, report: dict[str, Any]) -> None:
    """decision → outcome lineage; missing links stay UNKNOWN, never zero."""
    if report["tables"].get("scenario_decisions_v1", {}).get("rows") is None:
        report["lineage"] = {"status": "ABSENT_OR_UNREADABLE"}
        return
    try:
        n_dec = conn.execute("SELECT count(*) FROM scenario_decisions_v1").fetchall()[0][0]
    except Exception as e:
        report["lineage"] = {"status": "QUERY_FAILED", "error": str(e)}
        return
    try:
        n_labels = conn.execute("SELECT count(*) FROM outcome_labels_v1").fetchall()[0][0]
        n_unlabelled = conn.execute(
            "SELECT count(*) FROM scenario_decisions_v1 d WHERE NOT EXISTS ("
            "SELECT 1 FROM outcome_labels_v1 o WHERE o.decision_id = d.decision_id)"
        ).fetchall()[0][0]
    except Exception:
        n_labels, n_unlabelled = None, None
    report["lineage"] = {
        "n_decisions": int(n_dec),
        "n_outcome_labels": (int(n_labels) if n_labels is not None else None),
        "n_decisions_without_outcome": (int(n_unlabelled)
                                        if n_unlabelled is not None else None),
        "note": "decisions without outcome labels are CENSORED/UNKNOWN — "
                "never zero losses and never invented wins",
    }



def _outcome_sufficiency(conn, report: dict[str, Any]) -> None:
    """Data-sufficiency verdict: counts vs the 30–60 session target."""
    try:
        n_labels = conn.execute("SELECT count(*) FROM outcome_labels_v1").fetchall()[0][0]
        n_censored = conn.execute(
            "SELECT count(*) FROM outcome_labels_v1 WHERE censored").fetchall()[0][0]
        classes = [str(r[0]) for r in conn.execute(
            "SELECT DISTINCT label FROM outcome_labels_v1").fetchall() or []]
        n_sessions = conn.execute(
            "SELECT count(DISTINCT substr(at_ts, 1, 10)) FROM outcome_labels_v1"
        ).fetchall()[0][0]
    except Exception as e:
        report["outcome_sufficiency"] = {"status": "ABSENT_OR_UNREADABLE",
                                         "error": str(e)}
        return
    report["outcome_sufficiency"] = {
        "n_outcome_labels": int(n_labels),
        "n_censored": int(n_censored),
        "n_terminal": int(n_labels) - int(n_censored),
        "label_classes": sorted(classes),
        "n_sessions": int(n_sessions),
        "collection_target_sessions": "30-60",
        "verdict": ("INSUFFICIENT EVIDENCE"
                    if int(n_sessions) < 30 else "SAMPLE_TARGET_MET"),
        "note": "underlying labels are not option P&L; terminal labels measure "
                "underlying movement vs the frozen protocol, not profitability",
    }


def _range_envelope_census(conn, report: dict[str, Any]) -> None:
    if report["tables"].get("range_analytics_envelopes_v1", {}).get("rows") is None:
        report["range_analytics"] = {"status": "ABSENT"}
        return
    try:
        rows = conn.execute(
            "SELECT ticker, window_min, window_max, asof_date, status, count(*) "
            "FROM range_analytics_envelopes_v1 "
            "GROUP BY ticker, window_min, window_max, asof_date, status").fetchall()
        report["range_analytics"] = {
            "envelopes": [{"ticker": r[0], "window": [r[1], r[2]],
                           "asof_date": r[3], "status": r[4], "n": int(r[5])}
                          for r in rows],
        }
    except Exception as e:
        report["range_analytics"] = {"status": "QUERY_FAILED", "error": str(e)}

