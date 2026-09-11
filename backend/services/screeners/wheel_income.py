"""
Wheel / Premium-Selling Income Screener (steal-list rank #3)
============================================================

Ranks cash-secured puts (CSPs) and covered calls by:

  * Annualized Return on Collateral (ARR%)
  * Breakeven distance (% of spot)
  * Liquidity floor (volume)
  * IV floor (cheap-premia guard)
  * Max-breakeven-distance cap (don't sell into pinned strikes)

This is the FIRST floww surface built for premium selling — the only
journal-validated edge the system has. Pure addition: does not modify
any existing vol analytics or GEX pipeline.

Approach mirrors ``fanzhenya/options_lab`` ``find_best_put_to_sell`` /
``find_best_call_to_sell``: per-contract ARR + breakeven math, then a
sortable rank. There is no broker execution and no compensation logic —
this is a SCREENER (rank candidates), not a trade ticket.

Steal from: fanzhenya/options_lab ``options_lab.ipynb`` — find_best_put_to_sell,
            find_best_call_to_sell, annualize_return / calc_put_breakeven
Lands in:    backend/services/screeners/wheel_income.py (this file)
             exposed via steal_three_server.py on :8001
             surface targeted at https://localhost:3000/steal-three

Audit: docs/reports/2026-07-11-steal-list-integration-roadmap.md #3
       tests/services/screeners/test_wheel_income.py
"""

from datetime import date, datetime
from typing import Any


def _arr_pct(mid_per_share: float, collateral_per_share: float, dte: int) -> float:
    """Annualized return on collateral, in percent.

    ASSUMES premium is collected up-front (CSP / covered call). For a CSP,
    collateral == strike (cash needed to buy 100 shares at K). For a CC,
    collateral == S (100 shares you already own). Returns 0.0 for invalid
    inputs (matches the silent-masking convention used elsewhere).
    """
    if mid_per_share <= 0 or collateral_per_share <= 0 or dte <= 0:
        return 0.0
    return (mid_per_share / collateral_per_share) * (365.0 / dte) * 100.0


def _normalize_contract(c: dict) -> dict | None:
    """Coerce a contract dict into the uniform shape used by the ranker.

    Accepts yfinance's option_chain row shape: {strike, lastPrice, bid, ask,
    iv, volume, openInterest, contractSymbol, ...}, or shapes from cvforge
    / databento: {strike, mid, iv/volume, T/dte/expiry, ...}. We only need
    the fields below; missing fields default to 0.
    """
    try:
        K = float(c.get("strike") or c.get("K") or 0)
    except (TypeError, ValueError):
        return None
    bid = float(c.get("bid") or 0.0)
    ask = float(c.get("ask") or 0.0)
    last = float(c.get("lastPrice") or c.get("last") or 0.0)
    if bid > 0 and ask > 0:
        mid = 0.5 * (bid + ask)
    else:
        mid = float(c.get("mid") or last or 0.0)
    iv = float(c.get("iv") or c.get("impliedVolatility") or 0.0)
    vol = int(float(c.get("volume") or c.get("vol") or 0))
    oi = int(float(c.get("openInterest") or c.get("oi") or 0))
    # No tradable market (2026-09-03): zero prints AND zero holders means
    # the mid is a phantom wide quote — annualizing it yields nonsense ARR
    # (e.g. 1600%+). Drop it here so both rankers never surface it.
    # Rows with OI but no volume today (existing holders) are kept.
    if vol == 0 and oi == 0:
        return None
    # dte comes from either T (years) or expiry (string) or dte (int)
    dte_raw = c.get("dte")
    if dte_raw is None:
        t = c.get("T") or c.get("tte")
        if t is not None:
            try:
                dte = max(int(float(t) * 365), 0)
            except (TypeError, ValueError):
                dte = 0
        else:
            # yfinance chain rows carry only the expiry string — derive dte
            # from it (the documented contract; without this every bare row
            # normalized to dte=0 and the ranker dropped it).
            dte = 0
            exp_s = c.get("expiry") or c.get("expiration")
            if exp_s:
                try:
                    dte = max(
                        (datetime.strptime(str(exp_s), "%Y-%m-%d").date() - date.today()).days,
                        0,
                    )
                except ValueError:
                    dte = 0
    else:
        try:
            dte = int(float(dte_raw))
        except (TypeError, ValueError):
            dte = 0
    return {
        "strike": K,
        "mid": mid,
        "iv": iv,
        "volume": vol,
        "openInterest": oi,
        "dte": dte,
        "expiry": str(c.get("expiry") or c.get("expiration") or ""),
    }


