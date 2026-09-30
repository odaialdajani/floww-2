"""Solstice rank boundary — strict, fuse-once ranking for Solstice/Triad.

LEASE NOTE: routes/flowseeker.py (TideHunter, protected) owns
services.conviction_rank.rank_one/rank_many. This module never edits that
path. It is a narrowly versioned Solstice-scoped adapter that:

- shares the arithmetic kernel (WEIGHTS, tier cutoffs) with conviction_rank
  rather than inventing a second scoring engine;
- applies a STRICT typed input boundary: NaN/inf/bool are INVALID (never
  "ok"), missing is ABSENT, measured zero stays zero, and ML confidence 0
  stays 0 (never `or 0.5`);
- fuses ONCE: rows that already carry a fused score (numeric conviction +
  tier + evidence) are preserved with score/evidence intact and only
  re-sorted — never re-fused into a lower score with dropped evidence
  (R10-03: 55.5 must not become 24.0);
- keeps rank (a sorting key) distinct from calibrated probability: no
  output here is a win probability.

Version: solstice-rank.v1. Pure math, no I/O.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from typing import Any

from services.conviction_rank import WEIGHTS

RANK_VERSION = "solstice-rank.v1"
SCHEMA_VERSION = "solstice_rank.v1"

FUSED_MARKERS = ("tier", "evidence", "conviction")


def _num(value: Any) -> float | None:
    """Strict scalar: finite float, bools rejected, None stays None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def norm_flow_strict(flow: Any) -> tuple[float, str]:
    """Flow conviction 0-100 → 0-1. NaN/inf/bool → (0.0, invalid)."""
    if flow is None:
        return 0.0, "missing"
    raw = flow.get("conviction", flow.get("score")) if isinstance(flow, dict) else flow
    if raw is None:
        return 0.0, "missing"
    if isinstance(raw, bool):
        return 0.0, "invalid"
    v = _num(raw)
    if v is None:
        return 0.0, "invalid"
    return max(0.0, min(1.0, v / 100.0)), "ok"


def norm_opp_strict(opp: Any) -> tuple[float, str]:
    """Opportunity 0-10 → 0-1 with the same strict boundary."""
    if opp is None:
        return 0.0, "missing"
    raw = opp.get("opportunity_score", 0) if isinstance(opp, dict) else opp
    if isinstance(raw, bool):
        return 0.0, "invalid"
    v = _num(raw)
    if v is None:
        return 0.0, "invalid"
    return max(0.0, min(1.0, v / 10.0)), "ok"


def norm_conf_strict(conf: Any) -> tuple[float, str]:
    """Signed confluence total → magnitude 0-1. Bull/bear symmetric."""
    if conf is None:
        return 0.0, "missing"
    try:
        raw = conf.get("total", 0) if isinstance(conf, dict) else conf
    except AttributeError:
        return 0.0, "invalid"
    if raw is None or (isinstance(conf, dict) and not conf):
        return 0.0, "missing"
    if isinstance(raw, bool):
        return 0.0, "invalid"
    v = _num(raw)
    if v is None:
        return 0.0, "invalid"
    return max(0.0, min(1.0, abs(v) / 100.0)), "ok"


_ML_MAP = {
    "UP": 1.0, "BULLISH": 1.0, "BULL": 1.0,
    "HOLD": 0.5, "NEUTRAL": 0.5,
    "DOWN": 0.0, "BEARISH": 0.0, "BEAR": 0.0,
}


def norm_ml_strict(ml: Any) -> tuple[float, str]:
    """ML label+confidence → symmetric quality. Confidence 0 stays 0."""
    if ml is None:
        return 0.0, "missing"
    if isinstance(ml, dict):
        lab_raw = ml.get("prediction", ml.get("label", ml.get("direction")))
        if lab_raw is None:
            return 0.0, "missing"
        lab = str(lab_raw).upper()
        conf_raw = ml.get("confidence", 0.5)
        if conf_raw is None:
            return 0.0, "missing"
        if isinstance(conf_raw, bool):
            return 0.0, "invalid"
        conf = _num(conf_raw)
        if conf is None:
            return 0.0, "invalid"
    else:
        if isinstance(ml, bool):
            return 0.0, "invalid"
        lab = str(ml).upper()
        conf = 0.75
    base = _ML_MAP.get(lab)
    if base is None:
        return 0.0, "invalid"
    neutral = 0.5
    w = max(0.0, min(1.0, conf))
    return max(0.0, min(1.0, abs(base - neutral) * (0.5 + 0.5 * w))), "ok"


def is_fused_row(row: Any) -> bool:
    """A row already carrying a fused score: numeric conviction + tier + evidence."""
    if not isinstance(row, dict):
        return False
    conv = row.get("conviction")
    return (
        isinstance(conv, (int, float))
        and not isinstance(conv, bool)
        and math.isfinite(conv)
        and isinstance(row.get("tier"), str)
        and isinstance(row.get("evidence"), dict)
    )


