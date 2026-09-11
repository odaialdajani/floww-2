"""Signal-truth regressions (agent-2 PR47 follow-up).

RED on main @ 56cfff2:
1. calc_charm_integral vec path matches contract type with exact
   == "call" / == "put". A non-lowercase type ("CALL", "Call", None)
   matches neither pass, contributes 0.0, yet is marked vec-done so the
   scalar fallback never runs. Silent zero.
2. liquidity_state.feed pushes cumulative chain volumes as one interval
   observation. Kyle x becomes the cumulative share (near-constant) and
   Amihud DV becomes cumulative dollar-volume (grows all day), so both
   estimators drift regardless of actual interval flow.
"""
import math

import pytest


def _contract(**over):
    base = {"strike": 100.0, "T": 0.25, "iv": 0.25, "oi": 100.0,
            "type": "call", "volume": 10.0, "expiry": "2026-09-18"}
    base.update(over)
    return base


def test_charm_uppercase_type_matches_lowercase():
    import advanced_analytics as aa_mod

    lower = [_contract(type="call"), _contract(type="put", strike=110.0)]
    upper = [_contract(type="CALL"), _contract(type="PUT", strike=110.0)]
    lo = aa_mod.calc_charm_integral(100.0, lower, "SPY")
    hi = aa_mod.calc_charm_integral(100.0, upper, "SPY")
    assert lo["total_charm_to_close"] == pytest.approx(
        hi["total_charm_to_close"], rel=1e-9, abs=1e-9), (
        lo["total_charm_to_close"], hi["total_charm_to_close"])


def test_charm_unknown_type_falls_back_to_scalar(monkeypatch):
    """Unknown types must take the legacy scalar path, not silent zero."""
    import advanced_analytics as aa_mod

    contracts = [_contract(type="weird")]
    with_vec = aa_mod.calc_charm_integral(100.0, contracts, "SPY")
    monkeypatch.setattr(aa_mod, "bs_charm_vec", None)
    scalar_only = aa_mod.calc_charm_integral(100.0, contracts, "SPY")
    assert with_vec["total_charm_to_close"] == pytest.approx(
        scalar_only["total_charm_to_close"], rel=1e-9, abs=1e-9), (
        with_vec["total_charm_to_close"],
        scalar_only["total_charm_to_close"])
    assert math.isfinite(with_vec["total_charm_to_close"])


def test_liquidity_feed_uses_interval_flow():
    from services import liquidity_state

    liquidity_state.reset()
    sym = "SIGTRUTH"
    # feed 1 seeds the cumulative baseline (no push — no interval yet);
    # feed 2 pushes the first diff but the estimators skip obs on their own
    # first push (no last spot); feed 3 yields the first real observation.
    liquidity_state.feed(sym, 100.0, 100.0, 100.0)
    liquidity_state.feed(sym, 150.0, 100.0, 101.0)
    liquidity_state.feed(sym, 200.0, 100.0, 102.0)
    kyle = liquidity_state._regime[sym]["kyle"]
    # Interval flow: call +50, put +0 -> directional share x = +1.0.
    # Cumulative (buggy): (200-100)/300 = 1/3.
    assert kyle._obs[-1][0] == pytest.approx(1.0), kyle._obs[-1]


def test_liquidity_feed_interval_dollar_volume():
    from services import liquidity_state

    liquidity_state.reset()
    sym = "SIGTRUTH_DV"
    liquidity_state.feed(sym, 100.0, 100.0, 100.0)
    liquidity_state.feed(sym, 150.0, 100.0, 101.0)
    liquidity_state.feed(sym, 200.0, 100.0, 102.0)
    amihud = liquidity_state._regime[sym]["amihud"]
    # Interval DV = (50 + 0) * 102. Cumulative (buggy): 300 * 102.
    assert amihud._obs[-1][2] == pytest.approx(50.0 * 102.0), amihud._obs[-1]
