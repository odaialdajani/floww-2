"""Read-only, bounded pages of original saved scenario decisions."""
from __future__ import annotations

import base64
import contextlib
import hmac
import json
import re
import secrets
import threading
from datetime import UTC, datetime

from services.connection_guard import connection_lock

MAX_PAGE = 100
MAX_CURSOR = 1024
MAX_FIELD_CHARS = 65536
LOCK_WAIT_SECONDS = 1.0
QUERY_SECONDS = 3.0
STATES = {"pending", "reviewed", "waiting", "skipped"}
_CURSOR_KEY = secrets.token_bytes(32)
_CLOCK_PATTERN = (r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}"
                  r"(\.[0-9]{1,9})?(Z|[+-](0[0-9]|1[0-9]|2[0-3]):[0-5][0-9])")
_ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}"


class DecisionHistoryUnavailable(RuntimeError):
    """Saved storage could not answer; absence has not been established."""


def _ticker(value):
    if not isinstance(value, str):
        raise ValueError("Choose a valid stock")
    value = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,31}", value):
        raise ValueError("Choose a valid stock")
    return value


def _cursor(time, identity, ticker, state, order):
    body = json.dumps({"v": 2, "ticker": ticker, "state": state, "order": order,
                       "time": time.astimezone(UTC).isoformat(timespec="microseconds"),
                       "id": identity}, sort_keys=True, separators=(",", ":")).encode()
    signature = hmac.digest(_CURSOR_KEY, body, "sha256")
    return base64.urlsafe_b64encode(body + signature).decode().rstrip("=")


def _read_cursor(cursor, ticker, state, order):
    if (not isinstance(cursor, str) or not 1 <= len(cursor) <= MAX_CURSOR
            or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor)):
        raise ValueError("Saved-page position is invalid; reload history")
    try:
        encoded = base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
        body, signature = encoded[:-32], encoded[-32:]
        if (not body or len(signature) != 32
                or not hmac.compare_digest(signature, hmac.digest(_CURSOR_KEY, body, "sha256"))):
            raise ValueError()
        saved = json.loads(body)
        if (not isinstance(saved, dict) or set(saved) != {"v", "ticker", "state", "order", "time", "id"}
                or type(saved["v"]) is not int or saved["v"] != 2
                or saved["ticker"] != ticker or saved["state"] != state or saved["order"] != order
                or not isinstance(saved["id"], str) or not re.fullmatch(_ID_PATTERN, saved["id"])
                or not isinstance(saved["time"], str) or len(saved["time"]) > 40):
            raise ValueError()
        at = datetime.fromisoformat(saved["time"])
        if (at.tzinfo is None or at.utcoffset().total_seconds() != 0
                or at.isoformat(timespec="microseconds") != saved["time"]):
            raise ValueError()
        return at, saved["id"]
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError):
        raise ValueError("Saved-page position is invalid; reload history") from None


