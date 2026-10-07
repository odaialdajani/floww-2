"""Offline import of verified saved decision summaries into an existing stopped store."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.legacy_decision_recovery import import_summaries, load_export


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--database", required=True)
    args = parser.parse_args(argv)
    conn = None
    try:
        # Validation precedes even opening the target. The importer rechecks
        # bytes afterwards, so a changed source cannot enter the transaction.
        load_export(args.source, expected_sha256=args.expected_sha256)
        target = Path(args.database).resolve(strict=True)
        if (not target.is_file() or target.suffix.lower() != ".duckdb"
                or target.stat().st_size == 0):
            raise ValueError("Choose the existing backed-up stopped research store")
        # DuckDB's file lock refuses another process's running writer. Never
        # force a lock, replace the file, initialize the app, or start a service.
        conn = duckdb.connect(str(target))
        result = import_summaries(conn, args.source, expected_sha256=args.expected_sha256)
        conn.execute("CHECKPOINT")
        print(json.dumps(result))
        return 0
    except Exception as error:
        message = str(error) if isinstance(error, ValueError) else "Recovery could not open or save the stopped research store"
        print(message, file=sys.stderr)
        return 2
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
