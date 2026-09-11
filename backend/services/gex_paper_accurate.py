"""
backend/services/gex_paper_accurate.py

Paper-accurate GEX metrics implementing the methodology from:

  Paper #1 — Ni, Pearson, Poteshman & White (2021)
    "Does Option Trading Have a Pervasive Impact on Underlying Stock Prices?"
    SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2867461

  Paper #2 — Barbon & Buraschi (2021)
    "Gamma Fragility"
    SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3725454

This module adds the paper-prescribed normalizations and decompositions
that the practitioner GEX formula (gamma × OI × 100 × S² × 0.01) alone
does not capture. The raw dollar GEX computation is unchanged — this
module WRAPS it with the academic risk metrics proven in the literature.

Key additions over the raw practitioner GEX:
  1. Gamma Imbalance (% of ADV) — Barbon-Buraschi Eq. (2)
  2. Zero-Gamma Flip Distance — Barbon-Buraschi Section II.B
  3. Intraday Regime Signal (momentum vs reversal) — Barbon-Buraschi Sec. I
  4. Gamma Decomposition (Hedge vs Info) — Ni-Pearson Sec. 3
  5. Flash Crash Probability Proxy — Barbon-Buraschi Sec. III.C
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# 1. Gamma Imbalance (Barbon-Buraschi Eq. 2)
#    ΓIB_i(t) = Hedgers Gamma_i × S_i(t) / ADSV_i(t)
#
#    Note on scale: the paper defines ΓIB as raw gamma×inventory×S/ADSV
#    (units: $/share). Our practitioner GEX = γ×OI×100×S²×0.01. Converting
#    back: raw γ×OI = GEX/S², so paper ΓIB = GEX/(S×ADSV). Our computation
#    additionally multiplies by 100/(S×0.01) ≈ 13× for SPY at $768. This
#    preserves relative ordering (paper uses standardized ΓIB in regressions)
#    but absolute values differ from the paper's raw scale. For cross-stock
#    comparability, normalize by the same formula consistently.
# ---------------------------------------------------------------------------

def compute_gamma_imbalance(
    net_gex_dollars: float,
    spot: float,
    adv_shares: float,
) -> dict[str, Any]:
    """Compute the Barbon-Buraschi Gamma Imbalance (% of ADV).

    Args:
        net_gex_dollars: Net dollar GEX (Σ sign × gamma × OI × 100 × S² × 0.01)
        spot: Underlying price
        adv_shares: Average daily share volume (21-day rolling)

    Returns:
        dict with gamma_imbalance_pct, regime, and interpretation
    """
    if spot <= 0 or adv_shares <= 0:
        return {
            "gamma_imbalance_pct": 0.0,
            "gamma_imbalance_dollars_per_share": 0.0,
            "regime": "insufficient_data",
            "interpretation": "Cannot compute — missing spot or ADV data.",
        }

    # ΓIB = (Net GEX in dollars) / (S × ADSV) × 100
    # Net GEX is already in dollars-per-1%-move
    # First convert to dollars-per-$1-move: divide by (S × 0.01)
    # Then normalize by daily dollar volume: divide by (S × ADSV)
    # Simplification: ΓIB_pct = net_gex / (S² × 0.01 × ADSV) × 100

    daily_dollar_volume = spot * adv_shares
    if daily_dollar_volume <= 0:
        return {
            "gamma_imbalance_pct": 0.0,
            "gamma_imbalance_dollars_per_share": 0.0,
            "regime": "zero_volume",
            "interpretation": "Zero ADV — cannot normalize.",
        }

    # The practitioner GEX is already per-1%-move. The paper ΓIB normalizes
    # raw gamma×inventory by ADSV. We convert: raw_gamma_dollars = GEX / (S × 0.01)
    # Then ΓIB = raw_gamma_dollars / (S × ADSV) × 100
    #       = GEX / (S² × 0.01 × ADSV) × 100
    gamma_imbalance_pct = (net_gex_dollars / (spot * spot * 0.01 * adv_shares)) * 100.0

    # Also compute as dollars-per-share for display
    gamma_imbalance_dollars_per_share = net_gex_dollars / adv_shares if adv_shares > 0 else 0.0

    # Regime classification per Barbon-Buraschi:
    #   ΓIB > 0  → positive gamma → stabilizing (dealers mean-revert)
    #   ΓIB < 0  → negative gamma → destabilizing (dealers amplify)
    if gamma_imbalance_pct > 1.0:
        regime = "strong_positive_gamma"
        interpretation = (
            "Dealers strongly net long gamma — hedging is counter-cyclical. "
            "Expect intraday mean reversion and compressed volatility. "
            "Favorable for selling premium."
        )
    elif gamma_imbalance_pct > 0.1:
        regime = "positive_gamma"
        interpretation = (
            "Dealers net long gamma — hedging provides modest stabilization. "
            "Mild mean reversion expected."
        )
    elif gamma_imbalance_pct > -0.1:
        regime = "neutral_gamma"
        interpretation = (
            "Gamma imbalance near zero — dealer hedging has minimal directional impact. "
            "Volatility driven by other factors."
        )
    elif gamma_imbalance_pct > -1.0:
        regime = "negative_gamma"
        interpretation = (
            "Dealers net short gamma — hedging is pro-cyclical. "
            "Expect intraday momentum and elevated volatility. "
            "Gamma squeeze risk elevated."
        )
    else:
        regime = "strong_negative_gamma"
        interpretation = (
            "Dealers strongly net short gamma — hedging AMPLIFIES moves. "
            "Flash crash risk significantly elevated. "
            "Expect strong intraday momentum and wide ranges. Avoid short gamma strategies."
        )

    return {
        "gamma_imbalance_pct": round(gamma_imbalance_pct, 4),
        "gamma_imbalance_dollars_per_share": round(gamma_imbalance_dollars_per_share, 4),
        "regime": regime,
        "interpretation": interpretation,
        "spot": spot,
        "adv_shares": adv_shares,
        "net_gex_dollars": net_gex_dollars,
    }


# ---------------------------------------------------------------------------
# 2. Zero-Gamma Flip Distance (Barbon-Buraschi Section II.B)
#
#    The "Zero-Gamma Flip" is the price level where aggregate dealer gamma
#    transitions from positive to negative. Barbon-Buraschi shows this is
#    a critical regime boundary — crossing it triggers a shift from
#    stabilizing to destabilizing dealer hedging.
#
#    flip_distance_pct = (spot - flip_level) / spot × 100
#
#    Positive → spot is above flip → positive gamma regime (safe)
#    Negative → spot is below flip → negative gamma regime (risk)
# ---------------------------------------------------------------------------

def compute_flip_metrics(
    spot: float,
    zero_gamma_level: float | None,
    net_gex: float,
) -> dict[str, Any]:
    """Compute flip-level distance and regime proximity metrics.

    Args:
        spot: Current underlying price
        zero_gamma_level: Interpolated price where net GEX = 0
        net_gex: Current net dollar GEX

    Returns:
        dict with flip_distance_pct, regime, fragility_warning
    """
    if zero_gamma_level is None or zero_gamma_level <= 0 or spot <= 0:
        return {
            "flip_distance_pct": None,
            "flip_level": zero_gamma_level,
            "regime": "unknown",
            "fragility_warning": False,
            "warning_text": "",
        }

    flip_distance_pct = ((spot - zero_gamma_level) / spot) * 100.0

    # Barbon-Buraschi find that effects are strongest when the index
    # is within ~2-3% of the flip level. Within 1% = critical zone.
    fragility = False
    warning = ""
    if abs(flip_distance_pct) < 1.0:
        fragility = True
        direction = "above" if flip_distance_pct > 0 else "below"
        warning = (
            f"CRITICAL: Spot is within 1% of zero-gamma flip at ${zero_gamma_level:.2f}. "
            f"A {abs(flip_distance_pct):.1f}% move {direction} triggers regime flip. "
            "Dealer hedging direction will reverse — expect sharp acceleration."
        )
    elif abs(flip_distance_pct) < 2.5:
        warning = (
            f"WARNING: Spot within 2.5% of zero-gamma flip at ${zero_gamma_level:.2f}. "
            "Monitor closely for potential regime transition."
        )

    if flip_distance_pct > 2.5:
        regime = "safe_positive_gamma"
    elif flip_distance_pct > 0:
        regime = "positive_gamma_approach_flip"
    elif flip_distance_pct > -2.5:
        regime = "negative_gamma_approach_flip"
    else:
        regime = "deep_negative_gamma"

    return {
        "flip_distance_pct": round(flip_distance_pct, 4),
        "flip_level": round(zero_gamma_level, 2),
        "spot": spot,
        "net_gex": net_gex,
        "regime": regime,
        "fragility_warning": fragility,
        "warning_text": warning,
    }


# ---------------------------------------------------------------------------
# 3. Intraday Regime Signal — Momentum vs Reversal
#    (Barbon-Buraschi Section III.B)
#
#    Negative gamma imbalance → positive autocorrelation (momentum)
#    Positive gamma imbalance → negative autocorrelation (reversal)
#
#    The paper finds this effect is strongest at h=60 minute horizon,
#    consistent with dealers adjusting hedges intraday.
# ---------------------------------------------------------------------------

def predict_intraday_regime(
    gamma_imbalance_pct: float,
    flip_distance_pct: float | None = None,
) -> dict[str, Any]:
    """Predict intraday momentum vs reversal regime from gamma imbalance.

    Per Barbon-Buraschi Table II/III:
      - Negative ΓIB → dealers short gamma → sell into declines →
        POSITIVE autocorrelation (momentum/trend continuation)
      - Positive ΓIB → dealers long gamma → buy dips, sell rips →
        NEGATIVE autocorrelation (mean reversion)

    Args:
        gamma_imbalance_pct: ΓIB as percent of ADV
        flip_distance_pct: Optional distance to zero-gamma flip for confidence

    Returns:
        dict with predicted_regime, expected_autocorr_sign, confidence
    """
    # Default confidence based on ΓIB magnitude
    abs_gib = abs(gamma_imbalance_pct)

    if abs_gib > 2.0:
        confidence = "high"
    elif abs_gib > 0.5:
        confidence = "medium"
    elif abs_gib > 0.1:
        confidence = "low"
    else:
        confidence = "negligible"

    # Increase confidence near the flip level
    if flip_distance_pct is not None and abs(flip_distance_pct) < 2.0:
        if confidence == "low":
            confidence = "medium"
        elif confidence == "medium":
            confidence = "high"

    if gamma_imbalance_pct < -1.0:
        regime = "momentum"
        autocorr_sign = "positive"
        description = (
            "Strong negative gamma — dealer hedging amplifies trends. "
            "Expect intraday MOMENTUM: trends persist, breakouts run, "
            "reversals are false. Avoid fading moves. Ride the trend."
        )
    elif gamma_imbalance_pct < -0.1:
        regime = "mild_momentum"
        autocorr_sign = "positive"
        description = (
            "Mild negative gamma — slight trend amplification. "
            "Weaker momentum than strong negative regime."
        )
    elif gamma_imbalance_pct > 1.0:
        regime = "mean_reversion"
        autocorr_sign = "negative"
        description = (
            "Strong positive gamma — dealer hedging dampens trends. "
            "Expect intraday MEAN REVERSION: rallies fade, dips bought. "
            "Favorable for range-bound strategies, selling premium."
        )
    elif gamma_imbalance_pct > 0.1:
        regime = "mild_reversal"
        autocorr_sign = "negative"
        description = (
            "Mild positive gamma — slight mean reversion bias."
        )
    else:
        regime = "neutral"
        autocorr_sign = "none"
        description = (
            "Gamma near neutral — no strong intraday bias from dealer hedging."
        )

    return {
        "predicted_regime": regime,
        "expected_autocorr_sign": autocorr_sign,
        "confidence": confidence,
        "description": description,
        "gamma_imbalance_pct": round(gamma_imbalance_pct, 4),
    }


# ---------------------------------------------------------------------------
# 4. Gamma Decomposition — HedgeGamma vs InfoGamma
#    (Ni-Pearson Internet Appendix, Section 3)
#
#    The total net position gamma can be decomposed into:
#      HedgeGamma(t-τ,t) = component due to past stock price changes
#        — measures how much gamma changed because spot moved
#        — dealers MUST hedge this mechanically
#      InfoGamma(t-τ,t) = component due to changes in option positions
#        — measures how much gamma changed because OI changed
#        — reflects informed options flow
#      Gamma(t-τ, S_{t-τ}) = gamma from τ days ago at old spot
#        — baseline reference level
#
#    The paper finds:
#      - HedgeGamma is the STRONGEST predictor of future |returns|
#      - Negative HedgeGamma → higher subsequent volatility
#      - InfoGamma also predicts volatility but with smaller magnitude
#      - HedgeGamma interacts with direction: negative gamma + negative
#        returns → momentum continuation (dealers sell more)
# ---------------------------------------------------------------------------

def decompose_gamma(
    current_gex: float,              # GEX(S_t, OI_t)  — today's GEX at today's spot
    gex_at_old_spot: float | None,   # GEX(S_t, OI_{t-τ})  — old OI at today's spot
    gex_at_old_spot_old_oi: float | None,  # GEX(S_{t-τ}, OI_{t-τ}) — old OI at old spot
) -> dict[str, Any]:
    """Decompose net gamma change into Hedge and Information components.

    Follows Ni-Pearson decomposition (Internet Appendix, Section 3):

      HedgeGamma(t-τ,t) = GEX(S_t, OI_{t-τ}) - GEX(S_{t-τ}, OI_{t-τ})
        → change due to spot moving (MECHANICAL dealer hedging)

      InfoGamma(t-τ,t) = GEX(S_t, OI_t) - GEX(S_t, OI_{t-τ})
        → change due to OI changing (INFORMED options flow)

    Paper finding: HedgeGamma is the strongest predictor of future
    absolute returns. One std dev lower HedgeGamma → ~50 bps higher |return|.

    Args:
        current_gex: Today's GEX at today's spot and today's OI
        gex_at_old_spot: Today's GEX recomputed with OLD OI at today's spot
        gex_at_old_spot_old_oi: GEX at old spot with old OI (τ days ago)

    Returns:
        dict with hedge_gamma, info_gamma, total_change
    """
    if gex_at_old_spot is None and gex_at_old_spot_old_oi is None:
        return {
            "hedge_gamma": None,
            "info_gamma": None,
            "old_baseline_gamma": None,
            "total_change": None,
            "decomposition_available": False,
            "interpretation": "Insufficient data for decomposition — need prior GEX snapshots.",
        }

    # Default: if we don't have both historical snapshots, we can't decompose
    if gex_at_old_spot is None or gex_at_old_spot_old_oi is None:
        return {
            "hedge_gamma": None,
            "info_gamma": None,
            "old_baseline_gamma": gex_at_old_spot_old_oi,
            "total_change": current_gex - (gex_at_old_spot_old_oi or current_gex),
            "decomposition_available": False,
            "interpretation": "Partial data — full decomposition requires both old OI at new spot and old OI at old spot.",
        }

    hedge_gamma = gex_at_old_spot - gex_at_old_spot_old_oi
    info_gamma = current_gex - gex_at_old_spot
    total_change = current_gex - gex_at_old_spot_old_oi

    # Interpretation per Ni-Pearson:
    #   Negative HedgeGamma + negative returns → dealers sell → momentum
    #   Negative HedgeGamma + positive returns → dealers buy → momentum
    #   Positive HedgeGamma → stabilizing regardless of direction
    hedge_interpretation = ""
    if hedge_gamma < -1e8:  # threshold for "large negative"
        hedge_interpretation = (
            "Large negative HedgeGamma — spot moved against dealer positioning. "
            "Dealers likely forced to hedge, amplifying recent price move. "
            "Expect: elevated subsequent volatility (Ni-Pearson coefficient ≈ -0.3 to -0.6)."
        )
    elif hedge_gamma < 0:
        hedge_interpretation = "Negative HedgeGamma — minor dealer hedging pressure."
    elif hedge_gamma > 1e8:
        hedge_interpretation = (
            "Large positive HedgeGamma — spot moved favorably for dealer book. "
            "Dealers may reduce hedges, dampening volatility."
        )
    else:
        hedge_interpretation = "HedgeGamma near zero — minimal mechanical hedging impact."

    info_interpretation = ""
    if abs(info_gamma) > 1e8:
        direction = "increased" if info_gamma > 0 else "decreased"
        info_interpretation = (
            f"Significant InfoGamma — options positions {direction} net gamma by ${abs(info_gamma)/1e9:.2f}B. "
            "Indicates informed options flow entering/exiting."
        )
    else:
        info_interpretation = "InfoGamma near zero — no significant options position changes."

    return {
        "hedge_gamma": round(hedge_gamma, 2),
        "info_gamma": round(info_gamma, 2),
        "old_baseline_gamma": round(gex_at_old_spot_old_oi, 2),
        "current_gamma": round(current_gex, 2),
        "total_change": round(total_change, 2),
        "decomposition_available": True,
        "hedge_interpretation": hedge_interpretation,
        "info_interpretation": info_interpretation,
    }


# ---------------------------------------------------------------------------
# 5. Flash Crash Probability Proxy (Barbon-Buraschi Section III.C)
#
#    The paper finds that negative gamma imbalance is associated with
#    higher frequency and magnitude of flash crash events. Conditional
#    on negative ex-ante gamma imbalance, flash crashes are more likely
#    and larger in magnitude.
#
#    We provide a heuristic probability score based on:
#      - Gamma imbalance magnitude and sign
#      - Distance to zero-gamma flip
#      - Illiquidity (Amihud proxy)
# ---------------------------------------------------------------------------

def flash_crash_risk(
    gamma_imbalance_pct: float,
    flip_distance_pct: float | None = None,
    amihud_illiquidity: float | None = None,
    net_gex: float = 0.0,
) -> dict[str, Any]:
    """Classify flash crash fragility from gamma imbalance.

    Heuristic tag only — this function does not estimate a numeric crash
    probability. Barbon-Buraschi finding (Table V): one std dev decrease
    in ΓIB → ~16 bps increase in daily High-Low spread, and the effect is
    stronger for illiquid stocks and near the flip level.

    Args:
        gamma_imbalance_pct: ΓIB as percent of ADV
        flip_distance_pct: Distance to zero-gamma flip (%)
        amihud_illiquidity: Amihud illiquidity ratio (|return|/dollar_volume)
        net_gex: Raw net dollar GEX for context

    Returns:
        dict with risk_level, stability (fragile/stable), warning flags
    """
    # Base risk from gamma imbalance sign and magnitude
    if gamma_imbalance_pct > 2.0:
        base_risk = 0.01  # 1% — very low
    elif gamma_imbalance_pct > 0.5:
        base_risk = 0.03  # 3%
    elif gamma_imbalance_pct > -0.5:
        base_risk = 0.08  # 8% — neutral zone
    elif gamma_imbalance_pct > -2.0:
        base_risk = 0.18  # 18% — negative gamma
    elif gamma_imbalance_pct > -5.0:
        base_risk = 0.30  # 30% — strong negative
    else:
        base_risk = 0.50  # 50% — extreme negative

    # Amplify near flip level (Barbon-Buraschi: effects strongest near flip)
    if flip_distance_pct is not None and abs(flip_distance_pct) < 1.0:
        base_risk *= 1.5
    elif flip_distance_pct is not None and abs(flip_distance_pct) < 2.5:
        base_risk *= 1.2

    # Amplify for illiquid stocks (Barbon-Buraschi interaction term)
    illiquidity_factor = 1.0
    if amihud_illiquidity is not None and amihud_illiquidity > 0:
        # Normalize: Amihud > 1e-6 is considered illiquid
        if amihud_illiquidity > 1e-5:
            illiquidity_factor = 1.5
        elif amihud_illiquidity > 1e-6:
            illiquidity_factor = 1.2

    crash_prob = min(base_risk * illiquidity_factor, 0.95)

    # Risk classification
    if crash_prob > 0.35:
        risk_level = "EXTREME"
        recommendation = (
            "EXTREME FLASH CRASH RISK. Dealer gamma profile highly unstable. "
            "Reduce position sizes, widen stops, avoid illiquid names. "
            "Consider long vol / tail hedge strategies."
        )
    elif crash_prob > 0.20:
        risk_level = "HIGH"
        recommendation = (
            "HIGH flash crash risk. Negative gamma + proximity to flip. "
            "Use tighter stops, favor liquid names, monitor intraday volume spikes."
        )
    elif crash_prob > 0.10:
        risk_level = "ELEVATED"
        recommendation = (
            "Elevated crash risk. Monitor gamma profile for deterioration. "
            "Standard risk controls sufficient."
        )
    elif crash_prob > 0.05:
        risk_level = "MODERATE"
        recommendation = "Moderate risk — normal market conditions."
    else:
        risk_level = "LOW"
        recommendation = (
            "Low flash crash risk. Positive gamma regime — dealer hedging "
            "provides structural stabilization."
        )

    stability = "fragile" if risk_level in ("EXTREME", "HIGH", "ELEVATED") else "stable"

    return {
        "risk_level": risk_level,
        "stability": stability,
        "gamma_imbalance_pct": round(gamma_imbalance_pct, 4),
        "flip_distance_pct": round(flip_distance_pct, 4) if flip_distance_pct is not None else None,
        "recommendation": recommendation,
    }


# ---------------------------------------------------------------------------
# Summary: Full paper-accurate GEX diagnostic (combines all 5 metrics)
# ---------------------------------------------------------------------------

def full_paper_diagnostic(
    net_gex: float,
    spot: float,
    adv_shares: float | None = None,
    zero_gamma_level: float | None = None,
    current_gex: float | None = None,
    gex_at_old_spot: float | None = None,
    gex_at_old_spot_old_oi: float | None = None,
    amihud_illiquidity: float | None = None,
) -> dict[str, Any]:
    """Compute the complete paper-accurate GEX diagnostic suite.

    This is the single entry point that wraps all five paper metrics
    into one response payload suitable for the briefing API.

    Args:
        net_gex: Net dollar GEX (from gex_aggregator or gex_core)
        spot: Underlying price
        adv_shares: Average daily share volume (optional — skips ΓIB if None)
        zero_gamma_level: Zero-gamma flip strike (optional)
        current_gex: Today's GEX for decomposition (optional)
        gex_at_old_spot: Prior GEX recomputed at current spot (optional)
        gex_at_old_spot_old_oi: Prior GEX at prior spot (optional)
        amihud_illiquidity: Amihud ratio (optional)

    Returns:
        Complete diagnostic dict with all paper metrics
    """
    result: dict[str, Any] = {
        "net_gex": net_gex,
        "spot": spot,
        "paper_metrics": {},
    }

    # 1. Gamma Imbalance
    if adv_shares is not None and adv_shares > 0:
        gi = compute_gamma_imbalance(net_gex, spot, adv_shares)
        result["paper_metrics"]["gamma_imbalance"] = gi
        gib_pct = gi["gamma_imbalance_pct"]
    else:
        result["paper_metrics"]["gamma_imbalance"] = {
            "error": "ADV not provided — skip Gamma Imbalance computation"
        }
        # Default ADV fallback — avoids magic number; mirrors briefing ADV dict
        _default_adv = 10_000_000
        gib_pct = (
            net_gex / (spot * spot * 0.01 * _default_adv) * 100
            if spot > 0
            else 0.0
        )  # rough proxy with explicit default

    # 2. Flip Metrics
    fm = compute_flip_metrics(spot, zero_gamma_level, net_gex)
    result["paper_metrics"]["flip_metrics"] = fm
    flip_dist = fm.get("flip_distance_pct")

    # 3. Intraday Regime
    ir = predict_intraday_regime(gib_pct, flip_dist)
    result["paper_metrics"]["intraday_regime"] = ir

    # 4. Gamma Decomposition
    dc = decompose_gamma(
        current_gex or net_gex,
        gex_at_old_spot,
        gex_at_old_spot_old_oi,
    )
    result["paper_metrics"]["gamma_decomposition"] = dc

    # 5. Flash Crash Risk
    fcr = flash_crash_risk(
        gib_pct,
        flip_dist,
        amihud_illiquidity,
        net_gex,
    )
    result["paper_metrics"]["flash_crash_risk"] = fcr

    return result


def put_call_ratio_signal(
    call_oi: float,
    put_oi: float,
    call_vol: float = 0.0,
    put_vol: float = 0.0,
) -> dict[str, Any]:
    """Put-call ratio directional signal (OI-based proxy).

    Motivated by Pan-Poteshman (2006), 'The Information in Option Volume
    for Future Stock Prices', who used buyer-initiated trade volume.
    This function does NOT have that volume data: it uses OI-based PCR
    as a proxy, and the P&P return finding is not verified for OI PCR here.
    """
    total_oi = call_oi + put_oi
    total_vol = call_vol + put_vol
    pcr_oi = (put_oi / total_oi) if total_oi > 0 else None
    pcr_vol = (put_vol / total_vol) if total_vol > 0 else None
    pcr = pcr_oi if pcr_oi is not None else (pcr_vol if pcr_vol is not None else 0.5)

    if pcr < 0.35:
        signal, confidence = "BULLISH", "high"
        interp = f"PCR {pcr:.2f} — calls dominate (OI-based proxy, not P&P volume)."
    elif pcr < 0.45:
        signal, confidence = "BULLISH", "medium"
        interp = f"PCR {pcr:.2f} — mild call dominance."
    elif pcr > 0.65:
        signal, confidence = "BEARISH", "high"
        interp = f"PCR {pcr:.2f} — puts dominate (OI-based proxy, not P&P volume)."
    elif pcr > 0.55:
        signal, confidence = "BEARISH", "medium"
        interp = f"PCR {pcr:.2f} — mild put dominance."
    else:
        signal, confidence = "NEUTRAL", "low"
        interp = f"PCR {pcr:.2f} — balanced. No directional edge."

    return {
        "pcr_oi": round(pcr_oi, 4) if pcr_oi is not None else None,
        "pcr_vol": round(pcr_vol, 4) if pcr_vol is not None else None,
        "signal": signal,
        "confidence": confidence,
        "interpretation": interp,
    }


def stock_order_imbalance_signal(
    net_delta: float,
    net_delta_old_spot: float | None = None,
    net_gamma: float = 0.0,
) -> dict[str, Any]:
    """Stock order imbalance from hedge rebalancing — Ni-Pearson appendix §3.

    'Does Option Trading Have a Pervasive Impact on Underlying Stock Prices?'
    Internet Appendix, Section 3: Effect of Hedge Rebalancing on Directional
    Stock Price Movements.

    Key formula:
      HedgeDeltaOI(t-τ,t) = -[netDelta(t-τ, S_t) - netDelta(t-τ, S_{t-τ})]
      InfoDeltaOI(t-τ,t) = -[netDelta(t, S_t) - netDelta(t-τ, S_t)]

    Where netDelta is the normalized net delta of market makers:
      netDelta(t,S) = 100 × (1/M_t) × Σ(net_oi_j × Δ_j(t,S)) / N_t

    Findings:
      - Negative gamma + positive HedgeDeltaOI → dealers buying → momentum UP
      - Negative gamma + negative HedgeDeltaOI → dealers selling → momentum DOWN
      - Positive gamma → weak/unclear relationship (dealers stabilize)
      - Coefficient on HedgeDeltaOI × I_{G-}: 0.791 (t=8.30) for 1990-2001

    Args:
        net_delta: Today's net delta of market makers at today's spot
        net_delta_old_spot: Net delta using old OI at today's spot (optional)
        net_gamma: Net position gamma for sign context
        spot: Current spot price (for display)
        shares_outstanding: Shares outstanding for normalization

    Returns:
        dict with hedge_oi, info_oi, imbalance_signal, predicted_direction
    """
    result: dict[str, Any] = {
        "hedge_delta_oi": None,
        "info_delta_oi": None,
        "imbalance_signal": "insufficient_data",
        "predicted_direction": "unknown",
        "net_gamma_context": "neutral" if abs(net_gamma) < 1e6 else ("negative" if net_gamma < 0 else "positive"),
    }

    if net_delta_old_spot is None:
        result["interpretation"] = (
            "Insufficient data for HedgeDeltaOI decomposition. "
            "Need prior net delta recomputed at current spot."
        )
        return result

    # HedgeDeltaOI = negative of delta change from spot move (dealers rebalance)
    # When net_delta decreases (becomes more negative) as spot falls →
    # HedgeDeltaOI is positive = dealers BUYING stock
    hedge_oi = -(net_delta - net_delta_old_spot)

    # Net gamma determines whether dealers amplify or dampen
    has_negative_gamma = net_gamma < -1e6
    has_positive_gamma = net_gamma > 1e6

    # Interpretation per paper Table 3:
    # Negative gamma + HedgeDeltaOI > 0 → dealers buying pushes price UP → momentum
    # Negative gamma + HedgeDeltaOI < 0 → dealers selling pushes price DOWN → momentum
    # Positive gamma → relationship weak/unclear (dealers stabilize)

    if has_negative_gamma:
        if hedge_oi > 0.01:
            result["imbalance_signal"] = "DEALER_BUYING"
            result["predicted_direction"] = "bullish_momentum"
            result["interpretation"] = (
                f"Negative gamma ({net_gamma/1e9:.1f}B) + dealers BUYING stock "
                f"(HedgeDeltaOI={hedge_oi:.4f}). Per Ni-Pearson Table 3: "
                "positive feedback — expect upward momentum continuation. "
                "Coefficient on HedgeDeltaOI×I_{G-}: 0.791 (t=8.30)."
            )
        elif hedge_oi < -0.01:
            result["imbalance_signal"] = "DEALER_SELLING"
            result["predicted_direction"] = "bearish_momentum"
            result["interpretation"] = (
                f"Negative gamma ({net_gamma/1e9:.1f}B) + dealers SELLING stock "
                f"(HedgeDeltaOI={hedge_oi:.4f}). Per Ni-Pearson Table 3: "
                "downward momentum from dealer rebalancing."
            )
        else:
            result["imbalance_signal"] = "DEALER_NEUTRAL"
            result["predicted_direction"] = "neutral"
            result["interpretation"] = (
                "Negative gamma but dealers near delta-neutral. "
                "No directional pressure from rebalancing."
            )
    elif has_positive_gamma:
        result["imbalance_signal"] = "POSITIVE_GAMMA_STABILIZING"
        result["predicted_direction"] = "mean_reverting"
        result["interpretation"] = (
            f"Positive gamma ({net_gamma/1e9:.1f}B) — dealers stabilize. "
            f"HedgeDeltaOI={hedge_oi:.4f}. Per Ni-Pearson: weak/unclear "
            "relationship between delta rebalancing and returns."
        )
    else:
        result["imbalance_signal"] = "NEUTRAL_GAMMA"
        result["predicted_direction"] = "neutral"
        result["interpretation"] = (
            "Gamma near zero — no strong dealer hedging pressure."
        )

    result["hedge_delta_oi"] = round(hedge_oi, 6)
    result["net_gamma"] = round(net_gamma, 2)

    # Return reversal probability per Ni-Pearson: after dealer rebalancing
    # pushes price, we see reversal next day (coeff -0.022, t=-1.92)
    if has_negative_gamma and abs(hedge_oi) > 0.01:
        result["next_day_reversal_probability"] = "moderate"
        result["reversal_horizon"] = "1-2 days"
    else:
        result["next_day_reversal_probability"] = "low"

    return result


DEFAULT_ADV_SHARES = 10_000_000


def option_demand_pressure(
    net_gex: float,
    put_call_ratio_oi: float | None = None,
    put_call_ratio_vol: float | None = None,
    bid_ask_spread: float | None = None,
) -> dict[str, Any]:
    """Option demand pressure signal — Gârleanu-Pedersen-Poteshman (2008).

    'Demand-Based Option Pricing'
    Review of Financial Studies 22, 4259-4299.

    GPP show that end-users' net demand for options creates price pressure
    that market makers must absorb, leading to predictable patterns in
    option prices relative to Black-Scholes. When end-user demand is net
    positive (buying pressure), implied volatilities deviate from fair value.

    Key mechanism:
      - Market makers are risk-averse and cannot perfectly hedge
      - Net end-user demand creates inventory imbalances
      - Inventory imbalances affect option prices through demand pressure
      - Higher demand → higher IV relative to fundamental value

    Our proxy: combine GEX-based gamma imbalance with PCR ratio to infer
    directional demand pressure on the market maker book.

    Args:
        net_gex: Net dollar GEX (negative = dealers short, positive = dealers long)
        spot: Current spot price
        put_call_ratio_oi: Put/Call OI ratio (optional)
        put_call_ratio_vol: Put/Call volume ratio (optional)
        bid_ask_spread: Relative bid-ask spread (optional)
        implied_vol: ATM implied volatility (optional)

    Returns:
        dict with demand_pressure, dealer_inventory_type, expected_price_impact
    """
    result: dict[str, Any] = {
        "demand_pressure": "neutral",
        "dealer_inventory_type": "balanced",
        "expected_price_impact": "none",
    }

    # Dealer inventory direction from GEX sign
    if net_gex < -1e9:
        dealer_position = "short"
        result["dealer_inventory_type"] = "net_short_gamma"
    elif net_gex > 1e9:
        dealer_position = "long"
        result["dealer_inventory_type"] = "net_long_gamma"
    else:
        dealer_position = "neutral"

    # End-user demand pressure: if dealers are short gamma, end-users are long
    # (buying pressure). Long end-users → upward demand pressure on IV.
    pcr = put_call_ratio_oi if put_call_ratio_oi is not None else put_call_ratio_vol

    if dealer_position == "short" and (pcr is None or pcr < 0.5):
        result["demand_pressure"] = "end_user_buying"
        result["expected_price_impact"] = "upward_iv_pressure"
        result["interpretation"] = (
            "Dealers net short gamma → end-users net long. "
            "Per GPP 2008: end-user buying pressure biases IV above "
            "fundamental value. Favorable for volatility selling strategies. "
            "Also consistent with Ni-Pearson: dealers forced to hedge amplify moves."
        )
    elif dealer_position == "long" and (pcr or 0.5) > 0.5:
        result["demand_pressure"] = "end_user_selling"
        result["expected_price_impact"] = "downward_iv_pressure"
        result["interpretation"] = (
            "Dealers net long gamma → end-users net short/hedging. "
            "Per GPP 2008: end-user selling pressure biases IV below "
            "fundamental value. Consider buying volatility cheaply."
        )
    elif pcr is not None:
        if pcr < 0.35:
            result["demand_pressure"] = "call_demand_dominant"
            result["interpretation"] = (
                f"PCR={pcr:.2f} — strong call demand. "
                "End-users buying calls, dealers short calls (negative gamma)."
            )
        elif pcr > 0.65:
            result["demand_pressure"] = "put_demand_dominant"
            result["interpretation"] = (
                f"PCR={pcr:.2f} — strong put demand. "
                "Hedging/protection buying dominates, dealers short puts."
            )
        else:
            result["demand_pressure"] = "balanced"
    else:
        if dealer_position == "short":
            result["demand_pressure"] = "moderate_buying"
        elif dealer_position == "long":
            result["demand_pressure"] = "moderate_selling"

    # Liquidity friction: higher spread → stronger demand price impact
    if bid_ask_spread and bid_ask_spread > 0.002:
        result["demand_pressure_amplified"] = True
        result["liquidity_note"] = (
            f"Bid-ask spread {bid_ask_spread*100:.2f}% > 0.2% → "
            "demand price impact amplified per GPP illiquidity channel."
        )

    return result


def options_order_imbalance(
    trade_direction: list[int] | None = None,
    trade_volume: list[float] | None = None,
    trade_deltas: list[float] | None = None,
    call_open_interest: float = 0.0,
    put_open_interest: float = 0.0,
) -> dict[str, Any]:
    """Options Order Imbalance — Hu (2014) JFE 111, 625-645.

    'Does Option Trading Convey Stock Price Information?'
    Journal of Financial Economics, 2014.

    Converts option trade flow into share-equivalent stock order imbalance
    by weighting each option trade by its delta. This proxies the
    inventory-driven hedging pressure market makers pass to the stock.

    Formula: OOI = Σ Dir_i × Volume_i × Δ_i × 100

    Where:
      Dir_i = +1 for buyer-initiated (customer buys option)
      Dir_i = -1 for seller-initiated (customer sells option)
      Volume_i = number of contracts traded
      Δ_i = Black-Scholes delta of the option
      ×100 = converts contracts to share equivalents

    Key finding: OOI predicts next-day stock returns. Positive OOI
    (net buying of calls/selling of puts) → bullish. Negative OOI → bearish.

    When trade-level data is unavailable, infers from OI changes.

    Args:
        trade_direction: List of trade direction indicators (+1/-1)
        trade_volume: List of contract volumes
        trade_deltas: List of Black-Scholes deltas at trade time
        call_open_interest: Total call OI (fallback)
        put_open_interest: Total put OI (fallback)

    Returns:
        dict with ooi_value, signal, interpretation
    """
    result: dict[str, Any] = {
        "ooi_value": None,
        "ooi_normalized": None,
        "signal": "insufficient_data",
        "interpretation": "",
    }

    # Trade-level computation
    if trade_direction and trade_volume and trade_deltas:
        if len(trade_direction) == len(trade_volume) == len(trade_deltas):
            ooi = sum(
                d * v * delta * 100.0
                for d, v, delta in zip(trade_direction, trade_volume, trade_deltas, strict=False)
            )
            result["ooi_value"] = round(ooi, 2)

            if ooi > 0:
                result["signal"] = "BULLISH_ORDER_FLOW"
                result["interpretation"] = (
                    f"Net options buying pressure: {ooi:,.0f} share equivalents. "
                    "Positive OOI predicts higher returns (Hu 2014). "
                    "Market makers short calls → must BUY stock to delta-hedge."
                )
            elif ooi < 0:
                result["signal"] = "BEARISH_ORDER_FLOW"
                result["interpretation"] = (
                    f"Net options selling pressure: {ooi:,.0f} share equivalents. "
                    "Negative OOI predicts lower returns. "
                    "Market makers long puts → must SELL stock to delta-hedge."
                )
            else:
                result["signal"] = "NEUTRAL"
                result["interpretation"] = "No directional options order imbalance."

            # Normalize by typical daily volume
            result["ooi_normalized"] = round(ooi / 10_000_000, 6)  # per 10M ADV
            return result

    # OI-based fallback: approximate OOI from OI changes
    # Calls: positive delta → buying calls = bullish OOI
    # Puts: negative delta → buying puts = bearish OOI
    total_oi = call_open_interest + put_open_interest
    if total_oi > 0:
        # Approximate: call OI contributes +Δ, put OI contributes -Δ
        # Assume ATM delta ≈ 0.5 for calls, -0.5 for puts
        approx_ooi = (call_open_interest * 0.5 - put_open_interest * 0.5) * 100.0
        result["ooi_value"] = round(approx_ooi, 2)
        result["method"] = "oi_approximation"

        if approx_ooi > 1e6:
            result["signal"] = "BULLISH_OI_SKEW"
            ratio = call_open_interest / max(put_open_interest, 1)
            result["interpretation"] = (
                f"Call OI dominates (C/P={ratio:.1f}:1). "
                f"Approximate OOI ~{approx_ooi/1e6:.1f}M share equivalents."
            )
        elif approx_ooi < -1e6:
            result["signal"] = "BEARISH_OI_SKEW"
            ratio = put_open_interest / max(call_open_interest, 1)
            result["interpretation"] = (
                f"Put OI dominates (P/C={ratio:.1f}:1). "
                f"Approximate OOI ~{approx_ooi/1e6:.1f}M share equivalents."
            )
        else:
            result["signal"] = "BALANCED_OI"
            result["interpretation"] = "Call and put OI balanced — no skew signal."

        result["ooi_normalized"] = round(approx_ooi / 10_000_000, 6)
        return result

    result["interpretation"] = "No trade-level or OI data available."
    return result


def charm_hedging_pressure(
    delta: float,
    theta: float,
    dte_days: float = 1.0,
) -> dict[str, Any]:
    """Charm hedging pressure (theta-derived proxy, unverified against tape).

    Charm (dDelta/dTime) measures how option delta changes as time passes.
    Unlike gamma which reacts to spot moves, charm creates a PERSISTENT
    hedging need that accumulates each day regardless of spot direction.
    Computed here from daily theta as a heuristic proxy — NOT measured
    dealer flow. Treat signals as unverified estimates.

    For ATM options near expiry:
      Charm ≈ -Θ / S  (for calls)
      Charm ≈ Θ / S   (for puts)

    Key implications (heuristic):
      - High negative charm → dealers must buy more stock each day
      - High positive charm → dealers must sell more stock each day
      - Charm effects peak in the final week before expiration

    Args:
        delta: Current option delta
        theta: Current option theta (daily)
        dte_days: Days to expiration

    Returns:
        dict with charm_signal, hedging_direction
    """
    # Charm = -∂Δ/∂t ≈ -Θ/S for ATM calls
    # Using theta (already daily) as charm proxy
    charm = -theta if abs(delta) > 0.3 else 0.0  # meaningful only near ATM

    result: dict[str, Any] = {
        "charm_value": round(charm, 8),
        "dte_days": dte_days,
        "signal": "neutral",
    }

    # Charm effect amplifies near expiration (DTE < 5 days)
    near_expiry = dte_days < 5.0

    if charm < -0.01 and near_expiry:
        result["signal"] = "CHARM_BUYING_PRESSURE"
        result["interpretation"] = (
            f"Theta-proxy charm {charm:.4f} near expiry ({dte_days:.0f}d). "
            "Heuristic estimate: dealers may BUY more stock daily to maintain delta-neutral. "
            "Unverified proxy, not measured dealer flow."
        )
    elif charm > 0.01 and near_expiry:
        result["signal"] = "CHARM_SELLING_PRESSURE"
        result["interpretation"] = (
            f"Theta-proxy charm +{charm:.4f} near expiry ({dte_days:.0f}d). "
            "Heuristic estimate: dealers may SELL more stock daily to maintain delta-neutral. "
            "Unverified proxy, not measured dealer flow."
        )
    elif near_expiry:
        result["signal"] = "CHARM_NEUTRAL_NEAR_EXPIRY"
        result["interpretation"] = (
            "Near expiry but charm near zero. Monitor for acceleration."
        )
    else:
        result["signal"] = "CHARM_NEGLIGIBLE"
        result["interpretation"] = (
            f"DTE {dte_days:.0f}d > 5 — charm effects negligible."
        )

    return result


def drift_burst_risk(
    returns: list[float] | None = None,
    gamma_imbalance_pct: float = 0.0,
    window_minutes: int = 60,
) -> dict[str, Any]:
    """Drift burst detection — Christensen-Oomen-Reno (2018).

    'The Drift Burst Hypothesis'
    Used in Barbon-Buraschi Table VIII for flash crash identification.

    A drift burst is a short-lived explosive price trend where the
    drift term dominates the diffusion term. The test statistic compares
    local drift magnitude to local volatility over a rolling window.

    When gamma imbalance is negative AND a drift burst is detected,
    the probability of a flash crash is significantly elevated
    (Barbon-Buraschi Table VIII: ΓIB coefficient -1.15, t=-2.97).

    Args:
        returns: List of minute-level returns (optional - computes proxy if None)
        gamma_imbalance_pct: Current Gamma Imbalance (% of ADV)
        spot: Current spot price for display
        window_minutes: Detection window in minutes (default 60)

    Returns:
        dict with drift_burst_detected, severity, and risk level
    """
    result: dict[str, Any] = {
        "drift_burst_detected": False,
        "severity": "none",
        "risk_level": "LOW",
    }

    # Gamma-based proxy when price data unavailable
    if returns is None or len(returns) < window_minutes:
        # Barbon-Buraschi finding: negative ΓIB → higher drift burst probability
        # Conditional on negative gamma, flash crash probability ≈ 2-5x
        if gamma_imbalance_pct < -1.0:
            result["drift_burst_detected"] = True
            result["severity"] = "elevated"
            result["risk_level"] = "MODERATE"
            result["method"] = "gamma_proxy"
            result["interpretation"] = (
                f"Negative ΓIB ({gamma_imbalance_pct:.1f}%) → elevated drift burst risk. "
                "Per Barbon-Buraschi Table VIII: conditional flash crash probability "
                "significantly higher under negative gamma imbalance."
            )
        elif gamma_imbalance_pct < -0.5:
            result["drift_burst_detected"] = False
            result["severity"] = "low"
            result["risk_level"] = "LOW"
            result["method"] = "gamma_proxy"
            result["interpretation"] = (
                "Mild negative gamma — monitor for drift burst development."
            )
        else:
            result["method"] = "gamma_proxy"
            result["interpretation"] = (
                "Neutral/positive gamma — drift burst risk minimal."
            )
        return result

    # Full drift burst detection from price returns
    n = len(returns)
    if n < 30:
        return result

    # Compute rolling drift (mean return) and volatility
    drift = sum(returns) / n
    vol = (sum((r - drift) ** 2 for r in returns) / (n - 1)) ** 0.5 if n > 1 else 0.0

    if vol > 0:
        # Test statistic: |drift| / (vol / sqrt(n)) — like a t-stat
        t_stat = abs(drift) / (vol / (n ** 0.5)) if n > 0 else 0.0
        result["t_statistic"] = round(t_stat, 4)

        # Christensen-Oomen-Reno thresholds:
        # |t| > 2.0 → potential drift burst (95% confidence)
        # |t| > 3.0 → confirmed drift burst (99.7% confidence)
        if t_stat > 3.0:
            result["drift_burst_detected"] = True
            result["severity"] = "confirmed"
            result["risk_level"] = "HIGH"
            direction = "UPWARD" if drift > 0 else "DOWNWARD"
            result["interpretation"] = (
                f"CONFIRMED drift burst |t|={t_stat:.1f} — explosive {direction} trend. "
                f"Per Christensen-Oomen-Reno: drift dominates diffusion, crash risk elevated. "
                f"Combine with negative ΓIB ({gamma_imbalance_pct:.1f}%) for flash crash probability."
            )
        elif t_stat > 2.0:
            result["drift_burst_detected"] = True
            result["severity"] = "potential"
            result["risk_level"] = "MODERATE"
            result["interpretation"] = (
                f"Potential drift burst |t|={t_stat:.1f} — monitor for acceleration."
            )
        else:
            result["interpretation"] = (
                f"No drift burst detected |t|={t_stat:.1f}. Diffusion dominates."
            )
    else:
        result["interpretation"] = "Zero volatility — no burst risk."

    # Flash crash interaction (Barbon-Buraschi)
    if result["drift_burst_detected"] and gamma_imbalance_pct < -1.0:
        result["flash_crash_conditional_risk"] = "HIGH"
        result["combined_risk"] = (
            f"Drift burst + negative gamma ({gamma_imbalance_pct:.1f}%) → "
            "conditional flash crash risk greatly elevated. "
            "Per Barbon-Buraschi Tables VIII-IX: probability 2-5x baseline."
        )

    return result


def dealer_hedging_liquidity_impact(
    net_gamma: float,
    gamma_imbalance_pct: float,
    amihud_illiquidity: float | None = None,
) -> dict[str, Any]:
    """Dealer hedging → stock liquidity impact — O'Donovan-Yu-Zhang (2023).

    'Option Market Maker Hedging and Stock Market Liquidity'
    SSRN 4567604.

    Key finding: when option market makers hold net SHORT positions
    (negative gamma), their pro-cyclical delta hedging withdraws liquidity
    from the underlying, widening bid-ask spreads and increasing Amihud
    illiquidity. Net LONG positions supply counter-cyclical liquidity.

    This interacts with Ni-Pearson: negative gamma → dealers amplify
    moves → liquidity deteriorates → wider spreads → higher vol.

    Args:
        net_gamma: Net position gamma (negative = dealers short)
        gamma_imbalance_pct: ΓIB as % of ADV
        amihud_illiquidity: Existing Amihud illiquidity ratio (optional)

    Returns:
        dict with liquidity_impact, spread_direction
    """
    result: dict[str, Any] = {
        "liquidity_impact": "neutral",
        "spread_direction": "stable",
    }

    has_negative = net_gamma < -1e9
    has_positive = net_gamma > 1e9
    abs_gib = abs(gamma_imbalance_pct)

    if has_negative and abs_gib > 1.0:
        result["liquidity_impact"] = "liquidity_withdrawal"
        result["spread_direction"] = "widening"
        result["interpretation"] = (
            f"Dealers net short gamma ({net_gamma/1e9:.1f}B, ΓIB={gamma_imbalance_pct:.1f}%). "
            "Pro-cyclical hedging withdraws liquidity from underlying. "
            "Per O'Donovan-Yu-Zhang: expect wider bid-ask spreads, "
            "higher Amihud illiquidity. Amplified for small-cap/illiquid names."
        )
    elif has_negative:
        result["liquidity_impact"] = "mild_withdrawal"
        result["spread_direction"] = "slightly_widening"
        result["interpretation"] = (
            "Mild negative gamma — moderate liquidity impact."
        )
    elif has_positive and abs_gib > 1.0:
        result["liquidity_impact"] = "liquidity_provision"
        result["spread_direction"] = "tightening"
        result["interpretation"] = (
            f"Dealers net long gamma ({net_gamma/1e9:.1f}B, ΓIB={gamma_imbalance_pct:.1f}%). "
            "Counter-cyclical hedging supplies liquidity. "
            "Expect tighter spreads, lower Amihud."
        )
    elif has_positive:
        result["liquidity_impact"] = "mild_provision"
        result["spread_direction"] = "slightly_tightening"
    else:
        result["liquidity_impact"] = "neutral"
        result["interpretation"] = "Gamma near neutral — no liquidity impact."

    # Amplify for already-illiquid stocks
    if amihud_illiquidity and amihud_illiquidity > 1e-6 and has_negative:
        result["amplified_for_illiquid"] = True
        result["warning"] = (
            f"Stock already illiquid (Amihud={amihud_illiquidity:.2e}) + "
            "negative gamma → liquidity spiral risk elevated."
        )

    return result


def gamma_liquidity_regime(
    gamma_imbalance_pct: float,
    flip_distance_pct: float | None = None,
    amihud_illiquidity: float | None = None,
) -> dict[str, Any]:
    """Gamma → option liquidity regime — Barbon-Buraschi (SSRN 4138512).

    'Option Liquidity and Gamma Imbalances'
    Maps gamma imbalance to option market liquidity conditions.

    Key finding: dealer inventory risk from gamma imbalances creates
    predictable patterns in option market liquidity. Large absolute
    gamma imbalances → reduced option liquidity as dealers widen quotes
    to manage inventory risk. Near the zero-gamma flip → maximum
    uncertainty → option liquidity worst.

    Args:
        gamma_imbalance_pct: ΓIB as % of ADV
        flip_distance_pct: Distance to zero-gamma flip (%)
        amihud_illiquidity: Stock-level Amihud (optional)

    Returns:
        dict with option_liquidity_regime, dealer_quote_behavior
    """
    abs_gib = abs(gamma_imbalance_pct)
    near_flip = flip_distance_pct is not None and abs(flip_distance_pct) < 2.0

    result: dict[str, Any]
    if abs_gib > 2.0 and near_flip:
        regime = "critically_illiquid"
        quote_behavior = "wide_quotes_withdrawing"
        result = {
            "regime": regime,
            "dealer_quote_behavior": quote_behavior,
            "interpretation": (
                f"Large |ΓIB| ({abs_gib:.1f}%) NEAR the zero-gamma flip — "
                "maximum dealer inventory risk. Per Barbon-Buraschi: "
                "option market makers widen spreads significantly. "
                "Option liquidity critically impaired."
            ),
        }
    elif abs_gib > 2.0:
        result = {
            "regime": "illiquid",
            "dealer_quote_behavior": "wider_spreads",
            "interpretation": (
                f"Large |ΓIB| ({abs_gib:.1f}%) — elevated dealer inventory risk. "
                "Option liquidity below normal."
            ),
        }
    elif abs_gib > 0.5:
        result = {
            "regime": "moderate",
            "dealer_quote_behavior": "normal_spreads",
            "interpretation": "Moderate ΓIB — normal option liquidity conditions.",
        }
    else:
        result = {
            "regime": "liquid",
            "dealer_quote_behavior": "tight_spreads",
            "interpretation": (
                "Low ΓIB — dealers face minimal inventory risk. "
                "Option liquidity abundant, tight spreads."
            ),
        }

    result["gamma_imbalance_pct"] = round(gamma_imbalance_pct, 4)
    result["near_flip"] = near_flip
    if amihud_illiquidity and amihud_illiquidity > 1e-5:
        result["illiquid_stock_interaction"] = (
            "Underlying stock illiquid → option liquidity doubly impaired."
        )
    return result


def informed_option_volume_signal(
    buyer_initiated_call_vol: float = 0.0,
    seller_initiated_call_vol: float = 0.0,
    buyer_initiated_put_vol: float = 0.0,
    seller_initiated_put_vol: float = 0.0,
    total_call_volume: float | None = None,
    total_put_volume: float | None = None,
    days_observed: int = 20,
) -> dict[str, Any]:
    """Informed option volume signal — Easley-O'Hara-Srinivas (1998).

    'Option Volume and Stock Prices: Evidence on Where Informed Traders Trade'
    Journal of Finance 53, 431-465.

    EOS 1998 is THE foundational paper showing that option volume contains
    private information about future stock prices. Their key insight:
    informed traders prefer options over stocks because of leverage and
    downside protection. Positive (negative) option volume predicts
    positive (negative) stock returns.

    The PIN (Probability of Informed Trading) model adapted for options:
      PIN = αμ / (αμ + 2ε)
      where:
        α = prob of information event per day (~0.2-0.4 for active stocks)
        μ = informed trader arrival rate (buyer-initiated unusual volume)
        ε = uninformed trader arrival rate (balanced buy/sell background)

    When trade-level data is unavailable, we proxy PIN from:
      InformedRatio = |buy_vol - sell_vol| / total_vol
      Higher ratio → more one-sided flow → more likely informed

    Args:
        buyer_initiated_call_vol: Buyer-initiated call volume (contracts or premium)
        seller_initiated_call_vol: Seller-initiated call volume
        buyer_initiated_put_vol: Buyer-initiated put volume
        seller_initiated_put_vol: Seller-initiated put volume
        total_call_volume: Total call volume (optional, auto-computed if None)
        total_put_volume: Total put volume (optional)
        days_observed: Days of data for PIN estimation

    Returns:
        dict with pin_estimate, informed_direction, signal
    """
    # Auto-compute totals if not provided
    if total_call_volume is None:
        total_call_volume = buyer_initiated_call_vol + seller_initiated_call_vol
    if total_put_volume is None:
        total_put_volume = buyer_initiated_put_vol + seller_initiated_put_vol

    total_vol = total_call_volume + total_put_volume
    if total_vol <= 0:
        return {
            "pin_estimate": 0.0,
            "informed_direction": "insufficient_data",
            "signal": "NO_DATA",
            "interpretation": "No option volume data available.",
        }

    # --- PIN estimation ---
    # Informed buys = buyer-initiated calls + buyer-initiated puts
    # (buying calls = bullish, buying puts = bearish)
    _informed_vol = buyer_initiated_call_vol + buyer_initiated_put_vol
    _uninformed_vol = seller_initiated_call_vol + seller_initiated_put_vol

    # PIN proxy: fraction of one-sided volume
    # Higher values = more informed (more directional conviction)
    if total_vol > 0:
        net_directional = abs(buyer_initiated_call_vol - seller_initiated_call_vol) + \
                          abs(buyer_initiated_put_vol - seller_initiated_put_vol)
        pin_estimate = net_directional / total_vol
    else:
        pin_estimate = 0.0

    # --- Informed direction ---
    # Net call buying = bullish informed
    # Net put buying = bearish informed
    net_call_buying = buyer_initiated_call_vol - seller_initiated_call_vol
    net_put_buying = buyer_initiated_put_vol - seller_initiated_put_vol

    # EOS finding: positive (negative) option volume → positive (negative) returns
    # Call buying is more informative for positive returns
    # Put buying is more informative for negative returns
    call_call_ratio = total_call_volume / max(total_put_volume, 1)

    if pin_estimate < 0.15:
        signal = "LOW_INFORMATION"
        direction = "neutral"
        interp = f"PIN={pin_estimate:.3f} — low information content. Balanced buy/sell flow."
    elif pin_estimate > 0.4:
        signal = "HIGH_INFORMATION"
        if net_call_buying > 0 and net_put_buying < 0:
            direction = "bullish"
            interp = (
                f"PIN={pin_estimate:.3f} — HIGH informed content, BULLISH direction. "
                f"Net call buying ${net_call_buying/1e6:.1f}M. "
                "Per EOS 1998: positive option volume predicts positive returns."
            )
        elif net_put_buying > 0 and net_call_buying < 0:
            direction = "bearish"
            interp = (
                f"PIN={pin_estimate:.3f} — HIGH informed content, BEARISH direction. "
                f"Net put buying ${net_put_buying/1e6:.1f}M. "
                "Per EOS 1998: negative option volume predicts negative returns."
            )
        else:
            direction = "mixed"
            interp = (
                f"PIN={pin_estimate:.3f} — HIGH informed content but mixed direction. "
                "Both calls and puts seeing informed buying — potential volatility event."
            )
    else:
        signal = "MODERATE_INFORMATION"
        if net_call_buying > net_put_buying:
            direction = "mildly_bullish"
            interp = f"PIN={pin_estimate:.3f} — moderate information, leaning bullish."
        elif net_put_buying > net_call_buying:
            direction = "mildly_bearish"
            interp = f"PIN={pin_estimate:.3f} — moderate information, leaning bearish."
        else:
            direction = "neutral"
            interp = f"PIN={pin_estimate:.3f} — moderate information, balanced direction."

    return {
        "pin_estimate": round(pin_estimate, 4),
        "informed_direction": direction,
        "signal": signal,
        "interpretation": interp,
        "net_call_buying": round(net_call_buying, 2),
        "net_put_buying": round(net_put_buying, 2),
        "call_put_ratio": round(call_call_ratio, 2),
        "days_observed": days_observed,
    }


def cremers_weinbaum_spread(
    call_bids: list[float] | None = None,
    put_asks: list[float] | None = None,
    strikes: list[float] | None = None,
    open_interests: list[float] | None = None,
    spot: float = 0.0,
    risk_free_rate: float = 0.05,
    dte_days: float = 30.0,
) -> dict[str, Any]:
    """Cremers-Weinbaum (2010) Put-Call Parity deviation spread.

    'Deviations from Put-Call Parity and Stock Return Predictability'
    Journal of Finance 65, 589-626.

    CW spread measures the OI-weighted average deviation from put-call
    parity across all strikes and expiries. Positive CW → calls expensive
    relative to puts → BULLISH (predicts HIGHER future returns).

    Formula:
      CW = Σ_i w_i × [(C_bid_i - P_ask_i) - (S - PV(K_i))] / S
      where w_i = OI_i / Σ OI_i

    Key finding: decile of highest CW outperforms lowest by ~50 bps/day.

    Args:
        call_bids: List of call bid prices per strike
        put_asks: List of put ask prices per strike
        strikes: List of strike prices
        open_interests: List of (call+put) open interest per strike
        spot: Current underlying price
        risk_free_rate: Annual risk-free rate (default 5%)
        dte_days: Days to expiration

    Returns:
        dict with cw_spread, signal, interpretation
    """
    if not call_bids or not put_asks or not strikes:
        return {
            "cw_spread_bps": None,
            "signal": "insufficient_data",
            "interpretation": "Need call bids, put asks, and strikes per option.",
        }

    T = dte_days / 365.0
    pv_factor = 1.0 / (1.0 + risk_free_rate * T) if T > 0 else 1.0

    num_contracts = min(len(call_bids), len(put_asks), len(strikes))
    if num_contracts == 0:
        return {"cw_spread_bps": None, "signal": "insufficient_data", "interpretation": "No contracts."}

    # Default equal weighting if no OI provided
    if not open_interests or len(open_interests) < num_contracts:
        weights = [1.0 / num_contracts] * num_contracts
    else:
        total_oi = sum(open_interests[:num_contracts])
        weights = [oi / max(total_oi, 1) for oi in open_interests[:num_contracts]]

    if spot <= 0:
        return {"cw_spread_bps": None, "signal": "no_spot", "interpretation": "Spot price required."}

    # CW = Σ w_i × [(C_bid_i - P_ask_i) / S - (1 - PV(K_i)/S)]
    #    = Σ w_i × [(C_bid_i - P_ask_i - S + PV(K_i)) / S]
    cw_sum = 0.0
    for i in range(num_contracts):
        synthetic_forward = call_bids[i] - put_asks[i]
        parity_value = spot - strikes[i] * pv_factor
        deviation = (synthetic_forward - parity_value) / spot
        cw_sum += weights[i] * deviation

    cw_bps = cw_sum * 10000.0  # Convert to basis points

    # Thresholds per Cremers-Weinbaum:
    # |CW| > 10 bps = economically significant deviation
    if cw_bps > 15:
        signal = "BULLISH_CW"
        interp = (
            f"CW={cw_bps:.1f} bps — calls EXPENSIVE relative to puts. "
            "Per CW 2010: positive deviations predict HIGHER returns. "
            "High CW decile outperforms low by ~50 bps/day."
        )
    elif cw_bps > 5:
        signal = "SLIGHTLY_BULLISH"
        interp = f"CW={cw_bps:.1f} bps — mild call premium. Modestly bullish."
    elif cw_bps < -15:
        signal = "BEARISH_CW"
        interp = (
            f"CW={cw_bps:.1f} bps — puts EXPENSIVE relative to calls. "
            "Negative deviations predict LOWER returns."
        )
    elif cw_bps < -5:
        signal = "SLIGHTLY_BEARISH"
        interp = f"CW={cw_bps:.1f} bps — mild put premium. Modestly bearish."
    else:
        signal = "NEUTRAL_CW"
        interp = f"CW={cw_bps:.1f} bps — PCP holds within normal bounds."

    return {
        "cw_spread_bps": round(cw_bps, 2),
        "signal": signal,
        "interpretation": interp,
        "num_contracts": num_contracts,
    }


def real_drift_burst_risk(
    returns: list[float],
    gamma_imbalance_pct: float = 0.0,
    window_minutes: int = 60,
    significance: float = 2.0,
) -> dict[str, Any]:
    """Real drift burst detection from price returns — Christensen-Oomen-Reno (2018).

    Uses ACTUAL tick/minute returns to detect drift bursts rather than
    the gamma proxy fallback in drift_burst_risk().

    Algorithm:
      1. Compute local drift μ = mean(returns over window)
      2. Compute local volatility σ = std(returns over window)
      3. t-stat = |μ| × √n / σ  (test for drift dominating diffusion)
      4. |t| > 2.0 → potential drift burst (95% confidence)
      5. |t| > 3.0 → confirmed drift burst (99.7% confidence)
      6. If negative gamma + drift burst → FLASH CRASH risk elevated

    Args:
        returns: List of period returns (e.g., 1-min returns over 60-min window)
        gamma_imbalance_pct: Current Gamma Imbalance for interaction
        window_minutes: Number of periods (default 60 for 1-min returns)
        significance: t-stat threshold for detection (default 2.0)

    Returns:
        dict with drift_burst_detected, t_statistic, flash_crash_risk
    """
    n = len(returns)
    if n < 10:
        return {
            "drift_burst_detected": False,
            "t_statistic": 0.0,
            "severity": "insufficient_data",
            "interpretation": f"Need at least 10 returns, got {n}.",
        }

    # Local drift and volatility
    mu = sum(returns) / n
    variance = sum((r - mu) ** 2 for r in returns) / (n - 1) if n > 1 else 0.0
    sigma = variance ** 0.5

    if sigma <= 0:
        return {
            "drift_burst_detected": False,
            "t_statistic": 0.0,
            "severity": "zero_volatility",
            "interpretation": "Zero local volatility — no burst possible.",
        }

    t_stat = abs(mu) * (n ** 0.5) / sigma
    direction = "UPWARD" if mu > 0 else "DOWNWARD"

    # Christensen-Oomen-Reno thresholds
    if t_stat > 3.0:
        severity = "confirmed"
        drift_detected = True
        interp = (
            f"CONFIRMED drift burst |t|={t_stat:.1f} — explosive {direction} trend. "
            f"Per Christensen-Oomen-Reno 2018: drift dominates diffusion."
        )
    elif t_stat > significance:
        severity = "potential"
        drift_detected = True
        interp = (
            f"Potential drift burst |t|={t_stat:.1f} — monitor for acceleration."
        )
    else:
        severity = "none"
        drift_detected = False
        interp = f"No drift burst |t|={t_stat:.1f}. Diffusion dominates."

    result: dict[str, Any] = {
        "drift_burst_detected": drift_detected,
        "t_statistic": round(t_stat, 4),
        "severity": severity,
        "local_drift_bps": round(mu * 10000, 2),
        "local_vol_bps": round(sigma * 10000, 2),
        "direction": direction,
        "window_periods": n,
        "interpretation": interp,
    }

    # Flash crash interaction (Barbon-Buraschi Table VIII)
    if drift_detected and gamma_imbalance_pct < -1.0:
        result["flash_crash_risk"] = "HIGH"
        result["combined_risk"] = (
            f"Drift burst ({severity}, |t|={t_stat:.1f}) + "
            f"negative gamma ({gamma_imbalance_pct:.1f}%) → "
            "conditional flash crash probability 2-5x baseline."
        )
    elif drift_detected and gamma_imbalance_pct < -0.5:
        result["flash_crash_risk"] = "ELEVATED"

    return result


def demand_pressure_premium(
    net_gex: float,
    spot: float,
    atm_iv: float | None = None,
    put_call_ratio_oi: float | None = None,
    bid_ask_spread: float | None = None,
    vix: float | None = None,
) -> dict[str, Any]:
    """Demand pressure IV premium — GPP (2009) RFS published extension.

    Garleanu, Pedersen, Poteshman (2009) 'Demand-Based Option Pricing'
    Review of Financial Studies 22, 4259-4299.

    The published RFS version extends the 2008 SSRN with:
      1. Market maker CARA utility optimization with risk aversion γ
      2. End-user demand curve: D(P) = a - bP + noise
      3. Equilibrium price: P = BS + λ × NetDemand
         where λ = γ × σ² × (1-ρ) / market_depth
      4. Margin constraints amplify λ during funding stress

    Key finding: options with high end-user demand trade at a premium
    to Black-Scholes. This premium predicts future IV changes: high
    premium today → IV compression tomorrow as demand normalizes.

    Our proxy: combine GEX-based dealer inventory with PCR ratio
    to estimate the demand pressure premium on ATM IV.

    Args:
        net_gex: Net dollar GEX (negative = dealers short, end-users long)
        spot: Current spot price
        atm_iv: ATM implied volatility (optional, for premium estimation)
        put_call_ratio_oi: Put/Call OI ratio (optional)
        bid_ask_spread: Relative bid-ask spread (optional)
        vix: VIX level for funding stress proxy (optional)

    Returns:
        dict with demand_premium_bps, signal, iv_prediction
    """
    result: dict[str, Any] = {
        "demand_premium_bps": 0.0,
        "signal": "neutral",
        "iv_prediction": "stable",
    }

    # --- Dealer inventory pressure ---
    # Negative GEX → dealers short → end-users long → upward IV pressure
    # λ increases with: larger |GEX|, higher VIX (funding stress), wider spreads
    if spot <= 0:
        return result

    abs_gex_ratio = abs(net_gex) / (spot * 10_000_000) if spot > 0 else 0  # per $10M ADV

    # Base lambda (demand price impact coefficient)
    # GPP: λ = γ × σ² / market_depth
    # Proxy: λ ∝ |GEX| / (spot × ADV) × IV × spread
    base_lambda = abs_gex_ratio * 100  # scale to bps

    # Funding stress amplifier (VIX > 25 = stressed)
    funding_mult = 1.0
    if vix and vix > 30:
        funding_mult = 2.5
    elif vix and vix > 25:
        funding_mult = 1.8
    elif vix and vix > 20:
        funding_mult = 1.3

    # Illiquidity amplifier (wider spreads = higher λ)
    spread_mult = 1.0
    if bid_ask_spread and bid_ask_spread > 0.005:
        spread_mult = 2.0
    elif bid_ask_spread and bid_ask_spread > 0.002:
        spread_mult = 1.5

    demand_premium = base_lambda * funding_mult * spread_mult

    # Direction: negative GEX + low PCR = call demand dominant → IV bid up
    if net_gex < -1e9:
        if put_call_ratio_oi is not None and put_call_ratio_oi < 0.5:
            result["demand_premium_bps"] = round(demand_premium, 2)
            result["signal"] = "call_demand_premium"
            result["iv_prediction"] = "upward_pressure_then_compression"
            result["interpretation"] = (
                f"Dealers short gamma ({net_gex/1e9:.1f}B) + call demand dominant "
                f"(PCR={put_call_ratio_oi:.2f}). Per GPP 2009: end-user buying "
                f"pressure bids IV above fundamental value. "
                f"Expected: IV stays elevated near-term, compresses as demand normalizes. "
                f"Demand premium: {demand_premium:.0f} bps. "
                "Favorable for volatility selling strategies."
            )
        else:
            result["demand_premium_bps"] = round(demand_premium * 0.7, 2)
            result["signal"] = "moderate_demand_premium"
            result["iv_prediction"] = "mild_upward_pressure"
            result["interpretation"] = (
                "Dealers short gamma with moderate end-user demand. "
                "Mild IV premium expected."
            )
    elif net_gex > 1e9:
        result["demand_premium_bps"] = round(-demand_premium * 0.5, 2)
        result["signal"] = "demand_discount"
        result["iv_prediction"] = "downward_pressure"
        result["interpretation"] = (
            f"Dealers long gamma ({net_gex/1e9:.1f}B) — end-users net short. "
            "IV trading at discount to fundamental value."
        )
    else:
        result["interpretation"] = "Gamma near neutral — no significant demand pressure."

    if atm_iv:
        result["atm_iv"] = round(atm_iv, 4)
        result["estimated_fair_iv"] = round(atm_iv - demand_premium / 10000, 4)

    return result


def option_illiquidity_signal(
    option_price_changes: list[float] | None = None,
    option_dollar_volumes: list[float] | None = None,
    stock_amihud: float | None = None,
    bid_ask_spread: float | None = None,
    open_interest: float = 0.0,
) -> dict[str, Any]:
    """Option illiquidity → stock return signal — Goyenko-Ornthanalai-Tang.

    'Option Liquidity and Stock Return Predictability'

    Extends the Amihud (2002) illiquidity measure to options:
      Option Amihud = |ΔOptionPrice| / OptionDollarVolume

    Key finding: illiquid options predict LOWER stock returns.
    Stocks with illiquid options underperform by 30-50 bps/month.
    The effect is strongest for OTM options and near expirations.

    Channel: illiquid options → higher transaction costs → informed
    traders avoid → less price discovery in options → delayed
    information flow to stocks.

    Args:
        option_price_changes: List of daily option price changes
        option_dollar_volumes: List of daily option dollar volumes
        stock_amihud: Stock-level Amihud illiquidity (optional, for interaction)
        bid_ask_spread: Average relative bid-ask spread (optional)
        open_interest: Total OI for normalization

    Returns:
        dict with option_amihud, illiquidity_level, return_prediction
    """
    result: dict[str, Any] = {
        "option_amihud": None,
        "illiquidity_level": "insufficient_data",
        "return_prediction": "unknown",
    }

    # Compute option Amihud from daily data
    if option_price_changes and option_dollar_volumes:
        n = min(len(option_price_changes), len(option_dollar_volumes))
        if n > 5:
            daily_amihuds = []
            for i in range(n):
                dv = option_dollar_volumes[i]
                if dv > 0:
                    daily_amihuds.append(abs(option_price_changes[i]) / dv)
            if daily_amihuds:
                opt_amihud = sum(daily_amihuds) / len(daily_amihuds)
                result["option_amihud"] = round(opt_amihud, 8)
                result["n_days"] = len(daily_amihuds)
    elif bid_ask_spread is not None and bid_ask_spread > 0:
        # Proxy: wider spread → higher illiquidity
        result["option_amihud"] = round(bid_ask_spread * 100, 8)
        result["method"] = "spread_proxy"
    elif open_interest > 0:
        # Proxy: lower OI → higher illiquidity
        # Normalize: illiquidity ∝ 1/OI
        result["option_amihud"] = round(1.0 / max(open_interest, 1), 8)
        result["method"] = "oi_proxy"
    else:
        result["interpretation"] = "No data for option Amihud computation."
        return result

    opt_amihud = result.get("option_amihud") or 0

    # Threshold classification (Goyenko-Ornthanalai-Tang):
    # Option Amihud > 1e-6 → illiquid options → predicts lower returns
    if opt_amihud > 1e-5:
        result["illiquidity_level"] = "highly_illiquid"
        result["return_prediction"] = "bearish"
        result["expected_underperformance_bps"] = 50
        interp = (
            f"Option Amihud={opt_amihud:.2e} — HIGHLY illiquid options. "
            "Per Goyenko-Ornthanalai-Tang: stocks with illiquid options "
            "underperform by 30-50 bps/month. Informed traders avoid "
            "illiquid options → delayed price discovery."
        )
    elif opt_amihud > 1e-6:
        result["illiquidity_level"] = "moderately_illiquid"
        result["return_prediction"] = "mildly_bearish"
        result["expected_underperformance_bps"] = 20
        interp = (
            f"Option Amihud={opt_amihud:.2e} — moderately illiquid options. "
            "Mild underperformance expected."
        )
    else:
        result["illiquidity_level"] = "liquid"
        result["return_prediction"] = "neutral"
        interp = f"Option Amihud={opt_amihud:.2e} — liquid options. No illiquidity discount."

    result["interpretation"] = interp

    # Interaction with stock illiquidity (double penalty)
    if stock_amihud and stock_amihud > 1e-6 and opt_amihud > 1e-6:
        result["double_illiquidity"] = True
        result["interpretation"] += (
            f" Stock also illiquid (Amihud={stock_amihud:.2e}) — "
            "double penalty: both option and stock illiquidity."
        )

    return result


def vix_gamma_fragility(
    vix_spot: float | None = None,
    vix_future: float | None = None,
    gamma_imbalance_pct: float = 0.0,
    flip_distance_pct: float | None = None,
) -> dict[str, Any]:
    """VIX term structure × Gamma fragility interaction.

    Combines VIX futures curve steepness with gamma imbalance to
    produce a fragility regime signal. Based on the empirical
    relationship documented in Barbon-Buraschi and practitioner
    observations:

    - VIX contango (future > spot): dealers willing to warehouse risk
    - VIX backwardation (future < spot): dealers pulling capacity
    - Backwardation + negative gamma = MAXIMUM fragility
    - Near flip level + backwardation = regime transition risk

    VIX spread in %: (VIX_future - VIX_spot) / VIX_spot × 100

    Args:
        vix_spot: Current VIX level
        vix_future: Front-month VIX futures price
        gamma_imbalance_pct: ΓIB as % of ADV
        flip_distance_pct: Distance to zero-gamma flip (%)

    Returns:
        dict with fragility_regime, dealer_capacity, combined_risk
    """
    result: dict[str, Any] = {
        "fragility_regime": "unknown",
        "dealer_capacity": "normal",
        "combined_risk": "LOW",
    }

    # VIX term structure signal
    vix_spread_pct = 0.0
    if vix_spot and vix_future and vix_spot > 0:
        vix_spread_pct = (vix_future - vix_spot) / vix_spot * 100
        result["vix_spread_pct"] = round(vix_spread_pct, 2)

        if vix_spread_pct < -5:
            result["dealer_capacity"] = "severely_constrained"
            result["vix_regime"] = "strong_backwardation"
            interp = (
                f"VIX spread {vix_spread_pct:.1f}% — STRONG backwardation. "
                "Dealers severely pulling risk capacity. Options expensive "
                "near-term, cheap far-term. Hedging costs elevated."
            )
        elif vix_spread_pct < -2:
            result["dealer_capacity"] = "constrained"
            result["vix_regime"] = "backwardation"
            interp = (
                f"VIX spread {vix_spread_pct:.1f}% — backwardation. "
                "Dealers reducing risk warehouse capacity."
            )
        elif vix_spread_pct > 10:
            result["dealer_capacity"] = "expanding"
            result["vix_regime"] = "strong_contango"
            interp = (
                f"VIX spread {vix_spread_pct:.1f}% — STRONG contango. "
                "Dealers expanding risk capacity. Favorable for vol selling."
            )
        elif vix_spread_pct > 5:
            result["dealer_capacity"] = "comfortable"
            result["vix_regime"] = "contango"
            interp = f"VIX spread {vix_spread_pct:.1f}% — contango. Normal risk environment."
        else:
            result["dealer_capacity"] = "normal"
            result["vix_regime"] = "flat"
            interp = f"VIX spread {vix_spread_pct:.1f}% — flat term structure."
    else:
        result["vix_regime"] = "data_unavailable"
        interp = "VIX data unavailable."

    # Gamma interaction
    result["interpretation"] = interp
    neg_gamma = gamma_imbalance_pct < -1.0
    near_flip = flip_distance_pct is not None and abs(flip_distance_pct) < 2.0

    if result.get("dealer_capacity") in ("severely_constrained", "constrained") and neg_gamma:
        result["fragility_regime"] = "maximum_fragility"
        result["combined_risk"] = "EXTREME"
        result["interpretation"] += (
            f" + Negative gamma ({gamma_imbalance_pct:.1f}%) — MAXIMUM fragility. "
            "Dealers cannot absorb shocks. Flash crash risk extreme. "
            "Reduce all risk, avoid short gamma strategies."
        )
        if near_flip:
            result["combined_risk"] = "CRITICAL"
            result["interpretation"] += " NEAR FLIP LEVEL — regime transition imminent."
    elif result.get("dealer_capacity") in ("severely_constrained", "constrained"):
        result["fragility_regime"] = "elevated_fear"
        result["combined_risk"] = "HIGH"
        result["interpretation"] += (
            " Dealers constrained but gamma neutral — elevated vol but not crash-prone."
        )
    elif neg_gamma and result.get("dealer_capacity") == "expanding":
        result["fragility_regime"] = "contained_fragility"
        result["combined_risk"] = "MODERATE"
        result["interpretation"] += (
            " Negative gamma but dealers expanding capacity — contained risk."
        )
    elif result.get("dealer_capacity") == "expanding":
        result["fragility_regime"] = "low_fragility"
        result["combined_risk"] = "LOW"
    else:
        result["fragility_regime"] = "normal"
        result["combined_risk"] = "LOW"

    return result


# ============================================================================
# NEW SIGNALS — 2024-2025 Research Frontier
# ============================================================================


def overnight_drift_risk(
    net_gex_at_close: float,
    gamma_imbalance_pct: float,
    vix: float | None = None,
    vix_term_structure: float | None = None,
    put_call_ratio_oi: float | None = None,
    dte_days: float = 1.0,
) -> dict[str, Any]:
    """Overnight gap risk from dealer gamma positioning at market close.

    Based on the empirical relationship between end-of-day dealer gamma
    and overnight/next-day returns documented in Barbon-Buraschi (2021)
    and practitioner observations from SqueezeMetrics Implied Order Book.

    Mechanism:
      - Dealers holding large net gamma positions at close MUST delta-hedge
        any overnight gap at the open, amplifying the move
      - Negative gamma + gap down → dealers sell into weakness → cascade
      - Positive gamma + gap up → dealers buy → amplifying rally
      - VIX elevation indicates dealer hedging costs are higher →
        more aggressive hedging at open

    Key formula:
      OvernightDriftRisk = f(ΓIB_close, VIX, VIX_futures_slope, DTE)

    Args:
        net_gex_at_close: Net dollar GEX at market close
        gamma_imbalance_pct: ΓIB at close as % of ADV
        vix: Current VIX level (optional, default 18)
        vix_term_structure: VIX futures - VIX spot spread (optional)
        put_call_ratio_oi: OI-based put/call ratio (optional)
        dte_days: Days to expiration for front-month options

    Returns:
        dict with overnight_risk_level, predicted_gap_direction, hedging_pressure
    """
    result: dict[str, Any] = {
        "overnight_risk_level": "LOW",
        "predicted_gap_direction": "neutral",
        "hedging_pressure_at_open": "minimal",
        "gap_magnitude_estimate_pct": 0.0,
    }

    vix_val = vix if vix is not None and vix > 0 else 18.0
    abs_gib = abs(gamma_imbalance_pct)

    # Base overnight risk from gamma imbalance magnitude
    # Larger |ΓIB| → more dealer positions to hedge at open
    if abs_gib > 2.0:
        base_risk = 0.30
        pressure = "aggressive"
    elif abs_gib > 1.0:
        base_risk = 0.18
        pressure = "significant"
    elif abs_gib > 0.5:
        base_risk = 0.10
        pressure = "moderate"
    elif abs_gib > 0.1:
        base_risk = 0.05
        pressure = "minimal"
    else:
        base_risk = 0.02
        pressure = "negligible"

    # VIX amplification: higher VIX → dealers hedge more aggressively at open
    if vix_val > 30:
        vix_mult = 2.0
        result["vix_regime"] = "extreme_fear"
    elif vix_val > 25:
        vix_mult = 1.5
        result["vix_regime"] = "elevated_fear"
    elif vix_val > 20:
        vix_mult = 1.2
        result["vix_regime"] = "moderate"
    elif vix_val > 15:
        vix_mult = 1.0
        result["vix_regime"] = "normal"
    else:
        vix_mult = 0.8
        result["vix_regime"] = "complacent"

    # VIX term structure: backwardation → dealers pulling capacity → higher risk
    if vix_term_structure is not None:
        if vix_term_structure < -1.0:
            vix_ts_mult = 1.5
            result["vix_term_regime"] = "backwardation"
        elif vix_term_structure < 0:
            vix_ts_mult = 1.2
            result["vix_term_regime"] = "mild_backwardation"
        else:
            vix_ts_mult = 1.0
            result["vix_term_regime"] = "contango"
    else:
        vix_ts_mult = 1.0

    # PCR interaction: high PCR + negative gamma = dealers short puts →
    # gap down forces aggressive put hedging at open
    pcr_val = put_call_ratio_oi if put_call_ratio_oi is not None else 0.5
    if pcr_val > 0.65 and gamma_imbalance_pct < 0 or pcr_val < 0.35 and gamma_imbalance_pct > 0:
        pcr_mult = 1.3
    else:
        pcr_mult = 1.0

    # Final overnight risk score
    overnight_risk = min(base_risk * vix_mult * vix_ts_mult * pcr_mult, 0.95)

    # Classification
    if overnight_risk > 0.30:
        result["overnight_risk_level"] = "CRITICAL"
    elif overnight_risk > 0.20:
        result["overnight_risk_level"] = "HIGH"
    elif overnight_risk > 0.10:
        result["overnight_risk_level"] = "ELEVATED"
    elif overnight_risk > 0.05:
        result["overnight_risk_level"] = "MODERATE"
    else:
        result["overnight_risk_level"] = "LOW"

    # Predicted gap direction
    if gamma_imbalance_pct < -1.0:
        result["predicted_gap_direction"] = "amplify_any_move"
        result["direction_note"] = (
            "Dealers net short gamma — any overnight gap will be AMPLIFIED "
            "by dealer hedging at open. Gap down → forced selling cascade. "
            "Gap up → forced buying. Expect wider-than-normal opening range."
        )
    elif gamma_imbalance_pct > 1.0:
        result["predicted_gap_direction"] = "fade_the_gap"
        result["direction_note"] = (
            "Dealers net long gamma — overnight gaps tend to FADE. "
            "Dealers buy into weakness and sell into strength at open. "
            "Expect mean reversion after initial gap."
        )
    elif pcr_val > 0.65:
        result["predicted_gap_direction"] = "bearish_bias"
    elif pcr_val < 0.35:
        result["predicted_gap_direction"] = "bullish_bias"
    else:
        result["predicted_gap_direction"] = "neutral"

    # Gap magnitude estimate (approximate from ΓIB × VIX regime)
    gap_est = abs_gib * 0.5 * (vix_val / 16.0)
    result["gap_magnitude_estimate_pct"] = round(gap_est, 2)
    result["overnight_risk_score"] = round(overnight_risk, 4)
    result["hedging_pressure_at_open"] = pressure
    result["gamma_imbalance_pct"] = round(gamma_imbalance_pct, 4)
    result["vix"] = round(vix_val, 2)
    result["net_gex_at_close"] = round(net_gex_at_close, 2)

    return result


def dealer_balance_sheet_fragility(
    vix: float | None = None,
    vix_term_structure: float | None = None,
    gamma_imbalance_pct: float = 0.0,
    ted_spread: float | None = None,
    credit_spread: float | None = None,
    dealer_leverage_proxy: float | None = None,
) -> dict[str, Any]:
    """Dealer balance sheet capacity and gamma absorption fragility.

    Post-SVB (March 2023) research on dealer capital constraints:
    When dealer balance sheets are stressed (high VIX, wide credit spreads,
    elevated funding costs), their capacity to absorb gamma risk diminishes.
    This creates a feedback loop: less capacity → wider spreads → higher
    hedging costs → even less capacity.

    Key channels:
      1. VIX level: higher VIX → higher VaR → dealers reduce risk limits
      2. VIX term structure: backwardation → funding stress
      3. Credit spreads: wider → dealer funding costs higher
      4. TED spread: wider → interbank funding stress → dealer balance sheet cost
      5. Gamma imbalance: large |ΓIB| → more inventory risk

    Composite Dealer Fragility Index (DFI):
      DFI = w1×VIX_stress + w2×VIX_TS_stress + w3×Credit_stress +
            w4×Funding_stress + w5×Gamma_stress

    Args:
        vix: Current VIX level
        vix_term_structure: VIX futures - VIX spot spread
        gamma_imbalance_pct: ΓIB as % of ADV
        ted_spread: TED spread in bps (3M LIBOR - 3M T-bill, or SOFR equivalent)
        credit_spread: IG credit spread in bps (e.g., CDX IG 5Y)
        dealer_leverage_proxy: Dealer leverage proxy (e.g., primary dealer repo)

    Returns:
        dict with dfi_score, fragility_regime, dealer_capacity_utilization
    """
    vix_val = vix if vix is not None and vix > 0 else 18.0

    # --- Component 1: VIX stress (0-1) ---
    if vix_val > 35:
        vix_stress = 1.0
    elif vix_val > 28:
        vix_stress = 0.8
    elif vix_val > 22:
        vix_stress = 0.5
    elif vix_val > 18:
        vix_stress = 0.3
    elif vix_val > 14:
        vix_stress = 0.1
    else:
        vix_stress = 0.0

    # --- Component 2: VIX term structure stress (0-1) ---
    if vix_term_structure is not None:
        if vix_term_structure < -2.0:
            vix_ts_stress = 1.0
        elif vix_term_structure < -1.0:
            vix_ts_stress = 0.7
        elif vix_term_structure < 0:
            vix_ts_stress = 0.4
        elif vix_term_structure < 1.0:
            vix_ts_stress = 0.1
        else:
            vix_ts_stress = 0.0
    else:
        vix_ts_stress = 0.3  # neutral assumption

    # --- Component 3: Credit stress (0-1) ---
    if credit_spread is not None:
        if credit_spread > 200:
            credit_stress = 1.0
        elif credit_spread > 130:
            credit_stress = 0.7
        elif credit_spread > 90:
            credit_stress = 0.4
        elif credit_spread > 60:
            credit_stress = 0.1
        else:
            credit_stress = 0.0
    else:
        credit_stress = 0.1  # low stress default

    # --- Component 4: Funding stress (TED spread proxy, 0-1) ---
    if ted_spread is not None:
        if ted_spread > 100:
            funding_stress = 1.0
        elif ted_spread > 50:
            funding_stress = 0.7
        elif ted_spread > 30:
            funding_stress = 0.4
        elif ted_spread > 15:
            funding_stress = 0.2
        else:
            funding_stress = 0.0
    else:
        funding_stress = 0.0

    # --- Component 5: Gamma inventory stress (0-1) ---
    abs_gib = abs(gamma_imbalance_pct)
    if abs_gib > 3.0:
        gamma_stress = 1.0
    elif abs_gib > 2.0:
        gamma_stress = 0.8
    elif abs_gib > 1.0:
        gamma_stress = 0.5
    elif abs_gib > 0.5:
        gamma_stress = 0.3
    else:
        gamma_stress = 0.0

    # --- Composite Dealer Fragility Index ---
    # Weights: VIX 25%, VIX TS 15%, Credit 20%, Funding 15%, Gamma 25%
    dfi = (
        0.25 * vix_stress
        + 0.15 * vix_ts_stress
        + 0.20 * credit_stress
        + 0.15 * funding_stress
        + 0.25 * gamma_stress
    )

    # --- Regime classification ---
    if dfi > 0.7:
        fragility = "CRITICAL"
        capacity = "severely_constrained"
        interpretation = (
            f"DFI={dfi:.2f} — CRITICAL dealer balance sheet fragility. "
            "Multiple stress channels active. Dealer capacity severely "
            "constrained. Option liquidity likely impaired. "
            "High probability of sharp dislocations. Reduce position sizes."
        )
    elif dfi > 0.5:
        fragility = "HIGH"
        capacity = "constrained"
        interpretation = (
            f"DFI={dfi:.2f} — HIGH fragility. Dealers operating with "
            "reduced capacity. Expect wider spreads, aggressive hedging."
        )
    elif dfi > 0.3:
        fragility = "ELEVATED"
        capacity = "moderately_constrained"
        interpretation = (
            f"DFI={dfi:.2f} — ELEVATED fragility. Some stress channels active."
        )
    elif dfi > 0.15:
        fragility = "MODERATE"
        capacity = "normal"
        interpretation = f"DFI={dfi:.2f} — MODERATE. Normal dealer conditions."
    else:
        fragility = "LOW"
        capacity = "ample"
        interpretation = (
            f"DFI={dfi:.2f} — LOW fragility. Dealers have ample balance sheet "
            "capacity. Favorable for option liquidity."
        )

    return {
        "dfi_score": round(dfi, 4),
        "fragility_regime": fragility,
        "dealer_capacity": capacity,
        "interpretation": interpretation,
        "components": {
            "vix_stress": round(vix_stress, 2),
            "vix_term_structure_stress": round(vix_ts_stress, 2),
            "credit_stress": round(credit_stress, 2),
            "funding_stress": round(funding_stress, 2),
            "gamma_inventory_stress": round(gamma_stress, 2),
        },
        "vix": round(vix_val, 2),
        "gamma_imbalance_pct": round(gamma_imbalance_pct, 4),
    }


def cross_asset_gamma_spillover(
    spx_gamma_imbalance_pct: float,
    single_stock_gamma_imbalance_pct: float = 0.0,
    spx_vix: float | None = None,
    cross_asset_beta: float | None = None,
    sector: str = "broad",
) -> dict[str, Any]:
    """Cross-asset gamma spillover — SPX gamma → single-stock volatility.

    Measures how gamma imbalances in index options (SPX/SPY) spill over
    into single-stock options through dealer hedging networks.

    Mechanism:
      - When index dealers are short gamma, their delta-hedging of index
        options creates correlated flows across ALL constituents
      - This means SPX gamma imbalance affects single-stock option liquidity
        and volatility even without stock-specific gamma changes
      - The spillover is strongest for high-beta stocks and during high VIX

    Cross-Asset Gamma Beta (CAGB):
      If not provided, estimated from sector:
        Tech: 1.5, Financials: 1.3, Broad: 1.0, Defensive: 0.7, Utilities: 0.5

    Args:
        spx_gamma_imbalance_pct: SPX/SPY ΓIB as % of ADV
        single_stock_gamma_imbalance_pct: Stock-specific ΓIB (optional)
        spx_vix: Current VIX (optional)
        cross_asset_beta: Stock's sensitivity to index gamma flows (optional)
        sector: Sector classification for beta estimation

    Returns:
        dict with spillover_risk, effective_gamma, index_driver_pct
    """
    # Cross-Asset Gamma Beta estimation
    if cross_asset_beta is not None:
        cagb = cross_asset_beta
    else:
        sector_betas = {
            "technology": 1.5,
            "tech": 1.5,
            "financials": 1.3,
            "financial": 1.3,
            "consumer_discretionary": 1.2,
            "consumer_cyclical": 1.2,
            "industrials": 1.1,
            "industrial": 1.1,
            "energy": 1.0,
            "materials": 1.0,
            "broad": 1.0,
            "healthcare": 0.8,
            "health_care": 0.8,
            "consumer_staples": 0.7,
            "defensive": 0.7,
            "utilities": 0.5,
            "real_estate": 0.6,
            "reit": 0.6,
        }
        cagb = sector_betas.get(sector.lower(), 1.0)

    # Effective gamma = stock-specific + spillover from index
    spillover_gamma = spx_gamma_imbalance_pct * cagb
    effective_gamma = single_stock_gamma_imbalance_pct + spillover_gamma

    # Index driver: what fraction of effective gamma comes from index spillover?
    if abs(effective_gamma) > 0.001:
        index_driver_pct = abs(spillover_gamma) / abs(effective_gamma) * 100
    else:
        index_driver_pct = 0.0

    # VIX amplification of spillover
    vix_val = spx_vix if spx_vix is not None and spx_vix > 0 else 18.0
    if vix_val > 30:
        spillover_mult = 1.5
    elif vix_val > 25:
        spillover_mult = 1.3
    elif vix_val > 20:
        spillover_mult = 1.1
    else:
        spillover_mult = 1.0

    spillover_risk = abs(spillover_gamma) * spillover_mult

    # Risk classification
    if spillover_risk > 3.0:
        risk_level = "EXTREME_SPILLOVER"
    elif spillover_risk > 1.5:
        risk_level = "HIGH_SPILLOVER"
    elif spillover_risk > 0.5:
        risk_level = "MODERATE_SPILLOVER"
    elif spillover_risk > 0.1:
        risk_level = "MILD_SPILLOVER"
    else:
        risk_level = "MINIMAL_SPILLOVER"

    # Interpretation
    if index_driver_pct > 50:
        driver_note = (
            f"Index gamma ({index_driver_pct:.0f}% of effective gamma) is the "
            f"DOMINANT driver of this stock's gamma profile. Single-stock "
            f"signals may be misleading — trade the index, not the stock."
        )
    elif index_driver_pct > 25:
        driver_note = (
            f"Index gamma contributes {index_driver_pct:.0f}% of effective "
            f"gamma — significant spillover. Factor index conditions into "
            f"single-stock decisions."
        )
    else:
        driver_note = (
            f"Stock-specific gamma dominates ({100 - index_driver_pct:.0f}%). "
            f"Index spillover is secondary."
        )

    return {
        "spillover_risk_level": risk_level,
        "spillover_risk_score": round(spillover_risk, 4),
        "effective_gamma_imbalance_pct": round(effective_gamma, 4),
        "spillover_gamma_pct": round(spillover_gamma, 4),
        "stock_specific_gamma_pct": round(single_stock_gamma_imbalance_pct, 4),
        "index_driver_pct": round(index_driver_pct, 1),
        "cross_asset_gamma_beta": round(cagb, 2),
        "sector": sector,
        "driver_note": driver_note,
        "spx_gamma_imbalance_pct": round(spx_gamma_imbalance_pct, 4),
        "vix": round(vix_val, 2),
    }
