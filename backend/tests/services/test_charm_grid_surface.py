"""The Charm grid must exist on the vendor-greek path, or the tab is a lie.

`SkylitHeatmapGrid.jsx` offers a Charm view (`GRID_BY_VIEW.charm` ->
`grid.charm_grid`), and `CharmDecayPanel.jsx` reads the same key. But only the
local Black-Scholes path in `compute_gex_grid` ever emitted it. The vendor
path -- what actually serves the app when the provider supplies Greeks --
returned no `charm_grid`, so selecting Charm rendered "surface unavailable in
this snapshot" on a perfectly healthy payload.

The same bug class as a UI field the backend never sends.
"""

from __future__ import annotations

from services.gex_core import compute_charm_grid_local


def _c(strike, expiry, kind="call", charm=None, oi=100):
    c = {"strike": strike, "expiry": expiry, "type": kind, "oi": oi, "gamma": 0.02}
    if charm is not None:
        c["charm"] = charm
    return c


def test_charm_grid_is_emitted_when_vendor_supplies_charm():
    got = compute_charm_grid_local(
        500.0,
        [_c(500, "2026-09-28", "call", 0.01), _c(495, "2026-09-28", "put", -0.02)],
        "SPY",
    )
    assert got["grid"], "a payload with vendor charm produced an empty surface"
    assert got["status"] == "ok"
    assert got["expiries"] == ["2026-09-28"]
    assert set(got["grid"]["2026-09-28"]) == {500.0, 495.0}


def test_call_and_put_charm_sum_at_the_same_strike():
    got = compute_charm_grid_local(
        500.0,
        [_c(500, "2026-09-28", "call", 0.01), _c(500, "2026-09-28", "put", -0.02)],
        "SPY",
    )
    assert got["grid"]["2026-09-28"][500.0] == 0.01 + (-0.02)


def test_missing_charm_is_partial_not_zero():
    """An absent Greek is unknown, never 0.0 -- the app's core honesty rule."""
    got = compute_charm_grid_local(
        500.0,
        [_c(500, "2026-09-28", "call", 0.01), _c(495, "2026-09-28", "call", None)],
        "SPY",
    )
    assert got["status"] == "partial"
    assert got["reason"] == "PARTIAL_CHARM_COVERAGE"
    assert got["missing_charm_inputs"] == 1
    # The contract with no charm contributes no cell at all.
    assert 495.0 not in got["grid"]["2026-09-28"]


def test_unknown_option_type_is_rejected_not_default_signed():
    got = compute_charm_grid_local(
        500.0,
        [_c(500, "2026-09-28", "call", 0.01), _c(490, "2026-09-28", "banana", 0.5)],
        "SPY",
    )
    assert got["invalid_type"] == 1
    assert 490.0 not in got["grid"]["2026-09-28"]


def test_non_finite_charm_is_treated_as_missing():
    got = compute_charm_grid_local(
        500.0, [_c(500, "2026-09-28", "call", float("nan"))], "SPY"
    )
    assert got["status"] == "unavailable"
    assert got["reason"] == "NO_CHARM_INPUT"


def test_empty_contracts_report_unavailable_rather_than_empty_ok():
    got = compute_charm_grid_local(500.0, [], "SPY")
    assert got["status"] == "unavailable"
    assert got["grid"] == {}


def test_server_attaches_a_charm_surface_to_the_payload():
    """The wiring is the actual bug -- the function existing proves nothing."""
    from pathlib import Path

    server_src = (Path(__file__).resolve().parents[2] / "server.py").read_text()
    assert 'grid["charm_grid"]' in server_src, (
        "server.py does not attach grid.charm_grid, so the Charm tab stays empty"
    )
    assert 'grid["charm_meta"]' in server_src, "charm must carry its own status/meta"
