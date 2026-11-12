"""Offline research plan preview only. There is deliberately no live factory."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.public_research_collector import preview
from services.public_research_store import ResearchRefusal


def main(argv=None):
    parser = argparse.ArgumentParser(description="Preview a fixed SPY/QQQ raw research plan; no collection is admitted.")
    parser.add_argument("--expiry", action="append", required=True, help="One or two fixed YYYY-MM-DD expiries, sorted and unique.")
    args = parser.parse_args(argv)
    try:
        result = preview(args.expiry)
    except ResearchRefusal:
        parser.error("invalid fixed expiry plan")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
