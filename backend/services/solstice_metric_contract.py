"""R11-H01 — Solstice metric display contract (summary layer, no arithmetic).

This module never computes exposure. It reads the sections the canonical
kernels already produced (`domain.exposure_metrics`, `services.gex_core`,
`services.solstice_window`) and publishes:

  * `surface_coverage` — one entry per displayable surface with its registry
    metric id, basis, formula version, population counts and a three-state
    status (ok / partial / unavailable). A surface with missing inputs is
    PARTIAL, never "ok"; a surface with no usable input is UNAVAILABLE with a
    reason, never zero.
  * `window_grid_section` — the governed window surface re-keyed into the
    same `{expiry: {strikeKey: value}}` shape as every other grid, or an
    explicit unavailable section. A refused window never falls back to raw.

Field paths are documented in docs/solstice/r11/METRIC_CONTRACT.md.
"""
from __future__ import annotations

import math
from typing import Any

CONTRACT_VERSION = "solstice-metric-contract.v1"


def _count(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _strike_key(strike: Any) -> str | None:
    if strike is None or isinstance(strike, bool):
        return None
    try:
        f = float(strike)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f) or f <= 0:
        return None
    return str(int(f)) if f.is_integer() else str(f)


def _status(usable: int | None, excluded: int, section_status: str | None = None) -> str:
    if section_status == "unavailable" or not usable:
        return "unavailable"
    return "partial" if excluded > 0 else "ok"


def window_grid_section(window: dict[str, Any] | None) -> dict[str, Any]:
    """Grid-shaped window section from a `window_activity_surface` packet."""
    base = {
        "exposure_basis": "VOLUME_WINDOW",
        "metric_id": "window_dadgex_v1",
        "formula_version": "gex.v2",
        "greek_convention": (window or {}).get("greek_convention"),
        "interval": (window or {}).get("interval"),
        "provenance_note": (window or {}).get("provenance_note"),
    }
    if not window or window.get("status") != "ok":
        return {**base, "status": "unavailable",
                "reason": (window or {}).get("reason") or "HISTORY_NOT_YET_RECORDED",
                "grid": None, "expiries": [], "strikes": [], "usable": 0}
    grid: dict[str, dict[str, float]] = {}
    strikes: set[float] = set()
    for cell in (window.get("surface") or {}).get("cells") or []:
        if not isinstance(cell, dict):
            continue
        key = _strike_key(cell.get("strike"))
        exp = str(cell.get("expiry") or "")
        v = cell.get("window_dadgex")
        if key is None or not exp or isinstance(v, bool) or not isinstance(v, (int, float)) \
                or not math.isfinite(v):
            continue
        grid.setdefault(exp, {})[key] = grid.get(exp, {}).get(key, 0.0) + float(v)
        strikes.add(float(key))
    cov = window.get("coverage") or {}
    return {**base, "status": "ok" if grid else "unavailable",
            "reason": None if grid else "NO_COMPARABLE_OBSERVATIONS",
            "grid": grid or None, "expiries": sorted(grid), "strikes": sorted(strikes),
            "usable": _count(cov.get("n_comparable_contracts")) or 0,
            "missing_delta": _count(cov.get("n_missing_delta")) or 0,
            "invalid": (_count(cov.get("n_invalid")) or 0) + (_count(cov.get("n_invalid_type")) or 0),
            "mixed_pair": _count(cov.get("n_mixed_pair")) or 0}


