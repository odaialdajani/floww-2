"""Tests for services/stochastic_vol.py — SABR, SVI, and Vol Surface."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.stochastic_vol import SABRModel, SVIProfile, VolSurfaceConstructor

# ── SABR Model ───────────────────────────────────────────────────────────


class TestSABRModel:
    def test_default_params(self):
        m = SABRModel()
        assert m.alpha == 0.2
        assert m.beta == 0.5
        assert m.rho == -0.3
        assert m.nu == 0.4

    def test_atm_lognormal_vol_positive(self):
        m = SABRModel()
        vol = m.hagan_lognormal_vol(F=100.0, K=100.0, T=1.0)
        assert vol > 0
        assert np.isfinite(vol)

    def test_atm_normal_vol_positive(self):
        m = SABRModel()
        vol = m.hagan_normal_vol(F=100.0, K=100.0, T=1.0)
        assert vol > 0
        assert np.isfinite(vol)

    def test_otm_vol_smile(self):
        """OTM calls and puts should have higher vol than ATM (vol smile)."""
        m = SABRModel(alpha=0.2, beta=0.5, rho=-0.3, nu=0.5)
        atm = m.hagan_lognormal_vol(F=100.0, K=100.0, T=1.0)
        m.hagan_lognormal_vol(F=100.0, K=120.0, T=1.0)
        otm_put = m.hagan_lognormal_vol(F=100.0, K=80.0, T=1.0)
        # With negative rho, put wing should be higher
        assert otm_put > atm

    def test_negative_rho_creates_skew(self):
        """Negative rho should make puts more expensive than calls."""
        m = SABRModel(alpha=0.2, beta=0.5, rho=-0.7, nu=0.4)
        call_vol = m.hagan_lognormal_vol(F=100.0, K=110.0, T=1.0)
        put_vol = m.hagan_lognormal_vol(F=100.0, K=90.0, T=1.0)
        assert put_vol > call_vol

    def test_invalid_inputs_return_alpha(self):
        m = SABRModel(alpha=0.25)
        assert m.hagan_lognormal_vol(F=0, K=100, T=1) == 0.25
        assert m.hagan_lognormal_vol(F=100, K=0, T=1) == 0.25
        assert m.hagan_lognormal_vol(F=100, K=100, T=0) == 0.25
        assert m.hagan_normal_vol(F=0, K=100, T=1) == 0.25

    def test_fit_returns_params_and_rmse(self):
        m = SABRModel()
        strikes = np.array([90, 95, 100, 105, 110], dtype=float)
        market_vols = np.array([0.25, 0.22, 0.20, 0.22, 0.26])
        result = m.fit(strikes, market_vols, F=100.0, T=1.0)
        for key in ("alpha", "beta", "rho", "nu", "rmse"):
            assert key in result
        assert result["rmse"] < float("inf")

    def test_fit_insufficient_data(self):
        m = SABRModel()
        result = m.fit(np.array([100.0]), np.array([0.2]), F=100.0, T=1.0)
        # Was float("inf"). That value is not JSON compliant, and
        # POST /api/vol-surface/{ticker}/sabr returns this dict directly, so an
        # unachievable fit produced a 500 instead of a reported failure. None
        # says exactly what happened: no error was measured, because no fit
        # was attempted.
        assert result["rmse"] is None
        assert result["fit_status"] == "insufficient_data"
        # The default parameters are still reported, so a caller can tell
        # which surface it is looking at.
        for key in ("alpha", "beta", "rho", "nu"):
            assert key in result

    def test_get_state(self):
        m = SABRModel(alpha=0.3, beta=0.7, rho=-0.5, nu=0.6)
        state = m.get_state()
        assert state["alpha"] == 0.3
        assert state["beta"] == 0.7


# ── SVI Profile ──────────────────────────────────────────────────────────


class TestSVIProfile:
    def test_default_params(self):
        svi = SVIProfile()
        assert svi.a == 0.04
        assert svi.b == 0.4

    def test_total_variance_atm(self):
        svi = SVIProfile()
        w = svi.total_variance(np.array([0.0]))
        assert w[0] > 0

    def test_total_variance_positive_everywhere(self):
        svi = SVIProfile(a=0.04, b=0.4, rho=-0.7, m=0.0, sigma=0.1)
        k = np.linspace(-0.5, 0.5, 50)
        w = svi.total_variance(k)
        assert np.all(w > 0)

    def test_implied_vol_positive(self):
        svi = SVIProfile()
        k = np.linspace(-0.3, 0.3, 20)
        iv = svi.implied_vol(k, T=1.0)
        assert np.all(iv > 0)

    def test_implied_vol_fallback_for_zero_T(self):
        svi = SVIProfile()
        iv = svi.implied_vol(np.array([0.0]), T=0.0)
        assert np.all(iv > 0)  # should fallback to 1/365 day

    def test_fit_returns_params_and_rmse(self):
        svi = SVIProfile()
        k = np.linspace(-0.3, 0.3, 10)
        # Generate synthetic market vols from SVI with known params
        true_svi = SVIProfile(a=0.04, b=0.4, rho=-0.5, m=0.0, sigma=0.1)
        market_vols = true_svi.implied_vol(k, T=1.0)
        result = svi.fit(k, market_vols, T=1.0)
        for key in ("a", "b", "rho", "m", "sigma", "rmse"):
            assert key in result

    def test_fit_insufficient_data(self):
        svi = SVIProfile()
        result = svi.fit(np.array([0.0, 0.1]), np.array([0.2, 0.22]), T=1.0)
        # See the SABR case above: rmse=inf was unserializable and turned an
        # unachievable fit into a 500 from POST /api/vol-surface/{t}/svi.
        assert result["rmse"] is None
        assert result["fit_status"] == "insufficient_data"

    def test_get_state(self):
        svi = SVIProfile(a=0.05, b=0.3, rho=-0.6, m=0.01, sigma=0.15)
        state = svi.get_state()
        assert state["a"] == 0.05
        assert state["sigma"] == 0.15


# ── Vol Surface Constructor ──────────────────────────────────────────────


class TestVolSurfaceConstructor:
    def _make_contracts(self, spot=100.0, n_strikes=10, n_expiries=3):
        """Generate synthetic option chain contracts."""
        strikes = np.linspace(spot * 0.8, spot * 1.2, n_strikes)
        expiries = [0.25, 0.5, 1.0]
        contracts = []
        for T in expiries[:n_expiries]:
            for K in strikes:
                # Synthetic smile: higher vol away from ATM
                iv = 0.20 + 0.5 * ((K - spot) / spot) ** 2
                contracts.append({"strike": K, "iv": iv, "expiry": T, "type": "call"})
        return contracts

    def test_build_surface_returns_expected_keys(self):
        vsc = VolSurfaceConstructor()
        contracts = self._make_contracts()
        surface = vsc.build_surface(spot=100.0, contracts=contracts)
        for key in ("grid_strikes", "grid_expiries", "iv_grid", "sabr_params", "svi_params_by_expiry", "atm_term_structure"):
            assert key in surface

    def test_build_surface_empty_contracts(self):
        vsc = VolSurfaceConstructor()
        surface = vsc.build_surface(spot=100.0, contracts=[])
        assert len(surface["grid_strikes"]) == 0

    def test_build_surface_invalid_spot(self):
        vsc = VolSurfaceConstructor()
        surface = vsc.build_surface(spot=0, contracts=[{"strike": 100, "iv": 0.2, "expiry": 1.0}])
        assert len(surface["grid_strikes"]) == 0

    def test_iv_grid_shape(self):
        vsc = VolSurfaceConstructor()
        contracts = self._make_contracts()
        surface = vsc.build_surface(spot=100.0, contracts=contracts)
        grid = surface["iv_grid"]
        assert grid.shape[0] == len(surface["grid_strikes"])
        assert grid.shape[1] == len(surface["grid_expiries"])

    def test_atm_term_structure_non_empty(self):
        vsc = VolSurfaceConstructor()
        contracts = self._make_contracts()
        surface = vsc.build_surface(spot=100.0, contracts=contracts)
        assert len(surface["atm_term_structure"]) > 0
        for _T, iv in surface["atm_term_structure"]:
            assert iv > 0

    def test_interpolate_iv(self):
        vsc = VolSurfaceConstructor()
        contracts = self._make_contracts()
        target_strikes = np.array([95.0, 100.0, 105.0])
        target_expiries = np.array([0.3, 0.6])
        result = vsc.interpolate_iv(spot=100.0, contracts=contracts, target_strikes=target_strikes, target_expiries=target_expiries)
        assert result.shape == (3, 2)
        assert np.all(result > 0)
