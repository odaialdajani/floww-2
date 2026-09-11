"""
backend/services/contract_validators.py — Agent D (D3 data-contract
enforcement).

Provider-boundary validators for the Public/cvserver/bars ingress paths.
Malformed payloads are quarantined with counters — validators NEVER raise
into callers. Reasons are short snake_case codes (bounded cardinality for
the Prometheus `quarantine_total{source,reason}` counter); details ride in
the quarantine store, not the metric labels.
"""
from __future__ import annotations

import math
from collections import Counter, deque
from collections.abc import Callable
from datetime import date
from typing import Any

BAR_KEYS = ("t", "o", "h", "l", "c", "v")


def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _finite(x: Any) -> bool:
    return _is_num(x) and not (math.isnan(x) or math.isinf(x))


def validate_bar(bar: Any) -> tuple[bool, str | None]:
    """OHLCV invariant check for one 1-min/daily candle (C13 bars shape)."""
    if not isinstance(bar, dict):
        return False, "not_a_dict"
    for k in BAR_KEYS:
        if k not in bar:
            return False, f"missing_key:{k}"
    o, h, lo, c, v = (bar["o"], bar["h"], bar["l"], bar["c"], bar["v"])
    for k, x in (("o", o), ("h", h), ("l", lo), ("c", c)):
        if not _finite(x):
            return False, f"non_finite:{k}"
    if h < lo:
        return False, "high_below_low"
    if o > h:
        return False, "open_above_high"
    if o < lo:
        return False, "open_below_low"
    if c > h:
        return False, "close_above_high"
    if c < lo:
        return False, "close_below_low"
    if not _is_num(v) or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return False, "bad_volume"
    if v < 0:
        return False, "negative_volume"
    return True, None


def validate_chain_row(row: Any) -> tuple[bool, str | None]:
    """10-col positional scan row (CONTRACTS C1)."""
    if not isinstance(row, list) or len(row) != 10:
        return False, "wrong_length"
    under, _occ, typ, strike, exp, vol, oi, iv, delta, spot = row
    if not isinstance(under, str) or not under:
        return False, "bad_underlying"
    if typ not in ("call", "put"):
        return False, "bad_type"
    if not _finite(strike) or strike <= 0:
        return False, "bad_strike"
    try:
        date.fromisoformat(str(exp))
    except (ValueError, TypeError):
        return False, "bad_expiry"
    if not _is_num(vol) or vol < 0:
        return False, "bad_volume"
    if not _is_num(oi) or oi < 0:
        return False, "bad_oi"
    if not _finite(iv):
        return False, "bad_iv"
    if not _finite(delta):
        return False, "bad_delta"
    if not _finite(spot) or spot <= 0:
        return False, "bad_spot"
    return True, None


def validate_quote(q: Any) -> tuple[bool, str | None]:
    """NBBO quote check. One-sided (None) = unknown, not malformed."""
    if not isinstance(q, dict):
        return False, "not_a_dict"
    px: dict[str, Any] = {}
    for k in ("bid", "ask", "last"):
        x = q.get(k)
        if x is None:
            continue
        if not _finite(x):
            return False, f"non_finite:{k}"
        if x < 0:
            return False, f"negative_{k}"
        px[k] = x
    if "bid" in px and "ask" in px and px["bid"] > px["ask"]:
        return False, "crossed_bid_ask"
    return True, None


Validator = Callable[[Any], tuple[bool, str | None]]


class Quarantine:
    """Bounded violator store + per-source counters. submit() never raises."""

    def __init__(self, max_items: int = 500):
        self._items: deque[dict] = deque(maxlen=max_items)
        self._counts: Counter[str] = Counter()

    def submit(self, source: str, payload: Any, reason: str) -> None:
        try:
            try:
                kept: Any = (
                    payload
                    if isinstance(payload, (str, int, float, bool, type(None)))
                    else repr(payload)[:500]
                )
            except Exception:
                kept = "<unrepresentable>"
            self._items.append({"source": source, "reason": reason, "payload": kept})
            self._counts[source] += 1
            try:
                from services.observability import quarantine_total

                quarantine_total.labels(source=source, reason=reason).inc()
            except Exception:
                pass  # metrics must never break the quarantine path
        except Exception:
            pass  # quarantine itself never raises

    def items(self) -> list[dict]:
        return list(self._items)

    def counts(self) -> dict[str, int]:
        return dict(self._counts)


def validate_batch(
    source: str,
    items: list[Any],
    validator: Validator,
    quarantine: Quarantine | None = None,
) -> tuple[list[Any], int]:
    """Split a batch into (valid, n_quarantined). Never raises on items."""
    valid: list[Any] = []
    n_bad = 0
    for it in items:
        try:
            ok, reason = validator(it)
        except Exception as e:  # validator bug must not kill the batch
            ok, reason = False, f"validator_error:{type(e).__name__}"
        if ok:
            valid.append(it)
        else:
            n_bad += 1
            if quarantine is not None:
                quarantine.submit(source, it, reason or "unknown")
    return valid, n_bad
