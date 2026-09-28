"""Unified conviction rank: fuse 4 scorers + invalidation feed.

Maximization build #3. The four scorers EXIST (flow conviction 0-100,
opportunity 0-10, confluence signed, ML UP/HOLD/DOWN); this module only
fuses them into ONE ranked row with invalidation + evidence links.
Pure math, no I/O, no network. Never invents direction: missing
inputs degrade the tier, never fabricate confidence.
"""

from __future__ import annotations

SCHEMA_VERSION = "conviction_rank.v1"
VERSION = "conviction_rank.v1"
WEIGHTS = {"flow": 0.35, "opportunity": 0.30, "confluence": 0.20, "ml": 0.15}
TIERS = ("HIGH", "MED", "WATCH", "LOW")


def _clamp01(x):
    try:
        f = float(x)
    except (TypeError, ValueError):
        return 0.0
    if f != f or f in (float("inf"), float("-inf")):
        return 0.0
    return max(0.0, min(1.0, f))


def _norm_flow(flow):
    if flow is None:
        return 0.0, "missing"
    try:
        v = float(flow.get("conviction", flow.get("score", 0)) if isinstance(flow, dict) else flow)
    except (TypeError, ValueError):
        return 0.0, "invalid"
    return _clamp01(v / 100.0), "ok"


def _norm_opp(opp):
    if opp is None:
        return 0.0, "missing"
    try:
        v = float(opp.get("opportunity_score", 0) if isinstance(opp, dict) else opp)
    except (TypeError, ValueError):
        return 0.0, "invalid"
    return _clamp01(v / 10.0), "ok"


def _norm_conf(conf):
    # A missing input is an ABSENT observation, not a neutral one. Returning
    # 0.5 here made an entirely empty setup score 17.5 (0.2*0.5 + 0.15*0.5),
    # which outranked real but weak evidence and read as a low-conviction
    # signal rather than the absence of one. `*_status` already reports
    # "missing", so the component must be 0.0 to agree with it.
    if conf is None:
        return 0.0, "missing"
    try:
        v = float(conf.get("total", 0) if isinstance(conf, dict) else conf)
    except (TypeError, ValueError):
        return 0.0, "invalid"
    # `total` is signed, so 0 is genuinely "no confluence signal". Rescale
    # around 0 rather than 0->0.5, so a neutral reading contributes nothing
    # instead of half a directional signal, and bearish/bullish totals of
    # equal magnitude receive equal quality.
    return _clamp01(abs(v) / 100.0), "ok"


_ML_MAP = {
    "UP": 1.0,
    "BULLISH": 1.0,
    "BULL": 1.0,
    "HOLD": 0.5,
    "NEUTRAL": 0.5,
    "DOWN": 0.0,
    "BEARISH": 0.0,
    "BEAR": 0.0,
}


def _norm_ml(ml):
    # Same rule as _norm_conf: absent is absent. A missing model reading was
    # returning 0.5, contributing 7.5 points of apparently-sourced conviction
    # to every row the model had not scored.
    if ml is None:
        return 0.0, "missing"
    try:
        if isinstance(ml, dict):
            lab = str(ml.get("prediction", ml.get("label", ml.get("direction", "")))).upper()
            conf = float(ml.get("confidence", 0.5) or 0.5)
        else:
            lab = str(ml).upper()
            conf = 0.75
    except (TypeError, ValueError):
        return 0.0, "invalid"
    base = _ML_MAP.get(lab)
    if base is None:
        # An unrecognised label is not a HOLD. Treat it as unavailable so an
        # unknown string cannot be silently scored as a neutral middle.
        return 0.0, "invalid"
    # Quality is evidence STRENGTH, not direction. BULLISH and BEARISH of equal
    # confidence must receive equal quality, so scale magnitude symmetrically
    # around the neutral label rather than mapping DOWN->0 and UP->1, which
    # handed a bearish model 0.0 and a bullish model 1.0 for identical evidence.
    neutral = 0.5
    w = max(0.0, min(1.0, conf))
    return _clamp01(abs(base - neutral) * (0.5 + 0.5 * w)), "ok"


