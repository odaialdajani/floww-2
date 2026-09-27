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
    if conf is None:
        return 0.5, "missing"
    try:
        v = float(conf.get("total", 0) if isinstance(conf, dict) else conf)
    except (TypeError, ValueError):
        return 0.5, "invalid"
    if v > 100 or v < -100:
        v = max(-100.0, min(100.0, v))
    return _clamp01((v + 100.0) / 200.0), "ok"


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
    if ml is None:
        return 0.5, "missing"
    try:
        if isinstance(ml, dict):
            lab = str(ml.get("prediction", ml.get("label", ml.get("direction", "")))).upper()
            conf = float(ml.get("confidence", 0.5) or 0.5)
        else:
            lab = str(ml).upper()
            conf = 0.75
    except (TypeError, ValueError):
        return 0.5, "invalid"
    base = _ML_MAP.get(lab, 0.5)
    w = max(0.0, min(1.0, conf))
    return _clamp01(0.5 + (base - 0.5) * (0.5 + 0.5 * w)), "ok"


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
        flow = conv if isinstance(conv, dict) and "conviction" in conv else None
        confl = conv if isinstance(conv, dict) and "total" in conv else None
        ml_in = conv if isinstance(conv, dict) and ("prediction" in conv or "label" in conv) else None
        if flow is None and confl is None and ml_in is None and isinstance(conv, dict):
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
