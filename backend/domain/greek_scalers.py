"""backend/domain/greek_scalers.py — Convention-named scaling helpers.

Routes every Charm Flip / GDW / CAR metric through a SINGLE source of
truth so consumers don't drift between per-unit-σ / per-1%-σ / per-1%-move
conventions and accidentally 100× the dollar P&L estimates.

Why these helpers
==================
The BS primitives in ``bs_greeks.py`` return:

  - vega, vomma, zomma: **per unit-σ** (a 1.0 vol change). The Hull Table
    pin test (``tests/test_bs_greeks_hull_table.py::test_vega_per_1pct_matches_hull``)
    derives the per-1%-σ value via ``vega / 100``.
  - vanna, charm: **per UNIT spot move / per UNIT time** respectively.
  - charm: **per YEAR** (T in years). To get per-trading-day: ``/252``.

The platform-wide dollar exposure convention
=============================================
``bs_greeks.dollar_*_per_contract`` exposes the *spot-1%-move* scaled
dollar view used by every dashboard across ``backend``. The convention
is pinned by ``tests/test_dollar_gex_convention.py`` against the
SqueezeMetrics/SpotGamma published band:

  GEX_per_contract  = γ * OI * 100 * spot² * 0.01   (γ units [1/spot²])
  VEX_per_contract  = vanna * OI * 100 * spot * 0.01  (vanna units [1/spot])
  charm_per_contract = charm * OI * 100 * spot * 0.01  (charm per YEAR, scaled to per-1%-spot-move)
  vomma_per_contract = vomma * OI * 100             (no spot factor — vomma units [1/σ²])
  vega_per_contract  = vega * OI * 100              (no spot factor — vega per-UNIT-σ)

This module adds **explicit-name** aliases and **per-1%-σ / per-day**
scalers so the call sites read like the spec they enforce.

Migrating call sites
====================
Replace::

  vex_unit = vanna * oi * 100                # BUG: missing spot * 0.01
  vex_unit = vanna * oi * 100 * spot          # BUG: missing 0.01 (per-spot-1%-move)
  vap_unit = vanna * oi *                     # BUG: missing CONTRACT_MULTIPLIER

with::

  from domain.greek_scalers import dollar_vex_per_1pct_spot_move
  vex_unit = dollar_vex_per_1pct_spot_move(vanna, oi, spot)
"""
from __future__ import annotations

from typing import Final

from bs_greeks import (
    CONTRACT_MULTIPLIER,
    DOLLAR_MOVE_CONVENTION,
    dollar_charm_per_contract,
    dollar_vex_per_contract,
)

# ── Time-unit conversions ────────────────────────────────────────────────
TRADING_DAYS_PER_YEAR: Final[float] = 252.0


# ── Vanna (VEX) scaling ─────────────────────────────────────────────────
def dollar_vex_per_1pct_spot_move(vanna: float, oi: float, spot: float) -> float:
    """Per-contract dollar VEX if the underlying moves UP 1%.

    Mathematically identical to ``bs_greeks.dollar_vex_per_contract`` —
    re-exported under a name that makes the convention obvious at the
    call site (``vanna_exposure_endpoint``, ``calc_vex``).

    Returns: ``vanna * OI * 100 * spot * 0.01``.
    """
    return dollar_vex_per_contract(vanna, oi, spot)


def dollar_vex_per_unit_sigma(vanna: float, oi: float, spot: float) -> float:
    """Per-contract dollar VEX for a UNIT (1.0) sigma change (no 0.01).

    Use this when a downstream metric will further divide by 100 to
    derive the per-1%-σ equivalent. Avoid for trading-floor display
    unless you specifically need per-unit-σ dollar exposure.
    """
    return vanna * oi * CONTRACT_MULTIPLIER * spot


def dollar_vex_per_1pct_vol_change(vanna: float, oi: float, spot: float) -> float:
    """Per-contract dollar VEX for a 1%-σ change in implied vol.

    This is "the vol was 20%, now it's 21% — what's the per-contract
    delta change times the spot move required to hedge it?" Useful
    for Charm Flip / GDW / CAR calculations that combine vega
    exposure with vol surprise shock scenarios.

    R7-F03 correction (units v1): a +1 volatility-point shock is
    Δσ = 0.01, so the factor is DOLLAR_MOVE_CONVENTION (0.01) — the
    same convention as dollar_vega_per_1pct_vol_change below. The
    previous ``(1 - DOLLAR_MOVE_CONVENTION)`` = 0.99 factor described
    a 99%-σ shock, contradicting the name/docstring (99× too large:
    198,000 vs 2,000 for vanna .2 / OI 100 / spot 100). No production
    caller existed; the pinning test is rewritten as an oracle below.

    Returns: ``vanna * OI * 100 * spot * 0.01``.
    """
    return vanna * oi * CONTRACT_MULTIPLIER * spot * DOLLAR_MOVE_CONVENTION


# ── Vega scaling ──────────────────────────────────────────────────────
def dollar_vega_per_1pct_vol_change(vega: float, oi: float) -> float:
    """Per-contract dollar Vega for a 1 percentage-point (0.01 σ) change.

    Industry-standard display convention for the trading floor. Raw
    ``bs_vega`` returns per-UNIT-σ; this divides by 100 implicitly by
    scaling the OI-weighted dollar exposure by ``DOLLAR_MOVE_CONVENTION``.

    Returns: ``vega * OI * 100 * 0.01``.
    """
    return vega * oi * CONTRACT_MULTIPLIER * DOLLAR_MOVE_CONVENTION


# ── Charm scaling ──────────────────────────────────────────────────────
def charm_per_day(charm_annual: float) -> float:
    """Convert charm from per-YEAR (T in years) to per-TRADING-DAY.

    The underlying BS primitive ``bs_charm`` returns charm per calendar
    year because ``T`` is in years. Trading-floor metrics that report
    P&L over a daily horizon (≈ 6.5 trading hours) want per-day charm:
    divide by ``TRADING_DAYS_PER_YEAR``.
    """
    return charm_annual / TRADING_DAYS_PER_YEAR


def dollar_charm_per_day(charm_annual: float, oi: float, spot: float) -> float:
    """Per-contract dollar Charm per trading day.

    Equivalent to ``bs_greeks.dollar_charm_per_contract(charm_annual)``
    divided by ``TRADING_DAYS_PER_YEAR`` — explicitly named to match
    common Charm Flip API contracts that report "USD of delta flipping
    per day per contract".
    """
    return dollar_charm_per_contract(charm_annual, oi, spot) / TRADING_DAYS_PER_YEAR


__all__ = [
    "TRADING_DAYS_PER_YEAR",
    "dollar_vex_per_1pct_spot_move",
    "dollar_vex_per_unit_sigma",
    "dollar_vex_per_1pct_vol_change",
    "dollar_vega_per_1pct_vol_change",
    "charm_per_day",
    "dollar_charm_per_day",
]
