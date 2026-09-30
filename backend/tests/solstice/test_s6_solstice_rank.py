"""S6 Solstice rank boundary (Spark, additive — Tide path untouched).

R10-03: a fused row re-ranked must keep 55.5, not fall to 24.0.
R10-04: NaN/inf/bool are invalid, never ok; ML confidence 0 stays 0.
R10-05: cache identity must carry the full scope.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.conviction_rank import rank_many, rank_one  # noqa: E402
from services.solstice_rank import (  # noqa: E402
    KeyedScanCache,
    fuse_one,
    is_fused_row,
    norm_flow_strict,
    norm_ml_strict,
    rank_rows,
    scan_cache_key,
)


def test_fused_row_preserved_not_refused():
    fused = rank_one("SPY", flow={"conviction": 90}, opportunity={"opportunity_score": 8})
    assert fused["conviction"] == 55.5
    # Legacy rank_many re-fuses from scratch and drops the flow evidence:
    legacy = rank_many([{
        "ticker": "SPY",
        "opportunity": {"opportunity_score": 8},
        "conviction": fused,
    }])
    assert legacy[0]["conviction"] == 24.0  # pinned legacy behavior, Tide-owned
    # Solstice boundary preserves the fused score and evidence:
    kept = rank_rows([fused])
    assert kept[0]["conviction"] == 55.5
    assert kept[0]["tier"] == fused["tier"]
    assert kept[0]["rank"] == 1
    assert is_fused_row(fused) is True


def test_raw_rows_fuse_once_with_strict_status():
    rows = rank_rows([{
        "ticker": "SPY",
        "flow": {"conviction": 90},
        "opportunity": {"opportunity_score": 8},
    }])
    assert rows[0]["conviction"] == 55.5
    assert rows[0]["evidence"]["flow_status"] == "ok"


def test_nonfinite_bool_inputs_are_invalid():
    for bad in (float("nan"), float("inf"), True):
        v, status = norm_flow_strict({"conviction": bad})
        assert (v, status) == (0.0, "invalid"), bad
    assert norm_flow_strict(None) == (0.0, "missing")
    assert norm_flow_strict({"conviction": 0}) == (0.0, "ok")  # measured zero stays zero


def test_ml_confidence_zero_stays_zero():
    zero = fuse_one("SPY", ml={"prediction": "UP", "confidence": 0})
    half = fuse_one("SPY", ml={"prediction": "UP", "confidence": 0.5})
    assert zero["conviction"] != half["conviction"]
    assert zero["evidence"]["components"]["ml"] == 0.25  # |1-.5|*(.5+.5*0)
    assert half["evidence"]["components"]["ml"] == 0.375
    # Bearish/bullish symmetry at equal confidence:
    up = fuse_one("SPY", ml={"prediction": "UP", "confidence": 0.8})
    down = fuse_one("SPY", ml={"prediction": "DOWN", "confidence": 0.8})
    assert up["evidence"]["components"]["ml"] == down["evidence"]["components"]["ml"]


def test_cache_key_distinguishes_scope():
    a = scan_cache_key(universe="popular", tickers=["SPY"], scope={"dte": 0, "max_expiries": 1})
    b = scan_cache_key(universe="popular", tickers=["SPY"], scope={"dte": 30, "max_expiries": 4})
    assert a != b
    assert scan_cache_key(universe="u", tickers=["QQQ", "SPY"]) == scan_cache_key(
        universe="u", tickers=["SPY", "QQQ"]
    )


def test_keyed_cache_single_flight_and_source_age():
    cache = KeyedScanCache(ttl_s=60.0)
    calls = []
    key = scan_cache_key(universe="u", tickers=["SPY"], scope={"dte": 0})
    first = cache.get_or_compute(key, lambda: (calls.append(1), {"source_asof": "t0", "v": 1})[1])
    second = cache.get_or_compute(key, lambda: {"source_asof": "t1", "v": 2})
    assert first["cache"] == "miss" and second["cache"] == "hit"
    assert calls == [1]  # computed once
    assert second["source_asof"] == "t0"  # cached reads do not reset source age
    other = scan_cache_key(universe="u", tickers=["SPY"], scope={"dte": 30})
    third = cache.get_or_compute(other, lambda: {"source_asof": "t1", "v": 2})
    assert third["cache"] == "miss"
