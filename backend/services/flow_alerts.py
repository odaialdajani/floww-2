"""
Institutional flow-alert engine — server-side port of the scanner's alert
math (frontend/src/components/flowseeker/scanLogic.js) plus the enrichment
an institutional feed needs and the browser never had:

  • Black-Scholes per-contract ENTRY price (not the 0.4-approx premium)
  • side/bias inference (BUY + BULLISH/BEARISH from opening-flow shape)
  • GOLD / SILVER / BRONZE conviction tiers from a deterministic factor count
  • DuckDB-persisted feed with rule-namespaced dedup TTLs
  • move-since-alert tracking (the feed's "+3.9%" column)

Runs on EVERY fresh /scan result inside the backend, so alerts fire and
persist regardless of whether the Scanner tab is open — the root cause of
"Blademap alerted PLTR today and we had nothing".

Rule semantics intentionally mirror scanLogic.js (same thresholds, same
priority order, same plain-English `why` discipline) so the frontend tape
and this feed never disagree about what qualifies.

DuckDB invariant: ALL writes go through engine.execute_write (never a raw
conn) — see floww-audit-2026-07-11 (thread-unsafe shared connection).
"""

from __future__ import annotations

import contextlib
import json
import logging
import math
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

# Column order of the cvforge `screen` call in routes/flowseeker.py:market_scan.
SCAN_COLUMNS = [
    "underlying_ticker", "ticker", "contract_type", "strike_price",
    "expiration_date", "day_volume", "open_interest",
    "implied_volatility", "delta", "underlying_price",
]

_RISK_FREE = 0.045

# Rule-namespaced dedup TTLs (seconds) — mirrors the frontend's ttl choices:
# confirmations are once-a-session claims, intraday prints re-arm faster.
_TTL_S = {
    "OICONF": 20 * 3600,
    "SIGMA": 4 * 3600,
    "SCORE": 2 * 3600,
    "PRIME": 2 * 3600,
    "CLUSTER": 4 * 3600,
    "WHALE": 6 * 3600,
    "0DTE": 1 * 3600,
}

_TIER_RANK = {"GOLD": 0, "SILVER": 1, "BRONZE": 2}

# Production alert gates (see eval_institutional). Module-level so exactly
# one test pins the values; logic tests pass explicit opts instead.
DEFAULT_EVAL_OPTS: dict = {
    "min_score": 92,
    "whale_premium": 25e6,
    # 0DTE parity with the frontend tape (scanLogic zeroDteScore=85 + volOI>=2
    # lotto shutout): the server must not fire where the tape stays silent.
    "zero_dte_score": 85,
    "zero_dte_vol_oi": 2.0,
    "oiconf_pct": 0.30,
    "oiconf_notional": 1e6,
    "sigma_min": 6.0,
    "fdr_q": 0.10,
}


# ── helpers ──────────────────────────────────────────────────────────

def _f(v):
    try:
        if v is None:
            return None
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except (TypeError, ValueError):
        return None


def _norm_iv(iv):
    """cvforge sometimes reports IV in percent; <3 means it's already decimal."""
    x = _f(iv)
    if x is None or x <= 0:
        return None
    return x / 100.0 if x >= 3 else x


def biz_dte(exp_str: str, today: date | None = None) -> int | None:
    """Business days from today to expiry (0 = expires today). None if unparseable."""
    try:
        exp = date.fromisoformat(str(exp_str)[:10])
    except (TypeError, ValueError):
        return None
    d = today or datetime.now(_ET).date()
    if exp <= d:
        return 0
    n, cur = 0, d
    while cur < exp:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            n += 1
    return n


def norm_rows(raw_rows, columns: list[str] | None = None) -> list[dict]:
    """cvforge screen list-rows → normalized dicts with derived metrics.

    Malformed rows are dropped, never raised — a feed hiccup must not take
    the alert engine down with it.
    """
    cols = columns or SCAN_COLUMNS
    idx = {c: i for i, c in enumerate(cols)}
    out = []
    for raw in raw_rows or []:
        try:
            if not raw or not isinstance(raw, (list, tuple)) or len(raw) < len(cols):
                continue
            under = str(raw[idx["underlying_ticker"]] or "").upper()
            strike = _f(raw[idx["strike_price"]])
            if not under or strike is None or strike <= 0:
                continue
            typ_raw = str(raw[idx["contract_type"]] or "").lower()
            typ = "call" if typ_raw.startswith("c") else "put" if typ_raw.startswith("p") else None
            if typ is None:
                continue
            vol = _f(raw[idx["day_volume"]]) or 0.0
            oi = _f(raw[idx["open_interest"]]) or 0.0
            iv = _norm_iv(raw[idx["implied_volatility"]])
            delta = _f(raw[idx["delta"]])
            spot = _f(raw[idx["underlying_price"]])
            exp = str(raw[idx["expiration_date"]] or "")[:10]
            dte = biz_dte(exp)
            vol_oi = vol / oi if oi > 0 else vol
            r = {
                "under": under, "occ": str(raw[idx["ticker"]] or ""),
                "type": typ, "strike": strike, "exp": exp, "dte": dte,
                "vol": vol, "oi": oi, "iv": iv, "delta": delta, "spot": spot,
                "vol_oi": vol_oi,
                "notional": vol * 100 * strike,
                "ckey": f"{under}|{typ}|{strike:g}|{exp}",
            }
            px = est_entry(r)
            r["est_entry"] = px
            r["premium"] = (vol * 100 * px) if px is not None else None
            out.append(r)
        except Exception:
            continue
    return out


# ── scoring (parity with scanLogic.scanScoreOf) ─────────────────────

def scan_score(r: dict, regime: str | None = None) -> int:
    dl = abs(r.get("delta") or 0.0)
    vol_oi = r.get("vol_oi") or 0.0
    vol = max(r.get("vol") or 0.0, 1.0)
    notional = max(r.get("notional") or 0.0, 1.0)
    dte = r.get("dte")

    pos = min(vol_oi / 3.0, 1.0)
    size = min(math.log(vol) / math.log(50000), 1.0)
    notl = min(math.log(notional) / math.log(50e6), 1.0)
    urg = 0.3 if dte is None else (1.0 if dte <= 2 else 0.7 if dte <= 7 else 0.4 if dte <= 30 else 0.15)
    otm = 0.3 if r.get("delta") is None else max(0.0, min((0.5 - dl) / 0.4, 1.0))

    s = (pos * 0.34 + size * 0.24 + notl * 0.18 + urg * 0.14 + otm * 0.10) * 100
    if regime == "negative" and dte is not None and dte <= 7:
        s += 5
    elif regime == "positive" and vol_oi >= 2:
        s += 3
    # Informed-positioning band (internal desk heuristic: 7–90 DTE +
    # vol≥3×OI + ≥$25k premium is where directional bets live; shorter is
    # gamma noise, longer is hedges). Pan & Poteshman (RFS 2006) is cited
    # ONLY for the directional put-call-ratio finding — that paper has no
    # DTE band and no volume/OI/premium thresholds. Keep it that way.
    if dte is not None and 7 <= dte <= 90 and vol_oi >= 3 and (r.get("premium") or 0) >= 25e3:
        s += 4
    return max(0, min(100, round(s)))


# ── entry price (true Black-Scholes, not the 0.4-approx) ────────────

