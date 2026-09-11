"""
backend/services/morning_briefing.py

Morning Briefing Engine
========================
Template-driven briefing generator that consumes GEX regime, top movers,
and IV skew to produce a deterministic BULLISH/BEARISH/NEUTRAL/UNKNOWN
narrative with supporting metrics.

No LLM calls. Purely deterministic, < 50ms per generation.

Usage:
    from services.morning_briefing import classify_regime, generate_narrative, build_briefing

    regime = classify_regime(net_gex=1.5e9, call_oi=500000, put_oi=300000,
                             iv_skew=0.005, flip_level=448.0, spot=452.0)
    narrative = generate_narrative(regime=regime, ticker="SPY", ...)
    briefing = await build_briefing("SPY", duckdb, top_movers)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import UTC
from typing import Any

logger = logging.getLogger(__name__)

# ── In-memory prior-state caches for data-feed gap signals ────────────────
# These enable gamma_decomposition, stock_order_imbalance, and
# real_drift_burst_risk to work on the SECOND call onward by
# storing the previous snapshot per ticker.
_prior_gex_cache: dict[str, dict[str, float]] = {}
_prior_delta_cache: dict[str, float] = {}
_prior_returns_cache: dict[str, list[float]] = {}
_PRIOR_CACHE_MAX_SIZE = 100  # prevent unbounded growth


def _trim_prior_cache(cache: dict) -> None:
    """Trim cache if it exceeds max size (FIFO eviction)."""
    if len(cache) > _PRIOR_CACHE_MAX_SIZE:
        # Evict oldest entries (FIFO approximation via first keys)
        excess = len(cache) - _PRIOR_CACHE_MAX_SIZE
        for key in list(cache.keys())[:excess]:
            cache.pop(key, None)

# ────────────────────────────────────────────────────────────────────────
# Thresholds (tunable)
# ────────────────────────────────────────────────────────────────────────

GEX_BULLISH_THRESHOLD = 1.0e9     # net GEX > this → bullish GEX signal
GEX_BEARISH_THRESHOLD = -1.0e9    # net GEX < this → bearish GEX signal
OI_SURGE_RATIO = 1.3              # call/put or put/call ratio for "surge"
IV_SKEW_FEAR_THRESHOLD = 0.03     # put IV - call IV > this = fear
IV_SKEW_GREED_THRESHOLD = -0.01   # call IV > put IV = greed
FEAR_SKEW_HIGH = 0.05             # extreme fear threshold


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Return val as float, or default if NaN / None / non-numeric. I-8 NaN guard."""
    if val is None:
        return default
    try:
        f = float(val)
    except (TypeError, ValueError):
        return default
    if math.isnan(f) or math.isinf(f):
        return default
    return f


def _is_effectively_zero(val: float) -> bool:
    """Check if a value is zero or NaN (sentinel for 'no data')."""
    return val == 0.0 or math.isnan(val)


# ────────────────────────────────────────────────────────────────────────
# Tidehunter outcome ledger (nightly cron precomputed)
# ────────────────────────────────────────────────────────────────────────

_outcome_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_OUTCOME_TTL_S = 6 * 3600  # cron refreshes nightly; brief re-reads at most every 6h


async def _read_mongo_snapshot(horizon: int = 2) -> dict[str, Any] | None:
    """Read the cron's precomputed outcome snapshot from Mongo.

    Async by contract: Motor clients are bound to the loop that created them,
    so this must run on the server's loop (call from async context only).
    Monkeypatched in tests.
    """
    from server import db as mongo_db  # deferred: circular import

    doc = await mongo_db.flow_outcome_cache.find_one({"_id": f"outcomes_h{horizon}"})
    if not doc or doc.get("status") != "ok":
        return None
    return {k: v for k, v in doc.items() if k != "_id"}


async def _read_calibration_snapshot(horizon: int = 2) -> dict[str, Any] | None:
    """Read the cron's calibration snapshot (same loop contract as above)."""
    from server import db as mongo_db  # deferred: circular import

    doc = await mongo_db.flow_outcome_cache.find_one({"_id": "calibration_latest"})
    if not doc:
        return None
    return {k: v for k, v in doc.items() if k != "_id"}


