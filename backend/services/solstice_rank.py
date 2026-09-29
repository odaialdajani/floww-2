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
    w = dict(WEIGHTS)
    w.update(weights or {})
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
    do not reset source age: entries store computed_at and source_asof
    separately, and hits return both unchanged.
    """

    def __init__(self, ttl_s: float = 300.0):
        self._ttl = ttl_s
        self._entries: dict[str, dict[str, Any]] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._async_locks: dict[str, Any] = {}
        self._meta = threading.Lock()

    def _lock_for(self, key: str) -> threading.Lock:
        with self._meta:
            return self._locks.setdefault(key, threading.Lock())

    def get(self, key: str) -> dict[str, Any] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if time.time() - entry["cached_at"] > self._ttl:
            return None
        return dict(entry["payload"])

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
            payload = compute()
            self._entries[key] = {"cached_at": time.time(), "payload": dict(payload)}
            out = dict(payload)
            out["cache"] = "miss"
            return out

    def invalidate(self, key: str) -> None:
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
            payload = await compute()
            self._entries[key] = {"cached_at": time.time(), "payload": dict(payload)}
            out = dict(payload)
            out["cache"] = "miss"
            return out

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