def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def est_entry(r: dict) -> float | None:
    """Per-contract Black-Scholes entry estimate from the screen row's own
    IV/spot/strike/DTE. Floored at $0.05 (option minimum tick reality)."""
    iv, spot, strike = r.get("iv"), r.get("spot"), r.get("strike")
    if not iv or not spot or not strike or spot <= 0 or strike <= 0:
        return None
    dte = r.get("dte")
    t = max(dte if dte is not None else 5, 0.3) / 365.0
    try:
        srt = iv * math.sqrt(t)
        d1 = (math.log(spot / strike) + (_RISK_FREE + iv * iv / 2.0) * t) / srt
        d2 = d1 - srt
        disc = math.exp(-_RISK_FREE * t)
        if r.get("type") == "put":
            px = strike * disc * _ncdf(-d2) - spot * _ncdf(-d1)
        else:
            px = spot * _ncdf(d1) - strike * disc * _ncdf(d2)
    except (ValueError, OverflowError, ZeroDivisionError):
        return None
    return round(max(0.05, px), 2)


# ── side / bias inference ───────────────────────────────────────────

def infer_side_bias(r: dict) -> tuple[str, str | None]:
    """Opening-dominant flow (vol well above resting OI) reads as initiated
    BUYing on a print-less feed; anything else is unlabeled FLOW — a desk
    never claims a side it can't defend.

    Paid-feed upgrade: initiation is KNOWN, not proxied, in two tiers —
    r["signed_side"] (Lee-Ready via flow_signing: quote rule, else tick test
    on the previous sweep's mid) wins; legacy r["nbbo_side"] (touch-only,
    no tick fallback) is the fallback. ASK = buyer lifted, BID = seller
    hit, with the desk's direction matrix.
    """
    signed = (r.get("signed_side") or "").upper()
    if signed in ("ASK", "BID"):
        from services.public_scanner import side_bias as _side_bias

        return _side_bias(str(r.get("type") or ""), signed)
    nbbo = (r.get("nbbo_side") or "").upper()
    if nbbo in ("ASK", "BID"):
        from services.public_scanner import side_bias as _side_bias

        return _side_bias(str(r.get("type") or ""), nbbo)
    if (r.get("vol_oi") or 0) >= 1.5:
        return "BUY", ("BULLISH" if r.get("type") == "call" else "BEARISH")
    return "FLOW", None


def apply_quote_truth(
    rows: list[dict],
    extras: dict[str, dict] | None,
) -> list[dict]:
    """Overlay paid-feed quote truth onto normalized rows (in place).

    extras is {ckey: {premium_true, nbbo_side, signed_side, sign_method,
    velocity_per_min, ...}} from the Public scanner. True premium replaces
    the BS estimate for the PRIME/WHALE money gates; signed/NBBO side
    upgrades bias inference; velocity feeds conviction. Missing keys leave
    the row untouched — cvserver rows without extras score exactly as before.
    """
    if not extras:
        return rows
    for r in rows or []:
        x = (extras or {}).get(r.get("ckey", "")) or {}
        pt = x.get("premium_true")
        if pt is not None and pt > 0:
            r["premium"] = pt
            r["premium_truth"] = True
        if x.get("nbbo_side") in ("ASK", "BID"):
            r["nbbo_side"] = x["nbbo_side"]
        if x.get("signed_side") in ("ASK", "BID"):
            r["signed_side"] = x["signed_side"]
            if x.get("sign_method") in ("quote", "tick"):
                r["sign_method"] = x["sign_method"]
        rs = x.get("rel_spread")
        try:
            if rs is not None and float(rs) >= 0:
                r["rel_spread"] = float(rs)
        except (TypeError, ValueError):
            pass
        v = x.get("velocity_per_min")
        if v is not None and v >= 0:
            r["velocity_per_min"] = v
    return rows


# ── tiering ─────────────────────────────────────────────────────────

def _norm_gex_regime(raw: object) -> str | None:
    """Normalize dealer-regime vocabulary to negative/positive/None.

    Producers disagree: gex_paper_accurate emits strong_positive_gamma /
    positive_gamma / neutral_gamma / negative_gamma / ..., the Public
    scanner emits negative / positive. Downstream (key levels, WHY block)
    only understands the short form — normalize once, at the boundary.
    """
    s = str(raw or "").lower()
    if "negative" in s:
        return "negative"
    if "positive" in s:
        return "positive"
    return None


def tier_of(factors: dict) -> str | None:
    n = sum(1 for v in (factors or {}).values() if v)
    if n >= 3:
        return "GOLD"
    if n == 2:
        return "SILVER"
    if n == 1:
        return "BRONZE"
    return None


# ── Blademap-style weighted conviction (v3) ─────────────────────────
#
# tier_of() counts booleans — a row with whale+cluster+CW reads GOLD the
# same as score90+sigma+prime, and a row with zero confluences still
# lands BRONZE off a single soft factor. Blademap weights DIMENSIONS:
# flow quality dominates, context confirms, and conviction is a number
# the desk can rank, not a bucket. score_conviction() keeps tier_of()
# for feed compatibility but is the ranking signal from v3 on.

# Dimension weights sum to 100.
_W_FLOW = 45        # vol/OI, size, notional — the tape itself
_W_STRUCTURE = 20   # informed band (Pan-Poteshman) + urgency (DTE shape)
_W_CONFLUENCE = 25  # GEX/CW/cluster/sigma/regime confluences
_W_TAIL = 10        # whale premium / score90 tail events


# ── Exposure-alert → conviction wiring (A3) ──────────────────────────
#
# Exposure alerts (services/exposure_alerts.py: vex_wall_formed/broken,
# charm_pin_formed/shifted) are evaluated beside the heatmap in
# routes/data_providers.py but never fed into any conviction scorer
# (A34 verdict: files coexist, no scorer consumes them). This mapper
# closes that gap additively: callers pass live exposure events for the
# row's ticker through exposure_adjustment_for_events() and hand the
# result to score_conviction(exposure_adjustment=...). Default 0 keeps
# every existing caller byte-identical; the ±5 clamp keeps a structural
# overlay from ever overriding the tape read.

_EXPOSURE_KIND_WEIGHTS: dict[str, int] = {
    "vex_wall_formed": -2,    # vol suppression defended — fade directional prints
    "vex_wall_broken": 3,     # suppression released — regime may shift, tradable
    "charm_pin_formed": 2,    # hedging concentration into expiry — follow-through
    "charm_pin_shifted": 1,   # magnet moved strikes — weak continuation
}

_EXPOSURE_ADJUST_MIN = -5
_EXPOSURE_ADJUST_MAX = 5


def _exposure_kind_of(item: dict) -> str:
    """Extract the exposure kind from an event dict or an alert dict.

    Events (evaluate_exposure_events) carry ``kind`` directly; alert
    dicts (events_to_alerts) embed it in ``key`` as
    ``exposure:<kind>:<ticker>:<expiry>:<strike>``.
    """
    kind = str(item.get("kind") or "").strip()
    if kind:
        return kind
    key = str(item.get("key") or "")
    if key.startswith("exposure:"):
        parts = key.split(":")
        if len(parts) >= 2 and parts[1]:
            return parts[1]
    return ""


def exposure_adjustment_for_events(events: list[dict] | None) -> int:
    """Map exposure events/alerts to a bounded conviction adjustment.

    Sums per-kind weights (unknown kinds contribute 0) and clamps the
    total to [-5, +5]. Empty/None input → 0.
    """
    total = 0
    for item in events or []:
        if not isinstance(item, dict):
            continue
        total += _EXPOSURE_KIND_WEIGHTS.get(_exposure_kind_of(item), 0)
    return max(_EXPOSURE_ADJUST_MIN, min(_EXPOSURE_ADJUST_MAX, total))


