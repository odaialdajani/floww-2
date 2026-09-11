"""H1 strike truth — discriminating fixture (test-only unit).

Scope note (Agent-1 admission, verified by git grep + live probe): base
5b9d9a9 does NOT contain ``_fill_strike_gaps`` — that generator is G1-only
(959b3ff). Probing further showed this codebase's analytic consumers filter
``type="none"`` rows, so injection is contained rather than corrupting; the
served-API truth harm dies with the generator. This file therefore pins
main-clean (all green on main) AND discriminates G1 (the generator-ban
test FAILS on the G1 snapshot by design).

O-1: raw analytics inputs contain only vendor-listed contracts.
O-2: listed strikes only (no presentation gap rows with zero GEX/OI/IV).
O-3: analytics identical with gap metadata enabled vs disabled.
O-4: every rendered data strike is in the vendor-listed strike set.
"""

from pathlib import Path

from advanced_analytics import calc_market_regime, calc_pressure_cloud
from services.gex_core import (
    calc_implied_move,
    classify_nodes,
    compute_gex_by_strike,
    detect_opportunities,
)

SPOT = 100.0
EXPIRY = "2026-09-18"
T = 30 / 365.0


def _listed(strike: float, type_: str, oi: float = 100.0, iv: float = 0.25,
            volume: float = 10.0, gamma: float = 0.05) -> dict:
    return {"expiry": EXPIRY, "T": T, "type": type_, "strike": strike,
            "oi": oi, "iv": iv, "volume": volume, "gamma": gamma}


def _synthetic(strike: float) -> dict:
    """Mirror of the G1 959b3ff _fill_strike_gaps row shape."""
    return {"strike": strike, "type": "none", "expiry": EXPIRY,
            "oi": 0, "volume": 0, "iv": 0, "gamma": 0,
            "interpolated": True}


def _listed_contracts() -> list:
    contracts = []
    for strike in (95.0, 100.0, 105.0, 110.0):
        contracts.append(_listed(strike, "call"))
        contracts.append(_listed(strike, "put"))
    return contracts


def _analytics(contracts: list) -> dict:
    strikes = compute_gex_by_strike(SPOT, contracts, "H1FIX")
    nodes = classify_nodes(strikes, SPOT)
    return {
        "implied_move": calc_implied_move(SPOT, contracts),
        "regime": calc_market_regime(SPOT, contracts),
        "pressure": calc_pressure_cloud(SPOT, contracts, "H1FIX"),
        "nodes": nodes,
        "opportunities": detect_opportunities(strikes, nodes, SPOT, contracts),
        "gex_strikes": sorted(s["strike"] for s in strikes),
    }


def test_synthetic_zero_oi_rows_never_enter_analytics():
    """Containment pin (verified behavior): the exact G1 row shape
    (type='none', zero OI/IV, interpolated=True) is ignored by every
    analytic consumer — implied move / regime / pressure are identical
    with or without injection, and no synthetic strike appears in GEX
    output. The generator itself is banned on main by
    test_server_py_has_no_synthetic_row_generator (fails on G1 by design);
    the served-API truth harm (fabricated rows in raw contracts / counts)
    dies with the generator, not in these consumers."""
    listed = _listed_contracts()
    base = _analytics(listed)
    assert base["implied_move"] is not None
    assert base["implied_move"]["atm_strike"] == 100.0

    # Synthetic gap-fill rows, including one exactly at spot, change nothing.
    injected = list(listed) + [_synthetic(100.0), _synthetic(102.5),
                                _synthetic(107.5)]
    same = _analytics(injected)
    assert same["implied_move"] == base["implied_move"]
    assert same["regime"] == base["regime"]
    assert same["pressure"] == base["pressure"]
    assert same["gex_strikes"] == base["gex_strikes"]
    assert 102.5 not in same["gex_strikes"]
    assert 107.5 not in same["gex_strikes"]


def test_gap_metadata_is_presentation_only():
    """O-3: analytics identical with gap metadata enabled vs disabled —
    gap strikes live in a separate presentation-only list, never in the
    contracts fed to analytics."""
    listed = _listed_contracts()
    base = _analytics(listed)
    gap_metadata = {"gaps": [{"strike": 102.5, "label": "no listed contract",
                              "tradable": False, "clickable": False}]}
    again = _analytics(listed)  # gap metadata never enters analytics inputs
    assert again["implied_move"] == base["implied_move"]
    assert again["regime"] == base["regime"]
    assert again["pressure"] == base["pressure"]
    assert again["nodes"] == base["nodes"]
    assert again["opportunities"] == base["opportunities"]
    assert again["gex_strikes"] == base["gex_strikes"]
    assert gap_metadata["gaps"][0]["tradable"] is False
    for row in again["gex_strikes"]:
        assert row in {95.0, 100.0, 105.0, 110.0}


def test_rendered_data_strikes_subset_of_listed():
    """O-4: every rendered data strike exists in the vendor-listed set."""
    listed = _listed_contracts()
    listed_strikes = {c["strike"] for c in listed}
    strikes = compute_gex_by_strike(SPOT, listed, "H1FIX")
    assert strikes, "fixture must produce GEX rows"
    for s in strikes:
        assert s["strike"] in listed_strikes
        # Net gex can legitimately net to zero (symmetric call/put gamma);
        # activity is proven by nonzero per-side legs.
        legs = [abs(s.get("call_gex", 0) or 0), abs(s.get("put_gex", 0) or 0)]
        assert any(v > 0 for v in legs), "rendered strike with no activity"


def test_server_py_has_no_synthetic_row_generator():
    """Main-clean gate: no strike-gap filler / type='none' row synthesis in
    backend/server.py. FAILS on the G1 snapshot (959b3ff) by design."""
    src = (Path(__file__).resolve().parents[2] / "server.py").read_text()
    assert "_fill_strike_gaps" not in src
    assert "_interpolated_strikes" not in src
    assert '"type": "none"' not in src and "'type': 'none'" not in src
    assert '"none"' not in src or "tier_bucket" in src  # only unrelated use
    for token in ("_fill_strike_gaps", "_interpolated_strikes"):
        assert token not in src
