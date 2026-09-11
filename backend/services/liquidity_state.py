"""Per-ticker Kyle/Amihud liquidity regime state (Agent-2 H2 follow-up).

Mirrors the VPIN registry pattern (routes/vpin.py): snapshot-fed stateful
estimators behind a read-only snapshot seam. Uses the TESTED snapshot-API
estimators (services/kyle_lambda, services/amihud_illiquidity) — NOT the
trade-level liquidity_metrics variants (different feed granularity; see
receipt on consolidation).

- feed() is called once per chain snapshot (warm path) with call/put
  volumes + spot. Never raises.
- snapshot() is read-only: unknown tickers yield None WITHOUT creating
  engines (no registry growth from scans).
"""
from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

MIN_OBS = 20  # both estimators default window=20; fewer = still warming

_regime: dict[str, dict[str, Any]] = {}


def _pair(ticker: str):
    entry = _regime.get(ticker)
    if entry is None:
        from services.amihud_illiquidity import AmihudIlliquidity
        from services.kyle_lambda import KylesLambda
        entry = {"kyle": KylesLambda(), "amihud": AmihudIlliquidity(),
                 "last": None}
        _regime[ticker] = entry
    return entry


def feed(ticker: str, call_vol: float, put_vol: float, spot: float) -> None:
    """Record one chain snapshot for a ticker. Never raises.

    Chain volumes are cumulative day totals, but the estimators consume
    per-interval flow. Differencing happens here: the first snapshot per
    ticker seeds the baseline (no push — there is no interval yet), later
    snapshots push max(0, cur - last). Resets (new day) clamp to zero and
    the estimators' own guards skip zero-volume pushes.
    """
    try:
        sym = (ticker or "").strip().upper()
        if not sym:
            return
        try:
            cur = (float(call_vol or 0.0), float(put_vol or 0.0))
        except (TypeError, ValueError):
            return
        if not all(math.isfinite(v) and v >= 0.0 for v in cur):
            return
        pair = _pair(sym)
        last = pair.get("last")
        pair["last"] = cur
        if last is None:
            return
        dcall = max(0.0, cur[0] - last[0])
        dput = max(0.0, cur[1] - last[1])
        pair["kyle"].push_snapshot(dcall, dput, spot)
        pair["amihud"].push_snapshot(dcall, dput, spot)
    except Exception as e:
        logger.debug("liquidity feed skipped for %s: %s", ticker, e)


def snapshot(ticker: str) -> dict[str, Any] | None:
    """Read-only regime snapshot or None when unknown/cold. Never raises,
    never creates engines."""
    try:
        sym = (ticker or "").strip().upper()
        if not sym:
            return None
        entry = _regime.get(sym)
        if entry is None:
            return None
        kyle = entry["kyle"].compute()
        amihud = entry["amihud"].compute()
        if bool(kyle.get("is_warming")) or bool(amihud.get("is_warming")):
            return None
        return {"kyle_label": str(kyle.get("label") or ""),
                "amihud_label": str(amihud.get("label") or ""),
                "n_obs": int(kyle.get("n_obs") or 0)}
    except Exception:
        return None


def reset() -> None:
    """Test isolation only — production never calls this."""
    _regime.clear()