def _json_field(value, expected, max_chars=MAX_FIELD_CHARS):
    if not isinstance(value, str) or len(value) > max_chars:
        return None
    try:
        parsed = json.loads(value, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        return parsed if isinstance(parsed, expected) else None
    except (TypeError, ValueError, RecursionError):
        return None



def _decision_sources(read):
    """Optional archival summaries never replace a full stored decision."""
    native = (
        "SELECT decision_id, ticker, at_ts, snapshot_id, scenario, side, eligible, reason_codes, features, "
        "NULL::VARCHAR AS recovered_json, NULL::VARCHAR AS source_sha256, "
        "NULL::VARCHAR AS source_file, NULL::VARCHAR AS imported_at FROM scenario_decisions_v1"
    )
    present = read.execute(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'main' AND table_name = ?",
        ["legacy_decision_summaries_v1"],
    ).fetchone()[0]
    if not present:
        return "WITH decisions AS (" + native + "), "
    return (
        "WITH legacy_safe AS (SELECT *, CASE WHEN length(summary_json) <= 131072 AND json_valid(summary_json) "
        "THEN summary_json ELSE 'null' END AS safe_summary FROM legacy_decision_summaries_v1), "
        "decisions AS (" + native + " UNION ALL "
        "SELECT l.decision_id, l.ticker, l.at_ts, l.snapshot_id, "
        "json_extract_string(l.safe_summary, '$.scenario'), "
        "json_extract_string(l.safe_summary, '$.side'), "
        "TRY_CAST(json_extract(l.safe_summary, '$.eligible') AS BOOLEAN), "
        "json_extract_string(l.safe_summary, '$.reason_codes'), "
        "json_extract_string(l.safe_summary, '$.features'), "
        "l.safe_summary, l.source_sha256, l.source_file, l.imported_at "
        "FROM legacy_safe l WHERE NOT EXISTS (SELECT 1 FROM scenario_decisions_v1 original "
        "WHERE original.decision_id = l.decision_id)), "
    )

def decision_page(conn, ticker: str, *, limit: int = 50, state: str | None = None,
                  cursor: str | None = None, order: str = "newest") -> dict:
    """Keyset pages use actual UTC time + identity, with unknown clocks explicit.

    The connection is never initialized or mutated here. A private read cursor
    owns the timeout, so its interrupt cannot cancel another shared operation.
    Newer inserts do not shift the next older page. Review changes between
    pages remain live changes; this is not a frozen export transaction.
    """
    ticker = _ticker(ticker)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_PAGE:
        raise ValueError("Use a page size from 1 to 100")
    if state is not None and (not isinstance(state, str) or state not in STATES):
        raise ValueError("Choose a known review state")
    if not isinstance(order, str) or order not in {"newest", "oldest"}:
        raise ValueError("Choose latest or first saved readings")
    before = _read_cursor(cursor, ticker, state, order) if cursor is not None else None
    comparison, direction = ("<", "DESC") if order == "newest" else (">", "ASC")
    if conn is None:
        raise DecisionHistoryUnavailable("Saved decisions are unavailable")
    lock = connection_lock(conn)
    if not lock.acquire(timeout=LOCK_WAIT_SECONDS):
        raise DecisionHistoryUnavailable("Saved decisions are busy; try again")
    read = None
    timeout = None
    expired = threading.Event()
    try:
        read = conn.cursor()

        def interrupt():
            expired.set()
            with contextlib.suppress(Exception):
                read.interrupt()

        timeout = threading.Timer(QUERY_SECONDS, interrupt)
        timeout.daemon = True
        timeout.start()
        review = "COALESCE(r.state, json_extract_string(d.recovered_json, '$.review_state'))"
        state_where = "AND " + review + " = ? " if state is not None else ""
        timed = _decision_sources(read) + (
            "timed AS (SELECT d.decision_id, d.ticker, d.at_ts, d.snapshot_id, "
            "d.scenario, d.side, d.eligible, "
            "CASE WHEN length(d.reason_codes) <= ? THEN d.reason_codes ELSE NULL END AS reason_codes, "
            "CASE WHEN length(d.features) <= ? THEN d.features ELSE NULL END AS features, "
            + review + " AS review_state, "
            "CASE WHEN regexp_full_match(d.at_ts, ?) "
            "THEN TRY_CAST(d.at_ts AS TIMESTAMPTZ) ELSE NULL END AS sort_time, "
            "d.recovered_json, d.source_sha256, d.source_file, d.imported_at "
            "FROM decisions d "
            "LEFT JOIN decision_reviews_v1 r ON r.decision_id = d.decision_id "
            "WHERE d.ticker = ? " + state_where + ") "
        )
        params = [MAX_FIELD_CHARS, MAX_FIELD_CHARS, _CLOCK_PATTERN, ticker]
        if state is not None:
            params.append(state)
        valid_identity = "regexp_full_match(decision_id, ?)"
        counts = read.execute(
            timed + "SELECT COUNT(*) FILTER (WHERE sort_time IS NULL), "
            "COUNT(*) FILTER (WHERE sort_time IS NOT NULL AND NOT COALESCE(" + valid_identity + ", FALSE)) "
            "FROM timed", [*params, _ID_PATTERN],
        ).fetchone()
        page_where = "WHERE sort_time IS NOT NULL AND " + valid_identity + " "
        page_params = [*params, _ID_PATTERN]
        if before:
            page_where += f"AND (sort_time {comparison} ? OR (sort_time = ? AND decision_id {comparison} ?)) "
            page_params.extend([before[0], before[0], before[1]])
        page_params.append(limit + 1)
        raw = read.execute(
            timed + "SELECT decision_id, ticker, at_ts, snapshot_id, scenario, side, eligible, "
            "reason_codes, features, review_state, sort_time, recovered_json, source_sha256, source_file, imported_at "
            "FROM timed " + page_where
            + f"ORDER BY sort_time {direction}, decision_id {direction} LIMIT ?", page_params,
        ).fetchall()
        has_more = len(raw) > limit
        raw = raw[:limit]
        identities = [row[0] for row in raw]
        quotes, outcomes = {}, {}
        if identities:
            placeholders = ",".join("?" for _ in identities)
            quotes = dict(read.execute(
                "SELECT decision_id, COUNT(DISTINCT osi) FROM candidate_quotes_v1 "
                "WHERE decision_id IN (" + placeholders + ") GROUP BY decision_id", identities,
            ).fetchall())
            outcome_rows = read.execute(
                "SELECT decision_id, string_agg(DISTINCT label, ',' ORDER BY label) "
                "FROM outcome_labels_v1 WHERE decision_id IN (" + placeholders + ") GROUP BY decision_id",
                identities,
            ).fetchall()
            outcomes = dict(outcome_rows)
        else:
            # Check supporting tables even for an empty page; missing storage
            # is unavailable, not a successful assertion of no quotes/outcomes.
            read.execute("SELECT decision_id FROM candidate_quotes_v1 LIMIT 0").fetchall()
            read.execute("SELECT decision_id FROM outcome_labels_v1 LIMIT 0").fetchall()
        snapshots = set()
        snapshot_ids = list({row[3] for row in raw if row[3] is not None})
        if snapshot_ids:
            marks = ",".join("?" for _ in snapshot_ids)
            snapshots = set(read.execute(
                "SELECT snapshot_id, ticker FROM heatmap_snapshots_v2 WHERE snapshot_id IN (" + marks + ")",
                snapshot_ids,
            ).fetchall())
        if expired.is_set():
            raise DecisionHistoryUnavailable("Saved decisions took too long; try again")
        decisions = []
        partial = bool(counts[0] or counts[1])
        for row in raw:
            features = _json_field(row[8], dict)
            reasons = _json_field(row[7], list)
            review_known = row[9] is None or row[9] in STATES
            if features is None or reasons is None or not review_known or row[6] is None:
                partial = True
            recovered = row[11] is not None
            summary = _json_field(row[11], dict, max_chars=131072) if recovered else None
            if recovered:
                partial = True  # full quote details were not recovered
            feature_outcomes = (summary.get("outcome_labels") if summary else None) if recovered else (
                features.get("outcome_labels") if features else None)
            decisions.append({
                "decision_id": row[0], "ticker": row[1], "at_ts": row[2],
                "snapshot_id": row[3], "scenario": row[4], "side": row[5],
                "eligible": row[6], "reason_codes": reasons,
                "features": features, "features_status": "available" if features is not None else "unavailable",
                "reason_codes_status": "available" if reasons is not None else "unavailable",
                "n_quotes": None if recovered else int(quotes.get(row[0], 0)),
                "quote_status": "summary_only" if recovered else "available",
                "reported_n_quotes": summary.get("n_quotes") if summary else None,
                "snapshot_status": "available" if (row[3], row[1]) in snapshots else "unavailable",
                "recovery_source": {"kind": "legacy_saved_export", "source_sha256": row[12],
                                    "imported_at": row[14]} if recovered else None,
                "outcome_labels": (feature_outcomes if isinstance(feature_outcomes, str) else None) if recovered else (
                    feature_outcomes if isinstance(feature_outcomes, str) else (outcomes.get(row[0]) or "")),
                "review_state": row[9], "review_status": "available" if review_known else "unknown",
            })
        next_cursor = _cursor(raw[-1][10], raw[-1][0], ticker, state, order) if has_more and raw else None
        return {"ticker": ticker, "order": order, "decisions": decisions, "count": len(decisions),
                "status": "partial" if partial else "available",
                "excluded_unknown_time": int(counts[0]), "excluded_invalid_identity": int(counts[1]),
                "has_more": has_more, "next_cursor": next_cursor,
                "checked_at": datetime.now(UTC).isoformat(),
                "note": "Original saved readings. Unknown times remain gaps. Reload after a service restart."}
    except (ValueError, DecisionHistoryUnavailable):
        raise
    except Exception:
        raise DecisionHistoryUnavailable("Saved decisions are unavailable") from None
    finally:
        if timeout is not None:
            timeout.cancel()
            timeout.join()  # no late interrupt can outlive this private cursor
        if read is not None:
            with contextlib.suppress(Exception):
                read.close()
        lock.release()