def _validate_weights(override: dict[str, Any] | None) -> tuple[dict[str, float], bool]:
    """Validate a caller weight override. Returns (weights, was_normalized).

    Resweep: the override used to be merged blindly. A string weight raised
    a TypeError deep in the arithmetic; a negative weight could drive the
    score outside [0, 100]; and an override that does not sum to 1
    silently rescaled every score while still reporting a 0-100-looking
    number. A weight vector that does not sum to 1 is now NORMALIZED and
    the fact is reported, so the scale is never a surprise. Non-finite,
    negative and boolean weights are rejected outright: a bad weight is a
    caller bug, not a measurement.
    """
    w = dict(WEIGHTS)
    if not override:
        return w, False
    for key, value in override.items():
        if key not in w:
            raise ValueError(f"unknown weight {key!r}; weights are {sorted(w)}")
        if isinstance(value, bool) or value is None:
            raise ValueError(f"weight {key!r} must be a finite non-negative number")
        try:
            num = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"weight {key!r} must be a finite non-negative number") from None
        if not math.isfinite(num) or num < 0:
            raise ValueError(f"weight {key!r} must be a finite non-negative number")
        w[key] = num
    total = sum(w.values())
    if total <= 0:
        raise ValueError("weight override must leave a positive total")
    if not math.isclose(total, 1.0, rel_tol=1e-9):
        w = {k: v / total for k, v in w.items()}
        return w, True
    return w, False


