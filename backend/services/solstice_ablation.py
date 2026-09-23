"""
backend/services/solstice_ablation.py — baseline/ablation ladder (T11/T28).

Frozen protocol abl.v1. Compares, on ONE snapshot, at equal eligible events:
  L0 price_only_reclaim — nearest-listed-strike touch (no Greeks at all)
  L1 raw_wall_plus_confirmation — top-3 gross wall proximity + contemporaneous
       zone occupancy (confirmation labeled weak: single snapshot, no path)
  L2 plus_delta — L1 + delta-gross share of wall above minimum support
  L3 plus_window_activity — L2 + nonzero window volume delta at the wall

Costs: fixed spread-cost assumption in bps of premium (labeled assumption —
real quotes needed for realized fills). Abstention counted with reasons.
This is an ENGINEERING smoke comparison, not validation and not an edge claim:
single snapshot, no holdout, no outcomes. Held-out costed evaluation with
walk-forward splits (solstice_labels) is the validation gate.
"""

from __future__ import annotations

from typing import Any

VERSION = "abl.v1"
TOUCH_PCT = 0.002
NEAR_PCT = 0.003
MIN_DELTA_SHARE = 0.20


def _walls(strikes: list[dict], spot: float) -> list[dict]:
    from services.wall_structure import discover_walls, nearest_walls
    return nearest_walls(discover_walls(strikes or [], spot), spot, n=3)


def run_ladder(snapshot: dict[str, Any], cost_bps: float = 20.0) -> dict[str, Any]:
    """Run L0–L3 on one snapshot. Returns per-level signals/abstentions."""
    spot = float(snapshot.get("spot", 0) or 0)
    strikes = snapshot.get("strikes", []) or []
    metrics = snapshot.get("metrics", {}) or {}
    out: dict[str, Any] = {"version": VERSION, "spot": spot,
                           "cost_assumption_bps": cost_bps, "levels": {}}
    if spot <= 0 or not strikes:
        for lvl in ("L0", "L1", "L2", "L3"):
            out["levels"][lvl] = {"signals": [], "abstentions": 1,
                                  "reason": "NO_COVERAGE"}
        return out

    near_strikes = [s for s in strikes
                    if abs(float(s.get("strike", 0)) - spot) / spot <= TOUCH_PCT]
    l0 = {"signals": [{"strike": s["strike"], "rule": "nearest-strike touch"}
                      for s in near_strikes],
          "abstentions": 0 if near_strikes else 1,
          "reason": None if near_strikes else "NO_TOUCH"}
    out["levels"]["L0_price_only"] = l0

    walls = _walls(strikes, spot)
    l1_sig = [w for w in walls
              if w["low"] * (1 - NEAR_PCT) <= spot <= w["high"] * (1 + NEAR_PCT)]
    out["levels"]["L1_raw_wall"] = {
        "signals": [{"wall_id": w["wall_id"], "rule": "contemporaneous zone occupancy (weak confirmation)"}
                    for w in l1_sig],
        "abstentions": 0 if l1_sig else 1,
        "reason": None if l1_sig else "NO_WALL_NEAR",
        "confirmation": "WEAK_single_snapshot_no_path"}

    ratio = metrics.get("magnitude_ratio_delta_over_raw")
    l2_sig = [w for w in l1_sig
              if ratio is not None and ratio >= MIN_DELTA_SHARE]
    out["levels"]["L2_plus_delta"] = {
        "signals": [{"wall_id": w["wall_id"], "delta_share": ratio} for w in l2_sig],
        "abstentions": 0 if l2_sig else 1,
        "reason": None if l2_sig else ("DELTA_SHARE_BELOW_SUPPORT" if ratio is not None else "DELTA_UNKNOWN")}

    vol = snapshot.get("volume_deltas") or (metrics.get("volume_proxy") or [])
    l3_sig = [w for w in l2_sig if vol]
    out["levels"]["L3_plus_activity"] = {
        "signals": [{"wall_id": w["wall_id"]} for w in l3_sig],
        "abstentions": 0 if l3_sig else 1,
        "reason": None if l3_sig else "NO_WINDOW_ACTIVITY"}
    return out