def score_conviction(r: dict, factors: dict | None = None,
                     regime: str | None = None,
                     exposure_adjustment: float = 0) -> int:
    """Weighted 0-100 conviction for one normalized row.

    Flow dimension reuses the parity scan_score components (they're the
    calibrated tape read); structure re-weights urgency toward the
    informed band; confluence counts Blademap-style confirmations with
    GEX confluency weighted heaviest (paper-accurate ΓIB is our hardest
    context signal); tail catches the 1-in-a-hundred prints; evidence
    rewards paid-feed truth (arrival velocity + NBBO-known initiation),
    absent on print-less rows by design.

    ``exposure_adjustment`` is an additive structural overlay from
    exposure_adjustment_for_events() (VEX walls / charm pins for the
    row's ticker). It defaults to 0 (existing callers unchanged), is
    defensively clamped to [-5, +5], and applies inside the 0..100
    clamp so it can nudge but never override the tape read.
    """
    f = factors or {}
    vol_oi = r.get("vol_oi") or 0.0
    vol = max(r.get("vol") or 0.0, 1.0)
    notional = max(r.get("notional") or 0.0, 1.0)
    dte = r.get("dte")
    premium = r.get("premium") or 0.0

    # Flow dimension (0-45)
    pos = min(vol_oi / 3.0, 1.0)
    size = min(math.log(vol) / math.log(50000), 1.0)
    notl = min(math.log(notional) / math.log(50e6), 1.0)
    flow = (pos * 0.45 + size * 0.33 + notl * 0.22) * _W_FLOW

    # Structure dimension (0-20): informed band is the structural claim
    informed = 1.0 if (dte is not None and 7 <= dte <= 90
                       and vol_oi >= 3 and premium >= 25e3) else 0.0
    urg = 0.3 if dte is None else (1.0 if dte <= 2 else 0.7 if dte <= 7
                                   else 0.4 if dte <= 30 else 0.15)
    structure = (informed * 0.6 + urg * 0.4) * _W_STRUCTURE

    # Confluence dimension (0-25): gex_confluent weighted double
    confluence_hits = sum(1 for k in ("cw_confirm", "cluster", "sigma_ticker",
                                      "regime_confluent") if f.get(k))
    gex = 2 if f.get("gex_confluent") else 0
    confluence = min(confluence_hits + gex, 5) / 5.0 * _W_CONFLUENCE

    # Tail dimension (0-10)
    tail = ((0.6 if premium >= 10e6 else 0.0)
            + (0.4 if (r.get("_score") or 0) >= 90 else 0.0)) * _W_TAIL

    # Negative-gamma short-DTE context adds a small convexity bump (the
    # same +5 the parity score grants), capped inside the clamp.
    bump = 3 if (regime == "negative" and dte is not None and dte <= 7) else 0

    # Evidence dimension (paid-feed truth only): arrival intensity +
    # known initiation. cvserver rows carry neither key and score exactly
    # as before — this rewards MEASURED urgency, never a proxy.
    vel = r.get("velocity_per_min") or 0
    vel_bonus = 4 if vel >= 1000 else (2 if vel >= 300 else 0)
    # Known initiation: quote-rule reads full weight, tick-fallback half —
    # a sweep-mid tick is evidence, not proof.
    _method = r.get("sign_method")
    if r.get("signed_side") in ("ASK", "BID"):
        know_bonus = 2 if _method == "quote" else 1
    else:
        know_bonus = 2 if r.get("nbbo_side") in ("ASK", "BID") else 0

    try:
        _adj = float(exposure_adjustment or 0.0)
    except (TypeError, ValueError):
        _adj = 0.0
    _adj = max(_EXPOSURE_ADJUST_MIN, min(_EXPOSURE_ADJUST_MAX, _adj))

    return max(0, min(100, round(flow + structure + confluence + tail + bump + vel_bonus + know_bonus + _adj)))


# ── Blademap alert contract: key levels + context ───────────────────

# Target/invalidation distances as fractions of underlying price. The
# invalidation sits near the delta-implied breakeven; targets scale with
# the GEX regime (short gamma moves harder — Ni-Pearson 2020).
_INVALIDATION_PCT = 0.025
_TARGET_POS_GAMMA = 0.035
_TARGET_NEG_GAMMA = 0.055


def build_key_levels(r: dict, bias: str | None,
                     gex_regime: str | None) -> dict | None:
    """Blademap alert contract: entry / invalidation / target on the
    UNDERLYING. None when the alert doesn't claim a direction."""
    spot = r.get("spot")
    if not bias or not spot or spot <= 0:
        return None
    entry = float(spot)
    if str(bias).upper() == "BULLISH":
        invalidation = entry * (1 - _INVALIDATION_PCT)
        tgt_pct = _TARGET_NEG_GAMMA if gex_regime == "negative" else _TARGET_POS_GAMMA
        target = entry * (1 + tgt_pct)
    else:
        invalidation = entry * (1 + _INVALIDATION_PCT)
        tgt_pct = _TARGET_NEG_GAMMA if gex_regime == "negative" else _TARGET_POS_GAMMA
        target = entry * (1 - tgt_pct)
    rnd = lambda v: round(v, 2)  # noqa: E731
    return {"entry": rnd(entry), "invalidation": rnd(invalidation),
            "target": rnd(target)}


_INDICATOR_LABELS = (
    ("score90", "Top-decile composite score"),
    ("whale", "Whale premium (≥$25M)"),
    ("sigma_ticker", "σ spike (BH-FDR surviving)"),
    ("informed_band", "Informed-positioning band (7–90 DTE, Pan-Poteshman)"),
    ("regime_confluent", "Regime-confluent tenor"),
    ("prime", "Prime print (≥$250k, ≥5× OI)"),
    ("cluster", "Same-bias cluster (≥3 contracts)"),
    ("cw_confirm", "Cremers-Weinbaum IV spread confirms"),
    ("gex_confluent", "Dealer gamma confluency (ΓIB)"),
)


def build_context(r: dict, factors: dict) -> dict:
    """Blademap-style WHY block: human-readable indicators, dealer
    positioning read, and the market regime label."""
    indicators = [label for key, label in _INDICATOR_LABELS if factors.get(key)]
    regime = factors.get("gex_regime")
    market_regime = ("NEGATIVE_GAMMA" if regime == "negative"
                     else "POSITIVE_GAMMA" if regime == "positive"
                     else "UNKNOWN")
    if regime == "negative":
        dealer = ("Net short gamma — dealer hedging amplifies moves; "
                  "flows in this regime tend to chase")
    elif regime == "positive":
        dealer = ("Net long gamma — dealer hedging dampens moves; "
                  "flows mean-revert toward walls")
    else:
        dealer = "Dealer positioning unknown (no GEX context for ticker)"
    vol = r.get("vol") or 0
    premium = r.get("premium") or 0
    vol_oi = r.get("vol_oi") or 0
    summary = (f"{r.get('type', 'call').capitalize()} print: {vol:,} contracts "
               f"vs {int(vol_oi * 100):,} resting OI ({vol_oi:.1f}×), "
               f"~${premium / 1e6:.2f}M premium, {r.get('dte')} DTE")
    return {
        "activity_summary": summary,
        "institutional_indicators": indicators,
        "market_regime": market_regime,
        "dealer_positioning": dealer,
    }


# ── the engine ──────────────────────────────────────────────────────

def minutes_since_open_now() -> float | None:
    """Minutes since today's 09:30 ET open (seconds-precision frozen at call
    time). None outside RTH — the caller freezes None honestly rather than a
    fake number; weekends/holidays are not special-cased (a holiday scan
    would freeze minutes-since-midnight, harmless for a covariate)."""
    now = datetime.now(_ET)
    open_dt = now.replace(hour=9, minute=30, second=0, microsecond=0)
    secs = (now - open_dt).total_seconds()
    if secs < 0:
        return None
    return round(secs / 60.0, 1)


