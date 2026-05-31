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
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

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

    # Spot vs flip level
    has_flip = not _is_effectively_zero(flip_level) and not _is_effectively_zero(spot)
    if has_flip:
        if spot > flip_level and has_gex and net_gex > 0:
            bullish_score += 1
        elif spot < flip_level and has_gex and net_gex < 0:
            bearish_score += 1
        elif spot > flip_level:
            bullish_score += 1
        elif spot < flip_level:
            bearish_score += 1

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


def _movers_description(top_movers: List[Dict[str, Any]]) -> str:
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
    top_movers: List[Dict[str, Any]],
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
    metrics: Dict[str, Any] = field(default_factory=dict)


# ────────────────────────────────────────────────────────────────────────
# Async Briefing Builder (DB integration point)
# ────────────────────────────────────────────────────────────────────────

async def build_briefing(
    ticker: str,
    duckdb_conn: Any = None,
    top_movers: Optional[List[Dict[str, Any]]] = None,
    spot: float = 0.0,
    chain_contracts: Optional[List[Dict[str, Any]]] = None,
    iv_skew_override: Optional[float] = None,
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
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()

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
        try:
            from services.gex_aggregator import GexAggregator
            agg = GexAggregator()
            gex_result = agg.compute(safe_spot, chain_contracts)
            net_gex = gex_result.get("net_gex", 0.0)
            zero_crossings = gex_result.get("zero_gamma_levels", [])
            if zero_crossings:
                flip_level = zero_crossings[0]
        except Exception:
            pass

        call_oi_total = sum(
            int(c.get("oi", c.get("open_interest", 0)))
            for c in chain_contracts
            if str(c.get("type", "")).lower() in ("call", "c", "0")
        )
        put_oi_total = sum(
            int(c.get("oi", c.get("open_interest", 0)))
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

    return BriefingResult(
        ticker=ticker,
        regime=regime,
        narrative=narrative,
        timestamp=now,
        metrics={
            "net_gex": net_gex,
            "flip_level": flip_level,
            "call_oi": call_oi_total,
            "put_oi": put_oi_total,
            "iv_skew": computed_iv_skew,
            "spot": spot,
        },
    )
