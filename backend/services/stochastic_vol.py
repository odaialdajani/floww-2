"""
SABR and SVI Stochastic Volatility Surface Interpolation
=========================================================

This module implements two industry-standard stochastic volatility models
for interpolating and extrapolating implied volatility (IV) surfaces:

1. SABR Model (Hagan et al., 2002):
   Stochastic Alpha Beta Rho model. Describes the evolution of the forward
   price F and its stochastic volatility alpha under the forward measure:
     dF = alpha * F^beta * dW1
     dalpha = nu * alpha * dW2
     dW1*dW2 = rho*dt
   Hagan derived closed-form asymptotic expansions for implied volatility
   as a function of strike, enabling fast calibration to market smiles.
   - beta controls the backbone: 0=normal, 0.5=stochastic vol, 1=lognormal
   - rho controls the skew (slope of the smile)
   - nu controls the smile curvature (vol of vol)
   - alpha sets the overall vol level

2. SVI Model (Gatheral, 2004):
   Stochastic Volatility Inspired parameterization. Models total variance
   w(k) = sigma^2 * T as a function of log-moneyness k = ln(K/F):
     w(k) = a + b * (rho * (k - m) + sqrt((k - m)^2 + sigma^2))
   - a: overall vertical shift (minimum total variance level)
   - b: controls the angle of the wings (wing slope)
   - rho: controls the skew (tilt of the smile)
   - m: horizontal translation (ATM location shift)
   - sigma: controls the smoothness at the minimum (ATM curvature)
   SVI guarantees no-arbitrage under simple parameter constraints.

3. VolSurfaceConstructor:
   Combines SABR and SVI to build a full 2D IV surface from option chain data.
   Fits SVI per-expiry for smile-consistent interpolation and SABR globally
   for parametric surface representation. Computes term structures for ATM
   vol, 25-delta risk reversal (skew), and 25-delta butterfly.

References:
   - Hagan, P., Kumar, D., Lesniewski, A., Woodward, D. (2002).
     "Managing Smile Risk." Wilmott Magazine.
   - Gatheral, J. (2004). "A Parsimonious Arbitrage-Free Implied
     Volatility Parameterization." Columbia University.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.interpolate import RectBivariateSpline
from scipy.optimize import minimize

logger = logging.getLogger(__name__)


class SABRModel:
    """
    SABR (Stochastic Alpha Beta Rho) model for implied volatility smile.

    Implements Hagan et al. (2002) asymptotic expansions for both
    lognormal (Black) and normal (Bachelier) implied volatility.
    """

    def __init__(
        self,
        alpha: float = 0.2,
        beta: float = 0.5,
        rho: float = -0.3,
        nu: float = 0.4,
    ):
        """
        Initialize SABR model parameters.

        Args:
            alpha: Initial volatility level (sigma_0). Typical range [0.01, 0.5].
            beta: CEV elasticity parameter. 0=normal, 0.5=stochastic vol, 1=lognormal.
            rho: Correlation between spot and vol. Range [-1, 1], typically negative.
            nu: Volatility of volatility. Range [0.01, 1.0], higher = more curvature.
        """
        self.alpha = alpha
        self.beta = beta
        self.rho = rho
        self.nu = nu

    def hagan_normal_vol(self, F: float, K: float, T: float) -> float:
        """
        Hagan's SABR implied normal (Bachelier) volatility.

        Uses the Hagan et al. (2002) formula for the Bachelier implied
        volatility under the SABR dynamics.

        Args:
            F: Forward price.
            K: Strike price.
            T: Time to expiry in years.

        Returns:
            Implied normal (Bachelier) volatility.
        """
        if F <= 0 or K <= 0 or T <= 0:
            return self.alpha

        alpha = self.alpha
        beta = self.beta
        rho = self.rho
        nu = self.nu

        # Handle ATM case
        if abs(F - K) < 1e-12:
            # ATM normal vol formula
            term1 = alpha / (F ** beta)
            term2 = (
                (beta - 1) ** 2 * alpha ** 2 / (24 * F ** (2 * beta))
                + rho * beta * nu * alpha / (4 * F ** beta)
                + (2 - 3 * rho ** 2) * nu ** 2 / 24
            ) * T
            sigma_n = term1 * (1 + term2)
            return max(sigma_n, 1e-8)

        z = (nu / alpha) * (F * K) ** ((1 - beta) / 2) * np.log(F / K)
        x_z = np.log((np.sqrt(1 - 2 * rho * z + z ** 2) + z - rho) / (1 - rho))

        if abs(x_z) < 1e-12:
            # Fallback to ATM
            return self.hagan_normal_vol(F, F, T)

        term1 = alpha / ((F * K) ** (beta / 2) * (1 + (1 - beta) ** 2 / 24 * np.log(F / K) ** 2 + (1 - beta) ** 4 / 1920 * np.log(F / K) ** 4))
        term2 = z / x_z
        term3 = (
            (1 - beta) ** 2 * alpha ** 2 / (24 * (F * K) ** (1 - beta))
            + rho * beta * nu * alpha / (4 * (F * K) ** ((1 - beta) / 2))
            + (2 - 3 * rho ** 2) * nu ** 2 / 24
        ) * T

        sigma_n = term1 * term2 * (1 + term3)
        return max(sigma_n, 1e-8)

    def hagan_lognormal_vol(self, F: float, K: float, T: float) -> float:
        """
        Hagan's SABR implied lognormal (Black) volatility.

        Uses the Hagan et al. (2002) formula for the Black implied
        volatility under the SABR dynamics.

        Args:
            F: Forward price.
            K: Strike price.
            T: Time to expiry in years.

        Returns:
            Implied lognormal (Black) volatility.
        """
        if F <= 0 or K <= 0 or T <= 0:
            return self.alpha

        alpha = self.alpha
        beta = self.beta
        rho = self.rho
        nu = self.nu

        # Handle ATM case
        if abs(F - K) < 1e-12:
            logFK = np.log(F / K) if K > 0 else 0.0
            term1 = alpha / (F ** (1 - beta))
            term2 = (
                (1 - beta) ** 2 * alpha ** 2 / (24 * F ** (2 - 2 * beta))
                + rho * beta * nu * alpha / (4 * F ** (1 - beta))
                + (2 - 3 * rho ** 2) * nu ** 2 / 24
            ) * T
            sigma_b = term1 * (1 + term2)
            return max(sigma_b, 1e-8)

        logFK = np.log(F / K)
        z = (nu / alpha) * (F * K) ** ((1 - beta) / 2) * logFK
        x_z = np.log((np.sqrt(1 - 2 * rho * z + z ** 2) + z - rho) / (1 - rho))

        if abs(x_z) < 1e-12:
            return self.hagan_lognormal_vol(F, F, T)

        term1 = alpha / ((F * K) ** ((1 - beta) / 2) * (1 + (1 - beta) ** 2 / 24 * logFK ** 2 + (1 - beta) ** 4 / 1920 * logFK ** 4))
        term2 = z / x_z
        term3 = (
            (1 - beta) ** 2 * alpha ** 2 / (24 * (F * K) ** (1 - beta))
            + rho * beta * nu * alpha / (4 * (F * K) ** ((1 - beta) / 2))
            + (2 - 3 * rho ** 2) * nu ** 2 / 24
        ) * T

        sigma_b = term1 * term2 * (1 + term3)
        return max(sigma_b, 1e-8)

    def fit(
        self,
        strikes: np.ndarray,
        market_vols: np.ndarray,
        F: float,
        T: float,
    ) -> Dict[str, float]:
        """
        Fit SABR parameters to market volatility smile using least squares.

        Uses scipy.optimize.minimize with L-BFGS-B method and bounded parameters.
        Fits lognormal (Black) implied volatility by default.

        Args:
            strikes: Array of strike prices.
            market_vols: Array of market implied volatilities.
            F: Forward price.
            T: Time to expiry in years.

        Returns:
            Dict with fitted alpha, beta, rho, nu, and rmse.
        """
        strikes = np.asarray(strikes, dtype=float)
        market_vols = np.asarray(market_vols, dtype=float)

        if len(strikes) < 4 or len(strikes) != len(market_vols):
            logger.warning("Insufficient data for SABR fit: %d points", len(strikes))
            return {
                "alpha": self.alpha,
                "beta": self.beta,
                "rho": self.rho,
                "nu": self.nu,
                "rmse": float("inf"),
            }

        # Filter out invalid data
        valid = (strikes > 0) & (market_vols > 0) & np.isfinite(market_vols)
        strikes = strikes[valid]
        market_vols = market_vols[valid]

        if len(strikes) < 4:
            logger.warning("Insufficient valid data for SABR fit after filtering")
            return {
                "alpha": self.alpha,
                "beta": self.beta,
                "rho": self.rho,
                "nu": self.nu,
                "rmse": float("inf"),
            }

        def objective(params: np.ndarray) -> float:
            a, b, r, v = params
            model = SABRModel(alpha=a, beta=b, rho=r, nu=v)
            try:
                model_vols = np.array(
                    [model.hagan_lognormal_vol(F, K, T) for K in strikes]
                )
                if not np.all(np.isfinite(model_vols)):
                    return 1e10
                return np.sum((model_vols - market_vols) ** 2)
            except (ValueError, ZeroDivisionError, OverflowError):
                return 1e10

        # Bounds: alpha > 0, beta in [0,1], rho in [-1,1], nu > 0
        bounds = [
            (0.001, 2.0),   # alpha
            (0.0, 1.0),     # beta
            (-0.999, 0.999), # rho
            (0.001, 2.0),   # nu
        ]

        x0 = [self.alpha, self.beta, self.rho, self.nu]

        try:
            result = minimize(
                objective,
                x0,
                method="L-BFGS-B",
                bounds=bounds,
                options={"maxiter": 1000, "ftol": 1e-12},
            )

            if result.success:
                self.alpha, self.beta, self.rho, self.nu = result.x
                fitted_vols = np.array(
                    [self.hagan_lognormal_vol(F, K, T) for K in strikes]
                )
                rmse = float(np.sqrt(np.mean((fitted_vols - market_vols) ** 2)))
            else:
                logger.warning("SABR fit did not converge: %s", result.message)
                rmse = float("inf")

        except Exception as e:
            logger.error("SABR fit failed: %s", e)
            rmse = float("inf")

        return {
            "alpha": float(self.alpha),
            "beta": float(self.beta),
            "rho": float(self.rho),
            "nu": float(self.nu),
            "rmse": rmse,
        }

    def get_state(self) -> Dict[str, Any]:
        """Return current model parameters as a dictionary."""
        return {
            "alpha": self.alpha,
            "beta": self.beta,
            "rho": self.rho,
            "nu": self.nu,
        }


class SVIProfile:
    """
    Stochastic Volatility Inspired (SVI) parameterization.

    Implements Gatheral's (2004) raw SVI model for total variance
    as a function of log-moneyness:
        w(k) = a + b * (rho * (k - m) + sqrt((k - m)^2 + sigma^2))

    This parameterization is popular for its simplicity and the ease
    of enforcing no-arbitrage conditions on the parameters.
    """

    def __init__(
        self,
        a: float = 0.04,
        b: float = 0.4,
        rho: float = -0.7,
        m: float = 0.0,
        sigma: float = 0.1,
    ):
        """
        Initialize SVI parameters.

        Args:
            a: Overall vertical shift (minimum variance level). Must be >= 0.
            b: Wing slope parameter (controls angle of wings). Must be >= 0.
            rho: Skew parameter (tilt of smile). Range (-1, 1), negative = left skew.
            m: Horizontal translation (ATM location shift). Typically near 0.
            sigma: ATM curvature (smoothness at minimum). Must be > 0.
        """
        self.a = a
        self.b = b
        self.rho = rho
        self.m = m
        self.sigma = sigma

    def total_variance(self, k: np.ndarray) -> np.ndarray:
        """
        Compute total variance w(k) for given log-moneyness values.

        Args:
            k: Array of log-moneyness values (ln(K/F)).

        Returns:
            Array of total variance values.
        """
        k = np.asarray(k, dtype=float)
        dm = k - self.m
        w = self.a + self.b * (self.rho * dm + np.sqrt(dm ** 2 + self.sigma ** 2))
        return w

    def implied_vol(self, k: np.ndarray, T: float) -> np.ndarray:
        """
        Convert total variance to implied volatility.

        sigma_iv = sqrt(w(k) / T)

        Args:
            k: Array of log-moneyness values.
            T: Time to expiry in years.

        Returns:
            Array of implied volatilities.
        """
        if T <= 0:
            T = 1.0 / 365.0  # fallback to 1 day
        w = self.total_variance(k)
        # Ensure non-negative before sqrt
        w = np.maximum(w, 0.0)
        return np.sqrt(w / T)

    def fit(
        self,
        log_moneyness: np.ndarray,
        market_vols: np.ndarray,
        T: float,
    ) -> Dict[str, float]:
        """
        Fit SVI parameters to market data via least squares.

        Minimizes sum of squared differences between SVI implied vols
        and market implied vols.

        Args:
            log_moneyness: Array of log-moneyness values (ln(K/F)).
            market_vols: Array of market implied volatilities.
            T: Time to expiry in years.

        Returns:
            Dict with fitted a, b, rho, m, sigma, and rmse.
        """
        log_moneyness = np.asarray(log_moneyness, dtype=float)
        market_vols = np.asarray(market_vols, dtype=float)

        if len(log_moneyness) < 5 or len(log_moneyness) != len(market_vols):
            logger.warning("Insufficient data for SVI fit: %d points", len(log_moneyness))
            return {
                "a": self.a,
                "b": self.b,
                "rho": self.rho,
                "m": self.m,
                "sigma": self.sigma,
                "rmse": float("inf"),
            }

        # Filter invalid data
        valid = np.isfinite(log_moneyness) & np.isfinite(market_vols) & (market_vols > 0)
        log_moneyness = log_moneyness[valid]
        market_vols = market_vols[valid]

        if len(log_moneyness) < 5:
            logger.warning("Insufficient valid data for SVI fit after filtering")
            return {
                "a": self.a,
                "b": self.b,
                "rho": self.rho,
                "m": self.m,
                "sigma": self.sigma,
                "rmse": float("inf"),
            }

        market_total_var = market_vols ** 2 * T

        def objective(params: np.ndarray) -> float:
            a, b, rho, m, sigma = params
            if sigma <= 0 or b < 0:
                return 1e10
            if abs(rho) >= 1:
                return 1e10
            dm = log_moneyness - m
            w = a + b * (rho * dm + np.sqrt(dm ** 2 + sigma ** 2))
            if np.any(w < 0):
                return 1e10
            return np.sum((w - market_total_var) ** 2)

        # Bounds: a >= 0, b >= 0, rho in (-1,1), m unbounded, sigma > 0
        bounds = [
            (0.0, 2.0),        # a
            (0.0, 5.0),        # b
            (-0.999, 0.999),   # rho
            (-2.0, 2.0),       # m
            (0.001, 2.0),      # sigma
        ]

        x0 = [self.a, self.b, self.rho, self.m, self.sigma]

        try:
            result = minimize(
                objective,
                x0,
                method="L-BFGS-B",
                bounds=bounds,
                options={"maxiter": 2000, "ftol": 1e-12},
            )

            if result.success:
                self.a, self.b, self.rho, self.m, self.sigma = result.x
                fitted_vols = self.implied_vol(log_moneyness, T)
                rmse = float(np.sqrt(np.mean((fitted_vols - market_vols) ** 2)))
            else:
                logger.warning("SVI fit did not converge: %s", result.message)
                rmse = float("inf")

        except Exception as e:
            logger.error("SVI fit failed: %s", e)
            rmse = float("inf")

        return {
            "a": float(self.a),
            "b": float(self.b),
            "rho": float(self.rho),
            "m": float(self.m),
            "sigma": float(self.sigma),
            "rmse": rmse,
        }

    def get_state(self) -> Dict[str, Any]:
        """Return current SVI parameters as a dictionary."""
        return {
            "a": self.a,
            "b": self.b,
            "rho": self.rho,
            "m": self.m,
            "sigma": self.sigma,
        }


class VolSurfaceConstructor:
    """
    Combines SABR and SVI models to build a full implied volatility surface.

    Takes option chain data (strikes, IVs, expiries) and produces:
    - A 2D IV grid (strikes x expiries)
    - SABR parameters fitted to the full surface
    - SVI parameters fitted per-expiry
    - ATM term structure
    - 25-delta skew (risk reversal) term structure
    - 25-delta butterfly term structure
    """

    def __init__(self):
        """Initialize the VolSurfaceConstructor."""
        self.sabr_model = SABRModel()
        self.svi_profiles: Dict[float, SVIProfile] = {}
        self._last_surface: Optional[Dict[str, Any]] = None

    def build_surface(
        self,
        spot: float,
        contracts: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Build a full IV surface from option chain contracts.

        Args:
            spot: Current spot price.
            contracts: List of dicts, each with keys:
                - 'strike' (float): Option strike price.
                - 'iv' (float): Implied volatility.
                - 'expiry' (float): Time to expiry in years.
                - 'type' (str): 'call' or 'put'.

        Returns:
            Dict containing:
                - grid_strikes: 1D array of strike grid points
                - grid_expiries: 1D array of expiry grid points
                - iv_grid: 2D array (n_strikes x n_expiries) of interpolated IVs
                - sabr_params: Fitted SABR parameters dict
                - svi_params_by_expiry: Dict mapping expiry -> SVI params dict
                - atm_term_structure: List of (T, atm_iv) tuples
                - skew_25d: List of (T, skew) tuples
                - butterfly_25d: List of (T, bf) tuples
        """
        if not contracts or spot <= 0:
            logger.warning("Empty contracts or invalid spot for surface build")
            return self._empty_surface()

        # Validate and extract contract data
        valid_contracts = []
        for c in contracts:
            try:
                strike = float(c["strike"])
                iv = float(c["iv"])
                expiry = float(c["expiry"])
                if strike > 0 and iv > 0 and expiry > 0:
                    valid_contracts.append(
                        {"strike": strike, "iv": iv, "expiry": expiry, "type": c.get("type", "call")}
                    )
            except (KeyError, ValueError, TypeError):
                continue

        if len(valid_contracts) < 5:
            logger.warning("Insufficient valid contracts: %d", len(valid_contracts))
            return self._empty_surface()

        # Group by expiry
        expiries_map: Dict[float, List[Dict]] = {}
        for c in valid_contracts:
            T = c["expiry"]
            if T not in expiries_map:
                expiries_map[T] = []
            expiries_map[T].append(c)

        # Sort expiries
        sorted_expiries = sorted(expiries_map.keys())

        # Fit SVI per expiry
        svi_params_by_expiry = {}
        all_strikes = []
        all_vols = []
        all_expiries = []
        atm_term_structure = []
        skew_25d = []
        butterfly_25d = []

        for T in sorted_expiries:
            expiry_contracts = expiries_map[T]
            if len(expiry_contracts) < 3:
                logger.warning("Expiry T=%.4f has only %d contracts, skipping SVI fit", T, len(expiry_contracts))
                continue

            strikes_t = np.array([c["strike"] for c in expiry_contracts])
            ivs_t = np.array([c["iv"] for c in expiry_contracts])
            log_moneyness_t = np.log(strikes_t / spot)

            # Fit SVI
            svi = SVIProfile()
            fit_result = svi.fit(log_moneyness_t, ivs_t, T)
            svi_params_by_expiry[T] = fit_result
            self.svi_profiles[T] = svi

            # Collect for global SABR fit
            all_strikes.extend(strikes_t.tolist())
            all_vols.extend(ivs_t.tolist())
            all_expiries.extend([T] * len(strikes_t))

            # ATM IV: interpolate at k=0
            try:
                atm_iv = float(svi.implied_vol(np.array([0.0], dtype=float), T)[0])
            except Exception:
                # Fallback: find closest to ATM
                atm_idx = np.argmin(np.abs(strikes_t - spot))
                atm_iv = float(ivs_t[atm_idx])
            atm_term_structure.append((T, atm_iv))

            # 25-delta skew and butterfly from SVI
            try:
                # Approximate 25-delta log-moneyness points
                # For a rough estimate: k_25c ~ 0.5 * atm_iv * sqrt(T), k_25d ~ -0.5 * atm_iv * sqrt(T)
                k_width = 0.5 * atm_iv * np.sqrt(T)
                k_call = k_width
                k_put = -k_width

                iv_call = float(svi.implied_vol(np.array([k_call]), T)[0])
                iv_put = float(svi.implied_vol(np.array([k_put]), T)[0])

                # Risk reversal = IV(25d call) - IV(25d put)
                rr_25 = iv_call - iv_put
                skew_25d.append((T, rr_25))

                # Butterfly = (IV(25c) + IV(25d)) / 2 - IV(ATM)
                bf_25 = (iv_call + iv_put) / 2.0 - atm_iv
                butterfly_25d.append((T, bf_25))
            except Exception as e:
                logger.debug("Could not compute 25d risk reversal/butterfly for T=%.4f: %s", T, e)
                skew_25d.append((T, 0.0))
                butterfly_25d.append((T, 0.0))

        # Fit SABR to all data (use first expiry as reference T for SABR)
        sabr_params = {}
        if len(all_strikes) >= 4:
            all_strikes_arr = np.array(all_strikes)
            all_vols_arr = np.array(all_vols)
            # Use weighted average expiry or just the first one for SABR fit
            ref_T = sorted_expiries[0] if sorted_expiries else 0.25
            sabr_params = self.sabr_model.fit(all_strikes_arr, all_vols_arr, spot, ref_T)
        else:
            sabr_params = self.sabr_model.get_state()
            sabr_params["rmse"] = float("inf")

        # Build 2D grid
        grid_strikes, grid_expiries, iv_grid = self._build_iv_grid(
            spot, sorted_expiries, expiries_map, svi_params_by_expiry
        )

        surface = {
            "grid_strikes": grid_strikes,
            "grid_expiries": grid_expiries,
            "iv_grid": iv_grid,
            "sabr_params": sabr_params,
            "svi_params_by_expiry": svi_params_by_expiry,
            "atm_term_structure": atm_term_structure,
            "skew_25d": skew_25d,
            "butterfly_25d": butterfly_25d,
        }

        self._last_surface = surface
        return surface

    def _build_iv_grid(
        self,
        spot: float,
        expiries: List[float],
        expiries_map: Dict[float, List[Dict]],
        svi_params_by_expiry: Dict[float, Dict],
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Build a 2D IV grid from per-expiry SVI fits.

        Args:
            spot: Current spot price.
            expiries: Sorted list of expiry times.
            expiries_map: Dict mapping expiry -> list of contracts.
            svi_params_by_expiry: Dict mapping expiry -> SVI fit results.

        Returns:
            Tuple of (grid_strikes, grid_expiries, iv_grid).
        """
        if not expiries:
            return np.array([]), np.array([]), np.array([]).reshape(0, 0)

        # Determine strike range across all expiries
        all_k = []
        for T in expiries:
            if T in expiries_map:
                for c in expiries_map[T]:
                    all_k.append(c["strike"])

        if not all_k:
            return np.array([]), np.array([]), np.array([]).reshape(0, 0)

        k_min = max(min(all_k) * 0.8, spot * 0.3)
        k_max = min(max(all_k) * 1.2, spot * 3.0)
        grid_strikes = np.linspace(k_min, k_max, 50)
        grid_expiries = np.array(expiries)

        iv_grid = np.full((len(grid_strikes), len(grid_expiries)), np.nan)

        for j, T in enumerate(grid_expiries):
            if T in svi_params_by_expiry:
                svi = self.svi_profiles.get(T)
                if svi is not None:
                    log_moneyness = np.log(grid_strikes / spot)
                    try:
                        ivs = svi.implied_vol(log_moneyness, T)
                        iv_grid[:, j] = ivs
                    except Exception:
                        pass

        # Fill any remaining NaNs with nearest valid column
        for j in range(iv_grid.shape[1]):
            col = iv_grid[:, j]
            if np.all(np.isnan(col)):
                # Find nearest non-NaN column
                for offset in range(1, iv_grid.shape[1]):
                    if j - offset >= 0 and not np.all(np.isnan(iv_grid[:, j - offset])):
                        iv_grid[:, j] = iv_grid[:, j - offset]
                        break
                    if j + offset < iv_grid.shape[1] and not np.all(np.isnan(iv_grid[:, j + offset])):
                        iv_grid[:, j] = iv_grid[:, j + offset]
                        break

        # Replace any remaining NaNs with 0
        iv_grid = np.nan_to_num(iv_grid, nan=0.0)

        return grid_strikes, grid_expiries, iv_grid

    def interpolate_iv(
        self,
        spot: float,
        contracts: List[Dict[str, Any]],
        target_strikes: np.ndarray,
        target_expiries: np.ndarray,
    ) -> np.ndarray:
        """
        Full 2D interpolation of the IV surface.

        Builds the surface from contracts and interpolates onto the
        requested (strikes x expiries) grid using bivariate spline.

        Args:
            spot: Current spot price.
            contracts: List of option contract dicts (strike, iv, expiry, type).
            target_strikes: 1D array of target strike prices.
            target_expiries: 1D array of target expiry times (years).

        Returns:
            2D array of interpolated IVs with shape
            (len(target_strikes), len(target_expiries)).
        """
        target_strikes = np.asarray(target_strikes, dtype=float)
        target_expiries = np.asarray(target_expiries, dtype=float)

        if len(target_strikes) == 0 or len(target_expiries) == 0:
            return np.array([]).reshape(0, 0)

        # Build surface
        surface = self.build_surface(spot, contracts)

        grid_strikes = surface["grid_strikes"]
        grid_expiries = surface["grid_expiries"]
        iv_grid = surface["iv_grid"]

        if len(grid_strikes) < 2 or len(grid_expiries) < 2:
            logger.warning("Surface grid too small for interpolation")
            # Return flat surface from SABR if available
            result = np.zeros((len(target_strikes), len(target_expiries)))
            for j, T in enumerate(target_expiries):
                for i, K in enumerate(target_strikes):
                    try:
                        result[i, j] = self.sabr_model.hagan_lognormal_vol(spot, K, T)
                    except Exception:
                        result[i, j] = self.sabr_model.alpha
            return result

        try:
            # Use RectBivariateSpline for smooth 2D interpolation
            # kx=1, ky=1 for linear interpolation (more stable with sparse data)
            # Increase to 3 for cubic if grid is dense enough
            kx = min(3, len(grid_strikes) - 1)
            ky = min(3, len(grid_expiries) - 1)
            if kx < 1:
                kx = 1
            if ky < 1:
                ky = 1

            spline = RectBivariateSpline(
                grid_strikes, grid_expiries, iv_grid, kx=kx, ky=ky
            )
            result = spline(target_strikes, target_expiries)
            result = np.maximum(result, 0.0)  # IVs must be non-negative
            return result

        except Exception as e:
            logger.error("2D interpolation failed: %s, using nearest fallback", e)
            # Fallback: nearest-neighbor interpolation
            result = np.zeros((len(target_strikes), len(target_expiries)))
            for i, K in enumerate(target_strikes):
                ki = np.argmin(np.abs(grid_strikes - K))
                for j, T in enumerate(target_expiries):
                    ti = np.argmin(np.abs(grid_expiries - T))
                    result[i, j] = iv_grid[ki, ti]
            return result

    def _empty_surface(self) -> Dict[str, Any]:
        """Return an empty surface dict for error cases."""
        return {
            "grid_strikes": np.array([]),
            "grid_expiries": np.array([]),
            "iv_grid": np.array([]).reshape(0, 0),
            "sabr_params": self.sabr_model.get_state(),
            "svi_params_by_expiry": {},
            "atm_term_structure": [],
            "skew_25d": [],
            "butterfly_25d": [],
        }