def fuse_one(
    ticker: str,
    *,
    flow: Any = None,
    opportunity: Any = None,
    confluence: Any = None,
    ml: Any = None,
    snapshot_id: str | None = None,
    asof: Any = None,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Fuse raw scorer payloads once. Same kernel as conviction_rank.rank_one."""
    w, normalized = _validate_weights(weights)
    fn, fs = norm_flow_strict(flow)
    on, os_ = norm_opp_strict(opportunity)
    cn, cs = norm_conf_strict(confluence)
    mn, ms = norm_ml_strict(ml)
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
        direction = "NEUTRAL"
    return {
        "ticker": str(ticker or "").upper(),
        "conviction": conviction,
        "tier": tier,
        "direction": direction,
        "snapshot_id": snapshot_id,
        "asof": asof,
        "evidence": {
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
            "weights_normalized": normalized,
            "rank_version": RANK_VERSION,
        },
        "schema_version": SCHEMA_VERSION,
        "rank_version": RANK_VERSION,
    }


def rank_rows(rows: list[dict[str, Any]] | None, **kw: Any) -> list[dict[str, Any]]:
    """Rank a mixed batch: fused rows preserved, raw rows fused once.

    A fused row keeps its score, tier, direction and evidence; only its
    rank position is assigned. Raw rows (scorer payloads under
    flow/opportunity/confluence/ml keys) are fused exactly once. Sorting
    is by conviction DESC, ticker ASC for stability.
    """
    out: list[dict[str, Any]] = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        if is_fused_row(r):
            kept = dict(r)
            kept.setdefault("rank_version", RANK_VERSION)
            out.append(kept)
            continue
        out.append(
            fuse_one(
                r.get("ticker"),
                flow=r.get("flow"),
                opportunity=r.get("opportunity"),
                confluence=r.get("confluence"),
                ml=r.get("ml"),
                snapshot_id=r.get("snapshot_id"),
                asof=r.get("asof"),
                **kw,
            )
        )
    out.sort(key=lambda x: (-x["conviction"], x["ticker"]))
    for i, x in enumerate(out, 1):
        x["rank"] = i
    return out


def scan_cache_key(
    *,
    universe: str,
    tickers: list[str] | tuple[str, ...],
    scope: dict[str, Any] | None = None,
    provider: str = "public_api",
    formula: str = "gex.v2",
    extra: dict[str, Any] | None = None,
) -> str:
    """Stable cache identity for one Solstice scan sweep.

    Keys the FULL relevant scope (universe, ordered tickers, dte/expiries/
    session scope, provider, formula version). Two sweeps that differ in any
    of these never share a cache entry (R10-05 class defect).
    """
    import hashlib
    import json

    body = {
        "universe": universe,
        "tickers": sorted(str(t).upper() for t in tickers),
        "scope": scope or {},
        "provider": provider,
        "formula": formula,
        "extra": extra or {},
        "rank_version": RANK_VERSION,
    }
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:24]
    return f"solstice-scan:{digest}"


class KeyedScanCache:
    """TTL cache with per-key single-flight (S6, Solstice-scoped).

    Identical concurrent requests share one computation; incompatible
    scopes never collide because the KEY carries the scope. Cached reads
    do not reset source age: entries store cached_at and the payload's own
    source fields separately, and hits return them unchanged.

    BOUNDED. The scope key has several dimensions (universe, tickers, dte,
    expiries, mode, scalp, provider, formula), so an unbounded map leaks in
    a long-lived process: 500 distinct scopes produced 500 entries and 500
    per-key locks, and expired entries were never reclaimed. This evicts the
    oldest-expired entries on write and caps the total, so memory is O(1) in
    the number of DISTINCT scopes ever seen rather than O(all scopes).
    Eviction drops a CACHE ENTRY only; it never invents or recomputes a
    value, so a dropped scope simply recomputes on next request.
    """

    def __init__(self, ttl_s: float = 300.0, max_entries: int = 256):
        self._ttl = ttl_s
        self._max_entries = max_entries
        self._entries: dict[str, dict[str, Any]] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._async_locks: dict[str, Any] = {}
        self._meta = threading.Lock()
        self.evictions = 0

    def _evict_locked(self) -> None:
        """Drop expired entries first, then the oldest, down to the cap."""
        if self._max_entries <= 0 or len(self._entries) <= self._max_entries:
            return
        now = time.time()
        expired = [k for k, e in self._entries.items() if now - e["cached_at"] > self._ttl]
        for k in expired:
            self._entries.pop(k, None)
        self.evictions += len(expired)
        overflow = len(self._entries) - self._max_entries
        if overflow > 0:
            oldest = sorted(self._entries.items(), key=lambda kv: kv[1]["cached_at"])
            for k, _e in oldest[:overflow]:
                self._entries.pop(k, None)
                self.evictions += 1
        # Per-key locks are pure synchronization scaffolding: dropping one
        # that no cache entry references cannot change a returned value.
        for k in [k for k in self._locks if k not in self._entries]:
            self._locks.pop(k, None)
        for k in [k for k in self._async_locks if k not in self._entries]:
            self._async_locks.pop(k, None)

    def _store(self, key: str, payload: dict[str, Any]) -> dict[str, Any]:
        # A result that reports itself unavailable is NOT cached. Caching a
        # failure turns one provider blip into a TTL-long outage: every
        # caller inside the window would be served the error without the
        # sweep ever being retried. Availability is re-attempted next call;
        # the caller is never handed a stale failure.
        if payload.get("status") == "unavailable":
            out = dict(payload)
            out["cache"] = "miss"
            out["cached_at"] = None
            out["cache_note"] = "unavailable results are not cached; the next call retries"
            return out
        with self._meta:
            self._entries[key] = {"cached_at": time.time(), "payload": dict(payload)}
            self._evict_locked()
        out = dict(payload)
        out["cache"] = "miss"
        out["cached_at"] = self._entries[key]["cached_at"] if key in self._entries else None
        return out

    def _lock_for(self, key: str) -> threading.Lock:
        with self._meta:
            return self._locks.setdefault(key, threading.Lock())

    def get(self, key: str) -> dict[str, Any] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if time.time() - entry["cached_at"] > self._ttl:
            return None
        out = dict(entry["payload"])
        # A hit reports WHEN IT WAS CACHED, so a consumer can never read a
        # fresh timestamp off a stale payload. Source age is unchanged.
        out["cached_at"] = entry["cached_at"]
        return out

    def get_or_compute(self, key: str, compute: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        hit = self.get(key)
        if hit is not None:
            out = dict(hit)
            out["cache"] = "hit"
            return out
        with self._lock_for(key):
            hit = self.get(key)
            if hit is not None:
                out = dict(hit)
                out["cache"] = "hit"
                return out
            return self._store(key, compute())

    def invalidate(self, key: str) -> None:
        with self._meta:
            self._entries.pop(key, None)

    async def get_or_compute_async(self, key: str, compute: Callable[[], Any]) -> dict[str, Any]:
        """Async single-flight. Identical concurrent scopes share one call.

        Uses an asyncio lock PER KEY, so two different scopes never serialize
        against each other while two identical ones never both compute.
        """
        hit = self.get(key)
        if hit is not None:
            out = dict(hit)
            out["cache"] = "hit"
            return out
        lock = self._async_lock_for(key)
        async with lock:
            hit = self.get(key)
            if hit is not None:
                out = dict(hit)
                out["cache"] = "hit"
                return out
            return self._store(key, await compute())

    def _async_lock_for(self, key: str) -> Any:
        import asyncio

        with self._meta:
            return self._async_locks.setdefault(key, asyncio.Lock())


__all__ = [
    "RANK_VERSION",
    "SCHEMA_VERSION",
    "norm_flow_strict",
    "norm_opp_strict",
    "norm_conf_strict",
    "norm_ml_strict",
    "is_fused_row",
    "fuse_one",
    "rank_rows",
    "scan_cache_key",
    "KeyedScanCache",
]
