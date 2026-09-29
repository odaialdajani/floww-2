"""Resweep part 3: population reporting and weight validation.

H7 - the raw and session-volume surfaces reported NO population, so a
     consumer could not distinguish a measured 0.0 from an unavailable one
     (spot missing / 0 / NaN makes every contract invalid and every gross
     0.0). The delta surfaces already reported theirs.
H8 - fuse_one merged a caller weight override blindly: a string weight
     raised a TypeError from inside the arithmetic, a negative weight
     could push the score outside [0, 100], and an override not summing
     to 1 silently rescaled every score while still looking like a 0-100
     number.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.exposure_metrics import (  # noqa: E402
    compute_delta_weighted_oi,
    compute_raw_oi,
    compute_session_delta_volume_gamma,
    compute_volume_gamma,
)
from services.solstice_rank import WEIGHTS, fuse_one, norm_flow_strict  # noqa: E402

SPOT = 100.0
ONE = [{"type": "call", "strike": 100, "gamma": 0.01, "oi": 1000,
        "delta": 0.5, "volume": 100, "multiplier": 100}]


# ---- H7: an unavailable surface must not read as a measured zero ----

@pytest.mark.parametrize("spot", [0, -1, float("nan"), None, True, "x"])
def test_every_surface_reports_why_it_is_zero(spot):
    for name, fn in (
        ("raw", compute_raw_oi),
        ("delta", compute_delta_weighted_oi),
        ("volume", compute_volume_gamma),
        ("session_delta_volume", compute_session_delta_volume_gamma),
    ):
        r = fn(ONE, spot)
        assert r.usable == 0, name
        # The 0.0 gross is only honest because the population says why.
        assert r.invalid >= 1, f"{name} did not report an invalid population"
        assert r.gross == 0.0


def test_the_server_exposes_a_population_for_every_value_it_publishes():
    """A published number with no population beside it is unreadable."""
    src = Path(__file__).resolve().parents[2] / "server.py"
    text = src.read_text(encoding="utf-8")
    for value_key, population_key in (
        ("gex_gross_v1", "raw_usable"),
        ("gex_net_v1", "raw_invalid"),
        ("volume_gamma_gross", "volume_gamma_usable"),
        ("dadgex_gross_v1", "dadgex_usable"),
        ("session_delta_volume_gross_v1", "session_delta_volume_usable"),
    ):
        assert f'"{value_key}"' in text, value_key
        assert f'"{population_key}"' in text, (
            f"{value_key} is published with no {population_key} beside it"
        )


# ---- H8: a weight vector is a caller contract, not a measurement ----

@pytest.mark.parametrize("bad", [
    {"flow": "x"},
    {"flow": -1},
    {"flow": float("nan")},
    {"flow": float("inf")},
    {"flow": True},
    {"flow": None},
    {"nope": 1.0},
    {"flow": 0.0, "opportunity": 0.0, "confluence": 0.0, "ml": 0.0},
])
def test_bad_weight_overrides_are_rejected_not_swallowed(bad):
    with pytest.raises(ValueError):
        fuse_one("SPY", flow={"conviction": 90}, weights=bad)


def test_a_non_unit_weight_vector_is_normalized_and_says_so():
    r = fuse_one("SPY", flow={"conviction": 100}, opportunity={"opportunity_score": 10},
                 weights={"flow": 2.0, "opportunity": 2.0, "confluence": 0.0, "ml": 0.0})
    ev = r["evidence"]
    assert ev["weights_normalized"] is True
    assert ev["weights"] == {"flow": 0.5, "opportunity": 0.5, "confluence": 0.0, "ml": 0.0}
    assert r["conviction"] == 100.0
    assert 0.0 <= r["conviction"] <= 100.0


def test_a_unit_weight_vector_is_not_flagged_as_normalized():
    r = fuse_one("SPY", flow={"conviction": 90}, opportunity={"opportunity_score": 8})
    assert r["evidence"]["weights_normalized"] is False
    assert r["evidence"]["weights"] == WEIGHTS
    assert r["conviction"] == 55.5


def test_weights_cannot_push_a_score_outside_the_reported_range():
    # Even with an extreme-but-legal override, the published score stays in
    # [0, 100] because a non-unit vector is normalized.
    for override in ({"flow": 1000.0}, {"flow": 0.0, "opportunity": 0.0,
                                          "confluence": 0.0, "ml": 0.0}):
        try:
            r = fuse_one("SPY", flow={"conviction": 100}, opportunity={"opportunity_score": 10},
                         weights=override)
        except ValueError:
            continue
        assert 0.0 <= r["conviction"] <= 100.0, override


def test_missing_is_still_absent_after_all_of_this():
    assert norm_flow_strict(None) == (0.0, "missing")
    assert norm_flow_strict({"conviction": 0}) == (0.0, "ok")