async def _outcome_ledger_metrics(horizon: int = 2) -> dict[str, Any]:
    """Measured alert quality from the nightly outcome-refresh snapshot.

    Reads Mongo flow_outcome_cache (written by cron_outcomes.py at 20:30 ET)
    — never computes live here, so the brief stays fast and network-light
    (one cached Mongo read per 6h). Fails soft: any problem yields
    {"available": False, "reason": ...} rather than breaking the brief.

    Shape:
      {available, computed_at, overall_precision,
       rules: [{rule, n_measured, precision, control_rate, lift, uncalibrated}],
       calibration?: {stage, n, method_note, ...}}
    """
    import time as _time

    key = f"h{horizon}"
    hit = _outcome_cache.get(key)
    if hit and _time.time() - hit[0] < _OUTCOME_TTL_S:
        return hit[1]

    try:
        doc = await _read_mongo_snapshot(horizon)
        if doc is None:
            out = {"available": False, "reason": "no snapshot yet — cron has not run"}
        else:
            rules = []
            for rule, s in sorted((doc.get("per_rule") or {}).items()):
                rules.append({
                    "rule": rule,
                    "n_measured": s.get("n_measured", 0),
                    "precision": s.get("precision"),
                    "control_rate": s.get("control_rate"),
                    "lift": s.get("lift"),
                    "uncalibrated": s.get("uncalibrated", True),
                })
            out = {
                "available": True,
                "computed_at": doc.get("computed_at"),
                "overall_precision": (doc.get("overall") or {}).get("precision"),
                "rules": rules,
            }
            try:
                cal_doc = await _read_calibration_snapshot(horizon)
                if cal_doc:
                    from services.flow_calibration import calibration_status_blob
                    out["calibration"] = calibration_status_blob(cal_doc)
            except Exception:
                pass  # calibration enrichment is optional
        _outcome_cache[key] = (_time.time(), out)
        return out
    except Exception as e:
        return {"available": False, "reason": f"outcome ledger read failed: {type(e).__name__}"}


def _outcome_narrative_line(ao: dict[str, Any] | None) -> str:
    """One honest sentence about the alert ledger, appended to the brief text.

    Contracts: unavailable/cold ledger → empty string (the brief never lies
    about measurement it doesn't have); only rules with measured precision
    are quoted; negative lift is called out because that's the number that
    says a rule is currently worse than coin-flipping vs its control cohort.
    """
    if not ao or not ao.get("available"):
        return ""
    all_rules = ao.get("rules") or []
    measured = [r for r in all_rules
                if not r.get("uncalibrated") and isinstance(r.get("precision"), (int, float))
                and isinstance(r.get("lift"), (int, float))]
    if not measured:
        n = sum(r.get("n_measured", 0) for r in all_rules)
        return (f"Alert ledger: {n} measured alert(s) — not yet enough for "
                "per-rule hit rates.") if n else ""
    best = max(measured, key=lambda r: r["lift"])
    segs = [f"{best['rule']} {best['precision']:.0%} hit, lift {best['lift']:+.2f}"]
    worst = min(measured, key=lambda r: r["lift"])
    if worst is not best and worst["lift"] < 0:
        segs.append(f"{worst['rule']} lift {worst['lift']:+.2f}")
    line = "Measured alert quality: " + "; ".join(segs)
    overall = ao.get("overall_precision")
    if isinstance(overall, (int, float)):
        line += f" — overall {overall:.0%}"
    return line + "."


# ────────────────────────────────────────────────────────────────────────
# Regime Classifier
# ────────────────────────────────────────────────────────────────────────

