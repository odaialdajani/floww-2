"""Offline recovery of original exported summaries; quote details stay unknown."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

from services.connection_guard import connection_lock

MAX_SOURCE_BYTES = 8_000_000
MAX_SUMMARIES = 5000
MAX_SUMMARY_CHARS = 131072
STATES = {"pending", "reviewed", "waiting", "skipped"}
FIELDS = {"decision_id", "ticker", "at_ts", "snapshot_id", "scenario", "side", "eligible",
          "reason_codes", "features", "n_quotes", "outcome_labels", "review_state"}
LEGACY_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS legacy_decision_summaries_v1 (
    decision_id VARCHAR PRIMARY KEY,
    ticker VARCHAR,
    at_ts VARCHAR,
    snapshot_id VARCHAR,
    summary_json VARCHAR,
    summary_sha256 VARCHAR,
    source_sha256 VARCHAR,
    source_file VARCHAR,
    imported_at VARCHAR
)
"""


def _symbol(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,31}", value):
        raise ValueError("Legacy summary has an invalid stock")
    return value


def _validate_summary(row, ticker):
    if not isinstance(row, dict) or set(row) != FIELDS:
        raise ValueError("Unsupported legacy summary fields")
    if _symbol(row["ticker"]) != ticker:
        raise ValueError("Legacy summary stock differs from its source")
    identity = row["decision_id"]
    if not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", identity):
        raise ValueError("Legacy summary identity is invalid")
    at = row["at_ts"]
    if (not isinstance(at, str) or len(at) > 50
            or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}"
                                r"(\.[0-9]{1,9})?(Z|[+-](0[0-9]|1[0-9]|2[0-3]):[0-5][0-9])", at)):
        raise ValueError("Legacy summary time is unavailable")
    try:
        observed = datetime.fromisoformat(at.replace("Z", "+00:00"))
        if observed.tzinfo is None or observed.utcoffset() is None:
            raise ValueError()
    except (ValueError, OverflowError):
        raise ValueError("Legacy summary time is unavailable") from None
    if row["snapshot_id"] is not None and (not isinstance(row["snapshot_id"], str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", row["snapshot_id"])):
        raise ValueError("Legacy summary snapshot identity is invalid")
    for field in ("scenario", "side", "outcome_labels"):
        if row[field] is not None and (not isinstance(row[field], str) or len(row[field]) > 2000):
            raise ValueError("Legacy summary text field is invalid")
    if row["eligible"] is not None and type(row["eligible"]) is not bool:
        raise ValueError("Legacy summary eligibility is invalid")
    if (not isinstance(row["reason_codes"], list) or len(row["reason_codes"]) > 100
            or any(not isinstance(reason, str) or len(reason) > 1000 for reason in row["reason_codes"])):
        raise ValueError("Legacy summary reasons are invalid")
    if not isinstance(row["features"], dict):
        raise ValueError("Legacy summary features are unavailable")
    reported = row["n_quotes"]
    if reported is not None and (type(reported) is not int or not 0 <= reported <= 100000):
        raise ValueError("Legacy summary quote count is invalid")
    if row["review_state"] is not None and (not isinstance(row["review_state"], str)
            or row["review_state"] not in STATES):
        raise ValueError("Legacy summary review state is invalid")
    try:
        raw = json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False)
        if (len(raw) > MAX_SUMMARY_CHARS or len(json.dumps(row["features"], allow_nan=False)) > 65536
                or len(json.dumps(row["reason_codes"], allow_nan=False)) > 65536):
            raise ValueError()
    except (TypeError, ValueError, RecursionError):
        raise ValueError("Legacy summary is too large or contains unsupported values") from None
    return {"decision_id": identity, "ticker": ticker, "at_ts": at,
            "snapshot_id": row["snapshot_id"], "summary_json": raw,
            "summary_sha256": hashlib.sha256(raw.encode()).hexdigest()}


def load_export(source_path, *, expected_sha256):
    """Verify exact bytes and every row before a target store can be opened."""
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise ValueError("A verified source digest is required")
    source = Path(source_path).resolve(strict=True)
    if not source.is_file() or source.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Legacy source is too large or is not a file")
    content = source.read_bytes()
    if len(content) > MAX_SOURCE_BYTES or hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ValueError("Legacy source digest does not match")
    try:
        document = json.loads(content, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("Legacy source is not valid saved JSON") from None
    if not isinstance(document, list) or not 1 <= len(document) <= 100:
        raise ValueError("Unsupported legacy source format")
    prepared = {}
    duplicate_input = 0
    total = 0
    for entry in document:
        if (not isinstance(entry, dict) or set(entry) != {"path", "status", "body"}
                or type(entry["status"]) is not int or entry["status"] != 200
                or not isinstance(entry["path"], str) or not isinstance(entry["body"], dict)):
            raise ValueError("Legacy source contains an unavailable or invalid response")
        body = entry["body"]
        path = urlsplit(entry["path"]).path
        if "decisions" not in body:
            if path == "/api/flowseeker/alerts/feed" and isinstance(body.get("alerts"), list):
                continue  # retained alerts are a separate recovery source
            raise ValueError("Unsupported legacy source response")
        route = re.fullmatch(r"/api/solstice/([^/]+)/decisions", path)
        if route is None or not isinstance(body.get("decisions"), list):
            raise ValueError("Legacy source is not a saved decision response")
        ticker = _symbol(body.get("ticker"))
        if _symbol(unquote(route[1])) != ticker:
            raise ValueError("Legacy source stock differs from its saved route")
        rows = body["decisions"]
        if type(body.get("count")) is not int or body["count"] != len(rows):
            raise ValueError("Legacy source count does not match its saved rows")
        total += len(rows)
        if total > MAX_SUMMARIES:
            raise ValueError("Legacy source contains too many summaries")
        for row in rows:
            item = _validate_summary(row, ticker)
            prior = prepared.get(item["decision_id"])
            if prior is not None:
                if prior["summary_json"] != item["summary_json"]:
                    raise ValueError("Legacy summary identity conflict within source")
                duplicate_input += 1
            else:
                prepared[item["decision_id"]] = item
    if not prepared:
        raise ValueError("Legacy source contains no decision summaries")
    return {"source_file": str(source), "source_sha256": expected_sha256,
            "rows": list(prepared.values()), "source_rows": total, "duplicate_input": duplicate_input}


def import_summaries(conn, source_path, *, expected_sha256):
    """Atomic archival import, never a normal decision/quote/review write."""
    batch = load_export(source_path, expected_sha256=expected_sha256)
    if conn is None:
        raise RuntimeError("Saved summary storage is unavailable")
    rows = batch["rows"]
    imported_at = datetime.now(UTC).isoformat()
    inserted = 0
    already = 0
    overlaps = 0
    with connection_lock(conn):
        conn.execute("BEGIN TRANSACTION")
        try:
            identities = [row["decision_id"] for row in rows]
            marks = ",".join("?" for _ in identities)
            has_native = conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = 'main' AND table_name = 'scenario_decisions_v1'"
            ).fetchone()[0]
            if has_native:
                native = conn.execute(
                    "SELECT decision_id, ticker FROM scenario_decisions_v1 WHERE decision_id IN (" + marks + ")",
                    identities,
                ).fetchall()
                source_tickers = {row["decision_id"]: row["ticker"] for row in rows}
                if any(ticker != source_tickers[identity] for identity, ticker in native):
                    raise ValueError("Legacy summary identity conflict with another stock")
                overlaps = len({identity for identity, _ in native})
            conn.execute(LEGACY_TABLE_DDL)
            existing = {identity: (digest, raw) for identity, digest, raw in conn.execute(
                "SELECT decision_id, summary_sha256, summary_json FROM legacy_decision_summaries_v1 "
                "WHERE decision_id IN (" + marks + ")", identities,
            ).fetchall()}
            for row in rows:
                saved = existing.get(row["decision_id"])
                if saved is not None:
                    if saved != (row["summary_sha256"], row["summary_json"]):
                        raise ValueError("Legacy summary identity conflict with saved source")
                    already += 1
                    continue
                conn.execute(
                    "INSERT INTO legacy_decision_summaries_v1 "
                    "(decision_id, ticker, at_ts, snapshot_id, summary_json, summary_sha256, "
                    "source_sha256, source_file, imported_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [row["decision_id"], row["ticker"], row["at_ts"], row["snapshot_id"], row["summary_json"],
                     row["summary_sha256"], batch["source_sha256"], batch["source_file"], imported_at],
                )
                inserted += 1
            conn.execute("COMMIT")
        except Exception as error:
            conn.execute("ROLLBACK")
            if isinstance(error, ValueError):
                raise
            raise RuntimeError("Saved summary import failed; no partial recovery was kept") from None
    return {"inserted": inserted, "already_present": already, "native_overlaps": overlaps,
            "source_rows": batch["source_rows"], "duplicate_input": batch["duplicate_input"],
            "source_sha256": batch["source_sha256"], "source_file": batch["source_file"],
            "quote_details_recovered": 0,
            "note": "Only supplied decision summaries were recovered. Quote details and completeness of the earlier export are unknown."}
