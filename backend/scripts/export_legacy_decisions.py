"""Export saved decisions from an isolated STOPPED research-store copy.

Never opens a live/locked database, never initializes one, never imports.
Protection is: `--database` must be an existing non-empty `.duckdb` file,
opened `read_only=True`, so DuckDB's own file lock refuses a running writer;
there is no separate stopped-process check — pass an isolated stopped copy.
Output is the digest-verifiable document `load_export` accepts, with
full (uncapped) per-ticker rows and a receipt header; rows whose stored
`reason_codes`/`features` JSON does not parse are exported with empty
values and COUNTED in the receipt (`normalized_rows`) rather than dropped
silently. Completeness against the ORIGINAL store still requires authorized
access to that store's stopped copy (see NAV-CAPTURE hold).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIELDS = ("decision_id", "ticker", "at_ts", "snapshot_id", "scenario", "side",
          "eligible", "reason_codes", "features", "n_quotes", "outcome_labels",
          "review_state")


def _has_table(conn, name):
    return bool(conn.execute(
        "SELECT COUNT(*) FROM information_schema.tables "
        "WHERE table_schema = 'main' AND table_name = ?", [name]).fetchone()[0])


def export(conn):
    """Full uncapped rows per ticker; unknown/malformed clocks kept as stored."""
    if not _has_table(conn, "scenario_decisions_v1"):
        raise ValueError("No saved decision table in the supplied copy")
    quotes = _has_table(conn, "candidate_quotes_v1")
    outcomes = _has_table(conn, "outcome_labels_v1")
    reviews = _has_table(conn, "decision_reviews_v1")
    rows = conn.execute(
        "SELECT decision_id, ticker, at_ts, snapshot_id, scenario, side, eligible, "
        "reason_codes, features FROM scenario_decisions_v1 ORDER BY ticker, at_ts, decision_id"
    ).fetchall()
    by_ticker: dict[str, dict] = {}
    normalized_rows = 0
    for decision_id, ticker, at_ts, snapshot_id, scenario, side, eligible, reasons, features in rows:
        n_quotes = None
        if quotes:
            n_quotes = conn.execute(
                "SELECT COUNT(DISTINCT osi) FROM candidate_quotes_v1 WHERE decision_id = ?",
                [decision_id]).fetchone()[0]
        labels = None
        if outcomes:
            labels = conn.execute(
                "SELECT string_agg(DISTINCT label, ',' ORDER BY label) FROM outcome_labels_v1 "
                "WHERE decision_id = ?", [decision_id]).fetchone()[0]
        state = None
        if reviews:
            state = conn.execute(
                "SELECT state FROM decision_reviews_v1 WHERE decision_id = ?",
                [decision_id]).fetchone()
            state = state[0] if state else None
        try:
            reason_list = json.loads(reasons) if isinstance(reasons, str) else []
            feature_dict = json.loads(features) if isinstance(features, str) else {}
        except ValueError:
            reason_list, feature_dict = [], {}
            normalized_rows += 1
        body = by_ticker.setdefault(ticker, {"ticker": ticker, "decisions": []})
        body["decisions"].append({
            "decision_id": decision_id, "ticker": ticker, "at_ts": at_ts,
            "snapshot_id": snapshot_id, "scenario": scenario, "side": side,
            "eligible": eligible, "reason_codes": reason_list,
            "features": feature_dict, "n_quotes": n_quotes,
            "outcome_labels": labels, "review_state": state,
        })
    document = []
    for ticker, body in sorted(by_ticker.items()):
        body["count"] = len(body["decisions"])
        document.append({"path": f"/api/solstice/{ticker}/decisions",
                         "status": 200, "body": body})
    receipt = {
        "exported_at": datetime.now(UTC).isoformat(),
        "tickers": len(document),
        "rows": sum(item["body"]["count"] for item in document),
        "normalized_rows": normalized_rows,
        "quote_table_present": quotes,
        "outcome_table_present": outcomes,
        "review_table_present": reviews,
        "note": "Full uncapped export of the supplied STOPPED COPY only; "
                "completeness vs the original store is a separate receipt.",
    }
    return document, receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True,
                        help="Path to an isolated stopped COPY (never the live store)")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    target = Path(args.database).resolve(strict=True)
    if not target.is_file() or target.suffix.lower() != ".duckdb" or target.stat().st_size == 0:
        raise ValueError("Choose an existing stopped research-store copy")
    conn = duckdb.connect(str(target), read_only=True)
    try:
        document, receipt = export(conn)
    finally:
        conn.close()
    payload = json.dumps(document, sort_keys=True)
    out = Path(args.out)
    out.write_text(payload)
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(json.dumps({"out": str(out), "sha256": digest, **receipt}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