def _mk_alert(r: dict, rule: str, extra: dict, factors: dict, asof: str) -> dict:
    side, bias = infer_side_bias(r)
    regime = factors.get("gex_regime") if isinstance(factors, dict) else None
    a = {
        "key": f"{rule.lower()}|{r['ckey']}",
        "ckey": r["ckey"], "rule": rule,
        "tier": tier_of(factors) or "BRONZE",
        # Blademap v3: ranked weighted conviction (factor-count tier kept
        # above for feed compatibility).
        "conviction": score_conviction(r, factors),
        "side": side, "bias": bias,
        "under": r["under"], "type": r["type"], "strike": r["strike"],
        "exp": r["exp"], "dte": r.get("dte"),
        "score": r.get("_score"),
        "est_entry": r.get("est_entry"), "premium": r.get("premium"),
        "notional": r.get("notional"), "vol_oi": r.get("vol_oi"),
        "sigma": extra.get("sigma"), "oi_chg_pct": extra.get("oi_chg_pct"),
        "under_price": r.get("spot"),
        # Blademap alert contract: falsifiable levels + the WHY block.
        # STRATEGY (spread) rows claim no direction -> no levels.
        "key_levels": build_key_levels(r, bias, regime),
        "context": build_context(r, factors or {}),
        # Conviction v2 v2.1: surface the cluster factor that the engine
        # already computed in _common_factors(factors). A row whose ticker
        # laddered with ≥3 same-bias qualifying contracts in the snapshot
        # gets cluster=True; the frontend can now render an honest CLUSTER
        # chip without inferring a proxy from tier+SIGMA.
        "cluster": bool(factors.get("cluster", False)),
        # Always-emit provenance (CONTRACTS C6): consumers may rely on these
        # keys existing. premium_truth mirrors the row overlay; p_move stays
        # None until a calibration stage is explicitly passed in opts.
        "premium_truth": bool(r.get("premium_truth", False)),
        "p_move": None,
        "p_method": "uncalibrated",
        # C4 execution input: relative spread at fire time (None when the
        # feed had no two-sided quote). Kyle-λ arrives separately (B).
        "rel_spread": r.get("rel_spread"),
        "why": extra.get("why", ""),
        "ttl_s": _TTL_S.get(rule, 2 * 3600),
        "asof": asof,
        # Feature freeze (2026-09-02): intraday context frozen at fire time.
        "mins_since_open": minutes_since_open_now(),
    }
    return a


def _finalize(a: dict, r: dict, cw_map: dict | None) -> dict:
    """Conviction v2 post-pass: attach the ticker's CW spread, and demote
    paired strategy legs — a vertical's leg is never a directional whale."""
    cw = (cw_map or {}).get(a["under"])
    a["cw_spread"] = round(cw, 4) if cw is not None else None
    if r.get("spread_leg"):
        a["side"], a["bias"], a["tier"] = "STRATEGY", None, "BRONZE"
        a["why"] = (a.get("why") or "") + " [paired legs: likely spread — direction unclaimed]"
    return a


def _common_factors(r: dict, regimes: dict, sigma_tickers: set,
                    cw_map: dict | None = None, clusters: dict | None = None,
                    gex_context: dict | None = None) -> dict:
    from services.flow_quality import cw_confirms, is_prime

    reg = (regimes or {}).get(r["under"])
    dte, vol_oi = r.get("dte"), r.get("vol_oi") or 0
    _, bias = infer_side_bias(r)

    # Paper-accurate GEX confluency (Ni-Pearson 2020 + Barbon-Buraschi 2021)
    # Contract: gex_context is {underlying: {"gamma_imbalance": {...}}}
    # (both _cached_gex_context and the Public scanner's dealer feed speak
    # it). A flat {"gamma_imbalance": ...} payload is ALSO accepted — the
    # unit tests pin the factor math through it.
    gex_confluent = False
    gex_regime = None
    if gex_context:
        gi = gex_context.get("gamma_imbalance")
        if gi is None:
            per = gex_context.get(r["under"], {}) or {}
            gi = per.get("gamma_imbalance", {}) or {}
        gi = gi or {}
        gex_regime = _norm_gex_regime(gi.get("regime"))
        # pct None = regime-only feed (dealer walls without ADV magnitude):
        # propagate the regime, never confluence — None must not compare.
        gib_pct = gi.get("gamma_imbalance_pct", 0)
        gib_pct = 0 if gib_pct is None else gib_pct
        # Confluent: negative gamma + bearish flow, or positive gamma + bullish
        # flow. infer_side_bias returns "BULLISH"/"BEARISH" uppercase — compare
        # case-insensitively (was a case-sensitive dead comparison).
        bias_l = (bias or "").lower()
        if (gib_pct < -0.5 and bias_l == "bearish") or (gib_pct > 0.5 and bias_l == "bullish"):
            gex_confluent = True

    return {
        "score90": (r.get("_score") or 0) >= 90,
        "whale": (r.get("premium") or 0) >= 25e6,
        "sigma_ticker": r["under"] in sigma_tickers,
        "informed_band": dte is not None and 7 <= dte <= 90 and vol_oi >= 3 and (r.get("premium") or 0) >= 25e3,
        "regime_confluent": (reg == "negative" and dte is not None and dte <= 7)
                            or (reg == "positive" and vol_oi >= 2),
        # Conviction v2 factors (spec: 2026-07-20-flow-quality-conviction-v2)
        "prime": is_prime(r),
        "cluster": bool(clusters) and clusters.get(r["under"]) == bias and bias is not None,
        "cw_confirm": cw_confirms(bias, (cw_map or {}).get(r["under"])),
        # Paper-accurate GEX: Ni-Pearson 2020 + Barbon-Buraschi 2021
        "gex_confluent": gex_confluent,
        "gex_regime": gex_regime,
    }


