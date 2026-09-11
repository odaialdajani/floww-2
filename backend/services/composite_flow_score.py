"""
backend/services/composite_flow_score.py

Composite Flow Score synthesis service.

This is the *headline synthesis* of every analytics service that has
been ported into Flowseeker Pro so far. It takes the existing five
sub-services and produces a single 0..100 heuristic magnitude score +
a 4-band label, displayed as the LEAD chip in the Flowseeker Pro
summary bar.

Pure-Python only — no torch / numba / scipy (Round-9 freeze rule).

The score combines five sub-scores (each in [0, 1]). Statistical independence
and tradability are not established by this weighted construction:

  * **illiquidity** — average of (Amihud normalised) and (|Kyle's λ|
    normalised). High when the chained illiquidity story suggests
    shallow markets.
  * **toxicity**    — VPIN itself (already 0..1). High when the order
    flow proxy reads elevated; this does not observe an informed-trader fraction.
  * **dislocation** — HMM regime confidence × disagreement-with-OFI
    factor. ELEVATES when regime and flow disagree, without establishing
    mispricing or an executable opportunity.
  * **direction**   — |OFI aggregate| normalised to a 1000-share cap.
    High when short-term book dominance is strong in either direction.
  * **sentiment** — magnitude of the available sentiment polarity;
    missing sentiment contributes zero.

Composite::

    score = 100 · (0.25·illiquidity + 0.20·toxicity + 0.25·dislocation
                  + 0.20·direction + 0.10·sentiment)

Threshold bands (mirrors the Blademap
:func:`institutional_detector.convictionLabel` precedent)::

      score >= 80         → HIGH    (green)
      60 ≤ score < 80     → MED     (amber)
      40 ≤ score < 60     → WATCH   (slate-grey)
      score < 40          → LOW     (slate-dark)

The composite is **strictly ANY-warming**: if any sub-service reports
``is_warming=True`` (or OFI lacks ≥2 chain snapshots) the composite is
flagged ``is_warming=True`` and ``score = 0`` — we never report a
signal built on under-initialised components.

Output schema (snake_case, matches the established Flowseeker style)::

    {
        "composite":     float,    # 0..100 (or 0 while warming)
        "label":         "HIGH" | "MED" | "WATCH" | "LOW",
        "label_color":   "#...",
        "sub_scores":    { "illiquidity": .., "toxicity": ..,
                           "dislocation": .., "direction": ..,
                           "sentiment": .. },
        "components":    { "amihud_norm": .., "kyle_norm": ..,
                           "vpin": .., "regime": "TRENDING_BULL"|..,
                           "ofi_aggr": float },
        "n_obs_min":     int,
        "is_warming":    bool,
    }

Usage::

    from services.composite_flow_score import CompositeFlowScore
    out = CompositeFlowScore.compute(
        amihud_out  = amihud.compute(),
        kyle_out    = kyle.compute(),
        vpin_out    = vpin.compute(),
        regime_out  = hmm.classify(),
        ofi_out     = sof.compute(),
    )
"""

from __future__ import annotations

from typing import Any

# ─────────────────────────────────────────────────────────────────────
# Label band + colour palette (mirrors Blademap conviction palette)
# ─────────────────────────────────────────────────────────────────────

LABEL_HIGH = "HIGH"
LABEL_MED = "MED"
LABEL_WATCH = "WATCH"
LABEL_LOW = "LOW"

LABEL_COLORS: dict[str, str] = {
    LABEL_HIGH:  "#22c55e",  # green
    LABEL_MED:   "#fbbf24",  # amber
    LABEL_WATCH: "#a3a3a3",  # slate-grey
    LABEL_LOW:   "#64748b",  # slate-dark
}


def _classify_score(score: float) -> str:
    """Map a 0..100 composite to a 4-band label per Blademap convention."""
    if score >= 80.0:
        return LABEL_HIGH
    if score >= 60.0:
        return LABEL_MED
    if score >= 40.0:
        return LABEL_WATCH
    return LABEL_LOW


# ─────────────────────────────────────────────────────────────────────
# Sub-score normalisation helpers (pure functions, no torch)
# ─────────────────────────────────────────────────────────────────────

# Anchor values for the illiquidity sub-scores (10× the ILLIQUID threshold
# in each raw-unit space, so a "1.0" sub-score maps well above the spec
# ILLIQUID band).
_AMIHUD_ANCHOR = 1e-4
_KYLE_ANCHOR = 0.01     # 2× the spec ILLIQUID threshold (0.005)
_OFI_ANCHOR = 1000.0    # shares; caps absolute OFI aggregate


def _norm_amihud(amihud: float) -> float:
    a = float(amihud or 0.0)
    if a < 0.0:
        a = 0.0
    return min(a / _AMIHUD_ANCHOR, 1.0)


