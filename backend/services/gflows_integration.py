"""
backend/services/gflows_integration.py

Integration layer for G|Flows (Greek Flows) functionality within the floww ecosystem.

Provides:
  1. CBOE options data downloader (SPX, NDX, RUT)
  2. Treasury yield curve fetcher (FRED → yfinance → default)
  3. OPEX calendar (third Friday detection with market holidays)
  4. Greek exposure profile computation (Delta, Gamma, Vanna, Charm profiles)
  5. 0DTE volume-vs-OI prioritization logic

This wraps the standalone gflows modules copied into backend/gflows_modules/.
Usage:
    from services.gflows_integration import GFlowsIntegrator
    gf = GFlowsIntegrator()
    data = await gf.fetch_options_data("SPX", "all", is_json=True)
    profiles = gf.compute_exposure_profiles(data)
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# Try to import gflows modules (copied into backend/gflows_modules/)
# The gflows calc.py internally does 'import modules.stats as stats', so we
# need to alias 'modules' → 'gflows_modules' in sys.modules before importing.
try:
    import types as _types
    import sys as _sys

    _GF_MODULES_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "gflows_modules")
    if _GF_MODULES_PATH not in _sys.path:
        _sys.path.insert(0, os.path.dirname(_GF_MODULES_PATH))  # backend/ so 'gflows_modules' is importable
        _sys.path.insert(0, _GF_MODULES_PATH)  # gflows_modules/ for direct module lookups

    # Step 1: Import modules that DON'T depend on 'modules.*' aliases
    import gflows_modules.ticker_dwn as _gflows_ticker_dwn
    import gflows_modules.stats as _gflows_stats

    # Step 2: Set up 'modules' → 'gflows_modules' alias BEFORE importing calc
    _mod_pkg = _types.ModuleType('modules')
    _mod_pkg.__path__ = [_GF_MODULES_PATH]
    _mod_pkg.__package__ = 'modules'
    _sys.modules['modules'] = _mod_pkg
    _sys.modules['modules.stats'] = _gflows_stats
    _sys.modules['modules.ticker_dwn'] = _gflows_ticker_dwn

    # Step 3: Now calc.py can import 'modules.stats' — it finds the alias above
    import gflows_modules.calc as _gflows_calc
    from gflows_modules.calc import (
        fetch_treasury_yield_curve, get_tenor_matched_rate,
        is_third_friday, get_next_monthly_opex, get_options_data,
        calc_exposures, format_data,
    )
    from gflows_modules.ticker_dwn import dwn_data
    from gflows_modules.stats import calc_delta_ex, calc_gamma_ex, calc_vanna_ex, calc_charm_ex
    HAS_GFLOWS = True
except ImportError as e:
    log.warning("gflows modules not available: %s", e)
    HAS_GFLOWS = False


class GFlowsIntegrator:
    """Integrates G|Flows functionality into floww's ecosystem.

    Provides access to CBOE options data, treasury yield curves,
    OPEX calendar, and Greek exposure profile computations.

    Usage:
        gf = GFlowsIntegrator()
        # Fetch data from CBOE
        data = await gf.fetch_options_data("SPX", "all", is_json=True)
        # Or load from cached JSON files
        data = gf.load_cached_data("spx", is_json=True)
        # Get exposure profiles
        profiles = gf.compute_exposure_profiles(data)
        # Get treasury yield curve
        yields = gf.get_yield_curve()
    """

    def __init__(self, data_dir: Optional[str] = None):
        self._data_dir = data_dir or os.environ.get(
            "GFLOWS_DATA_DIR",
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "gflows_modules", "..", "data")
        )
        self._cached_yield_curve: Optional[Dict[str, float]] = None
        self._yield_curve_ts: Optional[float] = None
        self._yield_curve_ttl: int = 3600  # 1 hour cache

    # ------------------------------------------------------------------
    # CBOE Data Downloader
    # ------------------------------------------------------------------

    async def download_options_data(
        self, tickers: Optional[List[str]] = None, is_json: bool = True
    ) -> bool:
        """Download CBOE options data for specified tickers.

        Args:
            tickers: List of tickers (e.g., ['SPX', 'NDX', 'RUT']).
                     Defaults to SPX, NDX, RUT.
            is_json: True for JSON format, False for CSV.

        Returns:
            True if download succeeded.
        """
        if not HAS_GFLOWS:
            log.error("gflows modules not available — cannot download data")
            return False

        try:
            # Run download in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: dwn_data(
                    select=tickers,
                    is_json=is_json,
                )
            )
            log.info("CBOE data download complete for %s", tickers or ["SPX", "NDX", "RUT"])
            return True
        except Exception as e:
            log.error("CBOE data download failed: %s", e)
            return False

    def load_cached_data(
        self, ticker: str, is_json: bool = True, expir: str = "all"
    ) -> Optional[Dict[str, Any]]:
        """Load cached CBOE data from local JSON/CSV files.

        Args:
            ticker: Ticker symbol (lowercase, e.g., 'spx').
            is_json: True for JSON, False for CSV.
            expir: Expiration filter ('all', '0dte', 'opex', 'monthly').

        Returns:
            Tuple of computed exposures or None if data unavailable.
        """
        if not HAS_GFLOWS:
            log.error("gflows modules not available")
            return None

        try:
            result = get_options_data(
                ticker=ticker,
                expir=expir,
                is_json=is_json,
                tz="America/New_York",
            )
            if result and result[0] is not None:
                return self._pack_result(result)
            return None
        except Exception as e:
            log.warning("Failed to load cached data for %s: %s", ticker, e)
            return None

    def compute_exposure_profiles(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Compute Greek exposure profiles from loaded options data.

        Returns structured profile data ready for charting:
        - delta: Absolute, Calls/Puts, Profile views
        - gamma: Absolute, Calls/Puts, Profile views
        - vanna: Absolute, Profile views
        - charm: Absolute, Profile views
        - IV average: Call/Put IV curves
        - Zero delta/gamma flip points
        """
        result_data = data.get("raw_data")
        if result_data is None:
            return {"error": "No raw data available"}

        try:
            # The raw data includes exposures already computed
            df = result_data

            # Compute profiles at strike level
            from_strike = data.get("from_strike", data.get("spot", 5000) * 0.5)
            to_strike = data.get("to_strike", data.get("spot", 5000) * 1.5)

            # Aggregate by strike
            df_agg = df.groupby(["strike_price"]).sum(numeric_only=True).copy()
            df_agg = df_agg[from_strike:to_strike]

            strikes = df_agg.index.to_numpy()

            profiles = {
                "spot_price": data.get("spot", 0),
                "today_ddt_string": data.get("today_ddt_string", ""),
                "monthly_options_dates": data.get("monthly_options_dates", []),
                "zerodelta": data.get("zerodelta", 0),
                "zerogamma": data.get("zerogamma", 0),

                # Absolute exposures
                "delta_absolute": {
                    "strikes": strikes.tolist(),
                    "values": df_agg["total_delta"].to_numpy().tolist(),
                },
                "gamma_absolute": {
                    "strikes": strikes.tolist(),
                    "values": df_agg["total_gamma"].to_numpy().tolist(),
                },
                "vanna_absolute": {
                    "strikes": strikes.tolist(),
                    "values": df_agg["total_vanna"].to_numpy().tolist(),
                },
                "charm_absolute": {
                    "strikes": strikes.tolist(),
                    "values": df_agg["total_charm"].to_numpy().tolist(),
                },

                # Calls/Puts breakdown
                "delta_calls_puts": {
                    "strikes": strikes.tolist(),
                    "calls": (df_agg["call_dex"].to_numpy() / 10**9).tolist(),
                    "puts": (df_agg["put_dex"].to_numpy() / 10**9).tolist(),
                },
                "gamma_calls_puts": {
                    "strikes": strikes.tolist(),
                    "calls": (df_agg["call_gex"].to_numpy() / 10**9).tolist(),
                    "puts": (df_agg["put_gex"].to_numpy() / 10**9).tolist(),
                },

                # IV curves
                "iv_curves": {
                    "strikes": strikes.tolist(),
                    "call_iv": df_agg["call_iv"].to_numpy().tolist(),
                    "put_iv": df_agg["put_iv"].to_numpy().tolist(),
                },

                # Profile curves (all expiries, next expiry, monthly OPEX)
                "gamma_profile": {
                    "levels": data.get("levels", []),
                    "all": data.get("totalgamma", {}).get("all", []),
                    "ex_next": data.get("totalgamma", {}).get("ex_next", []),
                    "ex_fri": data.get("totalgamma", {}).get("ex_fri", []),
                },
                "delta_profile": {
                    "levels": data.get("levels", []),
                    "all": data.get("totaldelta", {}).get("all", []),
                    "ex_next": data.get("totaldelta", {}).get("ex_next", []),
                    "ex_fri": data.get("totaldelta", {}).get("ex_fri", []),
                },
                "vanna_profile": {
                    "levels": data.get("levels", []),
                    "all": data.get("totalvanna", {}).get("all", []),
                    "ex_next": data.get("totalvanna", {}).get("ex_next", []),
                    "ex_fri": data.get("totalvanna", {}).get("ex_fri", []),
                },
                "charm_profile": {
                    "levels": data.get("levels", []),
                    "all": data.get("totalcharm", {}).get("all", []),
                    "ex_next": data.get("totalcharm", {}).get("ex_next", []),
                    "ex_fri": data.get("totalcharm", {}).get("ex_fri", []),
                },
            }
            return profiles
        except Exception as e:
            log.error("Exposure profile computation error: %s", e)
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # Treasury Yield Curve
    # ------------------------------------------------------------------

    def get_yield_curve(self, force_refresh: bool = False) -> Dict[str, float]:
        """Get treasury yield curve with caching.

        Uses gflows' multi-tier fallback chain:
        FRED (primary) → yfinance (fallback) → default curve (last resort)

        Args:
            force_refresh: Bypass cache and fetch fresh data.

        Returns:
            Dict mapping tenor names to yield rates as decimals.
        """
        if not HAS_GFLOWS:
            return self._default_yield_curve()

        now = datetime.now(timezone.utc).timestamp()
        if (
            self._cached_yield_curve is not None
            and not force_refresh
            and (now - (self._yield_curve_ts or 0)) < self._yield_curve_ttl
        ):
            return self._cached_yield_curve

        try:
            curve = fetch_treasury_yield_curve()
            self._cached_yield_curve = curve
            self._yield_curve_ts = now
            return curve
        except Exception as e:
            log.warning("Yield curve fetch failed: %s", e)
            return self._default_yield_curve()

    def get_tenor_rate(
        self, days_to_expiry: int, yield_curve: Optional[Dict[str, float]] = None
    ) -> float:
        """Get the appropriate risk-free rate for a given days-to-expiry."""
        if not HAS_GFLOWS:
            return 0.030  # 3% default
        curve = yield_curve or self.get_yield_curve()
        try:
            return get_tenor_matched_rate(days_to_expiry, curve)
        except Exception:
            return 0.030

    # ------------------------------------------------------------------
    # OPEX Calendar
    # ------------------------------------------------------------------

    def get_opex_dates(
        self, year: int, month: int, tz: str = "America/New_York"
    ) -> Dict[str, Any]:
        """Get OPEX dates for a given month.

        Returns:
            Dict with third_friday, thursday_alt (if Friday is holiday),
            and calendar_range.
        """
        if not HAS_GFLOWS:
            return {"error": "gflows modules not available"}

        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo

            check_date = datetime(year, month, 1, tzinfo=ZoneInfo(tz))
            third_friday, calendar_range = is_third_friday(check_date, tz)
            next_monthly_opex = get_next_monthly_opex(check_date, tz)

            return {
                "third_friday": third_friday.isoformat() if third_friday else None,
                "next_monthly_opex": next_monthly_opex.isoformat() if next_monthly_opex else None,
                "calendar_range_start": calendar_range[0].isoformat() if len(calendar_range) > 0 else None,
                "calendar_range_end": calendar_range[-1].isoformat() if len(calendar_range) > 0 else None,
            }
        except Exception as e:
            log.warning("OPEX date calculation failed: %s", e)
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _pack_result(self, result: tuple) -> Dict[str, Any]:
        """Pack the gflows calc_exposures result tuple into a dict."""
        (
            option_data, today_ddt, today_ddt_string,
            monthly_options_dates, spot_price,
            from_strike, to_strike, levels,
            totaldelta, totalgamma, totalvanna, totalcharm,
            zerodelta, zerogamma, call_ivs, put_ivs,
        ) = result

        return {
            "raw_data": option_data,
            "today_ddt": today_ddt,
            "today_ddt_string": today_ddt_string,
            "monthly_options_dates": [d.isoformat() if hasattr(d, 'isoformat') else str(d) for d in monthly_options_dates],
            "spot": float(spot_price),
            "from_strike": float(from_strike),
            "to_strike": float(to_strike),
            "levels": [float(l) for l in levels],
            "totaldelta": {k: [float(v) for v in vals] for k, vals in totaldelta.items()},
            "totalgamma": {k: [float(v) for v in vals] for k, vals in totalgamma.items()},
            "totalvanna": {k: [float(v) for v in vals] for k, vals in totalvanna.items()},
            "totalcharm": {k: [float(v) for v in vals] for k, vals in totalcharm.items()},
            "zerodelta": float(zerodelta) if zerodelta is not None else 0,
            "zerogamma": float(zerogamma) if zerogamma is not None else 0,
        }

    @staticmethod
    def _default_yield_curve() -> Dict[str, float]:
        """Default neutral yield curve when gflows is unavailable."""
        return {
            "1mo": 0.025, "3mo": 0.027, "6mo": 0.029,
            "1yr": 0.030, "2yr": 0.031, "5yr": 0.033, "10yr": 0.035,
        }

    @staticmethod
    def get_available_tickers() -> List[str]:
        """Get tickers available in the CBOE data directory."""
        import glob
        import os

        data_dir = os.environ.get(
            "GFLOWS_DATA_DIR",
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "gflows_modules", "..", "data")
        )
        json_dir = os.path.join(os.path.dirname(data_dir), "data", "json")
        csv_dir = os.path.join(os.path.dirname(data_dir), "data", "csv")

        tickers = set()
        for d in [json_dir, csv_dir]:
            if os.path.exists(d):
                for f in glob.glob(os.path.join(d, "*_quotedata.*")):
                    name = os.path.basename(f).split("_quotedata")[0]
                    tickers.add(name.upper())

        return sorted(tickers) if tickers else ["SPX", "NDX", "RUT"]


# Global singleton
gflows_integrator = GFlowsIntegrator()