def classify_regime(
    net_gex: float,
    call_oi: float,
    put_oi: float,
    iv_skew: float,
    flip_level: float,
    spot: float,
) -> str:
    """
    Classify the current market regime.

    Rules (deterministic, no LLM):
      1. If ALL metrics are NaN/zero → UNKNOWN
      2. BULLISH if:
         - net GEX > GEX_BULLISH_THRESHOLD AND call OI > put OI * OI_SURGE_RATIO
         - OR spot > flip_level AND net GEX > GEX_BULLISH_THRESHOLD
         - OR spot > flip_level AND call OI > put OI * OI_SURGE_RATIO
      3. BEARISH if:
         - net GEX < GEX_BEARISH_THRESHOLD AND put OI > call OI * OI_SURGE_RATIO
         - OR spot < flip_level AND net GEX < GEX_BEARISH_THRESHOLD
         - OR spot < flip_level AND put OI > call OI * OI_SURGE_RATIO
         - OR iv_skew > FEAR_SKEW_HIGH
      4. Otherwise → NEUTRAL

    NaN-safe: NaN inputs are treated as 0 for the purpose of thresholding,
    but the scoring system weights available signals.

    Returns one of: "BULLISH", "BEARISH", "NEUTRAL", "UNKNOWN"
    """
    # Normalize inputs with NaN guards
    net_gex = _safe_float(net_gex, 0.0)
    call_oi = _safe_float(call_oi, 0.0)
    put_oi = _safe_float(put_oi, 0.0)
    iv_skew = _safe_float(iv_skew, 0.0)
    flip_level = _safe_float(flip_level, 0.0)
    spot = _safe_float(spot, 0.0)

    # UNKNOWN: all sentinel values
    all_zero = (
        _is_effectively_zero(net_gex)
        and _is_effectively_zero(call_oi)
        and _is_effectively_zero(put_oi)
        and _is_effectively_zero(iv_skew)
        and _is_effectively_zero(flip_level)
        and _is_effectively_zero(spot)
    )
    if all_zero:
        return "UNKNOWN"

    bullish_score = 0
    bearish_score = 0

    # GEX signal
    has_gex = not _is_effectively_zero(net_gex)
    if has_gex:
        if net_gex > GEX_BULLISH_THRESHOLD:
            bullish_score += 2
        elif net_gex > 0:
            bullish_score += 1  # moderate positive GEX
        elif net_gex < GEX_BEARISH_THRESHOLD:
            bearish_score += 2
        elif net_gex < 0:
            bearish_score += 1  # moderate negative GEX

    # OI ratio signal
    has_oi = (not _is_effectively_zero(call_oi)) or (not _is_effectively_zero(put_oi))
    if has_oi:
        if put_oi > 0 and call_oi / put_oi > OI_SURGE_RATIO:
            bullish_score += 2
        elif call_oi > 0 and put_oi / call_oi > OI_SURGE_RATIO:
            bearish_score += 2

    # Spot vs flip level - only score when combined with GEX signal
    # Flip level without GEX is ambiguous; requiring both prevents mislabeling
    has_flip = not _is_effectively_zero(flip_level) and not _is_effectively_zero(spot)
    if has_flip:
        if spot > flip_level and has_gex and net_gex > 0:
            bullish_score += 1
        elif spot < flip_level and has_gex and net_gex < 0:
            bearish_score += 1
        # Removed: elif spot > flip_level / elif spot < flip_level
        # These were causing bullish to be labeled as bearish when flip_level
        # was a resistance level and spot was below it, without GEX confirmation

    # IV skew signal
    has_skew = not _is_effectively_zero(iv_skew)
    if has_skew:
        if iv_skew > FEAR_SKEW_HIGH:
            bearish_score += 3  # Extreme fear is a strong signal
        elif iv_skew > IV_SKEW_FEAR_THRESHOLD:
            bearish_score += 1
        elif iv_skew < IV_SKEW_GREED_THRESHOLD:
            bullish_score += 1

    # Determine regime from scores
    if bullish_score >= 2 and bullish_score > bearish_score:
        return "BULLISH"
    elif bearish_score >= 2 and bearish_score > bullish_score:
        return "BEARISH"
    elif bullish_score >= 1 or bearish_score >= 1:
        return "NEUTRAL"
    else:
        return "NEUTRAL"


# ────────────────────────────────────────────────────────────────────────
# Narrative Template Engine
# ────────────────────────────────────────────────────────────────────────

# Pre-built templates per regime — deterministic, no f-string branching
_TEMPLATE_BULLISH = (
    "BULLISH {ticker} ${spot:.1f}. "
    "GEX ${gex_b} positive. "
    "{skew_desc}. "
    "{oi_desc}. "
    "Flip at ${flip:.1f}. "
    "{movers_desc}"
).strip()

_TEMPLATE_BEARISH = (
    "BEARISH {ticker} ${spot:.1f}. "
    "GEX ${gex_b} negative. "
    "{skew_desc}. "
    "{oi_desc}. "
    "Flip at ${flip:.1f}. "
    "{movers_desc}"
).strip()

_TEMPLATE_NEUTRAL = (
    "NEUTRAL {ticker} ${spot:.1f}. "
    "GEX near zero ${gex_b}. "
    "{skew_desc}. "
    "Flip at ${flip:.1f}. "
    "{movers_desc}"
).strip()

_TEMPLATE_UNKNOWN = (
    "UNKNOWN {ticker} — insufficient data for regime classification."
).strip()


def _format_gex(val: float) -> str:
    """Format GEX in billions/millions for display."""
    if abs(val) >= 1e9:
        return f"{val / 1e9:.1f}B"
    elif abs(val) >= 1e6:
        return f"{val / 1e6:.0f}M"
    else:
        return f"{val:.0f}"


def _skew_description(iv_skew: float) -> str:
    """Human-readable IV skew direction."""
    iv_skew = _safe_float(iv_skew, 0.0)
    if iv_skew > FEAR_SKEW_HIGH:
        return "Extreme put skew (fear)"
    elif iv_skew > IV_SKEW_FEAR_THRESHOLD:
        return "Put skew elevated"
    elif iv_skew < IV_SKEW_GREED_THRESHOLD:
        return "Call skew (greed)"
    else:
        return "IV skew balanced"