def rank_puts_to_sell(
    raw_puts: list[dict],
    spot: float,
    min_iv: float = 0.0,
    min_volume: int = 0,
    min_dte: int = 1,
    max_dte: int = 60,
    min_breakeven_drop_pct: float = 0.02,  # breakeven must be ≥ 2% below spot
    top: int = 25,
) -> list[dict]:
    """Rank cash-secured puts by annualized return on collateral.

    Output entries include fields the UI can render directly:
        strike, expiry, mid, iv, volume, dte,
        breakeven, breakeven_drop_pct, annualized_return_pct, side.

    Sorted by annualized_return_pct DESC. Sorted defenses (no network).
    """
    out: list[dict] = []
    for raw in raw_puts or []:
        c = _normalize_contract(raw)
        if c is None or c["strike"] <= 0 or c["mid"] <= 0 or c["dte"] <= 0:
            continue
        if not (min_dte <= c["dte"] <= max_dte):
            continue
        if c["iv"] < min_iv:
            continue
        if c["volume"] < min_volume:
            continue
        breakeven = c["strike"] - c["mid"]
        drop_pct = (spot - breakeven) / spot if spot > 0 else 0.0
        if drop_pct < min_breakeven_drop_pct:
            continue
        arr = _arr_pct(c["mid"], collateral_per_share=c["strike"], dte=c["dte"])
        if arr <= 0:
            continue
        out.append({
            "side": "put",
            "strike": c["strike"],
            "expiry": c["expiry"],
            "dte": c["dte"],
            "mid": round(c["mid"], 4),
            "iv": round(c["iv"], 4),
            "volume": c["volume"],
            "openInterest": c["openInterest"],
            "breakeven": round(breakeven, 2),
            "breakeven_drop_pct": round(drop_pct * 100.0, 2),
            "annualized_return_pct": round(arr, 2),
        })
    out.sort(key=lambda r: r["annualized_return_pct"], reverse=True)
    return out[:top]


def rank_calls_to_sell(
    raw_calls: list[dict],
    spot: float,
    min_iv: float = 0.0,
    min_volume: int = 0,
    min_dte: int = 1,
    max_dte: int = 60,
    min_strike_premium_pct: float = 0.005,  # strike at least 0.5% OTM
    top: int = 25,
) -> list[dict]:
    """Rank covered calls by annualized return on collateral (= spot at sale).

    For a covered call, collateral is the 100 shares the trader is assumed
    to own — valued at spot at the moment of the screen. Strike filter
    requires ≥ min_strike_premium_pct above spot (no deep-ITM lottery-ticket
    candidates; those dominate ARR but get pinned).
    """
    out: list[dict] = []
    if spot <= 0:
        return out
    for raw in raw_calls or []:
        c = _normalize_contract(raw)
        if c is None or c["strike"] <= 0 or c["mid"] <= 0 or c["dte"] <= 0:
            continue
        if not (min_dte <= c["dte"] <= max_dte):
            continue
        if c["iv"] < min_iv:
            continue
        if c["volume"] < min_volume:
            continue
        otm_pct = (c["strike"] - spot) / spot
        if otm_pct < min_strike_premium_pct:
            continue
        arr = _arr_pct(c["mid"], collateral_per_share=spot, dte=c["dte"])
        if arr <= 0:
            continue
        out.append({
            "side": "call",
            "strike": c["strike"],
            "expiry": c["expiry"],
            "dte": c["dte"],
            "mid": round(c["mid"], 4),
            "iv": round(c["iv"], 4),
            "volume": c["volume"],
            "openInterest": c["openInterest"],
            "breakeven": round(c["strike"] + c["mid"], 2),
            "otm_pct": round(otm_pct * 100.0, 2),
            "max_yield_at_strike_pct": round(c["mid"] / spot * 100.0, 2),
            "annualized_return_pct": round(arr, 2),
        })
    out.sort(key=lambda r: r["annualized_return_pct"], reverse=True)
    return out[:top]


def rank(
    raw_puts: list[dict],
    raw_calls: list[dict],
    spot: float,
    **filters: Any,
) -> dict[str, list[dict]]:
    """One-shot both-sides rank. Returns ``{"puts": [...], "calls": [...]}``."""
    return {
        "puts": rank_puts_to_sell(raw_puts, spot, **filters),
        "calls": rank_calls_to_sell(raw_calls, spot, **filters),
    }
