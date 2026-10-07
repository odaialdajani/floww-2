"""Record an inspected fix for future maintenance; never execute suggestions."""
import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.problem_journal import journal, redact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--problem", required=True)
    parser.add_argument("--fix", required=True)
    parser.add_argument("--proof", required=True)
    args = parser.parse_args()
    row = {"at": datetime.now(UTC).isoformat(), "problem": redact(args.problem),
           "fix": redact(args.fix), "proof": redact(args.proof), "status": "verified"}
    with (journal().directory / "verified-fixes.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(row) + "\n")
    print("Verified fix recorded")


if __name__ == "__main__":
    main()