def eval_institutional(rows, baselines=None, prev_oi=None, regimes=None, opts=None,
                       gex_context: dict | None = None, oi_tags: dict | None = None):
    """Evaluate normalized rows into enriched institutional alerts.

    One alert per contract, strongest claim first (OICONF > SCORE > WHALE >
    PRIME > 0DTE), plus per-ticker SIGMA and CLUSTER alerts. Pure logic —
    dedup/persistence are the I/O layer's job so this stays unit-testable.

    PRIME (premium >= $250k AND vol/OI >= 5, the 55-62% UOA bracket) sits
    BELOW whale size: a $25M+ line is whale flow first. PRIME exists for the
    sub-whale mid-cap bracket that never clears SCORE 92 — the SNDK gap.
    """
    from services.flow_quality import (
        bh_fdr,
        cluster_biases,
        cw_iv_spread,
        detect_spreads,
        is_prime,
        sigma_pvalue,
    )

    o = {
        # 2026-09-02 institutional noise pass — mirrors the frontend's tightened
        # defaults (scanLogic.js / FlowseekerProBlademap.jsx DEFAULT_RULES):
        # SCORE 85→92, WHALE $10M→$25M, SIGMA 3.0→6.0. Parity contract: the
        # frontend tape and this feed must never disagree about what qualifies.
        # Extracted as DEFAULT_EVAL_OPTS so the gate value is pinned by exactly
        # one test (test_default_gate_matches_noise_pass) instead of drifting
        # silently inside dozens of logic fixtures.
        **DEFAULT_EVAL_OPTS,
        # calibration: pre-fitted stage blob from flow_calibration.fit_calibration
        # (loaded by the caller from the cron's Mongo snapshot). When supplied,
        # every fired alert gains p_move/p_method/p_n — server-computed,
        # structural parity. GATING on p is intentionally inert until the
        # model promotes past stage 0: p_move=None must never block a fire.
        "calibration": None,
        **(opts or {}),
    }
    baselines = baselines or {}
    prev_oi = prev_oi or {}
    regimes = regimes or {}
    asof = datetime.now(_ET).isoformat(timespec="seconds")

    rows = list(rows or [])
    for r in rows:
        r["_score"] = scan_score(r, regimes.get(r["under"]))

    # Conviction v2 context: spread-leg flags, Cremers-Weinbaum call-put IV
    # spread, and same-bias laddering — all cross-row reads of THIS snapshot.
    detect_spreads(rows)
    cw_map = cw_iv_spread(rows)
    clusters = cluster_biases(rows)

    # Per-ticker σ vs multi-day baseline. Two-stage quality gate:
    #   1. market-mode removal — a broad volume day lifts every ticker's σ
    #      together; subtract the cross-sectional median (when the cross-
    #      section is wide enough to define one) so only IDIOSYNCRATIC
    #      spikes remain;
    #   2. Benjamini-Hochberg FDR at q — testing hundreds of tickers a day
    #      at a raw cutoff is a multiple-testing machine.
    by_ticker: dict[str, float] = {}
    for r in rows:
        by_ticker[r["under"]] = by_ticker.get(r["under"], 0.0) + (r.get("vol") or 0.0)
    raw_sigma: dict[str, float] = {}
    for under, tot in by_ticker.items():
        b = baselines.get(under)
        if not b or not b.get("std") or (b.get("days") or 0) < 2:
            continue
        raw_sigma[under] = (tot - b["avg"]) / b["std"]
    market_mode = 0.0
    if len(raw_sigma) >= 5:
        ordered = sorted(raw_sigma.values())
        mid = len(ordered) // 2
        med = ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2
        market_mode = max(0.0, med)
    adj_sigma = {t: s - market_mode for t, s in raw_sigma.items()}
    pvals = {t: sigma_pvalue(s) for t, s in adj_sigma.items() if s >= o["sigma_min"]}
    survivors = bh_fdr(pvals, q=o["fdr_q"])
    sigma_hits = {t: round(raw_sigma[t], 1) for t in survivors}
    sigma_tickers = set(sigma_hits)

    out: list[dict] = []

    # Pass 1 — OICONF: overnight OI build is the one hard "yesterday's flow
    # was real" proof a print-less feed offers. Top 5 by % build.
    # ΔOI hygiene (services/oi_hygiene.py, 2026-09-02): rollover/expiring
    # contracts are skipped entirely — a roll's next-expiry pop is migration,
    # not new flow. Earnings-window alerts still fire (never-remove) but the
    # why-string carries the ambiguity tag and tier is capped below GOLD.
    from services.oi_hygiene import oi_hygiene_why_suffix

    cand = []
    for r in rows:
        tag = (oi_tags or {}).get(r["ckey"]) or {}
        if tag.get("rollover") or tag.get("expiring"):
            continue
        prev = prev_oi.get(r["ckey"])
        if prev is None or prev <= 0 or not r.get("oi"):
            continue
        chg = r["oi"] - prev
        pct = chg / prev
        add_notl = abs(chg) * 100 * r["strike"]
        if pct >= o["oiconf_pct"] and add_notl >= o["oiconf_notional"]:
            cand.append((pct, add_notl, r, tag))
    cand.sort(key=lambda c: c[0], reverse=True)
    winners = set()
    for pct, add_notl, r, tag in cand[:5]:
        winners.add(r["ckey"])
        f = _common_factors(r, regimes, sigma_tickers, cw_map, clusters,
                            gex_context=gex_context)
        f["oiconf"] = True
        a = _finalize(_mk_alert(r, "OICONF", {
            "oi_chg_pct": round(pct, 4),
            "why": f"OI +{round(pct * 100)}% overnight (${add_notl / 1e6:.1f}M added notional) — prior-day flow HELD as new positioning",
        }, f, asof), r, cw_map)
        suffix = oi_hygiene_why_suffix(tag)
        if suffix:
            a["why"] += suffix
            if isinstance(tag.get("earnings"), dict) and a["tier"] == "GOLD":
                a["tier"] = "SILVER"   # direction ambiguous into the event
        out.append(a)

    # Pass 2 — intraday per-contract rules, strongest first, one per contract.
    for r in rows:
        if r["ckey"] in winners:
            continue
        f = _common_factors(r, regimes, sigma_tickers, cw_map, clusters,
                            gex_context=gex_context)
        rule, why = None, None
        score = r.get("_score") or 0
        if score >= o["min_score"]:
            rule = "SCORE"
            why = f"score {score} — vol {r['vol_oi']:.1f}× OI, ~${(r.get('premium') or 0) / 1e6:.2f}M premium, {r.get('dte')} DTE"
        elif (r.get("premium") or 0) >= o["whale_premium"]:
            rule = "WHALE"
            why = f"~${(r.get('premium') or 0) / 1e6:.1f}M estimated premium on a single line"
        elif is_prime(r):
            rule = "PRIME"
            why = (f"prime print — ~${(r.get('premium') or 0) / 1e3:.0f}k premium at "
                   f"{r['vol_oi']:.1f}× OI, score {score} (55-62% directional bracket)")
        elif (r.get("dte") is not None and r["dte"] <= 1
                and score >= o["zero_dte_score"]
                and (r.get("vol_oi") or 0) >= o.get("zero_dte_vol_oi", 2.0)):
            rule = "0DTE"
            why = f"{r['dte']} DTE with score {score} — urgent short-fuse positioning"
        if not rule:
            continue
        out.append(_finalize(_mk_alert(r, rule, {"why": why}, f, asof), r, cw_map))

    # Pass 3 — per-ticker SIGMA alerts (aggregate anomaly, no single strike).
    for under, s in sigma_hits.items():
        best = max((r for r in rows if r["under"] == under), key=lambda r: r.get("_score") or 0)
        b = baselines[under]
        f = {"sigma": True, "score90": (best.get("_score") or 0) >= 90}
        a = _mk_alert(best, "SIGMA", {
            "sigma": s,
            "why": f"{under} options volume {s}σ above its {b.get('days')}-day baseline",
        }, f, asof)
        a["key"] = f"sigma|{under}"
        a["ckey"] = under
        a["type"], a["strike"], a["exp"] = "", None, ""
        cw = cw_map.get(under)
        a["cw_spread"] = round(cw, 4) if cw is not None else None
        out.append(a)

    # Pass 4 — per-ticker CLUSTER alerts (laddered accumulation in ONE
    # snapshot: >=3 same-bias qualifying contracts). The SNDK read — steady
    # multi-strike building where no single line clears SCORE 92 and no
    # multi-day baseline exists yet for SIGMA. Anchored on the ticker's best
    # row so the desk can click through to the lead contract.
    for under, bias in (clusters or {}).items():
        legs = [r for r in rows
                if r["under"] == under and infer_side_bias(r) == ("BUY", bias)]
        if len(legs) < 3:
            continue
        best = max(legs, key=lambda r: r.get("_score") or 0)
        f = _common_factors(best, regimes, sigma_tickers, cw_map, clusters,
                            gex_context=gex_context)
        a = _mk_alert(best, "CLUSTER", {
            "why": (f"{under} laddered {bias} accumulation — {len(legs)} opening-shaped "
                    f"contracts in one snapshot, lead score {best.get('_score')}"),
        }, f, asof)
        a["key"] = f"cluster|{under}"
        cw = cw_map.get(under)
        a["cw_spread"] = round(cw, 4) if cw is not None else None
        out.append(_finalize(a, best, cw_map))

    # Calibration provenance — attach the server-computed p_move to every
    # fired alert. Stage-0 model → p_move=None + "uncalibrated" on each row:
    # the tape stays complete and the ledger records WHAT the model knew at
    # fire time (auditable stage promotion later). Gating on p is a future
    # change gated on stage ≥ 1 by design — never let None block a fire.
    cal = o.get("calibration")
    if cal is not None:
        from services.flow_calibration import predict_p_move
        for a in out:
            try:
                a.update(predict_p_move(cal, {**a, "score": a.get("score")}))
            except Exception:
                a["p_move"], a["p_method"] = None, "calibration_error"
    return out


