"""Server-side Roll effective-spread service (Agent A9, institutional loop).

Faithful port of the frontend SHIP-7 engine (scanLogic.js rollSpread /
rollPooled / pushCapped), which itself implements Roll (1984, JF):
s = 2*sqrt(-cov(dP_t, dP_{t+1})), defined ONLY for negative
autocovariance; cov >= 0 truncates (spread 0, truncated=True) per ROLL-02.
Measures quoted-bounce + staleness on snapshots, NOT taker cost (ROLL-07).

Return shapes mirror the JS exactly so both languages agree:
  roll_spread(mids)    -> {spread|None, n, truncated}
  roll_pooled(rings)   -> {spread|None, n, nd, building, truncated}
Needs ~30+ deltas for a non-degenerate read (ROLL-05) — under that the
caller shows a building state, never a number.

Pure functions only — no network. The sweeper (Agent B) owns persisting
per-contract mid rings; this module only does the math.
"""

from __future__ import annotations

import math


def _clean(mids: object) -> list[float]:
    xs: list[float] = []
    for v in mids or []:  # type: ignore[union-attr]
        try:
            x = float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if math.isfinite(x) and x > 0:
            xs.append(x)
    return xs


def _spread_from_deltas(deltas: list[float]) -> tuple[float | None, bool]:
    """(spread, truncated) from a delta series. None spread = degenerate."""
    if len(deltas) < 2:
        return None, False
    mu = sum(deltas) / len(deltas)
    cov = sum((deltas[i] - mu) * (deltas[i + 1] - mu) for i in range(len(deltas) - 1))
    cov /= len(deltas) - 1
    if cov >= 0:
        return 0.0, True
    return 2.0 * math.sqrt(-cov), False


def roll_spread(mids: object) -> dict[str, object]:
    """Effective spread from one mid series. <3 mids -> spread None."""
    xs = _clean(mids)
    if len(xs) < 3:
        return {"spread": None, "n": len(xs), "truncated": False}
    deltas = [xs[i] - xs[i - 1] for i in range(1, len(xs))]
    spread, truncated = _spread_from_deltas(deltas)
    if spread is None:  # single delta: no autocovariance exists
        return {"spread": None, "n": len(xs), "truncated": False}
    return {"spread": spread, "n": len(xs), "truncated": truncated}


def push_capped(ring: list[float] | None, v: object, cap: int = 60) -> list[float]:
    """Capped push for per-contract mid rings. Non-positive never enters."""
    r = list(ring) if isinstance(ring, list) else []
    try:
        x = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return r[-cap:] if cap > 0 else r
    if math.isfinite(x) and x > 0:
        r.append(x)
    while len(r) > cap:
        r.pop(0)
    return r


def roll_pooled(rings: object) -> dict[str, object]:
    """Pooled Roll over an expiry/ticker bucket of mid rings.

    Deltas concatenated per-ring (one spurious joint adjacency per ring —
    negligible past ~30 deltas, documented not hidden). Under 30 deltas →
    building state, never a number.
    """
    deltas: list[float] = []
    n_mid = 0
    for ring in rings or []:  # type: ignore[union-attr]
        xs = _clean(ring)
        n_mid += len(xs)
        deltas.extend(xs[i] - xs[i - 1] for i in range(1, len(xs)))
    if len(deltas) < 30:
        return {"spread": None, "n": n_mid, "nd": len(deltas),
                "building": True, "truncated": False}
    spread, truncated = _spread_from_deltas(deltas)
    if spread is None:  # pragma: no cover - needs exactly-1-delta pool
        return {"spread": None, "n": n_mid, "nd": len(deltas),
                "building": False, "truncated": False}
    return {"spread": spread, "n": n_mid, "nd": len(deltas),
            "building": False, "truncated": truncated}


def roll_pooled_for(rings_by_key: dict[str, list[float]] | None) -> dict[str, object] | None:
    """Pool a {key: ring} map (e.g. one ticker's contracts) into one read.

    None when there are no rings at all (caller distinguishes "no data"
    from the building state).
    """
    if not rings_by_key:
        return None
    return roll_pooled(list(rings_by_key.values()))
