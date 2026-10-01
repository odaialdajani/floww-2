"""
backend/services/solstice_scan.py — Solstice scan coordinator (S6).

A NARROWLY VERSIONED orchestrator over the EXISTING public primitives. It
owns no provider client, starts no poller, and duplicates no scoring engine:

- prefilter/rotation : services.universe_scan.prefilter_universe (the #86
  truncation repair is preserved by delegating, never re-implemented)
- budget/quota       : services.public_budget via universe_scan.scan_batch
- chain/heatmap      : server.build_heatmap, injected (unit-testable)
- ranking            : services.solstice_rank (fuse-once, strict inputs)
- cache              : services.solstice_rank.KeyedScanCache, keyed by the
  FULL scope, with per-key single flight

LEGACY / PROTECTED
==================
`routes/flowseeker.py` (TideHunterPro) is read-only. This coordinator is a
separate entry point. It does not mutate the legacy cache, cursor, budget
object or leaderboard table, and the legacy endpoint's behaviour is
unchanged by anything here. Two different caches can hold two different
scopes without interfering, which is exactly why the legacy global cache can
keep its (defective) behaviour while the Solstice path is correct.

ROTATION
========
Rotation is stable and round-robin over the ordered prefilter output, with
an explicit checkpoint so a resumed sweep continues where it stopped.
Priorities may reorder the queue, but the cursor is advanced by the number
of tickers actually taken, so a priority change cannot silently re-scan the
head of the universe and starve the tail.

CANCELLATION
============
Every sweep is cancellable. A cancelled sweep returns a partial result with
an explicit `cancelled` flag and keeps the rows it did measure: a
cancelled sweep is not an error and does not manufacture rows.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from services.solstice_rank import KeyedScanCache, rank_rows, scan_cache_key

COORDINATOR_VERSION = "solstice-scan.v1"
SCHEMA_VERSION = "solstice_scan.v1"

# Module-level cache + cursor for THIS coordinator only. Never shared with
# the legacy flowseeker cache (separate objects, separate keys).
_CACHE = KeyedScanCache(ttl_s=300.0)
_CURSOR: dict[str, int] = {}
_CURSOR_LOCK = asyncio.Lock()

REASON_OPTIONABILITY_UNKNOWN = "OPTIONABILITY_UNKNOWN"
REASON_ENTITLEMENT_UNVERIFIED = "ENTITLEMENT_UNVERIFIED"


def cache_key_for(tickers, *, universe: str, dte: int | None, max_expiries: int,
                  provider: str = "public_api", formula: str = "gex.v2",
                  mode: str = "day", scalp: int | None = None, limit: int | None = None) -> str:
    """The full sweep identity. Two sweeps differing in ANY of these are
    different entries — the legacy single-payload cache defect (dte /
    max_expiries ignored) cannot occur here."""
    return scan_cache_key(
        universe=universe,
        tickers=list(tickers or []),
        scope={"dte": dte, "max_expiries": max_expiries, "mode": mode, "scalp": scalp, "limit": limit},
        provider=provider,
        formula=formula,
    )


def next_slice(ordered: list[str], cursor: int, take: int) -> tuple[list[str], int]:
    """Stable round-robin slice + the next cursor. Pure, so it is testable.

    `ordered` is the canonical prefilter order. Returns the tickers taken
    and the cursor to persist. A caller that resumes with the returned
    cursor continues where this sweep stopped.
    """
    n = len(ordered)
    if n == 0 or take <= 0:
        return [], cursor
    start = cursor % n
    count = min(take, n)
    batch = [ordered[(start + k) % n] for k in range(count)]
    return batch, (start + count) % n


async def _advance_cursor(scope: str, to: int) -> None:
    async with _CURSOR_LOCK:
        _CURSOR[scope] = to


async def cursor_for(scope: str) -> int:
    async with _CURSOR_LOCK:
        return _CURSOR.get(scope, 0)


async def run_scan(
    *,
    universe: str = "popular",
    limit: int = 20,
    dte: int | None = None,
    max_expiries: int = 2,
    refresh: bool = False,
    movers: dict[str, float] | None = None,
    prior: dict[str, float] | None = None,
    flow_alert_tickers: set[str] | None = None,
    build_heatmap_fn=None,
    opportunity_fn=None,
    conviction_fn=None,
    scan_cancelled: asyncio.Event | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Run one Solstice sweep through the existing primitives.

    Returns the leaderboard rows plus the scope identity, coverage, cursor
    checkpoint and cache status. Injected `build_heatmap_fn` /
    `opportunity_fn` keep it unit-testable without a provider.
    """
    from services.movers import POPULAR_UNIVERSE
    from services.universe_scan import prefilter_universe, scan_batch

    universe_names = list(POPULAR_UNIVERSE) if universe == "popular" else [universe]
    pre = prefilter_universe(
        universe_names,
        movers=movers or {},
        prior=prior or {},
        flow_alert_tickers=flow_alert_tickers or set(),
        limit=limit,
    )
    ordered = [r["ticker"] for r in pre["ordered"]]
    key = cache_key_for(ordered, universe=universe, dte=dte, max_expiries=max_expiries, limit=limit)
    scope = key

    async def _compute() -> dict[str, Any]:
        try:
            return await _compute_inner()
        except Exception as exc:  # noqa: BLE001 - a sweep failure is a result, not a crash
            # Resweep: a provider/budget failure used to propagate raw, so a
            # caller behind a route would 500 instead of learning that the
            # sweep produced nothing. It is still an unavailable SWEEP: the
            # cursor is NOT advanced (nothing was measured), and no budget
            # is granted by the failure. The reason names the exception type
            # and the message; the traceback is not carried into a response.
            return {
                "schema_version": SCHEMA_VERSION,
                "coordinator_version": COORDINATOR_VERSION,
                "scope": _scope_block(universe, dte, max_expiries, []),
                "rows": [],
                "coverage": {"requested": 0, "returned": 0, "usable": 0, "skipped": [],
                             "cancelled": False,
                             "error": f"{type(exc).__name__}: {exc}"},
                "cursor": {"scope": scope, "position": await cursor_for(scope),
                           "advanced": False,
                           "note": "a failed sweep advances nothing; nothing was measured"},
                "status": "unavailable",
                "reason": "SWEEP_FAILED",
                "prefilter": None,
                "computed_at": _iso(now),
            }

    async def _compute_inner() -> dict[str, Any]:
        batch, next_cursor = next_slice(ordered, await cursor_for(scope), limit)
        if not batch:
            return {
                "schema_version": SCHEMA_VERSION,
                "coordinator_version": COORDINATOR_VERSION,
                "scope": _scope_block(universe, dte, max_expiries, ordered),
                "rows": [],
                "coverage": {"requested": 0, "returned": 0, "usable": 0,
                             "skipped": [], "cancelled": False},
                "cursor": {"scope": scope, "position": next_cursor, "complete": True},
                "prefilter": pre,
                "computed_at": _iso(now),
            }
        cancelled = bool(scan_cancelled and scan_cancelled.is_set())
        if cancelled:
            await _advance_cursor(scope, next_cursor)
            return {
                "schema_version": SCHEMA_VERSION,
                "coordinator_version": COORDINATOR_VERSION,
                "scope": _scope_block(universe, dte, max_expiries, ordered),
                "rows": [],
                "coverage": {"requested": 0, "returned": 0, "usable": 0, "skipped": [],
                             "cancelled": True,
                             "note": "cancelled before the sweep began; cursor advanced "
                                     "to the persisted checkpoint"},
                "cursor": {"scope": scope, "position": next_cursor, "complete": False},
                "prefilter": pre,
                "computed_at": _iso(now),
            }

        swept = await scan_batch(
            batch,
            build_heatmap_fn=build_heatmap_fn,
            opportunity_fn=opportunity_fn,
            conviction_fn=conviction_fn,
            max_expiries=max_expiries,
            dte=dte,
            pace_sec=0.0,
        )
        # Fuse ONCE through the Solstice boundary. A row that already carries
        # a fused score is passed through intact (rank_rows preserves its
        # score, tier, direction and evidence); a row carrying raw scorer
        # payloads is fused here exactly once.
        ranked = rank_rows([_rank_input(r) for r in (swept.get("rows") or [])])
        availability = []
        rows = []
        for row in ranked:
            evidence = row.get("evidence") or {}
            eligible = any(evidence.get(f"{name}_status") == "ok" for name in ("flow", "opportunity", "confluence", "ml"))
            availability.append({"ticker": row.get("ticker"), "status": "usable" if eligible else "unavailable",
                                 "reason": None if eligible else "NO_RANK_INPUTS",
                                 "asof": row.get("asof"), "inputs": evidence})
            if eligible:
                rows.append(row)
        for i, row in enumerate(rows, 1):
            row["rank"] = i
        skipped = swept.get("skipped") or []
        availability.extend({**r, "status": "unavailable"} for r in skipped)
        status = ("partial-budget" if any("BUDGET" in str(r.get("reason")) for r in skipped) else
                  "source-error" if skipped and not rows else "partial" if skipped else
                  "ready" if rows else "no-eligible-rows")
        await _advance_cursor(scope, next_cursor)
        return {
            "schema_version": SCHEMA_VERSION,
            "coordinator_version": COORDINATOR_VERSION,
            "scope": _scope_block(universe, dte, max_expiries, ordered),
            "rows": rows,
            "availability": availability,
            "status": status,
            "coverage": {
                "requested": len(batch),
                "returned": len(swept.get("rows") or []),
                "usable": sum(1 for r in rows if r.get("conviction") is not None),
                "skipped": swept.get("skipped") or [],
                "cancelled": False,
                "note": "budget-unaffordable tickers are skipped with a reason; "
                        "no exception grants additional budget",
            },
            "cursor": {"scope": scope, "position": next_cursor,
                       "complete": len(batch) < len(ordered)},
            "prefilter": pre,
            "computed_at": _iso(now),
        }

    if refresh:
        _CACHE.invalidate(key)
    out = await _CACHE.get_or_compute_async(key, _compute)
    out["cache"] = out.get("cache", "hit")
    # The rotation checkpoint is a property of THIS process, not of the
    # cached payload. A cache hit returns rows computed earlier; reporting
    # that payload's cursor would hand the caller a checkpoint from the
    # past and let two callers believe they advanced the same slice. The
    # live cursor is reported alongside, and the payload's own is labelled.
    live_cursor = await cursor_for(scope)
    cached_cursor = (out.get("cursor") or {}).get("position")
    out["cursor"] = {
        "scope": scope,
        "position": live_cursor,
        "payload_position": cached_cursor,
        "cursor_stale": cached_cursor is not None and cached_cursor != live_cursor,
        "advanced": (out.get("cursor") or {}).get("advanced", True),
        "note": "position is the live rotation checkpoint; payload_position is "
                "the checkpoint captured when these rows were computed",
    }
    return out