# ── DuckDB I/O ──────────────────────────────────────────────────────

def init_flow_alert_tables(engine) -> None:
    engine.execute_write("""
        CREATE TABLE IF NOT EXISTS flow_alerts_daily (
            asof_date DATE, asof_ts TIMESTAMP, key TEXT, ckey TEXT,
            rule TEXT, tier TEXT, side TEXT, bias TEXT,
            under TEXT, type TEXT, strike DOUBLE, exp TEXT, dte INTEGER,
            score INTEGER, est_entry DOUBLE, premium DOUBLE, notional DOUBLE,
            vol_oi DOUBLE, sigma DOUBLE, oi_chg_pct DOUBLE,
            under_price DOUBLE, last_price DOUBLE, move_pct DOUBLE,
            cw_spread DOUBLE, cluster BOOLEAN, why TEXT,
            PRIMARY KEY (asof_date, key)
        )
    """)
    with contextlib.suppress(Exception):
        # Migration for pre-Conviction-v2 tables (column added 2026-07-20).
        engine.execute_write(
            "ALTER TABLE flow_alerts_daily ADD COLUMN IF NOT EXISTS cw_spread DOUBLE")
    with contextlib.suppress(Exception):
        # Migration for v2.1 — cluster factor surfaced to the feed (2026-07-20).
        engine.execute_write(
            "ALTER TABLE flow_alerts_daily ADD COLUMN IF NOT EXISTS cluster BOOLEAN")
    with contextlib.suppress(Exception):
        # Migration for v2.3 — wins column (BIGINT). The alert_quality() SQL
        # CAST(SUM(...) AS BIGINT) requires this column. Pre-v2.3 prod tables
        # upgrade in place without manual SQL. Mirrors cw_spread / cluster
        # migration pattern above.
        engine.execute_write(
            "ALTER TABLE flow_alerts_daily ADD COLUMN IF NOT EXISTS wins BIGINT")
    for ddl in (
        "ALTER TABLE flow_alerts_daily ADD COLUMN IF NOT EXISTS conviction INTEGER",
        "ALTER TABLE flow_alerts_daily ADD COLUMN IF NOT EXISTS key_levels_json TEXT",
        "ALTER TABLE flow_alerts_daily ADD COLUMN IF NOT EXISTS context_json TEXT",
        # Outcome-ledger / calibration columns (2026-09-02): p_move provenance
        # persisted at fire time so stage promotion can be audited retroactively.
        "ALTER TABLE flow_alerts_daily ADD COLUMN IF NOT EXISTS p_move DOUBLE",
        # Feature-freeze columns (2026-09-02): frozen at fire time so the
        # stage-2 logistic trains on the snapshot the alert actually saw.
        "ALTER TABLE flow_alerts_daily ADD COLUMN IF NOT EXISTS mins_since_open DOUBLE",
        "ALTER TABLE flow_alerts_daily ADD COLUMN IF NOT EXISTS p_method TEXT",
    ):
        with contextlib.suppress(Exception):
            engine.execute_write(ddl)
    engine.execute_write("""
        CREATE TABLE IF NOT EXISTS flow_alert_dedup (
            key TEXT PRIMARY KEY, last_fired_ts DOUBLE, ttl_s DOUBLE
        )
    """)
    # Horizon-move legs (Agent C, C1, 2026-09-05): per-stamp persistence so
    # +1/+5/+20 reads don't collapse into the latest move_pct. Append-only;
    # readers derive session legs from ordered stamps. No PK (stamps are
    # scan-cadence; microsecond ts keeps collisions practically impossible).
    engine.execute_write("""
        CREATE TABLE IF NOT EXISTS flow_alert_moves (
            asof_date DATE, key TEXT, under TEXT,
            stamp_ts TIMESTAMP, stamp_date DATE,
            last_price DOUBLE, move_pct DOUBLE
        )
    """)


def persist_alerts(engine, alerts, snapshot_date: str | None = None) -> int:
    """UPSERT alerts under today's ET session date. Same-day re-evals
    overwrite their row (idempotent) rather than duplicating the feed."""
    if not alerts:
        return 0
    day = snapshot_date or datetime.now(_ET).date().isoformat()
    rows = [[
        day, a.get("asof"), a["key"], a.get("ckey"), a["rule"], a["tier"],
        a.get("side"), a.get("bias"), a["under"], a.get("type"),
        a.get("strike"), a.get("exp"), a.get("dte"), a.get("score"),
        a.get("est_entry"), a.get("premium"), a.get("notional"),
        a.get("vol_oi"), a.get("sigma"), a.get("oi_chg_pct"),
        a.get("under_price"), a.get("cw_spread"), bool(a.get("cluster", False)),
        a.get("why"),
        # Blademap v3 contract (conviction / levels / context)
        a.get("conviction"),
        json.dumps(a.get("key_levels")) if a.get("key_levels") else None,
        json.dumps(a.get("context")) if a.get("context") else None,
        # Calibration provenance (2026-09-02): server-computed p_move.
        a.get("p_move"), a.get("p_method"),
        a.get("mins_since_open"),
    ] for a in alerts]
    engine.execute_write("""
        INSERT INTO flow_alerts_daily (
            asof_date, asof_ts, key, ckey, rule, tier, side, bias, under, type,
            strike, exp, dte, score, est_entry, premium, notional, vol_oi,
            sigma, oi_chg_pct, under_price, cw_spread, cluster, why,
            conviction, key_levels_json, context_json, p_move, p_method,
            mins_since_open
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (asof_date, key) DO UPDATE SET
            asof_ts = excluded.asof_ts, tier = excluded.tier, side = excluded.side,
            bias = excluded.bias, score = excluded.score,
            est_entry = excluded.est_entry, premium = excluded.premium,
            notional = excluded.notional, vol_oi = excluded.vol_oi,
            sigma = excluded.sigma, oi_chg_pct = excluded.oi_chg_pct,
            under_price = excluded.under_price, cw_spread = excluded.cw_spread,
            cluster = excluded.cluster, why = excluded.why,
            conviction = excluded.conviction,
            key_levels_json = excluded.key_levels_json,
            context_json = excluded.context_json,
            p_move = excluded.p_move, p_method = excluded.p_method
    """, rows)
    return len(rows)


