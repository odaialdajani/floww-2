"""
backend/routes/quant.py

Quant signal catalog API — Phase 6.4.

Exposes the existing quant infrastructure as a catalog so the frontend can
browse available signals, their current state, and raw values without
duplicating logic between backend and frontend.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/quant", tags=["quant"])


@router.get("/signals")
async def quant_signal_catalog(
    ticker: str = Query("SPY", description="Ticker to evaluate signals for"),
) -> dict[str, Any]:
    """Return the catalog of available quant signals and their current values.

    Each signal entry includes:
        - name: canonical signal name
        - source: quant service that produces it
        - value: current numeric or categorical value (empty if unavailable)
        - unit: human-readable unit
        - description: one-line explanation
    """
    _ticker = ticker.get("ticker", ticker) if isinstance(ticker, dict) else ticker
    t = _ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"

    signals: list[dict[str, Any]] = []    # --- GEX regime signals (from signal_translator / GEX core) ---
    try:
        from signal_translator import SignalInput, translate_signal

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
                "description": "Translated GEX regime signal (buy_call / buy_put / hold / etc.)",
            })
        else:
            # translate_signal returned None — show the raw gex_state as the signal label
            signals.append({
                "name": "gex_regime",
                "source": "signal_translator",
                "value": "no_signal",
                "unit": "label",
                "description": "translate_signal returned None — insufficient conviction to emit a regime",
            })
    except Exception as e:
        logger.debug(f"gex_regime unavailable for {t}: {e}")

    # --- HMM regime classification ---
    try:
        from services.hmm_regime import GaussianHMMRegime

        hmm = GaussianHMMRegime()
        state = hmm.classify()  # no-arg: uses internal ticker state
        if state:
            signals.append({
                "name": "hmm_regime",
                "source": "hmm_regime",
                "value": state.get("state", state.get("label", "unknown")),
                "unit": "label",
                "description": "HMM-classified market regime (trending/ranging/volatile/quiet)",
            })
    except Exception as e:
        logger.debug(f"hmm_regime unavailable for {t}: {e}")

    # --- Composite flow score ---
    try:
        from services.composite_flow_score import CompositeFlowScore

        cfs = CompositeFlowScore()
        # compute() requires 5 dict inputs from upstream services
        # We pass empty dicts here — real values would come from /api/quant/full
        score = cfs.compute(
            amihud_out={},
            kyle_out={},
            vpin_out={},
            regime_out={},
            ofi_out={},
        )
        if score is not None:
            signals.append({
                "name": "composite_flow_score",
                "source": "composite_flow_score",
                "value": round(score.get("score", score.get("flow_score", 0)), 3),
                "unit": "index (-1..1)",
                "description": "Composite institutional flow score (negative = heavy put/flow selling)",
            })
    except Exception as e:
        logger.debug(f"composite_flow_score unavailable for {t}: {e}")

    # --- VPIN toxicity ---
    try:
        from services.vpin_toxicity import VPINToxicity

        vt = VPINToxicity()
        result = vt.compute()
        if result:
            signals.append({
                "name": "vpin_toxicity",
                "source": "vpin_toxicity",
                "value": round(result.get("z_score", result.get("toxicity", 0)), 4),
                "unit": "z-score",
                "description": "VPIN-based market toxicity measure (high = stressed/liquidated)",
            })
    except Exception as e:
        logger.debug(f"vpin_toxicity unavailable for {t}: {e}")

    # --- IV rank / percentile ---
    try:
        from vol_analytics import calc_iv_rank_percentile

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
        from vol_analytics import calc_realized_volatility

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
        from services.volume_clock import VolumeClock

        vc = VolumeClock()
        state = vc.get_state()
        if state:
            current = state.get("current", {})
            bucket_id = current.get("bucket_id", state.get("current_bucket", 0))
            # Bind fill_ratio out of the f-string: nesting the same quote character
            # inside an f-string expression is PEP 701 syntax (Python 3.12+), and this
            # service ships on python:3.11-slim (Dockerfile.backend) / CI python 3.11.
            fill_ratio = current.get("fill_ratio", 0)
            signals.append({
                "name": "volume_clock_bucket",
                "source": "volume_clock",
                "value": f"bucket_{bucket_id}",
                "unit": "label",
                "description": f"Current volume-clock bucket (fill_ratio={fill_ratio:.2f})",
            })
    except Exception as e:
        logger.debug(f"volume_clock unavailable for {t}: {e}")

    # --- IV surface metrics: NOT emitted here ---
    # calc_skew_metrics(vol_analytics) needs spot + the option chain, which this
    # catalog endpoint does not fetch. iv_skew comes from /api/quant/full instead.
    # (Was a try/except that only imported the symbol and never called it.)

    # --- Charm estimate: NOT emitted here ---
    # calc_charm_integral(advanced_analytics) needs ticker + the option chain,
    # same reason. charm comes from /api/quant/full instead.

    return {
        "ticker": t,
        "signals": signals,
        "count": len(signals),
    }
