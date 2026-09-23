"""Solstice foundation regression (T00–T03, T27 fixtures)."""

import sys
sys.path.insert(0, "backend")

from domain.exposure_metrics import (
    abs_delta,
    compute_delta_weighted_oi,
    compute_raw_oi,
    decimal_strike,
)


def test_gamma_source_reconciliation_vendor_changes_output():
    from services.gex_core import compute_gex_grid_vendor, compute_gex_by_strike_vendor
    spot = 100.0
    base = {"strike": 100.0, "type": "call", "oi": 1000, "expiry": "2026-09-23"}
    c1 = dict(base, gamma=0.01)
    c2 = dict(base, gamma=0.99)
    g1 = compute_gex_grid_vendor(spot, [c1])
    g2 = compute_gex_grid_vendor(spot, [c2])
    assert abs(list(g1["grid"]["2026-09-23"].values())[0] - 100000.0) < 1.0
    assert abs(list(g2["grid"]["2026-09-23"].values())[0] - 9900000.0) < 1.0
    assert g1["grid"] != g2["grid"]
    r1 = compute_gex_by_strike_vendor(spot, [c1])
    r2 = compute_gex_by_strike_vendor(spot, [c2])
    assert r1[0]["gex"] != r2[0]["gex"]


def test_delta_ranking_weighting_arithmetic():
    spot, m = 500.0, 100.0
    a = {"strike": 500, "type": "call", "gamma": 0.05, "oi": 10000, "delta": 0.45, "multiplier": m}
    b = {"strike": 500, "type": "call", "gamma": 0.01, "oi": 50000, "delta": 0.10, "multiplier": m}
    raw = compute_raw_oi([a, b], spot)
    w = compute_delta_weighted_oi([a, b], spot)
    # raw: both 125M each side of the unit scale
    assert abs(a["gamma"] * m * spot * spot * 0.01 * a["oi"] - 125_000_000) < 1.0
    assert abs(w.gross - (56_250_000 + 12_500_000)) < 1.0


def test_put_sign_trap_abs_before_sign():
    spot, m = 100.0, 100.0
    contracts = [
        {"strike": 100, "type": "call", "gamma": 0.10, "oi": 1000, "delta": 0.5, "multiplier": m},
        {"strike": 100, "type": "put", "gamma": 0.10, "oi": 1000, "delta": -0.5, "multiplier": m},
    ]
    w = compute_delta_weighted_oi(contracts, spot)
    assert abs(w.call - 500_000) < 1.0
    assert abs(w.put - 500_000) < 1.0  # gross-side magnitude
    assert abs(w.net - 0.0) < 1.0  # call-minus-put cancels; naive double-sign would give +1M


def test_same_coverage_invariants():
    spot, m = 100.0, 100.0
    contracts = [
        {"strike": 100, "type": "call", "gamma": 0.05, "oi": 100, "delta": 0.6, "multiplier": m},
        {"strike": 100, "type": "put", "gamma": 0.05, "oi": 100, "delta": -0.4, "multiplier": m},
    ]
    raw = compute_raw_oi(contracts, spot)
    w = compute_delta_weighted_oi(contracts, spot)
    assert abs(raw.net) <= raw.gross + 1e-6
    assert abs(w.net) <= w.gross + 1e-6
    assert w.gross <= raw.gross + 1e-6


def test_missing_delta_unavailable_not_zero():
    spot = 100.0
    contracts = [{"strike": 100, "type": "call", "gamma": 0.05, "oi": 100, "multiplier": 100}]
    w = compute_delta_weighted_oi(contracts, spot)
    assert w.usable == 0 and w.missing_delta == 1 and w.gross == 0.0


def test_abs_delta_bounds():
    v, r = abs_delta(1.0000000001)
    assert v == 1.0 and r == "DELTA_ROUNDED"
    v2, r2 = abs_delta(1.5)
    assert v2 is None and r2 == "DELTA_OUT_OF_RANGE"


def test_decimal_strike_identity():
    assert str(decimal_strike("500.5")) == "500.5"
    assert decimal_strike(None) is None
    assert decimal_strike(-1) is None


def test_exact_clock_0dte_not_one_day():
    from datetime import UTC, datetime
    from services.solstice_time import time_to_expiry_years
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    # 10:00 ET on expiry day → ~6h remaining, not 1.0/365 full day
    now = datetime(2026, 9, 23, 10, 0, tzinfo=et)
    t, floored, reason = time_to_expiry_years("2026-09-23", now=now, ticker="SPY")
    assert t is not None and reason is None
    assert abs(t - (6 / 24) / 365) < 0.5 / 24 / 365 + 1e-9
    assert t < 1.0 / 365  # proves the old max(days,1)/365 floor is gone


def test_exact_clock_expired_is_none():
    from datetime import UTC, datetime
    from services.solstice_time import time_to_expiry_years
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")
    now = datetime(2026, 9, 24, 10, 0, tzinfo=et)
    t, _, reason = time_to_expiry_years("2026-09-23", now=now, ticker="SPY")
    assert t is None and reason == "EXPIRED"


def test_timestamps_preserved_not_fabricated():
    from services.public_api import PublicBroker
    pb = PublicBroker.__new__(PublicBroker)
    oc = pb._parse_option_contract(
        {"symbol": "SPY260923C00500000"},
        {"bid": 1.0, "ask": 1.2, "last": 1.1, "bidTimestamp": "2026-09-23T14:00:00Z",
         "askTimestamp": "2026-09-23T14:00:01Z", "lastTimestamp": "2026-09-23T13:59:00Z",
         "volume": 10, "openInterest": 100,
         "optionDetails": {"greeks": {"delta": 0.5, "gamma": 0.02, "impliedVolatility": 0.2}}},
    )
    assert oc.bid_timestamp == "2026-09-23T14:00:00Z"
    assert oc.ask_timestamp == "2026-09-23T14:00:01Z"
    assert oc.last_timestamp == "2026-09-23T13:59:00Z"
    oc2 = pb._parse_option_contract({"symbol": "SPY260923C00500000"}, {"bid": 1.0, "ask": 1.2})
    assert oc2.bid_timestamp is None  # unknown stays null, never now()


def test_instrument_resolver_spx():
    from services.public_api import resolve_public_instrument_type
    assert resolve_public_instrument_type("SPX", "chain") == "UNDERLYING_SECURITY_FOR_INDEX_OPTION"
    assert resolve_public_instrument_type("SPX", "quote") == "INDEX"
    assert resolve_public_instrument_type("SPY", "chain") == "EQUITY"


def test_cancel_is_delete_tolerant_empty():
    import inspect
    from services import public_api
    src = inspect.getsource(public_api.PublicBroker.cancel_order)
    assert ".delete(" in src and "CANCEL_PENDING" in src


def test_multileg_uses_type_not_ordertype():
    import inspect
    from services import public_api
    src = inspect.getsource(public_api.PublicBroker.place_multileg_order)
    assert '"type": order_type' in src
    assert '"orderType": order_type' not in src


def test_unknown_history_is_unknown():
    from services.heatseeker import calc_node_lifecycle, calc_velocity_mode
    contracts = [{"strike": 100, "type": "call", "gamma": 0.02, "open_interest": 500}]
    lc = calc_node_lifecycle(100.0, contracts, [])
    assert lc["history_status"] == "unknown"
    assert all(n["state"] == "unknown" and n["tap_probability"] is None for n in lc["nodes"])
    vm = calc_velocity_mode([])
    assert vm["mode"] == "unknown" and vm["velocity_strikes_per_min"] is None