def conviction_calibration(engine, days: int = 30) -> list[dict]:
    """Blademap v3 — hit-rate by CONVICTION BAND (the score's own report card).

    Buckets: 50-59 / 60-74 / 75+ (the sizing tiers in flow_trade_bridge).
    hit = same ≥0.5%-in-direction threshold as alert_quality. If the curve
    isn't monotonic (75+ hitting no better than 50-59), conviction sizing
    is decoration and the weights need retuning — this table is how the
    desk sees that.

    Bands with zero measured alerts still appear (n_measured=0) so the
    frontend renders an honest "—" rather than dropping the row.
    """
    since = (datetime.now(_ET).date() - timedelta(days=max(1, days))).isoformat()
    try:
        rows = engine.query("""
            SELECT CASE
                     WHEN conviction >= 75 THEN '75+'
                     WHEN conviction >= 60 THEN '60-74'
                     WHEN conviction >= 50 THEN '50-59'
                     ELSE '<50'
                   END AS band,
                   count(*) AS n,
                   count(move_pct) AS n_measured,
                   CAST(SUM(CASE WHEN move_pct IS NULL THEN 0
                                 WHEN bias = 'BULLISH' AND move_pct >= 0.5 THEN 1
                                 WHEN bias = 'BEARISH' AND move_pct <= -0.5 THEN 1
                                 ELSE 0 END) AS BIGINT) AS wins,
                   avg(CASE WHEN move_pct IS NULL THEN NULL
                            WHEN bias = 'BULLISH' AND move_pct >= 0.5 THEN 1.0
                            WHEN bias = 'BEARISH' AND move_pct <= -0.5 THEN 1.0
                            ELSE 0.0 END) AS hit_rate,
                   avg(move_pct) AS avg_move_pct
            FROM flow_alerts_daily
            WHERE asof_date >= ? AND bias IS NOT NULL AND conviction IS NOT NULL
            GROUP BY band
        """, [since])
    except Exception as e:
        logger.warning(f"flow_alerts.conviction_calibration: {e}")
        rows = []
    order = {"75+": 0, "60-74": 1, "50-59": 2, "<50": 3}
    rows.sort(key=lambda r: order.get(r.get("band"), 9))
    for r in rows:
        r["wins"] = int(r.get("wins") or 0)
        r["n_measured"] = int(r.get("n_measured") or 0)
        r["n"] = int(r.get("n") or 0)
    return rows


def alert_quality(engine, days: int = 30) -> list[dict]:
    """Per rule × tier precision from realized moves — the calibration loop.

    hit = the underlying moved ≥0.5% in the alert's claimed direction since
    the alert fired (move_pct is stamped by update_moves on every scan).
    Directionless rows (bias NULL — STRATEGY legs, SIGMA) are excluded.

    v2.3: also emits `wins` (integer count of hits) alongside hit_rate so the
    frontend can pool many (rule, tier) rows into a tier-level binomial CI
    (Wilson 90%) using integer-accurate totals. The float-rounding fallback
    n_measured*hit_rate is acceptable when `wins` is absent (older DBs),
    but the integer SUM is the bit-exact source of truth.

    v2.x contract — also returns `sigma_median` per (rule, tier) row (DuckDB
    MEDIAN over the window's per-alert sigma values; null when no sigma
    was stamped) and a per-row boolean `is_best_rule` (False for runners-up,
    True for the winner in each tier). The is_best_rule ranking mirrors the
    frontend's bestRuleForTier: weighted-hits DESC, n_measured DESC, hit_rate
    DESC; min-n floor = 3; tier must have ≥2 qualifying rules. The boolean is
    a per-row flat-field design rather than a per-tier aggregate so the
    root type stays a list-of-dicts and existing consumers do not need to
    branch on response shape.
    """
    since = (datetime.now(_ET).date() - timedelta(days=max(1, days))).isoformat()
    try:
        rows = engine.query("""
            SELECT rule, tier, count(*) AS n,
                   count(move_pct) AS n_measured,
                   CAST(SUM(CASE WHEN move_pct IS NULL THEN 0
                                 WHEN bias = 'BULLISH' AND move_pct >= 0.5 THEN 1
                                 WHEN bias = 'BEARISH' AND move_pct <= -0.5 THEN 1
                                 ELSE 0 END) AS BIGINT) AS wins,
                   avg(CASE WHEN move_pct IS NULL THEN NULL
                            WHEN bias = 'BULLISH' AND move_pct >= 0.5 THEN 1.0
                            WHEN bias = 'BEARISH' AND move_pct <= -0.5 THEN 1.0
                            ELSE 0.0 END) AS hit_rate,
                   avg(move_pct) AS avg_move_pct,
                   MEDIAN(sigma) AS sigma_median
            FROM flow_alerts_daily
            WHERE asof_date >= ? AND bias IS NOT NULL
            GROUP BY rule, tier
            ORDER BY rule, tier
        """, [since])
    except Exception as e:
        logger.warning(f"flow_alerts.alert_quality: {e}")
        rows = []

    # Per-row is_best_rule flag — Python-side ranking mirrors the frontend
    # so a consumer of this endpoint directly does not need to re-run
    # bestRuleForTier to know which row is the tier winner. The min-n floor
    # is intentionally consistent so the two views agree on "GOLD's best
    # rule is X" without a timezone-of-truth regression.
    _BEST_RULE_MIN_N = 3  # mirrors convictionUi.js BEST_RULE_MIN_N — keep identical
    for r in rows:
        r["is_best_rule"] = False
    by_tier = {}
    for r in rows:
        by_tier.setdefault(str(r.get("tier") or "").upper(), []).append(r)
    for _tier, tier_rows in by_tier.items():
        candidates = [r for r in tier_rows if (r.get("n_measured") or 0) > 0]
        if len(candidates) < _BEST_RULE_MIN_N:
            continue
        ranked = sorted(
            candidates,
            key=lambda c: (
                -(c.get("wins") or 0),
                -(c.get("n_measured") or 0),
                -(c.get("hit_rate") or 0.0),
            ),
        )
        best = ranked[0]
        if (best.get("n_measured") or 0) >= _BEST_RULE_MIN_N:
            best["is_best_rule"] = True
    return rows

def alert_quality_daily(engine, tier: str | None = None, days: int = 30) -> list[dict]:
    """v2.5 — daily (date, tier) precision series for the per-tier sparkline.

    Same hit threshold as alert_quality (>=0.5% |move| in claimed direction),
    but indexed by asof_date so the frontend can render a ~30-point
    sparkline instead of just 7/14/30 windows. SIGMA / STRATEGY rows
    (bias NULL) are excluded — they cannot claim a directional hit by
    definition.

    Group-by is (asof_date, tier); the rule dimension is collapsed because
    the strip's per-tier card only needs the AGGREGATE hit-rate trend, not
    per-rule breakdown (per-(rule, tier) data is what alert_quality() +
    the 7/14/30 endpoint windows already expose as `quality_windows`).

    Missing dates are NOT backfilled with zeros. A bursty tier (5 hits on
    Mon, zero alerts Tue / Wed / Thu) renders as a 4-point series with
    gaps — the gap is information (no measured alerts = no signal), the
    visual breaks the line so a desk reads it as noise, NOT as a 0% loss.
    """
    since = (datetime.now(_ET).date() - timedelta(days=max(1, days))).isoformat()
    params: list = [since]
    tier_clause = ""
    if tier:
        tier_clause = " AND tier = ?"
        params.append(str(tier).upper())
    try:
        rows = engine.query(f"""
            SELECT asof_date AS date, tier,
                   count(*) AS n,
                   count(move_pct) AS n_measured,
                   CAST(SUM(CASE WHEN move_pct IS NULL THEN 0
                                 WHEN bias = 'BULLISH' AND move_pct >= 0.5 THEN 1
                                 WHEN bias = 'BEARISH' AND move_pct <= -0.5 THEN 1
                                 ELSE 0 END) AS BIGINT) AS wins,
                   avg(CASE WHEN move_pct IS NULL THEN NULL
                            WHEN bias = 'BULLISH' AND move_pct >= 0.5 THEN 1.0
                            WHEN bias = 'BEARISH' AND move_pct <= -0.5 THEN 1.0
                            ELSE 0.0 END) AS hit_rate,
                   avg(move_pct) AS avg_move_pct
            FROM flow_alerts_daily
            WHERE asof_date >= ? AND bias IS NOT NULL{tier_clause}
            GROUP BY asof_date, tier
            ORDER BY asof_date ASC, tier ASC
        """, params)
    except Exception as e:
        logger.warning(f"flow_alerts.alert_quality_daily: {e}")
        return []
    # DuckDB date columns come back as either datetime.date or
    # datetime.datetime depending on the lib version + bind context; some
    # paths serialize to a 19-char ISO datetime via .isoformat(). The JSON
    # contract to React is strictly "YYYY-MM-DD" (10 chars) so a desk
    # never confuses 2026-07-19 with 2026-07-19T00:00:00. Force the slice.
    for r in rows:
        d = r.get("date")
        if d is None:
            continue
        if hasattr(d, "isoformat"):
            r["date"] = d.isoformat()[:10]
        elif isinstance(d, str):
            # Already a string (some engine wrappers pre-serialize); trim
            # any T... suffix defensively so legacy paths still hit the
            # 10-char YYYY-MM-DD contract.
            r["date"] = d[:10]
    return rows