def _norm_kyle(lam: float) -> float:
    a = abs(float(lam or 0.0))
    if a < 0.0:
        a = 0.0
    return min(a / _KYLE_ANCHOR, 1.0)


def _norm_vpin(vpin: float) -> float:
    v = float(vpin or 0.0)
    if v < 0.0:
        v = 0.0
    return min(v, 1.0)


def _norm_direction(ofi_aggr: float) -> float:
    v = abs(float(ofi_aggr or 0.0))
    return min(v / _OFI_ANCHOR, 1.0)


def _dislocation(regime_out: dict[str, Any], ofi_out: dict[str, Any]) -> float:
    """Combine HMM regime confidence with regime/flow disagreement.

    A trending regime agreeing with the flow direction scores
    ~``0.5 · confidence`` (normal trend; *some* dislocation).
    A trending regime disagreeing with the flow direction scores
    ``min(1.5 · confidence, 1.0)`` (heuristic disagreement, not proven mispricing).
    A ranging regime scores 0 regardless of OFI.

    Capped at 1.0.
    """
    state = regime_out.get("current_state", "RANGING") or "RANGING"
    confidence = float(regime_out.get("confidence", 0.0) or 0.0)
    raw_ofi = float(ofi_out.get("of_aggregated", 0.0) or 0.0)

    if state == "RANGING":
        return 0.0

    state_bull = state == "TRENDING_BULL"
    ofi_bull = raw_ofi > 0.0
    conflict = 1.0 if (state_bull != ofi_bull) else 0.0
    non_ranging = 1.0
    raw = confidence * (non_ranging * 0.5 + conflict * 1.0)
    return min(raw, 1.0)


# ─────────────────────────────────────────────────────────────────────
# Pure synthesis class (no per-instance state; sub-services own the
# rolling windows).
# ─────────────────────────────────────────────────────────────────────

# Sub-score weights (sum = 1.0). The five-component split was reshaped
# in the steal-list deferred-(b) ship to absorb sentiment as a 5th
# orthogonal sub-score: illiquidity 0.30 → 0.25, toxicity 0.25 → 0.20,
# dislocation stays 0.25, direction stays 0.20, NEW sentiment 0.10.
# Mirror in services/composite_confidence.py:80 — update both files
# together when these weights change.
_W_ILLIQUIDITY = 0.25
_W_TOXICITY    = 0.20
_W_DISLOCATION = 0.25
_W_DIRECTION   = 0.20
_W_SENTIMENT   = 0.10


def _norm_sentiment(raw_score: float) -> float:
    """Normalise the [-1, 1] sentiment polarity to a [0, 1] sub-score.

    The composite evaluates ``conviction magnitude`` (already 0..100).
    Strong sentiment polarisation in EITHER direction translates to
    elevated conviction — same convention as ``_norm_direction``
    treating a +1000 or -1000 OFI aggregate as equally directional.

    Returns 0.0 (not 1.0) when ``raw_score`` is exactly 0.0 (neutral).
    """
    s = abs(float(raw_score or 0.0))
    if s < 0.0:
        s = 0.0
    return min(s, 1.0)


