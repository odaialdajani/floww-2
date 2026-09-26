"""Scalers for BS Greek unit conventions.

Pins the formulas in ``backend/domain/greek_scalers.py`` so a future
refactor cannot silently shift Charm Flip / GDW / CAR metrics by 100×.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ────────────────────────────────────────────────────────────────────
# Constants
# ────────────────────────────────────────────────────────────────────

CONTRACT_MULTIPLIER: float = 100.0
DOLLAR_MOVE_CONVENTION: float = 0.01
TRADING_DAYS_PER_YEAR: float = 252.0


# ────────────────────────────────────────────────────────────────────
# Class 1 — Identity / aliasing
# ────────────────────────────────────────────────────────────────────

class TestVexAliasIdentity:
    """``dollar_vex_per_1pct_spot_move`` is a name-aliased re-export of
    ``bs_greeks.dollar_vex_per_contract``. The two MUST be numerically
    identical so ``routes/analytics.py`` and ``advanced_analytics.py``
    get exactly the same vanna per strike.
    """

    def test_dollar_vex_per_1pct_spot_move_matches_dollar_vex_per_contract(
        self,
    ) -> None:
        from bs_greeks import dollar_vex_per_contract
        from domain.greek_scalers import dollar_vex_per_1pct_spot_move

        for vanna, oi, spot in [
            (0.05, 100, 580.0),    # SPY at $580, ATM-like vanna
            (-0.03, 250, 450.0),   # puts
            (0.001, 1, 100.0),     # tiny
            (-0.5, 10000, 580.0),  # large
        ]:
            scaler = dollar_vex_per_1pct_spot_move(vanna, oi, spot)
            canonical = dollar_vex_per_contract(vanna, oi, spot)
            assert scaler == pytest.approx(canonical, abs=1e-12)
            expected_direct = (
                vanna * oi * CONTRACT_MULTIPLIER * spot * DOLLAR_MOVE_CONVENTION
            )
            assert scaler == pytest.approx(expected_direct, abs=1e-9)


# ────────────────────────────────────────────────────────────────────
# Class 2 — Per-unit-σ scaling (NOT for trading-floor display)
# ────────────────────────────────────────────────────────────────────

class TestVexPerUnitSigma:
    """Per-unit-σ version: missing the 0.01 factor by design. Useful when
    a downstream metric will further divide by 100.
    """

    def test_dollar_vex_per_unit_sigma_omits_dollar_move_convention(
        self,
    ) -> None:
        from domain.greek_scalers import dollar_vex_per_unit_sigma

        vanna, oi, spot = 0.05, 100, 580.0
        got = dollar_vex_per_unit_sigma(vanna, oi, spot)
        expected = vanna * oi * CONTRACT_MULTIPLIER * spot
        assert got == pytest.approx(expected, abs=1e-9)
        # And MUST NOT have the 0.01 factor — should be 100× an
        # per-1%-spot-move value.
        per_1pct = vanna * oi * CONTRACT_MULTIPLIER * spot * DOLLAR_MOVE_CONVENTION
        assert got == pytest.approx(per_1pct * 100.0, abs=1e-9)


class TestDoVexPerVolChange:
    """Per-1%-σ (vol change, not spot change) version: used by Charm Flip
    / GDW / CAR when projecting a 1% rise in implied vol.
    """

    def test_dollar_vex_per_1pct_vol_change_uses_vol_point_convention(self):
        # R7-F03: the old test mirrored the implementation's (1 - 0.01)
        # factor — a tautology that pinned a 99x unit error. A +1 vol-point
        # shock is Δσ = 0.01 (same convention as the vega helper below).
        from domain.greek_scalers import dollar_vex_per_1pct_vol_change

        vanna, oi, spot = 0.05, 100, 580.0
        got = dollar_vex_per_1pct_vol_change(vanna, oi, spot)
        assert got == pytest.approx(vanna * oi * 100 * spot * 0.01, abs=1e-9)
        # Audit numbers: vanna .2, OI 100, spot 100 -> 2,000 (was 198,000).
        assert dollar_vex_per_1pct_vol_change(0.2, 100, 100.0) == pytest.approx(2000.0)


# ────────────────────────────────────────────────────────────────────
# Class 3 — Vega per 1%-σ display convention
# ────────────────────────────────────────────────────────────────────

class TestVegaPer1pctVolChange:
    """``dollar_vega_per_1pct_vol_change`` is the trading-floor display
    convention. Verified against ``bs_vega / 100 * OI * 100`` form.

    Hand-derived: vega_per_unit_sigma (raw ``bs_vega``) × OI ×
    CONTRACT_MULTIPLIER × DOLLAR_MOVE_CONVENTION.
    """

    def test_dollar_vega_per_1pct_vol_change_matches_direct(self):
        from domain.greek_scalers import dollar_vega_per_1pct_vol_change

        vega, oi = 0.40, 500  # SPY-like ATM vega
        got = dollar_vega_per_1pct_vol_change(vega, oi)
        expected = vega * oi * CONTRACT_MULTIPLIER * DOLLAR_MOVE_CONVENTION
        assert got == pytest.approx(expected, abs=1e-9)
        # Sanity: $200 per 1%-σ vol move (vega=0.40 × oi=500 × 100 × 0.01).
        assert got == pytest.approx(200.0, abs=1e-9)


# ────────────────────────────────────────────────────────────────────
# Class 4 — Charm per-day conversion
# ────────────────────────────────────────────────────────────────────

class TestCharmPerDay:
    """``bs_charm`` returns the second derivative ∂Δ/∂T per YEAR (T
    in years). To get per-trading-day charm: divide by 252.
    """

    def test_charm_per_day_divides_by_252(self):
        from domain.greek_scalers import charm_per_day

        # ATM 30-day call: typical charm ≈ -0.020 per year per contract.
        # Per day: -0.020 / 252 ≈ -7.94e-5.
        charm_annual = -0.020
        got = charm_per_day(charm_annual)
        assert got == pytest.approx(-0.020 / 252.0, abs=1e-12)

    def test_charm_per_day_zero_is_zero(self):
        from domain.greek_scalers import charm_per_day
        assert charm_per_day(0.0) == pytest.approx(0.0, abs=1e-12)

    def test_dollar_charm_per_day_matches_charm_per_day_times_dollar_charm(self):
        from bs_greeks import dollar_charm_per_contract
        from domain.greek_scalers import dollar_charm_per_day

        charm_annual, oi, spot = -0.05, 100, 580.0
        got = dollar_charm_per_day(charm_annual, oi, spot)
        canonical_per_year = dollar_charm_per_contract(
            charm_annual, oi, spot
        )
        # The per-day scaler is THE canonical per-year divided by 252.
        assert got == pytest.approx(canonical_per_year / 252.0, abs=1e-9)


# ────────────────────────────────────────────────────────────────────
# Class 5 — Route-handler end-to-end pin (analytics.py + advanced_analytics.py)
# ────────────────────────────────────────────────────────────────────

class TestRouteAndHelperConvergence:
    """The route ``vanna_exposure_endpoint`` and ``calc_vex`` BOTH now
    route through ``dollar_vex_per_1pct_spot_move``. This guarantees
    that downstream UI metrics and the advanced analytics they feed
    converge to the same number per strike.
    """

    def test_calc_vex_uses_canonical_scaler_for_synthetic_chain(self):
        """Drive ``calc_vex`` with a synthetic single-contract chain and
        verify the returned per-strike VEX matches the canonical
        platform-wide formula.
        """
        from advanced_analytics import calc_vex

        spot = 580.0
        strike = 580.0
        oi = 100
        # Hand-picked synthetic call: moderate vanna positive.
        contracts = [{
            "strike": strike, "T": 30 / 365.0, "iv": 0.20,
            "type": "CALL", "oi": oi,
        }]
        result = calc_vex(spot, contracts)
        # Should be exactly the dollar_charm equivalent × sign:
        # vega formula is gamma * OI * 100 * spot * 0.01.
        # For ATM 30-day call: vanna ≈ -phi(d1) * d2 / sigma.
        import math

        from scipy.stats import norm
        r = 0.045
        T = 30 / 365.0
        sigma = 0.20
        d1 = (math.log(spot / strike) + (r + 0.5 * sigma**2) * T) / (
            sigma * math.sqrt(T)
        )
        d2 = d1 - sigma * math.sqrt(T)
        vanna = -math.exp(0.0) * norm.pdf(d1) * d2 / sigma
        expected = vanna * oi * CONTRACT_MULTIPLIER * spot * DOLLAR_MOVE_CONVENTION
        # calc_vex rounds per-strike VEX to 2dp; allow ±0.005 for rounding.
        assert result["vex_by_strike"][float(strike)] == pytest.approx(
            round(expected, 2), abs=0.005
        )

    def test_calc_vex_total_vex_aggregates_per_strike(self):
        """The sum of per-strike VEX must equal total_vex (rounded).
        """
        from advanced_analytics import calc_vex
        spot = 580.0
        contracts = [
            {"strike": 580, "T": 30 / 365.0, "iv": 0.20, "type": "CALL", "oi": 100},
            {"strike": 575, "T": 30 / 365.0, "iv": 0.22, "type": "PUT",  "oi":  50},
        ]
        result = calc_vex(spot, contracts)
        s = sum(result["vex_by_strike"].values())
        # Each per-strike value already rounded to 2dp in calc_vex;
        # total_vex is the sum of all rounded values.
        expected_total = round(s, 2)
        assert result["total_vex"] == pytest.approx(expected_total, abs=0.05)


# ────────────────────────────────────────────────────────────────────
# Class 6 — Symbol-export guard
# ────────────────────────────────────────────────────────────────────

class TestModuleSurface:
    """Pin the helper-module public surface so callers using `from X
    import Y` get a loud ImportError on typos."""

    def test_module_exports_expected_symbols(self):
        import domain.greek_scalers as m

        expected = {
            "TRADING_DAYS_PER_YEAR",
            "dollar_vex_per_1pct_spot_move",
            "dollar_vex_per_unit_sigma",
            "dollar_vex_per_1pct_vol_change",
            "dollar_vega_per_1pct_vol_change",
            "charm_per_day",
            "dollar_charm_per_day",
        }
        assert set(m.__all__) == expected