def build_surface_coverage(metrics: dict[str, Any], grid: dict[str, Any] | None) -> dict[str, Any]:
    """Per-surface population summary for the display contract."""
    metrics = metrics or {}
    grids = metrics.get("grids") or {}
    grid = grid or {}
    out: dict[str, Any] = {}

    raw_usable = _count(metrics.get("raw_usable"))
    raw_missing = _count(metrics.get("raw_missing_oi")) or 0
    raw_invalid = _count(metrics.get("raw_invalid")) or 0
    out["raw"] = {"metric_id": "gex_net_v1", "basis": "OI", "formula_version": "gex.v2",
                  "usable": raw_usable, "missing_oi": raw_missing, "invalid": raw_invalid,
                  "status": _status(raw_usable, raw_missing + raw_invalid),
                  "reason": None if raw_usable else "NO_USABLE_CONTRACTS"}

    def overlay(key: str, metric_id: str, basis: str, missing_key: str | None) -> dict[str, Any]:
        sec = grids.get(key) or {}
        usable = _count(sec.get("usable"))
        missing = (_count(sec.get(missing_key)) or 0) if missing_key else 0
        invalid = ((_count(sec.get("invalid_type")) or 0) + (_count(sec.get("quarantined")) or 0)
                   + (_count(sec.get("invalid_mult")) or 0))
        invalid_delta = (_count(sec.get("invalid_delta")) or 0) if missing_key else 0
        entry = {"metric_id": metric_id, "basis": sec.get("exposure_basis") or basis,
                 "formula_version": sec.get("formula_version") or "gex.v2",
                 "usable": usable, "invalid": invalid,
                 "status": _status(usable, missing + invalid + invalid_delta,
                                   sec.get("status") if sec else "unavailable"),
                 "reason": sec.get("reason") if sec else "SURFACE_NOT_EMITTED"}
        if missing_key:
            entry["missing_delta"] = missing
            entry["invalid_delta"] = invalid_delta
        if _count(sec.get("invalid_mult")) is not None:
            entry["invalid_mult"] = _count(sec.get("invalid_mult"))
        return entry

    out["delta"] = overlay("delta", "dadgex_net_v1", "OI_DELTA_WEIGHTED", "missing_delta")
    out["activity"] = overlay("activity", "volume_gamma_v1", "VOLUME", None)
    out["session_delta_volume"] = overlay("session_delta_volume", "session_delta_volume_gamma_v1",
                                          "VOLUME_DELTA_WEIGHTED", "missing_delta")

    win = grids.get("window") or {}
    w_usable = _count(win.get("usable"))
    w_excl = (_count(win.get("missing_delta")) or 0) + (_count(win.get("invalid")) or 0)
    out["window"] = {"metric_id": "window_dadgex_v1", "basis": "VOLUME_WINDOW",
                     "formula_version": "gex.v2", "usable": w_usable,
                     "missing_delta": _count(win.get("missing_delta")) or 0,
                     "invalid": _count(win.get("invalid")) or 0,
                     "interval": win.get("interval"),
                     "status": _status(w_usable, w_excl, win.get("status") or "unavailable"),
                     "reason": win.get("reason") if win.get("status") != "ok" else None}
    if out["window"]["status"] == "unavailable" and not out["window"]["reason"]:
        out["window"]["reason"] = metrics.get("window_dadgex_reason") or "HISTORY_NOT_YET_RECORDED"

    vex = grid.get("vex_meta") or {}
    vex_cells = bool(grid.get("vex_grid"))
    vex_missing = _count(vex.get("missing_vanna_inputs")) or 0
    vex_invalid = (_count(vex.get("invalid_type")) or 0) + (_count(vex.get("quarantined")) or 0)
    out["vex"] = {"metric_id": "vex_net_1volpt", "basis": vex.get("exposure_basis") or "VEX_1VOLPT",
                  "model": vex.get("model"), "usable": None,
                  "missing_inputs": vex_missing, "invalid": vex_invalid,
                  "status": ("unavailable" if not vex_cells else
                             "partial" if vex_missing + vex_invalid else "ok"),
                  "reason": vex.get("reason") if not vex_cells else None}
    charm = grid.get("charm_meta") or {}
    charm_cells = bool(grid.get("charm_grid"))
    c_usable = _count(charm.get("usable_charm_inputs"))
    c_missing = _count(charm.get("missing_charm_inputs")) or 0
    c_invalid = (_count(charm.get("invalid_type")) or 0) + (_count(charm.get("quarantined")) or 0)
    out["charm"] = {"metric_id": "charm_1pct_per_year", "basis": charm.get("exposure_basis"),
                    "unit": charm.get("unit"), "usable": c_usable,
                    "missing_inputs": c_missing, "invalid": c_invalid,
                    "status": ("unavailable" if not charm_cells else
                               "partial" if c_missing + c_invalid else "ok"),
                    "reason": charm.get("reason") if not charm_cells else None}
    return out


__all__ = ["CONTRACT_VERSION", "build_surface_coverage", "window_grid_section"]