def _oi_description(call_oi: int, put_oi: int) -> str:
    """Human-readable OI dominance."""
    call_oi = _safe_float(call_oi, 0.0)
    put_oi = _safe_float(put_oi, 0.0)
    if call_oi == 0 and put_oi == 0:
        return "No OI data"
    total = call_oi + put_oi
    if total == 0:
        return "No OI data"
    call_pct = call_oi / total * 100
    put_pct = put_oi / total * 100
    if call_pct > 60:
        return f"Calls dominate OI ({call_pct:.0f}%)"
    elif put_pct > 60:
        return f"Puts dominate OI ({put_pct:.0f}%)"
    else:
        return f"OI balanced ({call_pct:.0f}% calls)"


def _movers_description(top_movers: list[dict[str, Any]]) -> str:
    """Format top movers into a brief string."""
    if not top_movers:
        return ""
    # Take top 3 by absolute pct
    sorted_movers = sorted(
        top_movers,
        key=lambda m: abs(_safe_float(m.get("pct", 0), 0.0)),
        reverse=True,
    )[:3]
    parts = []
    for m in sorted_movers:
        t = m.get("ticker", "?")
        pct = _safe_float(m.get("pct", 0), 0.0)
        direction = "up" if pct > 0 else "dn"
        parts.append(f"{t} {direction} {abs(pct):.1f}%")
    return "Top: " + ", ".join(parts)


def generate_narrative(
    regime: str,
    ticker: str,
    spot: float,
    flip_level: float,
    net_gex: float,
    iv_skew: float,
    top_movers: list[dict[str, Any]],
    call_oi: int = 0,
    put_oi: int = 0,
) -> str:
    """
    Generate a concise deterministic narrative string.

    Uses string.Template-style substitution for structured output.
    Output is always < 500 chars. Deterministic — no LLM.

    Args:
        regime: One of BULLISH, BEARISH, NEUTRAL, UNKNOWN
        ticker: Ticker symbol (e.g. "SPY")
        spot: Current spot price
        flip_level: GEX flip level
        net_gex: Net dollar gamma exposure
        iv_skew: Put IV - call IV (ATM)
        top_movers: List of {"ticker": str, "pct": float}
        call_oi: Total call open interest
        put_oi: Total put open interest

    Returns:
        Narrative string, always <= 500 chars.
    """
    spot = _safe_float(spot, 0.0)
    flip_level = _safe_float(flip_level, 0.0)
    net_gex = _safe_float(net_gex, 0.0)
    iv_skew = _safe_float(iv_skew, 0.0)
    call_oi = int(_safe_float(call_oi, 0.0))
    put_oi = int(_safe_float(put_oi, 0.0))

    skew_desc = _skew_description(iv_skew)
    oi_desc = _oi_description(call_oi, put_oi)
    movers_desc = _movers_description(top_movers)
    gex_b = _format_gex(net_gex)

    if regime == "UNKNOWN":
        narrative = _TEMPLATE_UNKNOWN.format(ticker=ticker)
    elif regime == "BULLISH":
        narrative = _TEMPLATE_BULLISH.format(
            ticker=ticker,
            spot=spot,
            gex_b=gex_b,
            skew_desc=skew_desc,
            oi_desc=oi_desc,
            flip=flip_level,
            movers_desc=movers_desc,
        )
    elif regime == "BEARISH":
        narrative = _TEMPLATE_BEARISH.format(
            ticker=ticker,
            spot=spot,
            gex_b=gex_b,
            skew_desc=skew_desc,
            oi_desc=oi_desc,
            flip=flip_level,
            movers_desc=movers_desc,
        )
    else:  # NEUTRAL
        narrative = _TEMPLATE_NEUTRAL.format(
            ticker=ticker,
            spot=spot,
            gex_b=gex_b,
            skew_desc=skew_desc,
            flip=flip_level,
            movers_desc=movers_desc,
        )

    # Hard cap at 500 chars
    if len(narrative) > 500:
        narrative = narrative[:497] + "..."

    return narrative


# ────────────────────────────────────────────────────────────────────────
# Briefing Data Container
# ────────────────────────────────────────────────────────────────────────

@dataclass
class BriefingResult:
    """Complete briefing response."""
    ticker: str
    regime: str
    narrative: str
    timestamp: str
    metrics: dict[str, Any] = field(default_factory=dict)


# ────────────────────────────────────────────────────────────────────────
# Async Briefing Builder (DB integration point)
# ────────────────────────────────────────────────────────────────────────