def _rank_input(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize one scanned row into a rank_rows input.

    An already-fused row (numeric conviction + tier + evidence) is returned
    UNTOUCHED so its score and evidence survive. Only a row with raw scorer
    payloads is reshaped into the fuser's keyword form; its raw `conviction`
    blob is passed as `flow` only when it is unambiguously a scorer payload,
    never when it is fused output.
    """
    from services.solstice_rank import is_fused_row

    if is_fused_row(row):
        return dict(row)
    out = {
        "ticker": row.get("ticker"),
        "flow": row.get("flow"),
        "opportunity": row.get("opportunity"),
        "confluence": row.get("confluence"),
        "ml": row.get("ml"),
        "snapshot_id": row.get("snapshot_id"),
        "asof": row.get("asof"),
    }
    conv = row.get("conviction")
    if out["flow"] is None and isinstance(conv, dict) and ("conviction" in conv or "score" in conv):
        out["flow"] = conv
    return out


def _scope_block(universe, dte, max_expiries, ordered) -> dict[str, Any]:
    return {
        "universe": universe,
        "dte": dte,
        "max_expiries": max_expiries,
        "formula_version": "gex.v2",
        "provider": "public_api",
        "n_candidates": len(ordered),
        "ordered_symbols": list(ordered),
        "mode": "day", "scalp": None,
    }


def _iso(now: float | None) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(now if now is not None else time.time(), tz=UTC).isoformat()


def peek_scan(*, universe: str = "popular", limit: int = 20, dte: int | None = None,
              max_expiries: int = 2) -> dict[str, Any]:
    """Copy-only read of this process' exact scan scope; never builds or debits."""
    from services.movers import POPULAR_UNIVERSE
    from services.universe_scan import prefilter_universe

    names = list(POPULAR_UNIVERSE) if universe == "popular" else [universe]
    pre = prefilter_universe(names, limit=limit)
    ordered = [r["ticker"] for r in pre["ordered"]]
    key = cache_key_for(ordered, universe=universe, dte=dte, max_expiries=max_expiries, limit=limit)
    out = _CACHE.get(key, allow_stale=True)
    if out is None:
        return {"schema_version": SCHEMA_VERSION, "status": "not-scanned", "rows": [],
                "scope": _scope_block(universe, dte, max_expiries, ordered),
                "availability": pre["excluded"], "computed_at": None,
                "durability": "process_memory_only"}
    out["cache"] = "hit"
    if time.time() - out["cached_at"] > 300:
        out["status"] = "stale"
    out["durability"] = "process_memory_only"
    return out


def health() -> dict[str, Any]:
    """Coordinator health. Cache state only; no provider state is claimed."""
    return {
        "coordinator_version": COORDINATOR_VERSION,
        "cursors": dict(_CURSOR),
        "note": "the legacy flowseeker cache/cursor are separate objects and are "
                "not read or written here",
    }


__all__ = [
    "COORDINATOR_VERSION",
    "SCHEMA_VERSION",
    "cache_key_for",
    "next_slice",
    "cursor_for",
    "run_scan",
    "health",
]
