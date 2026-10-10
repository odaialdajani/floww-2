"""B02 historical grids, recorder health, capability census. Synthetic only."""
import pytest


def test_parse_archived_gex_vanna():
    from services.chart_exposure import parse_grid

    gex = {"metric": "gex", "unit": "S2", "basis": "gex.v2", "model": "gex.v2",
           "values": [{"strike": 100, "signed_value": -50}, {"strike": 105, "signed_value": 30}]}
    assert parse_grid(gex)["status"] == "available"
    vanna = {"metric": "vex", "unit": "USD-per-volpt", "basis": "local-bs-vanna.v1",
             "model": "VEX_1VOLPT", "values": [{"strike": 100, "signed_value": 5}]}
    assert parse_grid(vanna)["status"] == "available"
    # Legacy VOMMA surface rejected for VANNA view.
    legacy = {"metric": "vex", "unit": "S1", "basis": "gex.v2", "model": "vex_surface",
              "values": [{"strike": 100, "signed_value": 5}]}
    assert parse_grid(legacy)["status"] == "unavailable"
    # Missing schemas/expiries stay unknown, never zero.
    assert parse_grid({})["status"] == "unknown"
    assert parse_grid({"metric": "gex"})["status"] == "unknown"


def test_newer_malformed_supersedes_without_carry():
    from services.chart_exposure import select_display

    old = {"asof": 100, "scope": "front", "grid": {"status": "available", "values": [1]}}
    bad = {"asof": 110, "scope": "front", "grid": {"status": "malformed"}}
    out = select_display([old, bad])
    assert out["status"] in ("degraded", "unavailable")
    assert out.get("values", None) is None


def test_capability_census():
    from services.chart_capabilities import census

    out = census(["C137", "C001"], {"C137": "supported", "C001": "degraded"})
    assert out["total"] == 2
    assert out["by_status"]["supported"] == 1
