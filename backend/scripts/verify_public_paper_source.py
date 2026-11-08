#!/usr/bin/env python3
"""Read-only readiness probe: no network, writes, approval issuance or orders.

Input paths are operator-selected local evidence, never an application request.
The clock is real UTC with no historical-time override. A refusal is expected
for legacy saved scans, weekends, and missing independently verified evidence.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import stat
from datetime import UTC, datetime

from services.agent.paper.public_source_adapter import (
    MAX_BYTES,
    SourceRefusal,
    StoredPublicSnapshots,
    inspect_saved_observations,
    inspect_stored_row,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--saved-observations")
    group.add_argument("--snapshot-db")
    parser.add_argument("--snapshot-id")
    parser.add_argument("--contract-id")
    args = parser.parse_args()
    now = datetime.now(UTC)
    try:
        if args.saved_observations:
            descriptor = os.open(args.saved_observations, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                    raise SourceRefusal("source_file_invalid")
                raw = stream.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise SourceRefusal("source_bytes_exceeded")
            result = inspect_saved_observations(json.loads(raw), now=now)
        else:
            source = StoredPublicSnapshots(args.snapshot_db)
            rows = asyncio.run(source.read([dict(snapshot_id=args.snapshot_id, contract_id=args.contract_id)]))
            result = dict(admitted=False, checked_at=now.isoformat(),
                          observations=[inspect_stored_row(row, now=now, max_age_seconds=60) for row in rows])
        print(json.dumps(result, indent=2, allow_nan=False))
        return 2  # The standalone probe never authenticates or admits a trade.
    except (OSError, ValueError, TypeError):
        print(json.dumps(dict(admitted=False, reason="source_probe_refused")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
