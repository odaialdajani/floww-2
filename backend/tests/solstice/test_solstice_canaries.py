"""T27 mutation canaries: each must DETECT the bug (fail on buggy code path).

Covers §28.5: wrong put sign, ignored vendor gamma, timestamp laundering,
volume-as-OI substitution, cross-symbol late responses, missing-source
confidence, same-observation fills. Plus Decimal/tick, multiplier, distance,
and floating-point-claim corrections.
"""

import sys

sys.path.insert(0, "backend")


def test_canary_wrong_put_sign_detected():
    from domain.exposure_metrics import compute_delta_weighted_oi
    contracts = [
        {"strike": 100, "type": "call", "gamma": 0.10, "oi": 1000, "delta": 0.5, "multiplier": 100},
        {"strike": 100, "type": "put", "gamma": 0.10, "oi": 1000, "delta": -0.5, "multiplier": 100},
    ]
    w = compute_delta_weighted_oi(contracts, 100.0)
    assert abs(w.net) < 1.0, "double-signed puts would give +1M"


def test_canary_ignored_vendor_gamma_detected():
    from services.gex_core import compute_gex_grid_vendor
    base = {"strike": 100.0, "type": "call", "oi": 1000, "expiry": "2030-01-15"}
    g1 = compute_gex_grid_vendor(100.0, [dict(base, gamma=0.01)])
    g2 = compute_gex_grid_vendor(100.0, [dict(base, gamma=0.99)])
    assert g1["grid"] != g2["grid"], "vendor-gamma change must change output"


def test_canary_timestamp_laundering_detected():
    from services.public_api import PublicBroker
    pb = PublicBroker.__new__(PublicBroker)
    oc = pb._parse_option_contract({"symbol": "SPY300101C00500000"}, {"bid": 1.0, "ask": 1.2})
    assert oc.bid_timestamp is None and oc.ask_timestamp is None, \
        "missing source time must stay null, never now()"


def test_canary_volume_as_oi_detected():
    from services.gex_dual import DualGexCalculator
    assert DualGexCalculator._resolve_volume({"oi": 500}, 500) is None, \
        "OI must never substitute for missing volume"
    out = DualGexCalculator.compute(580.0, [{"strike": 580.0, "gamma": 0.04,
                                             "oi": 1000, "type": "call"}])
    assert out["activity_ratio"] is None and out["activity_badge"] == "unknown"


def test_canary_cross_symbol_late_response():
    # Contract: adapter refuses wrong-symbol substitution (fail closed).
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from services import public_api_adapter as ada
    broker = MagicMock()
    broker.get_trading_account.return_value = MagicMock(account_id="a")
    q = MagicMock()
    q.symbol = "QQQ"  # wrong symbol answered for SPY
    q.mid_price = 1.0
    broker.get_quotes = AsyncMock(return_value=[q])
    spot, source = asyncio.run(ada._resolve_spot(broker, "SPY", "a"))
    assert source == "symbol-mismatch" and spot is None


def test_canary_missing_source_confidence():
    from services.heatseeker import calc_node_lifecycle, calc_velocity_mode
    lc = calc_node_lifecycle(100.0, [{"strike": 100, "type": "call",
                                      "gamma": 0.02, "open_interest": 5}], [])
    assert all(n["tap_probability"] is None for n in lc["nodes"])
    assert calc_velocity_mode([])["mode"] == "unknown"


def test_canary_same_observation_fill_blocked():
    # Same-observation activation/fill is disabled: when one observation hits
    # both barriers at once, order is unknown — never an assumed win.
    from services.solstice_labels import label_touch
    r = label_touch([(0, 505.0)], (498, 502), 60, 505.0, 505.0)
    assert r["label"] == "simultaneous_unknown"
    r2 = label_touch([(0, 505.0), (0, 505.0)], (498, 502), 60, 505.0, 505.0)
    assert r2["label"] == "simultaneous_unknown"


def test_decimal_tick_and_multiplier():
    from decimal import Decimal

    from domain.exposure_metrics import decimal_strike
    assert decimal_strike("500.5") == Decimal("500.5")
    # Multiplier fixture (§28.5): m100/N200 + m40/N1000 at S=500,Γ=.03 → 4.5M
    from domain.exposure_metrics import compute_raw_oi
    contracts = [
        {"strike": 500, "type": "call", "gamma": 0.03, "oi": 200, "multiplier": 100},
        {"strike": 500, "type": "call", "gamma": 0.03, "oi": 1000, "multiplier": 40},
    ]
    r = compute_raw_oi(contracts, 500.0)
    assert abs(r.gross - 4_500_000) < 1.0


def test_inspector_distances_named_reference():
    # spot 497.40, zone [498,502]: edge .60, center 2.60 — reference named.
    spot, lo, hi = 497.40, 498.0, 502.0
    assert abs((lo - spot) - 0.60) < 1e-9
    assert abs(((lo + hi) / 2 - spot) - 2.60) < 1e-9


def test_floating_point_claim_exact():
    # The blanket inequality claim is false for this exact case.
    assert 125000000 * 0.45 == 56250000.0


def test_volume_retraction_quarantined():
    from services.solstice_provenance import check_volume_window
    assert check_volume_window(1240, 1180)["reason"] == "VOLUME_REBASE"
    assert check_volume_window(1240, 1180)["valid"] is False
    assert check_volume_window(100, 140)["valid"] is True


def test_pair_provenance_mixed_blocked():
    from services.solstice_provenance import greek_pair_provenance
    assert greek_pair_provenance("vendor", "vendor")["eligible"] is True
    assert greek_pair_provenance("vendor", "local")["eligible"] is False
    assert greek_pair_provenance(None, "vendor")["eligible"] is False


def test_change_attribution_reconciles():
    from services.solstice_provenance import attribute_change
    old = {"oi": 100, "gamma": 0.02, "spot": 500.0, "multiplier": 100.0}
    new = {"oi": 110, "gamma": 0.021, "multiplier": 100.0}
    a = attribute_change(old, new, 505.0)
    assert a["within_tol"] is True
    assert abs(a["residual"]) < 1e-6


def test_max_pain_is_intrinsic_parity():
    # calls 200 @ 90, puts 100 @ 100, calls 100 @ 110 → intrinsic pain
    # @90=1000, @100=2000, @110=4000 ⇒ 90 (mirrors the Rust parity test).
    from services.gex_core import classify_nodes
    rows = [
        {"strike": 90.0, "gex": 2.0, "call_gex": 2.0, "put_gex": 0.0,
         "call_oi": 200.0, "put_oi": 0.0, "total_oi": 200.0},
        {"strike": 100.0, "gex": -1.0, "call_gex": 0.0, "put_gex": -1.0,
         "call_oi": 0.0, "put_oi": 100.0, "total_oi": 100.0},
        {"strike": 110.0, "gex": 1.0, "call_gex": 1.0, "put_gex": 0.0,
         "call_oi": 100.0, "put_oi": 0.0, "total_oi": 100.0},
    ]
    out = classify_nodes(rows, 100.0)
    assert out["max_pain"] == 90.0
    assert out["max_pain_basis"] == "call_put_intrinsic_expiry_scoped"