class CompositeFlowScore:
    """Stateless synthesis of the Flowseeker Pro 5-service stack."""

    @staticmethod
    def compute(
        amihud_out:  dict[str, Any],
        kyle_out:    dict[str, Any],
        vpin_out:    dict[str, Any],
        regime_out:  dict[str, Any],
        ofi_out:     dict[str, Any],
        sentiment_out: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # 1. Strict ANY-warming across sub-services. OFI is special-cased
        # because it doesn't expose ``is_warming`` — its warming marker
        # is ``snaps_used < 2``. Sentiment is special-cased: missing
        # sentiment does NOT flip is_warming (social-flow payloads are
        # inherently flaky and a near-zero sentiment is a valid input,
        # not a "service not yet initialised" sentinel).
        amihud_warming = bool(amihud_out.get("is_warming", True))
        kyle_warming   = bool(kyle_out.get("is_warming", True))
        vpin_warming   = bool(vpin_out.get("is_warming", True))
        regime_warming = bool(regime_out.get("is_warming", True))
        ofi_snaps      = int(ofi_out.get("snaps_used", 0) or 0)
        ofi_warming    = ofi_snaps < 2
        is_warming     = any([
            amihud_warming, kyle_warming, vpin_warming,
            regime_warming, ofi_warming,
        ])

        # The minimum n_obs across the stack (excluding OFI which uses
        # snaps_used).
        n_obs_min = min(
            int(amihud_out.get("n_obs", 0) or 0),
            int(kyle_out.get("n_obs", 0) or 0),
            int(vpin_out.get("n_buckets",
                             vpin_out.get("n_obs", 0)) or 0),
            int(regime_out.get("n_obs", 0) or 0),
        )

        # 2. Per-sub-score normalisation.
        raw_amihud   = float(amihud_out.get("amihud", 0.0) or 0.0)
        norm_amihud  = _norm_amihud(raw_amihud)
        raw_kyle     = float(kyle_out.get("lambda_value", 0.0) or 0.0)
        norm_kyle    = _norm_kyle(raw_kyle)
        illiquidity_score = (norm_amihud + norm_kyle) / 2.0

        raw_vpin     = float(vpin_out.get("vpin", 0.0) or 0.0)
        toxicity_score    = _norm_vpin(raw_vpin)

        dislocation_score = _dislocation(regime_out, ofi_out)

        raw_ofi_aggr = float(ofi_out.get("of_aggregated", 0.0) or 0.0)
        direction_score   = _norm_direction(raw_ofi_aggr)

        # 2b. Sentiment sub-score (steal-list deferred-(b) ship). Pulls
        # through the canonical extract_sentiment_feature helper so the
        # clamp + aggregation gate lives in ONE place. Missing/wrong-shape
        # -> raw_score=0.0 (degrade gracefully, no warming flip).
        sentiment_score    = 0.0
        sentiment_available = False
        if sentiment_out is not None:
            try:
                from services.sentiment import extract_sentiment_feature
                sentiment_score, sentiment_available = (
                    extract_sentiment_feature(sentiment_out)
                )
            except Exception as exc:    # pragma: no cover
                # Defensive degrade — never let a sentiment exception
                # bring down the composite.
                import logging
                logging.warning(
                    f"composite_flow_score: sentiment extraction failed: "
                    f"{type(exc).__name__}: {exc}"
                )
                sentiment_score = 0.0
                sentiment_available = False
        norm_sentiment = _norm_sentiment(sentiment_score)

        # 3. Weighted composite (5-component split).
        composite_raw = 100.0 * (
            _W_ILLIQUIDITY * illiquidity_score
            + _W_TOXICITY    * toxicity_score
            + _W_DISLOCATION * dislocation_score
            + _W_DIRECTION   * direction_score
            + _W_SENTIMENT   * norm_sentiment
        )
        if is_warming:
            composite_raw = 0.0
        composite_final = float(round(composite_raw, 1))

        # 4. Label + colour.
        label = _classify_score(composite_final)
        label_color = LABEL_COLORS[label]

        # 5. Clip the components payload so it stays Ethernet-safe
        # (round large OFI aggregates to a 4-digit float to avoid
        # printing e.g. 9.87654e32 in the UI).
        clipped_ofi = max(-9999.0, min(raw_ofi_aggr, 9999.0))

        return {
            "composite":   composite_final,
            "label":       label,
            "label_color": label_color,
            "sub_scores": {
                "illiquidity": float(round(illiquidity_score, 3)),
                "toxicity":    float(round(toxicity_score, 3)),
                "dislocation": float(round(dislocation_score, 3)),
                "direction":   float(round(direction_score, 3)),
                "sentiment":   float(round(norm_sentiment, 3)),
            },
            "components": {
                "amihud_norm": float(round(norm_amihud, 3)),
                "kyle_norm":   float(round(norm_kyle, 3)),
                "vpin":        float(round(raw_vpin, 3)),
                "regime":      str(regime_out.get("current_state",
                                                   "RANGING") or "RANGING"),
                "ofi_aggr":    float(clipped_ofi),
                "sentiment":   float(round(sentiment_score, 4)),
                "sentiment_available": sentiment_available,
            },
            "n_obs_min":  int(n_obs_min),
            "is_warming": bool(is_warming),
            # Paper-accurate GEX (Ni-Pearson 2020 + Barbon-Buraschi 2021).
            # gex_out is optional — callers that fetch GEX pass it through;
            # _safe_gex_imbalance degrades to a neutral default otherwise.
            "gex_gamma_imbalance": _safe_gex_imbalance(
                amihud_out.get("gex_out") or kyle_out.get("gex_out")),
        }


__all__ = [
    "CompositeFlowScore",
    "LABEL_HIGH",
    "LABEL_MED",
    "LABEL_WATCH",
    "LABEL_LOW",
    "LABEL_COLORS",
]

def _safe_gex_imbalance(gex_out=None):
    """Extract Gamma Imbalance from GEX output, returning None if unavailable."""
    if not gex_out:
        return None
    try:
        net_gex = gex_out.get("net_gex", 0)
        spot = gex_out.get("spot", gex_out.get("_spot", 0)) or 0
        if spot > 0 and net_gex != 0:
            from services.gex_paper_accurate import compute_gamma_imbalance
            _adv = gex_out.get("adv_shares", 10_000_000) or 10_000_000
            gi = compute_gamma_imbalance(net_gex, spot, _adv)
            return {"gamma_imbalance_pct": gi["gamma_imbalance_pct"], "regime": gi["regime"]}
    except Exception:
        pass  # silent by design: gamma-imbalance sub-score is optional; caller gets None and skips it
    return None
