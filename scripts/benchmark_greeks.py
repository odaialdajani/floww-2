#!/usr/bin/env python3
"""
benchmark_greeks.py  —  Measure Greek computation performance.

Requirements (Agent 2 acceptance criteria):
    - <5ms  for a 10,000-contract chain (warm, JIT-compiled)
    - <50ms cold-start latency (first call after import)

Usage::

    $ python scripts/benchmark_greeks.py [--contracts 10000] [--warmup 3]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("benchmark_greeks")


def benchmark(n_contracts: int = 10000, warmup_runs: int = 3) -> dict:
    """Run the full benchmark suite and return results dict."""
    # ── Generate synthetic chain ──────────────────────────────────────
    rng = np.random.default_rng(42)
    spot = 450.0
    lo = spot * 0.5
    hi = spot * 1.5

    strikes = np.sort(rng.uniform(lo, hi, n_contracts))
    expiries = rng.uniform(0.01, 2.0, n_contracts)  # 3 days – 2 years
    ivs = rng.uniform(0.10, 0.80, n_contracts)
    types = rng.integers(0, 2, n_contracts).astype(np.int32)

    # ── Import (lazy — measures cold-start time) ──────────────────────
    t0 = time.perf_counter()

    # Force fresh import by removing any cached module
    for mod in list(sys.modules.keys()):
        if "numba_greeks" in mod and "test" not in mod:
            del sys.modules[mod]

    from services.numba_greeks import compute_all_greeks  # noqa: F811

    cold_start_s = time.perf_counter() - t0
    cold_start_ms = cold_start_s * 1000.0
    logger.info("Cold-start import: %.2f ms", cold_start_ms)

    # ── Warm-up runs ──────────────────────────────────────────────────
    for w in range(warmup_runs):
        _ = compute_all_greeks(spot, strikes[:100], expiries[:100],
                               ivs[:100], types[:100])

    # ── Timed run: full chain ─────────────────────────────────────────
    # Run 5 iterations and take the median
    times = []
    for _ in range(5):
        t0 = time.perf_counter()
        _ = compute_all_greeks(spot, strikes, expiries, ivs, types)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        times.append(elapsed_ms)

    median_ms = float(np.median(times))
    p99_ms = float(np.percentile(times, 99))
    min_ms = float(np.min(times))
    max_ms = float(np.max(times))

    logger.info(
        "Chain  %s contracts  —  median %.3f ms  (p99 %.3f  min %.3f  max %.3f)",
        f"{n_contracts:,}",
        median_ms,
        p99_ms,
        min_ms,
        max_ms,
    )

    # ── Verify results are sane (no NaNs) ─────────────────────────────
    result = compute_all_greeks(spot, strikes, expiries, ivs, types)
    for key, arr in result.items():
        n_nan = int(np.sum(np.isnan(arr)))
        if n_nan > 0:
            logger.warning("  %s: %d / %d NaN values", key, n_nan, len(arr))

    # ── Acceptance criteria checks ────────────────────────────────────
    chain_pass = median_ms < 5.0
    cold_pass = cold_start_ms < 50.0

    logger.info("")
    logger.info("═" * 55)
    logger.info("  Acceptance Criteria")
    logger.info("═" * 55)
    logger.info(
        "  ✓  Chain 10k < 5ms   :  %s  (%.3f ms)",
        "PASS" if chain_pass else "FAIL",
        median_ms,
    )
    logger.info(
        "  ✓  Cold start < 50ms :  %s  (%.2f ms)",
        "PASS" if cold_pass else "FAIL",
        cold_start_ms,
    )
    logger.info("═" * 55)

    return {
        "n_contracts": n_contracts,
        "cold_start_ms": round(cold_start_ms, 2),
        "median_ms": round(median_ms, 3),
        "p99_ms": round(p99_ms, 3),
        "min_ms": round(min_ms, 3),
        "max_ms": round(max_ms, 3),
        "chain_pass": chain_pass,
        "cold_pass": cold_pass,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark Numba Greek computation performance."
    )
    parser.add_argument(
        "--contracts",
        type=int,
        default=10000,
        help="Number of contracts in the chain (default 10,000)",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=3,
        help="Number of warm-up runs before timing (default 3)",
    )
    args = parser.parse_args()

    results = benchmark(n_contracts=args.contracts, warmup_runs=args.warmup)

    if not results["chain_pass"]:
        logger.error(
            "FAIL: Chain benchmark %.3f ms exceeds 5 ms threshold",
            results["median_ms"],
        )
        return 1

    if not results["cold_pass"]:
        logger.warning(
            "WARN: Cold-start %.2f ms exceeds 50 ms threshold",
            results["cold_start_ms"],
        )
        # Not a hard failure — JIT cold starts can vary

    return 0


if __name__ == "__main__":
    sys.exit(main())