def rank_one(
    ticker, *, flow=None, opportunity=None, confluence=None, ml=None, snapshot_id=None, asof=None, weights=None
):
    """Fuse 4 scorers into one ranked row. Pure. Missing degrades, never invents."""
    w = dict(WEIGHTS)
    w.update(weights or {})
    fn, fs = _norm_flow(flow)
    on, os_ = _norm_opp(opportunity)
    cn, cs = _norm_conf(confluence)
    mn, ms = _norm_ml(ml)
    conviction = round(100.0 * (w["flow"] * fn + w["opportunity"] * on + w["confluence"] * cn + w["ml"] * mn), 2)
    n_missing = sum(1 for s in (fs, os_, cs, ms) if s == "missing")
    if conviction >= 80 and n_missing == 0:
        tier = "HIGH"
    elif conviction >= 60 and n_missing <= 1:
        tier = "MED"
    elif conviction >= 40:
        tier = "WATCH"
    else:
        tier = "LOW"
    opp = opportunity if isinstance(opportunity, dict) else {}
    direction = str(opp.get("direction", "NEUTRAL") or "NEUTRAL").upper()
    if direction not in ("BULL", "BEAR", "NEUTRAL"):
        cdir = (
            str((confluence or {}).get("direction", "neutral")).lower() if isinstance(confluence, dict) else "neutral"
        )
        direction = {"bullish": "BULL", "bearish": "BEAR"}.get(cdir, "NEUTRAL")
    trade_type = str(opp.get("trade_type", "no_trade") or "no_trade")
    invalidation = str(opp.get("invalidation") or "No invalidation: opportunity engine gave none; no trade.")
    ev = {
        "flow_status": fs,
        "opportunity_status": os_,
        "confluence_status": cs,
        "ml_status": ms,
        "components": {
            "flow": round(fn, 4),
            "opportunity": round(on, 4),
            "confluence": round(cn, 4),
            "ml": round(mn, 4),
        },
        "weights": dict(w),
        "weights_version": "v1",
        "opportunity_regime": opp.get("regime"),
        "snapshot_id": snapshot_id,
        "asof": asof,
    }
    if isinstance(flow, dict) and flow.get("key"):
        ev["flow_alert_key"] = flow["key"]
    return {
        "ticker": str(ticker or "").upper(),
        "conviction": conviction,
        "tier": tier,
        "direction": direction,
        "trade_type": trade_type,
        "invalidation": invalidation,
        "snapshot_id": snapshot_id,
        "asof": asof,
        "evidence": ev,
        "schema_version": SCHEMA_VERSION,
    }


def rank_many(rows, **kw):
    """Rank scan-batch rows by fused conviction DESC. Pure."""
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        opp = r.get("opportunity") if isinstance(r.get("opportunity"), dict) else None
        conv = r.get("conviction")
        flow = confl = ml_in = None
        # A row's `conviction` is the ALREADY-FUSED output of an earlier
        # rank_one. It is not a scorer payload. Re-reading it here re-fused a
        # fused score: a blob carrying `label` matched the ML branch and
        # `total` matched the confluence branch, so the row silently gained
        # components it never had. Only unpack a blob that is unambiguously a
        # raw scorer payload -- one that carries a scorer-shaped value and none
        # of the fused-output markers (components / total / *_status / tier).
        if isinstance(conv, dict):
            fused_markers = {"components", "total", "tier", "flow_status", "ml_status", "confluence_status"}
            if not (fused_markers & set(conv)):
                if "conviction" in conv or "score" in conv:
                    flow = conv
                elif "prediction" in conv or "label" in conv:
                    ml_in = conv
                elif "opportunity_score" in conv:
                    flow = conv
        out.append(
            rank_one(
                r.get("ticker"),
                flow=flow,
                opportunity=opp,
                confluence=confl,
                ml=ml_in,
                snapshot_id=r.get("snapshot_id"),
                asof=r.get("asof"),
                **kw,
            )
        )
    out.sort(key=lambda x: (-x["conviction"], x["ticker"]))
    for i, x in enumerate(out, 1):
        x["rank"] = i
    return out


__all__ = ["rank_one", "rank_many", "WEIGHTS", "SCHEMA_VERSION", "VERSION", "TIERS"]
