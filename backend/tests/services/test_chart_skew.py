"""Skew per expiry: |GEX| below vs above spot (GammaGrid convention).

RED first: module does not exist. Pure function over live chain contracts
(same cost class as the heatmap refresh it rides with) — no recording, no
new spend class. Skew = larger side / smaller side; one-sided expiries and
empty input give null/empty, never a fabricated ratio.
"""
import math

import pytest

from bs_greeks import bs_gamma
from services.chart_skew import skew_by_expiry

SPOT = 100.0


def gex_of(kind, strike, oi, iv=0.3, T=0.1):
    g = bs_gamma(SPOT, strike, T, iv)
    signed = g if kind == "call" else -g
    return signed * oi * 100.0 * SPOT**2 * 0.01


def test_two_expiries_bucketed_with_ratio():
    contracts = [
        {"expiry": "2026-10-17", "type": "call", "strike": 90, "oi": 100, "iv": 0.3, "T": 0.1},
        {"expiry": "2026-10-17", "type": "put", "strike": 110, "oi": 100, "iv": 0.3, "T": 0.1},
        {"expiry": "2026-10-24", "type": "call", "strike": 95, "oi": 50, "iv": 0.3, "T": 0.12},
    ]
    out = skew_by_expiry(contracts, SPOT)
    oct17 = out["by_expiry"]["2026-10-17"]
    assert oct17["below"] == pytest.approx(abs(gex_of("call", 90, 100)))
    assert oct17["above"] == pytest.approx(abs(gex_of("put", 110, 100)))
    assert oct17["skew"] == pytest.approx(max(oct17["below"], oct17["above"])
                                          / min(oct17["below"], oct17["above"]))
    assert oct17["skew"] >= 1.0
    assert out["by_expiry"]["2026-10-24"]["n"] == 1


def test_one_sided_expiry_skew_unknown():
    contracts = [
        {"expiry": "2026-10-17", "type": "call", "strike": 90, "oi": 100, "iv": 0.3, "T": 0.1},
    ]
    (row,) = list(skew_by_expiry(contracts, SPOT)["by_expiry"].values())
    assert row["below"] > 0
    assert row["above"] == 0.0
    assert row["skew"] is None  # no ratio from a single side


def test_at_the_money_tracked_apart_from_sides():
    contracts = [
        {"expiry": "2026-10-17", "type": "call", "strike": 100, "oi": 100, "iv": 0.3, "T": 0.1},
    ]
    (row,) = list(skew_by_expiry(contracts, SPOT)["by_expiry"].values())
    assert row["at"] == pytest.approx(abs(gex_of("call", 100, 100)))
    assert row["below"] == 0.0 and row["above"] == 0.0
    assert row["skew"] is None


def test_put_below_spot_counts_to_below_side():
    contracts = [
        {"expiry": "2026-10-17", "type": "put", "strike": 90, "oi": 100, "iv": 0.3, "T": 0.1},
        {"expiry": "2026-10-17", "type": "call", "strike": 110, "oi": 100, "iv": 0.3, "T": 0.1},
    ]
    (row,) = list(skew_by_expiry(contracts, SPOT)["by_expiry"].values())
    # Sides are absolute exposure (GammaGrid), not signed sums that cancel.
    assert row["below"] == pytest.approx(abs(gex_of("put", 90, 100)))
    assert row["above"] == pytest.approx(abs(gex_of("call", 110, 100)))


def test_empty_and_invalid_contracts_stay_empty():
    out = skew_by_expiry([], SPOT)
    assert out["by_expiry"] == {}
    out = skew_by_expiry(
        [{"expiry": "2026-10-17", "type": "call", "strike": -5, "oi": 100, "iv": 0.3, "T": 0.1},
         {"expiry": "2026-10-17", "type": "call", "strike": 90, "oi": 0, "iv": 0.3, "T": 0.1},
         {"expiry": "", "type": "call", "strike": 90, "oi": 100, "iv": 0.3, "T": 0.1},
         None, "junk"], SPOT)
    assert out["by_expiry"] == {}
    assert out["version"] == "skew-expiry.v1"


def test_sides_sum_to_total_absolute_gex():
    contracts = [
        {"expiry": "2026-10-17", "type": "call", "strike": 90, "oi": 100, "iv": 0.3, "T": 0.1},
        {"expiry": "2026-10-17", "type": "put", "strike": 110, "oi": 50, "iv": 0.4, "T": 0.2},
        {"expiry": "2026-10-17", "type": "call", "strike": 100, "oi": 10, "iv": 0.3, "T": 0.1},
    ]
    (row,) = list(skew_by_expiry(contracts, SPOT)["by_expiry"].values())
    total = sum(abs(gex_of(c["type"], c["strike"], c["oi"], c["iv"], c["T"])) for c in contracts)
    assert row["below"] + row["above"] + row["at"] == pytest.approx(total)
    assert math.isfinite(row["below"]) and math.isfinite(row["above"])