def dedup_filter(engine, alerts, now: float | None = None) -> list[dict]:
    """Drop alerts whose key fired within its TTL; record the survivors."""
    if not alerts:
        return []
    t = time.time() if now is None else now
    keys = [a["key"] for a in alerts]
    ph = ",".join("?" for _ in keys)
    try:
        seen = {r["key"]: r for r in engine.query(
            f"SELECT key, last_fired_ts, ttl_s FROM flow_alert_dedup WHERE key IN ({ph})", keys)}
    except Exception as e:
        # 2026-08-22: fail-open is intentional (alerts still fire on DB error)
        # but it MUST be observable — silent dedup loss = duplicate alert spam.
        logger.warning(f"flow_alerts.dedup query failed ({e}) — dedup disabled this cycle")
        seen = {}
    kept = []
    for a in alerts:
        s = seen.get(a["key"])
        if s and (t - (s["last_fired_ts"] or 0)) < (s["ttl_s"] or 0):
            continue
        kept.append(a)
    if kept:
        engine.execute_write("""
            INSERT INTO flow_alert_dedup (key, last_fired_ts, ttl_s)
            VALUES (?, ?, ?)
            ON CONFLICT (key) DO UPDATE SET
                last_fired_ts = excluded.last_fired_ts, ttl_s = excluded.ttl_s
        """, [[a["key"], t, float(a.get("ttl_s") or 7200)] for a in kept])
    return kept


def update_moves(engine, spot_map: dict, stamp_ts: str | None = None) -> int:
    """Stamp the latest underlying price onto open alerts → move-since-alert.
    Called with every fresh scan's spots; zero extra upstream calls.

    C1 horizon legs: every stamp ALSO appends one row per open alert into
    flow_alert_moves (fail-open — a leg-write failure never blocks the
    latest-price UPDATE above). stamp_ts is injectable for deterministic
    tests; live callers leave it None (now, ET).
    """
    n = 0
    now_iso = stamp_ts or datetime.now(_ET).isoformat()
    try:
        stamp_day = date.fromisoformat(str(now_iso)[:10]).isoformat()
    except Exception:
        stamp_day = date.today().isoformat()
    for under, px in (spot_map or {}).items():
        p = _f(px)
        if p is None or p <= 0:
            continue
        try:
            rows = engine.query(
                "SELECT count(*) AS c FROM flow_alerts_daily WHERE under = ? AND under_price > 0", [under])
            c = int(rows[0]["c"]) if rows else 0
            if not c:
                continue
            engine.execute_write("""
                UPDATE flow_alerts_daily
                SET last_price = ?, move_pct = (? - under_price) / under_price * 100.0
                WHERE under = ? AND under_price > 0
            """, [[p, p, under]])
            n += c
            with contextlib.suppress(Exception):
                open_rows = engine.query(
                    "SELECT asof_date, key, under_price FROM flow_alerts_daily "
                    "WHERE under = ? AND under_price > 0", [under])
                legs = []
                for r in open_rows or []:
                    try:
                        base = float(r["under_price"])
                    except (TypeError, ValueError):
                        continue
                    if base <= 0:
                        continue
                    legs.append([str(r["asof_date"]), str(r["key"]), under,
                                 now_iso, stamp_day, p,
                                 (p - base) / base * 100.0])
                if legs:
                    engine.execute_write("""
                        INSERT INTO flow_alert_moves
                        (asof_date, key, under, stamp_ts, stamp_date,
                         last_price, move_pct)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, legs)
        except Exception as e:
            logger.debug(f"flow_alerts.update_moves({under}): {e}")
    return n


def get_move_path(engine, asof_date: str, key: str) -> list[dict]:
    """Ordered horizon legs for one alert (oldest stamp first).

    Empty list = never stamped (unknown), never a fabricated zero leg.
    """
    try:
        return engine.query("""
            SELECT stamp_ts, stamp_date, last_price, move_pct
            FROM flow_alert_moves
            WHERE asof_date = ? AND key = ?
            ORDER BY stamp_ts ASC
        """, [str(asof_date), str(key)]) or []
    except Exception as e:
        logger.debug(f"flow_alerts.get_move_path({key}): {e}")
        return []


def horizon_moves(engine, asof_date: str, key: str,
                  horizons: tuple[int, ...] = (1, 5, 20)) -> dict[int, float | None]:
    """Per-horizon move legs: h-th distinct stamp session's move_pct.

    Sessions are counted as distinct stamp_dates in stamp order (no trading
    calendar needed at write time). Unmeasured horizons are None — honest
    empty, never interpolated.
    """
    legs = get_move_path(engine, asof_date, key)
    seen: list[str] = []
    sess_move: dict[str, float | None] = {}
    for leg in legs:
        day = str(leg.get("stamp_date") or "")[:10]
        if day and day not in sess_move:
            seen.append(day)
            try:
                sess_move[day] = None if leg.get("move_pct") is None else float(leg["move_pct"])
            except (TypeError, ValueError):
                sess_move[day] = None
        elif day:
            # Same session, later stamp wins (closest to close).
            with contextlib.suppress(TypeError, ValueError):
                sess_move[day] = None if leg.get("move_pct") is None else float(leg["move_pct"])
    out: dict[int, float | None] = {}
    for h in horizons:
        out[int(h)] = sess_move.get(seen[int(h) - 1]) if 0 < int(h) <= len(seen) else None
    return out


def read_alert_feed(engine, days: int = 7, min_tier: str | None = None,
                    ticker: str | None = None, min_conviction: int | None = None,
                    sort_by: str = "tier") -> list[dict]:
    """The institutional feed.

    sort_by="tier" (legacy): tier buckets then most recent.
    sort_by="conviction" (Blademap): ranked conviction DESC — a 92-conviction
    SILVER belongs above an 61-conviction GOLD.
    min_conviction: hard floor (Blademap alerts at >75 by default).
    """
    since = (datetime.now(_ET).date() - timedelta(days=max(1, days))).isoformat()
    sql = """
        SELECT * FROM flow_alerts_daily WHERE asof_date >= ?
    """
    params: list = [since]
    if ticker:
        sql += " AND under = ?"
        params.append(ticker.upper())
    if min_tier:
        rank = _TIER_RANK.get(min_tier.upper(), 2)
        allowed = [t for t, v in _TIER_RANK.items() if v <= rank]
        sql += f" AND tier IN ({','.join('?' for _ in allowed)})"
        params.extend(allowed)
    if min_conviction is not None:
        sql += " AND COALESCE(conviction, 0) >= ?"
        params.append(int(min_conviction))
    if sort_by == "conviction":
        sql += " ORDER BY COALESCE(conviction, 0) DESC, asof_ts DESC"
    else:
        sql += """
            ORDER BY CASE tier WHEN 'GOLD' THEN 0 WHEN 'SILVER' THEN 1 ELSE 2 END,
                     asof_ts DESC
        """
    try:
        return engine.query(sql, params)
    except Exception as e:
        logger.warning(f"flow_alerts.read_alert_feed: {e}")
        return []
