"""
backend/routes/quant_full.py

Full quant signal endpoint — Phase 6.4 supplement.

Returns all 6 catalog signals PLUS spot, IV surface data, GEX totals,
and the full option chain (contracts) for a ticker. Uses the live heatmap
data so signals that need market data get real values.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/quant", tags=["quant"])


@router.get("/full")
async def quant_full(
    ticker: str = Query("SPY", description="Ticker to evaluate signals for"),
    expiries: int = Query(4, ge=1, le=12, description="Max expiries to fetch"),
) -> dict[str, Any]:
    """Return full quant signal data with live market data.

    Calls build_heatmap to get live spot, contracts, GEX totals, and IV surface.
    Falls back to empty fields if heatmap is unavailable.
    """
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"

    result: dict[str, Any] = {
        "ticker": t,
        "signals": [],
        "spot": 0.0,
        "iv_surface": {},
        "gex_totals": {},
        "contracts": [],
        "expiries": [],
        "data_source": "",
    }

    # --- Fetch live heatmap data ---
    try:
        from server import build_heatmap

        hm = await build_heatmap(t, max_expiries=expiries)
        if hm and hm.get("spot", 0) > 0:
            result["spot"] = hm.get("spot", 0)
            result["contracts"] = hm.get("contracts", [])
            result["expiries"] = hm.get("expiries", [])
            result["data_source"] = hm.get("data_source", "")
            result["gex_totals"] = {
                "total_gex": hm.get("nodes", {}).get("total_gex", 0),
                "total_call_gex": hm.get("nodes", {}).get("total_call_gex", 0),
                "total_put_gex": hm.get("nodes", {}).get("total_put_gex", 0),
                "total_vega": hm.get("nodes", {}).get("total_vega", 0),
                "total_charm": hm.get("nodes", {}).get("total_charm", 0),
                "max_pain": hm.get("nodes", {}).get("max_pain", 0),
                "king_strike": hm.get("nodes", {}).get("king", {}).get("strike", 0),
                "king_gex": hm.get("nodes", {}).get("king", {}).get("gex", 0),
                "polarity_level": hm.get("nodes", {}).get("polarity_level", ""),
                "regime": hm.get("nodes", {}).get("regime", ""),
            }
            if hm.get("nodes"):
                nodes = hm["nodes"]
                result["iv_surface"] = {
                    "atm_iv": nodes.get("atm_iv", 0),
                    "iv_rank": nodes.get("iv_rank", 0),
                    "iv_percentile": nodes.get("iv_percentile", 0),
                    "skew": nodes.get("skew", 0),
                    "term_structure": nodes.get("term_structure", {}),
                }
    except Exception as e:
        logger.debug(f"heatmap unavailable for {t}: {e}")

    # --- Catalog signals ---
    signals = await _catalog_signals(t)
    result["signals"] = signals

    return result


async def _catalog_signals(ticker: str) -> list[dict[str, Any]]:
    """Return the 6-signal catalog (same logic as /api/quant/signals)."""
    from services.composite_flow_score import CompositeFlowScore
    from services.hmm_regime import GaussianHMMRegime
    from services.signal_translator import SignalInput, translate_signal
    from services.volume_clock import VolumeClock
    from services.vpin_toxicity import VPINToxicity
    from vol_analytics import calc_iv_rank_percentile, calc_realized_volatility

    signals: list[dict[str, Any]] = []
    t = ticker

    # --- GEX regime ---
    try:
        regime_result = translate_signal(SignalInput(
            ticker=t,
            gex_state="",
            trinity_score=0.0,
            spot_price=0.0,
            anomaly_score=0.0,
            delta=0.5,
            stop_spot=0.0,
            multiplier=100,
            kelly_win_prob=0.5,
            kelly_avg_rr=2.0,
            account_equity=100000.0,
            current_positions={},
            flashalpha_sentiment_z=0.0,
            vpin_cdf=0.5,
            kyle_lambda=0.0,
        ))
        if regime_result:
            signals.append({
                "name": "gex_regime",
                "source": "signal_translator",
                "value": regime_result.get("signal_type", regime_result.get("gex_state", "")),
                "unit": "label",
                "description": "Translated GEX regime signal",
            })
        else:
            signals.append({
                "name": "gex_regime",
                "source": "signal_translator",
                "value": "no_signal",
                "unit": "label",
                "description": "translate_signal returned None",
            })
    except Exception as e:
        logger.debug(f"gex_regime unavailable for {t}: {e}")

    # --- HMM regime ---
    try:
        hmm = GaussianHMMRegime()
        state = hmm.classify()
        if state:
            signals.append({
                "name": "hmm_regime",
                "source": "hmm_regime",
                "value": state.get("state", state.get("label", "unknown")),
                "unit": "label",
                "description": "HMM-classified market regime",
            })
    except Exception as e:
        logger.debug(f"hmm_regime unavailable for {t}: {e}")

    # --- Composite flow score ---
    try:
        cfs = CompositeFlowScore()
        score = cfs.compute(
            amihud_out={}, kyle_out={}, vpin_out={},
            regime_out={}, ofi_out={},
        )
        if score is not None:
            signals.append({
                "name": "composite_flow_score",
                "source": "composite_flow_score",
                "value": round(score.get("score", score.get("flow_score", 0)), 3),
                "unit": "index (-1..1)",
                "description": "Composite institutional flow score",
            })
    except Exception as e:
        logger.debug(f"composite_flow_score unavailable for {t}: {e}")

    # --- VPIN toxicity ---
    try:
        vt = VPINToxicity()
        result_vt = vt.compute()
        if result_vt:
            signals.append({
                "name": "vpin_toxicity",
                "source": "vpin_toxicity",
                "value": round(result_vt.get("z_score", result_vt.get("toxicity", 0)), 4),
                "unit": "z-score",
                "description": "VPIN-based market toxicity",
            })
    except Exception as e:
        logger.debug(f"vpin_toxicity unavailable for {t}: {e}")

    # --- IV rank ---
    try:
        ivr = calc_iv_rank_percentile(t, 0.2)
        if ivr:
            signals.append({
                "name": "iv_rank",
                "source": "vol_analytics",
                "value": round(ivr.get("iv_rank", 0), 3),
                "unit": "percentile (0..1)",
                "description": "Implied volatility rank vs trailing window",
            })
    except Exception as e:
        logger.debug(f"iv_rank unavailable for {t}: {e}")

    # --- Realized volatility ---
    try:
        rv = calc_realized_volatility(t.replace("^", ""), 20)
        if rv:
            signals.append({
                "name": "realized_volatility_20d",
                "source": "vol_analytics",
                "value": round(rv.get("rv_close", 0), 4),
                "unit": "annualized vol",
                "description": "20-day realized volatility (annualized)",
            })
    except Exception as e:
        logger.debug(f"realized_volatility unavailable for {t}: {e}")

    # --- Volume clock ---
    try:
        vc = VolumeClock()
        state = vc.get_state()
        if state:
            current = state.get("current", {})
            bucket_id = current.get("bucket_id", state.get("current_bucket", 0))
            signals.append({
                "name": "volume_clock_bucket",
                "source": "volume_clock",
                "value": f"bucket_{bucket_id}",
                "unit": "label",
                "description": f"Current volume-clock bucket (fill_ratio={current.get('fill_ratio', 0):.2f})",
            })
    except Exception as e:
        logger.debug(f"volume_clock unavailable for {t}: {e}")

    return signals