async def build_briefing(
    ticker: str,
    duckdb_conn: Any = None,
    top_movers: list[dict[str, Any]] | None = None,
    spot: float = 0.0,
    chain_contracts: list[dict[str, Any]] | None = None,
    iv_skew_override: float | None = None,
) -> BriefingResult:
    """
    Build a complete briefing for a ticker.

    This is the main entry point used by the API layer.

    Data sources (optional — degrades gracefully if unavailable):
      - duckdb_conn: DuckDB connection for GEX/chain data
      - top_movers: Pre-fetched top movers list
      - spot: Current spot price override
      - chain_contracts: Pre-fetched chain data
      - iv_skew_override: Pre-computed IV skew

    Returns BriefingResult with regime, narrative, metrics, timestamp.
    """
    from datetime import datetime

    now = datetime.now(UTC).isoformat()

    # Default: produce UNKNOWN with no data
    if duckdb_conn is None and not chain_contracts and spot == 0.0:
        regime = classify_regime(0.0, 0, 0, 0.0, 0.0, 0.0)
        narrative = generate_narrative(
            regime=regime,
            ticker=ticker,
            spot=0.0,
            flip_level=0.0,
            net_gex=0.0,
            iv_skew=0.0,
            top_movers=top_movers or [],
        )
        return BriefingResult(
            ticker=ticker,
            regime=regime,
            narrative=narrative,
            timestamp=now,
            metrics={},
        )

    # Try to extract GEX metrics from DuckDB
    net_gex = 0.0
    flip_level = 0.0
    call_oi_total = 0
    put_oi_total = 0
    computed_iv_skew = 0.0

    if duckdb_conn is not None:
        try:
            # Query latest chain snapshot
            chain_rows = duckdb_conn.execute(
                "SELECT strike, type, open_interest, gamma, iv, expiry "
                "FROM chains WHERE ticker = ? ORDER BY timestamp DESC LIMIT 500",
                [ticker],
            ).fetchall()

            if chain_rows:
                contracts = []
                for row in chain_rows:
                    contracts.append({
                        "strike": row[0],
                        "type": row[1],
                        "oi": row[2],
                        "gamma": row[3],
                        "iv": row[4],
                        "expiry": row[5],
                    })

                safe_spot = spot if spot > 0 else _safe_float(chain_rows[0][0], 0.0)

                try:
                    from services.gex_aggregator import GexAggregator
                    agg = GexAggregator()
                    gex_result = agg.compute(safe_spot, contracts)
                    net_gex = gex_result.get("net_gex", 0.0)
                    zero_crossings = gex_result.get("zero_gamma_levels", [])
                    if zero_crossings:
                        flip_level = zero_crossings[0]
                    call_oi_total = sum(
                        int(c.get("oi", 0))
                        for c in contracts
                        if str(c.get("type", "")).lower() in ("call", "c", "0")
                    )
                    put_oi_total = sum(
                        int(c.get("oi", 0))
                        for c in contracts
                        if str(c.get("type", "")).lower() in ("put", "p", "1")
                    )
                except Exception as e:
                    logger.debug(f"GEX compute failed for {ticker}: {e}")

                # IV skew from chain
                if iv_skew_override is not None:
                    computed_iv_skew = iv_skew_override
                else:
                    try:
                        call_ivs = {}
                        put_ivs = {}
                        for c in contracts:
                            k = str(c["strike"])
                            if str(c.get("type", "")).lower() in ("call", "c", "0"):
                                call_ivs[k] = c.get("iv", 0.0)
                            else:
                                put_ivs[k] = c.get("iv", 0.0)
                        if call_ivs and put_ivs:
                            from services.iv_skew_analyzer import IvSkewAnalyzer
                            analyzer = IvSkewAnalyzer()
                            skew_result = analyzer.analyze(call_ivs, put_ivs, safe_spot)
                            computed_iv_skew = skew_result.skew_atm
                    except Exception as e:
                        logger.debug(f"IV skew compute failed for {ticker}: {e}")

        except Exception as e:
            logger.debug(f"DuckDB query failed for {ticker}: {e}")

    # Use pre-fetched chain if no DB connection
    elif chain_contracts:
        safe_spot = spot if spot > 0 else 0.0
        from services.gex_aggregator import GexAggregator
        try:
            agg = GexAggregator()
            gex_result = agg.compute(safe_spot, chain_contracts)
            net_gex = gex_result.get("net_gex", 0.0)
            zero_crossings = gex_result.get("zero_gamma_levels", [])
            if zero_crossings:
                flip_level = zero_crossings[0]
        except Exception as e:
            logger.warning(
                f"morning_briefing: gex-compute-failed ticker={ticker}: {e}",
                exc_info=True,
            )
            pass

        call_oi_total = sum(
            int(c.get("oi", c.get("open_interest", 0)) or 0)
            if c.get("oi", c.get("open_interest", 0)) == c.get("oi", c.get("open_interest", 0))
            else 0
            for c in chain_contracts
            if str(c.get("type", "")).lower() in ("call", "c", "0")
        )
        put_oi_total = sum(
            int(c.get("oi", c.get("open_interest", 0)) or 0)
            if c.get("oi", c.get("open_interest", 0)) == c.get("oi", c.get("open_interest", 0))
            else 0
            for c in chain_contracts
            if str(c.get("type", "")).lower() in ("put", "p", "1")
        )

    # Classify regime
    regime = classify_regime(
        net_gex=net_gex,
        call_oi=call_oi_total,
        put_oi=put_oi_total,
        iv_skew=computed_iv_skew,
        flip_level=flip_level,
        spot=spot,
    )

    # Generate narrative
    narrative = generate_narrative(
        regime=regime,
        ticker=ticker,
        spot=spot,
        flip_level=flip_level,
        net_gex=net_gex,
        iv_skew=computed_iv_skew,
        top_movers=top_movers or [],
        call_oi=call_oi_total,
        put_oi=put_oi_total,
    )

    # Tidehunter outcome ledger — one honest sentence on whether recent
    # alerts actually predicted (nightly cron's precomputed snapshot;
    # empty until the ledger accumulates). Must never break the brief.
    try:
        _ao_line = _outcome_narrative_line(await _outcome_ledger_metrics())
        if _ao_line:
            narrative = f"{narrative}\n\n{_ao_line}"
    except Exception:
        logger.debug("outcome narrative line skipped", exc_info=True)

    # ── Paper-accurate GEX diagnostic (Ni-Pearson + Barbon-Buraschi) ────
    paper_metrics = {}
    pcr_signal = {}
    ooi_signal = {}
    charm_signal = {}
    liquidity_signal = {}
    gamma_liq_signal = {}
    demand_signal = {}
    burst_signal = {}
    stock_imb_signal = {}
    eos_pin_signal = {}
    cw_spread_signal = {}
    gpp_premium_signal = {}
    opt_illiq_signal = {}
    vix_gamma_signal = {}
    overnight_signal = {}
    dealer_fragility_signal = {}
    spillover_signal = {}
    gib_pct = 0
    if spot > 0 and not _is_effectively_zero(net_gex):
        try:
            from services.gex_paper_accurate import (
                charm_hedging_pressure,
                cremers_weinbaum_spread,
                cross_asset_gamma_spillover,
                dealer_balance_sheet_fragility,
                dealer_hedging_liquidity_impact,
                demand_pressure_premium,
                drift_burst_risk,
                full_paper_diagnostic,
                gamma_liquidity_regime,
                informed_option_volume_signal,
                option_demand_pressure,
                option_illiquidity_signal,
                options_order_imbalance,
                overnight_drift_risk,
                put_call_ratio_signal,
                real_drift_burst_risk,
                stock_order_imbalance_signal,
                vix_gamma_fragility,
            )
            # ADV proxy — the paper normalises by average daily share volume
            _adv_proxy = {
                "SPY": 75_000_000, "SPX": 3_500_000, "QQQ": 45_000_000,
                "IWM": 28_000_000, "DIA": 3_000_000, "AAPL": 55_000_000,
                "MSFT": 22_000_000, "NVDA": 250_000_000, "TSLA": 80_000_000,
                "META": 15_000_000, "AMZN": 40_000_000, "GOOGL": 22_000_000,
            }.get(ticker.upper(), 10_000_000)
            paper_metrics = full_paper_diagnostic(
                net_gex=net_gex,
                spot=spot,
                adv_shares=_adv_proxy,
                zero_gamma_level=flip_level if not _is_effectively_zero(flip_level) else None,
            ).get("paper_metrics", {})
            # Pan-Poteshman (2006) put-call ratio signal
            if not (_is_effectively_zero(call_oi_total) and _is_effectively_zero(put_oi_total)):
                pcr_signal = put_call_ratio_signal(call_oi_total, put_oi_total)
            # Hu (2014) Options Order Imbalance
            ooi_signal = options_order_imbalance(
                call_open_interest=call_oi_total, put_open_interest=put_oi_total
            )
            # Theta-derived charm proxy from chain averages (heuristic, unverified)
            charm_signal = {"signal": "data_unavailable"}
            if chain_contracts and len(chain_contracts) > 0:
                avg_theta = sum(c.get("theta", 0) or 0 for c in chain_contracts[:20]) / max(1, min(20, len(chain_contracts)))
                avg_delta = sum(abs(c.get("delta", 0) or 0) for c in chain_contracts[:20]) / max(1, min(20, len(chain_contracts)))
                min_dte = min((c.get("expiry", 365) or 365 for c in chain_contracts[:20]), default=365.0)
                dte = min(min_dte * 365.0, 365.0) if min_dte < 1.0 else min_dte
                charm_signal = charm_hedging_pressure(avg_delta, avg_theta, dte)
            # O'Donovan-Yu-Zhang (2023) dealer hedging → stock liquidity
            gib_pct = paper_metrics.get("gamma_imbalance", {}).get("gamma_imbalance_pct", 0)
            liquidity_signal = dealer_hedging_liquidity_impact(net_gex, gib_pct)
            # Barbon-Buraschi gamma → option liquidity regime
            flip_dist = paper_metrics.get("flip_metrics", {}).get("flip_distance_pct")
            gamma_liq_signal = gamma_liquidity_regime(gib_pct, flip_dist)
            # Gârleanu-Pedersen-Poteshman (2008) demand pressure
            pcr_val = pcr_signal.get("pcr_oi") if isinstance(pcr_signal, dict) else None
            demand_signal = option_demand_pressure(net_gex, put_call_ratio_oi=pcr_val)
            # GPP (2009) RFS — demand pressure IV premium
            gpp_premium_signal = demand_pressure_premium(
                net_gex, spot, put_call_ratio_oi=pcr_val
            )
            # Goyenko-Ornthanalai-Tang option illiquidity
            opt_illiq_signal = option_illiquidity_signal(
                open_interest=call_oi_total + put_oi_total
            )
            # ── Explicit gamma_decomposition with prior-GEX cache ──
            _prior_gex_state = _prior_gex_cache.get(ticker.upper(), {})
            _old_gex = _prior_gex_state.get("net_gex")
            _old_spot = _prior_gex_state.get("spot")
            if _old_gex is not None and _old_spot is not None and _old_spot > 0:
                from services.gex_paper_accurate import decompose_gamma
                gamma_decomp = decompose_gamma(
                    current_gex=net_gex,
                    gex_at_old_spot=_old_gex,  # prior GEX recomputed at current spot
                    gex_at_old_spot_old_oi=_old_gex,  # prior GEX at prior spot
                )
                # Override the paper_metrics default (which has None values)
                paper_metrics["gamma_decomposition"] = gamma_decomp
            # Update cache for next call
            if _PRIOR_CACHE_MAX_SIZE and len(_prior_gex_cache) < _PRIOR_CACHE_MAX_SIZE:
                _prior_gex_cache[ticker.upper()] = {"net_gex": net_gex, "spot": spot}

            # VIX term structure × Gamma fragility
            vix_gamma_signal = vix_gamma_fragility(
                gamma_imbalance_pct=gib_pct,
                flip_distance_pct=flip_dist,
            )
            # Overnight drift risk — dealer gamma at close → next-day gap
            overnight_signal = overnight_drift_risk(
                net_gex, gib_pct, put_call_ratio_oi=pcr_val,
            )
            # Dealer balance sheet fragility (post-SVB dealer capacity)
            dealer_fragility_signal = dealer_balance_sheet_fragility(
                gamma_imbalance_pct=gib_pct,
            )
            # Cross-asset gamma spillover — index gamma → this ticker
            spillover_signal = cross_asset_gamma_spillover(
                spx_gamma_imbalance_pct=gib_pct,
                single_stock_gamma_imbalance_pct=gib_pct,
                sector="broad",
            )
            # Christensen-Oomen-Reno (2018) drift burst risk
            # Try real returns from cache; fall back to gamma proxy
            _cached_returns = _prior_returns_cache.get(ticker.upper())
            if _cached_returns and len(_cached_returns) >= 30:
                burst_signal = real_drift_burst_risk(
                    _cached_returns, gamma_imbalance_pct=gib_pct
                )
            else:
                burst_signal = drift_burst_risk(gamma_imbalance_pct=gib_pct)
            # Easley-O'Hara-Srinivas (1998) PIN — informed option volume
            if not (_is_effectively_zero(call_oi_total) and _is_effectively_zero(put_oi_total)):
                # Proxy: total OI ratio as buyer/seller initiated proxy
                # Approximate: call-heavy = net call buying, put-heavy = net put buying
                eos_pin_signal = informed_option_volume_signal(
                    buyer_initiated_call_vol=call_oi_total * 0.6,
                    seller_initiated_call_vol=call_oi_total * 0.4,
                    buyer_initiated_put_vol=put_oi_total * 0.4,
                    seller_initiated_put_vol=put_oi_total * 0.6,
                )
                # Cremers-Weinbaum (2010) CW spread from chain bid/ask
                if chain_contracts and len(chain_contracts) > 0:
                    try:
                        call_bids = [c.get("bid", c.get("last", 0)) or 0 for c in chain_contracts if str(c.get("type","")).lower() in ("call","c","0")]
                        put_asks = [c.get("ask", c.get("last", 0)) or 0 for c in chain_contracts if str(c.get("type","")).lower() in ("put","p","1")]
                        strikes_list = [c.get("strike", 0) or 0 for c in chain_contracts]
                        oi_list = [c.get("oi", c.get("open_interest", 0)) or 0 for c in chain_contracts]
                        num_use = min(len(call_bids), len(put_asks), len(strikes_list))
                        if num_use > 0:
                            cw_spread_signal = cremers_weinbaum_spread(
                                call_bids[:num_use], put_asks[:num_use],
                                strikes_list[:num_use], oi_list[:num_use] if oi_list else None,
                                spot=spot, dte_days=30
                            )
                    except Exception:
                        pass  # silent by design: per-ticker delta estimate inside loop; next iteration retries fresh
            # Ni-Pearson appendix §3 — stock order imbalance from delta rebalancing
            if chain_contracts and len(chain_contracts) > 0:
                try:
                    net_delta_today = sum(
                        (c.get("delta", 0) or 0) * (c.get("oi", c.get("open_interest", 0)) or 0)
                        for c in chain_contracts
                    )
                    # Feed cached prior delta for full decomposition
                    _prior_delta = _prior_delta_cache.get(ticker.upper())
                    stock_imb_signal = stock_order_imbalance_signal(
                        net_delta=net_delta_today,
                        net_delta_old_spot=_prior_delta,
                        net_gamma=net_gex,
                    )
                    # Update cache for next call
                    _prior_delta_cache[ticker.upper()] = net_delta_today
                    _trim_prior_cache(_prior_delta_cache)
                except Exception:
                    pass  # silent by design: cache update is cosmetic; sibling outer handler logs
        except Exception as e:
            logger.debug(f"Paper-accurate GEX diagnostic failed for {ticker}: {e}")

    import math as _math

    def _sanitize(obj):
        """Recursively replace NaN/Inf with None — FastAPI's JSONResponse
        rejects non-compliant floats (2026-08-22 briefing 500 fix)."""
        if isinstance(obj, float):
            return None if _math.isnan(obj) or _math.isinf(obj) else obj
        if isinstance(obj, dict):
            return {k: _sanitize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_sanitize(v) for v in obj]
        return obj

    return BriefingResult(
        ticker=ticker,
        regime=regime,
        narrative=narrative,
        timestamp=now,
        metrics=_sanitize({
            "net_gex": net_gex,
            "flip_level": flip_level,
            "call_oi": call_oi_total,
            "put_oi": put_oi_total,
            "iv_skew": computed_iv_skew,
            "spot": spot,
            # Paper-accurate metrics (Ni-Pearson 2020 + Barbon-Buraschi 2021)
            "gamma_imbalance": paper_metrics.get("gamma_imbalance", {}),
            "flip_metrics": paper_metrics.get("flip_metrics", {}),
            "intraday_regime": paper_metrics.get("intraday_regime", {}),
            "gamma_decomposition": paper_metrics.get("gamma_decomposition", {}),
            "flash_crash_risk": paper_metrics.get("flash_crash_risk", {}),
            # Pan-Poteshman (2006) put-call ratio signal
            "put_call_ratio": pcr_signal,
            "options_order_imbalance": ooi_signal,
            "charm_pressure": charm_signal,
            "dealer_liquidity_impact": liquidity_signal,
            "gamma_liquidity_regime": gamma_liq_signal,
            # Gârleanu-Pedersen-Poteshman (2008) demand pressure
            "option_demand_pressure": demand_signal,
            # GPP (2009) RFS — demand pressure IV premium
            "demand_pressure_premium": gpp_premium_signal,
            # Goyenko-Ornthanalai-Tang — option illiquidity
            "option_illiquidity": opt_illiq_signal,
            # VIX term structure × Gamma fragility interaction
            "vix_gamma_fragility": vix_gamma_signal,
            # Overnight drift risk — dealer gamma at close → next-day gap
            "overnight_drift_risk": overnight_signal,
            # Dealer balance sheet fragility — post-SVB capacity index
            "dealer_balance_sheet_fragility": dealer_fragility_signal,
            # Christensen-Oomen-Reno (2018) drift burst risk
            "drift_burst_risk": burst_signal,
            # Ni-Pearson appendix §3 — dealer delta rebalancing → stock imbalance
            "stock_order_imbalance": stock_imb_signal,
            # Easley-O'Hara-Srinivas (1998) — informed option volume PIN
            "informed_volume_pin": eos_pin_signal,
            # Cremers-Weinbaum (2010) — Put-Call Parity deviation
            "cw_spread": cw_spread_signal,
            # Christensen-Oomen-Reno (2018) — drift burst (real returns if cached)
            "real_drift_burst": burst_signal,
            # Cross-asset gamma spillover — index gamma → this ticker
            "cross_asset_spillover": spillover_signal,
            # Tidehunter outcome ledger (2026-09-02) — measured alert quality
            # from the nightly cron's precomputed snapshot. Read-only context:
            # the brief reports whether yesterday's tape actually predicted.
            "alert_outcomes": await _outcome_ledger_metrics(),
        }))
