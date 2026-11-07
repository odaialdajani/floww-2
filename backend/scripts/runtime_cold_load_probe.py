"""Offline runtime probe for the chart read path (Task 4, step 1 and step 3).

Measure, in one fresh interpreter, what a chart read actually costs per stage,
and what the rest of the app does while two tickers are being read:

  python backend/scripts/runtime_cold_load_probe.py            # cold-load split
  python backend/scripts/runtime_cold_load_probe.py --concurrent AMD SPY

Nothing here talks to a network, a running service, or a persistent store. The
vendor is a double that waits a fixed time, the DuckDB file lives in a
temporary directory the probe deletes afterwards, and the numbers describe this
repository's code path — never the vendor's own latency.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from httpx import ASGITransport, AsyncClient  # noqa: E402

from tests.runtime_harness import (  # noqa: E402
    ADMISSION,
    BARS_STEP,
    CALCULATION,
    DAILY_BARS,
    DUCKDB,
    PUBLIC_READ,
    build_environment,
    chart_read,
    version_probe,
)


def _span_summary(recorder) -> dict:
    return {
        name: {
            "spans": len(recorder.stage(name)),
            "total_s": recorder.total(name),
            "max_s": recorder.maximum(name),
            "threads": recorder.threads(name),
            "labels": recorder.labels(name),
        }
        for name in (PUBLIC_READ, DAILY_BARS, CALCULATION, DUCKDB, BARS_STEP, ADMISSION)
    }


async def _cold_load(days: int, ticker: str, delay: float) -> dict:
    """First read in this process, then a repeat read, stage by stage."""
    store = Path(tempfile.mkdtemp(prefix="floww-cold-load-"))
    recorder, broker, _budget, _engine, app, patch = build_environment(store, delay=delay)
    try:
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://cold-load-probe") as client:
            _status, _body, idle = await version_probe(client)
            first, first_wall = await chart_read(client, ticker, days)
            second, second_wall = await chart_read(client, ticker, days)
        evidence = [span["elapsed_s"] for span in recorder.stage(DAILY_BARS)
                    if span["label"] == "evidence"]
        return {
            "mode": "cold-load",
            "ticker": ticker,
            "days": days,
            "vendor_delay_s": delay,
            "version_probe_idle_s": round(idle, 6),
            "first_read": {"status": first.status_code, "wall_s": round(first_wall, 6)},
            "repeat_read": {"status": second.status_code, "wall_s": round(second_wall, 6)},
            "first_evidence_spans_s": evidence[:1],
            "later_evidence_spans_s": evidence[1:],
            "vendor_calls": list(broker.calls),
            "stages": _span_summary(recorder),
        }
    finally:
        patch.restore()
        shutil.rmtree(store, ignore_errors=True)


async def _concurrent(tickers: list[str], days: int, delay: float) -> dict:
    """Two tickers at once, with /api/version probes while both are in flight."""
    store = Path(tempfile.mkdtemp(prefix="floww-concurrent-"))
    recorder, broker, budget, _engine, app, patch = build_environment(store, delay=delay)
    try:
        async with AsyncClient(transport=ASGITransport(app=app),
                               base_url="http://concurrent-probe") as client:
            _status, _body, idle = await version_probe(client)
            reads = [asyncio.create_task(chart_read(client, ticker, days))
                     for ticker in tickers]
            probes: list[float] = []
            while any(not read.done() for read in reads):
                _status, _body, elapsed = await version_probe(client)
                probes.append(round(elapsed, 6))
                if not probes:
                    break
                await asyncio.sleep(0.005)
            results = await asyncio.gather(*reads)
        vendor_windows = recorder.windows(PUBLIC_READ)
        return {
            "mode": "concurrent",
            "tickers": tickers,
            "days": days,
            "vendor_delay_s": delay,
            "version_probe_idle_s": round(idle, 6),
            "version_probes_during_work_s": probes,
            "version_probes_max_s": max(probes) if probes else None,
            "reads": [
                {"ticker": ticker, "status": response.status_code,
                 "wall_s": round(wall, 6)}
                for ticker, (response, wall) in zip(tickers, results, strict=True)
            ],
            "sum_of_read_walls_s": round(sum(wall for _r, wall in results), 6),
            "vendor_windows": [[round(a, 6), round(b, 6)] for a, b in vendor_windows],
            "vendor_reads_overlap": recorder.any_overlap(PUBLIC_READ),
            "store_reads_overlap": recorder.any_overlap(DUCKDB),
            "budget_inflight_left": budget.status()["inflight"],
            "vendor_calls": list(broker.calls),
            "stages": _span_summary(recorder),
        }
    finally:
        patch.restore()
        shutil.rmtree(store, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrent", nargs="+", metavar="TICKER",
                        help="read several tickers at once and probe /api/version")
    parser.add_argument("--days", type=int, default=260)
    parser.add_argument("--ticker", default="SPY")
    parser.add_argument("--vendor-delay", type=float, default=0.0,
                        help="seconds the vendor double waits per read")
    args = parser.parse_args()

    if args.concurrent:
        report = asyncio.run(_concurrent(args.concurrent, args.days, args.vendor_delay))
    else:
        report = asyncio.run(_cold_load(args.days, args.ticker, args.vendor_delay))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
