"""
backend/services/contract_identity.py — exact contract identity for review (S5).

WHY
===
R10-13 is a frontend correctness migration, but the backend half of it is
missing entirely: there is no contract-detail API at all, so the only way a
consumer can get contract detail today is to take a WALL's midpoint and its
FIRST expiry and present that as the contract. That is a guess wearing an
identity, and it is exactly the "wall midpoint plus first expiry by
assumption" the contract forbids.

This module is the backend support for that migration:

- `contract_identity()` builds ONE canonical identity from a contract row
  (exact decimal strike, OSI, expiry, type, series), so two spellings of the
  same contract resolve to the same key and two different contracts never do.
- `resolve_contract()` resolves an EXPLICIT identity against a population.
  It never falls back to a wall midpoint, a nearest strike, or the first
  expiry. A miss is a miss, and it says which part of the identity failed.
- `quote_state()` reports source quote age and spread per leg, with an
  explicit unknown for any leg the source did not provide. A missing
  timestamp is unknown, never "fresh".
- `triad_request_scope()` records what the mounted Triad client actually
  requests, so the scope a consumer sees is not inferred from a label.

Nothing here calls a broker, and nothing here infers a side, a dealer
position, or a probability.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

IDENTITY_VERSION = "contract-identity.v1"

REASON_NO_POPULATION = "NO_POPULATION"
REASON_NO_MATCH = "NO_MATCH"
REASON_AMBIGUOUS = "AMBIGUOUS_MATCH"
REASON_IDENTITY_INCOMPLETE = "IDENTITY_INCOMPLETE"


def _exact(value: Any) -> Decimal | None:
    """Exact decimal identity for a numeric field. Booleans are not numbers."""
    if value is None or isinstance(value, bool):
        return None
    try:
        d = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError, TypeError):
        return None
    return d if d.is_finite() else None


def _norm_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def series_for(contract: dict[str, Any]) -> str | None:
    """Series identity when the source carries one; else derived from expiry.

    Only used as an ADDITIONAL discriminator. It never replaces OSI, because
    a derived series is weaker evidence than a provider-supplied one, and a
    wrong series is worse than an absent one.
    """
    supplied = _norm_str(contract.get("series") or contract.get("underlying"))
    if supplied:
        return supplied
    expiry = _norm_str(contract.get("expiry"))
    return expiry  # expiry-scoped series identity, explicitly derived


def contract_identity(contract: dict[str, Any] | None) -> dict[str, Any] | None:
    """Canonical identity for one contract row, or None if unusable.

    Returns {osi, strike, expiry, type, series}. `strike` is a string so the
    exact decimal survives JSON (100.25 must not become 100.25 -> 100.0 ->
    "100" somewhere downstream).
    """
    if not isinstance(contract, dict):
        return None
    strike = _exact(contract.get("strike_exact") if contract.get("strike_exact") is not None else contract.get("strike"))
    expiry = _norm_str(contract.get("expiry"))
    otype = _norm_str(contract.get("type") or contract.get("opt_type"))
    osi = _norm_str(contract.get("osi"))
    # An identity is usable when it is EITHER an OSI OR a complete
    # (strike, expiry, type) tuple. A bare strike is not an identity: it
    # names a wall region, not a contract, and resolving it would be the
    # midpoint guess this module exists to prevent.
    if osi is None and (strike is None or expiry is None or otype is None):
        return None
    return {
        "osi": osi,
        "strike": str(strike) if strike is not None else None,
        "expiry": expiry,
        "type": otype.lower() if otype else None,
        "series": series_for(contract),
    }


def _matches(identity: dict[str, Any], row_identity: dict[str, Any]) -> bool:
    """Identity equality: OSI when present, else the full tuple. No fuzzy match."""
    has_osi = identity.get("osi") is not None
    if has_osi and identity["osi"] != row_identity.get("osi"):
        return False
    for field in ("strike", "expiry", "type"):
        want, got = identity.get(field), row_identity.get(field)
        if want is None and has_osi:
            continue
        if want is None or got is None:
            return False
        if field == "strike":
            if _exact(want) != _exact(got):
                return False
        elif str(want).lower() != str(got).lower():
            return False
    return True


def _age_s(ts: Any, now: datetime) -> tuple[float | None, str | None]:
    if not ts:
        return None, "NO_TIMESTAMP"
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None, "UNPARSEABLE_TIMESTAMP"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    age = (now - dt).total_seconds()
    if age < 0:
        return age, "FUTURE"
    return age, None


def quote_state(contract: dict[str, Any] | None, *, now: datetime | None = None) -> dict[str, Any]:
    """Source quote age and spread for one contract. Unknown stays unknown."""
    now = now or datetime.now(UTC)
    out: dict[str, Any] = {
        "version": IDENTITY_VERSION,
        "bid": None, "ask": None, "last": None,
        "spread_absolute": None, "spread_percent": None, "spread_ticks": None,
        "mid": None, "stale": None,
        "ages_s": {"bid": None, "ask": None, "last": None},
        "age_reasons": {"bid": "NO_TIMESTAMP", "ask": "NO_TIMESTAMP", "last": "NO_TIMESTAMP"},
        "quote_source": None, "side_has_aggressor_identity": False,
        "timestamps": {"bid": None, "ask": None, "last": None},
        "freshness_reason": "NO_DECLARED_FRESHNESS_POLICY",
        "note": "last-vs-quote is not buyer-minus-seller flow; no aggressor identity",
    }
    if not isinstance(contract, dict):
        out["note"] = "no contract supplied"
        return out
    for leg, keys in (("bid", ("bid",)), ("ask", ("ask",)), ("last", ("last",))):
        for key in keys:
            raw = contract.get(key)
            if raw is None or isinstance(raw, bool):
                continue
            try:
                val = float(raw)
            except (TypeError, ValueError):
                continue
            if math.isfinite(val):
                out[leg] = val
                break
        ts = contract.get(f"{leg}_timestamp") or contract.get(f"{leg}_ts")
        out["timestamps"][leg] = str(ts) if ts else None
        age, reason = _age_s(ts, now)
        out["ages_s"][leg] = None if age is None else round(age, 3)
        out["age_reasons"][leg] = reason
    if out["bid"] is not None and out["ask"] is not None:
        out["mid"] = (out["ask"] + out["bid"]) / 2.0
        out["spread_absolute"] = out["ask"] - out["bid"]
        # Percent is relative to the mid, so mid must exist first. Computing
        # the percent before the mid made it permanently None.
        if out["mid"]:
            out["spread_percent"] = out["spread_absolute"] / out["mid"]
    if contract.get("quote_status") == "stale":
        out["stale"] = True
        out["freshness_reason"] = "SOURCE_DECLARED_STALE"
    elif any(out["age_reasons"][leg] for leg in ("bid", "ask")):
        out["freshness_reason"] = "SOURCE_TIME_UNKNOWN_OR_INVALID"
    out["quote_source"] = _norm_str(
        contract.get("data_source") or contract.get("quote_source") or contract.get("provider"))
    return out


def resolve_contract(
    contracts: list[dict[str, Any]] | None,
    identity: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Resolve ONE explicit contract identity against a population.

    Never substitutes a wall midpoint, a nearest strike, or the first
    expiry. A miss returns status unavailable with a reason; an ambiguous
    identity returns AMBIGUOUS_MATCH with the candidates rather than
    silently picking one.
    """
    now = now or datetime.now(UTC)
    want = contract_identity(identity) if identity else None
    base = {
        "version": IDENTITY_VERSION,
        "requested_identity": want,
        "quote": None,
        "matched_identity": None,
    }
    if want is None:
        return {**base, "status": "unavailable", "reason": REASON_IDENTITY_INCOMPLETE,
                "candidates": [],
                "note": "a contract cannot be resolved without an exact identity"}
    rows = [c for c in (contracts or []) if isinstance(c, dict)]
    if not rows:
        return {**base, "status": "unavailable", "reason": REASON_NO_POPULATION, "candidates": [],
                "note": "no contract population supplied"}

    hits = [c for c in rows if (ri := contract_identity(c)) and _matches(want, ri)]
    if not hits:
        return {**base, "status": "unavailable", "reason": REASON_NO_MATCH, "candidates": [],
                "note": "no contract in this population carries that exact identity; "
                        "the wall midpoint and first expiry are NOT substituted"}
    if len(hits) > 1:
        return {**base, "status": "unavailable", "reason": REASON_AMBIGUOUS, "candidates":
                sorted(str(contract_identity(c).get("osi")) for c in hits),
                "note": "identity is not unique in this population"}
    row = hits[0]
    multiplier = _exact(row.get("multiplier"))
    if multiplier is None or multiplier <= 0:
        multiplier_state = {"value": None, "source": None, "status": "unknown"}
    else:
        source = _norm_str(row.get("multiplier_source"))
        multiplier_state = {"value": str(multiplier), "source": source,
                            "status": ("registered_assumption" if source == "DEFAULT_STANDARD" else
                                                                   "observed" if source else "source_unknown")}
    return {**base, "status": "ok", "reason": None,
            "multiplier": multiplier_state,
            "matched_identity": contract_identity(row),
            "quote": quote_state(row, now=now),
            "n_population": len(rows), "n_matched": 1, "candidates": []}


