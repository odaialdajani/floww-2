"""Roadmap #4 + #5: per-strike confluence overlay + flow-at-node.

Contracts pinned:
  * ranks levels by |GEX| (the structural significance read off the grid)
  * microstructure skew is the only strike dimension carrying direction
  * thin tape reports "missing", never a fabricated lean
  * structure is unsigned context, never folded into the signed total
  * dimensions with no real input are reported missing, contribute 0.0
  * flow-at-strike finds prints near the level and surfaces unpriced rows
    rather than silently assigning them
"""

from __future__ import annotations

from services.node_confluence import (
    NEAR_STRIKE_TOL,
    flow_at_strike,
    microstructure_skew,
    node_brief,
    structure_magnitude,
)


def _strikes():
    return [
        {"strike": 500.0, "gex": 5_000_000.0, "total_oi": 9000.0,
         "call_volume": 800.0, "put_volume": 200.0,
         "lifecycle": "fresh", "taps": 0, "tap_prob": None},
        {"strike": 495.0, "gex": -3_000_000.0, "total_oi": 4000.0,
         "call_volume": 100.0, "put_volume": 900.0,
         "lifecycle": "tested", "taps": 1, "tap_prob": 0.66},
        {"strike": 505.0, "gex": 1_000.0, "total_oi": 10.0,
         "call_volume": 2.0, "put_volume": 1.0,
         "lifecycle": "fresh", "taps": 0, "tap_prob": None},
    ]


def test_structure_magnitude_is_king_relative_and_missing_when_empty():
    val, status = structure_magnitude(_strikes())
    assert val == 1.0, "the king itself is 1.0 by construction"
    assert status == "ok"
    empty_val, empty_status = structure_magnitude([])
    assert empty_val == 0.0 and empty_status == "missing"


def test_microstructure_skew_signed_and_thin_tape_is_missing():
    call_heavy = {"call_volume": 800.0, "put_volume": 200.0}
    put_heavy = {"call_volume": 100.0, "put_volume": 900.0}
    call_val, call_status = microstructure_skew(call_heavy)
    put_val, put_status = microstructure_skew(put_heavy)
    assert call_val > 0 and call_status == "ok", "call-heavy activity balance"
    assert put_val < 0 and put_status == "ok", "put-heavy activity balance"
    # thin tape: absence of flow is not flow
    thin_val, thin_status = microstructure_skew({"call_volume": 1.0, "put_volume": 1.0})
    assert thin_val == 0.0 and thin_status == "missing"


def test_flow_at_strike_finds_prints_in_window():
    flow = [
        {"strike": 500.0, "type": "call", "size": 100},
        {"strike": 501.0, "type": "put", "size": 50},   # inside tolerance
        {"strike": 520.0, "type": "call", "size": 10},   # outside — must not count
    ]
    got = flow_at_strike(flow, 500.0)
    assert got["count"] == 2, "only prints within the window count"
    assert got["call_side"] == 1 and got["put_side"] == 1
    assert got["direction_net"] is None
    assert got["status"] == "ok"


def test_flow_at_strike_surfaces_unpriced_rows():
    flow = [{"strike": 500.0, "type": "call"}, {"note": "no price here"}]
    got = flow_at_strike(flow, 500.0)
    assert got["count"] == 1
    assert got["unpriced_rows"] == 1, "unpriced rows are surfaced, not assigned"


def test_flow_at_strike_no_prints_is_honest_status():
    got = flow_at_strike([], 500.0)
    assert got["count"] == 0
    assert got["status"] == "no_prints", "no prints is a state, not silence"


def test_node_brief_ranks_by_abs_gex():
    got = node_brief("SPY", _strikes(), limit=3)
    gexes = [r["gex"] for r in got["rows"]]
    abs_gexes = [abs(g) for g in gexes]
    assert abs_gexes == sorted(abs_gexes, reverse=True), "ranks by |GEX| desc"
    assert got["ticker"] == "SPY"
    assert got["schema_version"] == "node_confluence.v1"


def test_node_brief_confluence_has_honest_status_map():
    got = node_brief("SPY", _strikes(), limit=3)
    row = got["rows"][0]  # the 500 strike, call-heavy
    dims = row["confluence"]["dimensions"]
    # Only microstructure has a real per-strike input here.
    assert dims["microstructure"]["inputs_status"] == "context_only"
    # These have no per-strike input — they must be reported, not faked.
    assert dims["ml"]["inputs_status"] == "missing"
    assert dims["vol"]["inputs_status"] == "missing"
    assert dims["time_delta"]["inputs_status"] == "missing"
    # structure is unsigned context, never a direction claim
    assert dims["structure"]["inputs_status"] == "context_only"
    # Missing dimensions remain unknown, never fabricated zero.
    assert dims["ml"]["contribution"] is None
    assert dims["ml"]["value"] is None


def test_node_brief_never_fabricates_direction_on_thin_tape():
    # All strikes thin -> microstructure must be missing everywhere, so the
    # confluence total cannot lean bullish or bearish off thin volume.
    thin = [{"strike": 500.0, "gex": 5_000_000.0, "total_oi": 10.0,
             "call_volume": 1.0, "put_volume": 1.0}]
    got = node_brief("SPY", thin, limit=1)
    row = got["rows"][0]
    assert row["microstructure_status"] == "missing"
    assert row["confluence"]["direction"] == "insufficient_evidence", "no lean without evidence"
    assert row["confluence"]["total"] is None


def test_node_brief_handles_empty_payload():
    got = node_brief("SPY", [], limit=5)
    assert got["rows"] == []
    assert got["strikes_considered"] == 0


def test_node_brief_never_raises_on_junk_strike_rows():
    # A malformed row (None gex, string strike) must not crash the overlay.
    junk = [
        {"strike": "not-a-number", "gex": 1.0},
        {"strike": 500.0, "gex": None},
        {"strike": 500.0, "gex": 5_000_000.0, "call_volume": 1.0, "put_volume": 1.0},
    ]
    got = node_brief("SPY", junk, limit=5)  # must not raise
    assert isinstance(got["rows"], list)


def test_node_brief_keeps_net_zero_gex_strike():
    """A perfectly hedged call/put pair nets to exactly 0 GEX.

    That is a pin — a meaningful structural state — and must survive into
    the overlay. An earlier revision dropped gex == 0 rows and silently
    erased every hedged level from the board.
    """
    hedged = [
        {"strike": 500.0, "gex": 0.0, "total_oi": 5000.0,
         "call_volume": 600.0, "put_volume": 400.0},
    ]
    got = node_brief("SPY", hedged, limit=5)
    assert got["rows"], "net-zero GEX must not be filtered away"
    assert got["rows"][0]["gex"] == 0.0
    assert got["rows"][0]["strike"] == 500.0


def test_node_brief_drops_rows_with_no_strike_price():
    no_price = [{"strike": None, "gex": 5_000_000.0}, {"gex": 9_000_000.0}]
    got = node_brief("SPY", no_price, limit=5)
    assert got["rows"] == [], "a row with no strike price is not a level"


def test_flow_window_tolerance_is_positive():
    assert NEAR_STRIKE_TOL > 0
