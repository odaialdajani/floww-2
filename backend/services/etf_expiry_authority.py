"""backend/services/etf_expiry_authority.py — versioned authority for ETF option expiry closes.

WHY
====
Cboe expanded trading hours for designated multi-listed equity options. The
exchange documentation distinguishes:

  * expiring **designated ETF** options — regular trading hours close at
    **16:15 ET** on the expiry day;
  * **SPXW** expiration — unchanged at **16:00**;
  * the **underlying/settlement mark** at 16:00 — a SEPARATE fact, not the
    option's last trading time;
  * an **early close at 13:15 ET** for designated ETF options, **effective
    2026-11-16** (a DATE-BOUNDED rule, not a blanket +15 minutes).

The generic holiday table on the Cboe hours page says 13:00; that table alone
is NOT authority for an ETF early close, so the date-bounded FAQ rule is used
instead and any date outside it stays explicitly unknown.

SCOPE / LIMITS
==============
This module is PURE DATA + a PURE resolver. It performs no network call, no
account/authenticated request and no entitlement check. It establishes
exchange class documentation only. Whether a given broker/account/contract is
actually reachable in that session is a DIFFERENT question that this module
does not answer and must never be implied.

The rule applies to an EXACT canonical option root and the EXACT normalized
display ticker. A substring alias (an "SPY-like" root) never inherits it.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Authority record. Bump AUTHORITY_VERSION when the rule table changes.
# ---------------------------------------------------------------------------
AUTHORITY_VERSION = "etf-expiry-authority.v1"

#: Source URLs that establish the rule (read-only, retrieved by a human).
SOURCES: tuple[dict[str, str], ...] = (
    {
        "id": "cboe-equity-options-extended-trading-hours-faq",
        "url": "https://www.cboe.com/document/tech-spec/document/technical-specifications/equity-options-extended-trading-hours-faq",
        "retrieved": "2026-11-08",
        "establishes": (
            "expiring designated ETF options trade until 16:15 ET; SPXW expiration "
            "remains 16:00; 16:00 underlying/settlement marks are a distinct fact; "
            "designated ETF early close 13:15 ET effective 2026-11-16"
        ),
    },
    {
        "id": "cboe-us-options-hours",
        "url": "https://www.cboe.com/about/hours/us-options",
        "retrieved": "2026-11-08",
        "establishes": (
            "designated ETF option classes close at 16:15 ET while ordinary equity "
            "closes at 16:00 plus selected Curb; the generic 13:00 holiday table "
            "alone is NOT authority for an ETF early close"
        ),
    },
    {
        "id": "cboe-extended-trading-sessions-launch-notice",
        "url": "https://ir.cboe.com/news/news-details/2026/Cboe-Launches-Extended-Trading-Sessions-for-Select-Single-Stock-and-ETF-Options/default.aspx",
        "retrieved": "2026-11-08",
        "establishes": (
            "SPY and QQQ are among the designated ETF symbols included in the "
            "extended sessions — CLASS-LEVEL EXCHANGE DOCUMENTATION ONLY, not "
            "broker/account entitlement"
        ),
    },
)

#: The designated-ETF option class this authority covers.
ETF_OPTION_CLASS = "DESIGNATED_ETF"

#: Exact canonical option roots in the designated-ETF class, with their
#: normalized display tickers. Both must agree exactly — no substring alias.
ETF_ROOTS: dict[str, str] = {
    "SPY": "SPY",
    "QQQ": "QQQ",
}

#: Regular expiry-day close for designated ETF options (ET).
ETF_REGULAR_CLOSE_ET = (16, 15)

#: Early close for designated ETF options (ET) and the date it takes effect.
#: The effective date is EXCLUSIVE-below: a date before it has NO
#: authoritative ETF early-close rule and stays explicitly unknown.
ETF_EARLY_CLOSE_ET = (13, 15)
ETF_EARLY_CLOSE_EFFECTIVE_FROM = "2026-11-16"

#: Series that are explicitly NOT covered by this authority (their own
#: product rules apply and are unchanged by this module).
EXCLUDED_SERIES: frozenset[str] = frozenset({"SPX", "SPXW"})


def _normalize_root(root: str | None) -> str:
    """Canonical option-root form. No aliasing, no substring matching."""
    return str(root or "").strip().upper()


def _normalize_ticker(ticker: str | None) -> str:
    """Normalized DISPLAY ticker. Distinct from the option root."""
    return str(ticker or "").strip().upper().lstrip("^")


def is_etf_option_root(root: str | None) -> bool:
    """True only for an EXACT canonical root in the designated-ETF class."""
    return _normalize_root(root) in ETF_ROOTS


def etf_authority_for(root: str | None, ticker: str | None = None,
                      series: str | None = None) -> dict[str, Any]:
    """Resolve the ETF expiry-close authority for one contract.

    Returns a dict with:
      ``status``      "authoritative" | "not_applicable" | "unknown"
      ``close_et``    (hour, minute) when authoritative
      ``early_close`` (hour, minute) when an effective-date-bounded early
                      close applies to the requested date
      ``reason``      explicit reason when not authoritative
      ``authority``   the authority version + source ids used
    """
    norm_root = _normalize_root(root)
    norm_ticker = _normalize_ticker(ticker)
    norm_series = str(series or "").strip().upper()

    base = {
        "authority": AUTHORITY_VERSION,
        "sources": [s["id"] for s in SOURCES],
        "root": norm_root,
        "ticker": norm_ticker,
        "series": norm_series,
    }

    if norm_series in EXCLUDED_SERIES:
        return {**base, "status": "not_applicable", "close_et": None, "early_close": None,
                "reason": "series excluded from the designated-ETF rule"}
    if not norm_root:
        return {**base, "status": "unknown", "close_et": None, "early_close": None,
                "reason": "missing option root"}
    if norm_root not in ETF_ROOTS:
        return {**base, "status": "not_applicable", "close_et": None, "early_close": None,
                "reason": "root is not in the designated-ETF class"}
    # The exact root and the normalized display ticker must agree. A display
    # alias never inherits the rule.
    if norm_ticker and norm_ticker != ETF_ROOTS[norm_root]:
        return {**base, "status": "unknown", "close_et": None, "early_close": None,
                "reason": "option root and display ticker disagree"}

    return {
        **base,
        "status": "authoritative",
        "close_et": ETF_REGULAR_CLOSE_ET,
        "early_close": ETF_EARLY_CLOSE_ET,
        "early_close_effective_from": ETF_EARLY_CLOSE_EFFECTIVE_FROM,
        "reason": None,
    }


def etf_early_close_applies(authority: dict[str, Any], day_iso: str | None) -> bool:
    """True only when the date-bounded ETF early close is in force for that day.

    A date before the effective date, or an unknown date, does NOT get the
    early close — the early close is never applied retrospectively.
    """
    if not authority or authority.get("status") != "authoritative":
        return False
    if not authority.get("early_close"):
        return False
    day = str(day_iso or "").strip()
    if not day:
        return False
    return day >= str(authority.get("early_close_effective_from") or "")