# The mounted Triad client behaviour, recorded rather than inferred. These are
# FACTS about the current consumer, deliberately not aspirations: the design
# phase must not read `expiries=4` as "true 0DTE" or assume a refresh loop.
TRIAD_REQUESTED_EXPIRIES = 4
TRIAD_REQUEST_MODE = "day"


def triad_request_scope(
    *,
    mode: str = TRIAD_REQUEST_MODE,
    expiries: int = TRIAD_REQUESTED_EXPIRIES,
    refresh_interval_s: float | None = None,
) -> dict[str, Any]:
    """The scope a Triad consumer actually requested, with its limits stated.

    Records precisely that the mounted client requests a fixed
    mode=day / expiries=4 window on ticker change, that this is NOT a true
    0DTE request, and that there is no periodic refresh unless one is
    declared here. `window_basis` is disabled: window activity needs a
    comparable prior observation the client does not request.
    """
    return {
        "version": IDENTITY_VERSION,
        "mode": mode,
        "expiries_requested": expiries,
        "is_true_zero_dte": False,
        "zero_dte_note": "a fixed N-expiry window is not 0DTE; 0DTE would be a "
                         "same-session expiry request, which this scope is not",
        "refresh_interval_s": refresh_interval_s,
        "refreshes_periodically": refresh_interval_s is not None,
        "triggered_on": "ticker change",
        "window_basis_enabled": False,
        "window_basis_note": "window delta-volume activity requires a comparable prior "
                             "observation of the same scope; the mounted client does not "
                             "request one, so the surface is unavailable, not zero",
    }


__all__ = [
    "IDENTITY_VERSION",
    "REASON_NO_POPULATION",
    "REASON_NO_MATCH",
    "REASON_AMBIGUOUS",
    "REASON_IDENTITY_INCOMPLETE",
    "contract_identity",
    "quote_state",
    "resolve_contract",
    "series_for",
    "triad_request_scope",
    "TRIAD_REQUESTED_EXPIRIES",
    "TRIAD_REQUEST_MODE",
]
