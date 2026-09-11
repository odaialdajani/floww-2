"""Fixed research agreement weights, with explicit missing dimensions.

An agreement reading is not a calibrated probability or a trading edge.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any

_WEIGHTS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "config", "agent_weights_v1.json")


def load_weights() -> dict[str, Any]:
    try:
        with open(os.path.normpath(_WEIGHTS_PATH)) as f:
            return json.load(f)
    except Exception:
        return {"version": "v1-fallback", "dimensions": {"flow": 0.25, "structure": 0.25, "microstructure": 0.15, "ml": 0.10, "vol": 0.10, "time_delta": 0.15}}


def _clamp(x: float) -> float:
    try:
        return max(-1.0, min(1.0, float(x)))
    except Exception:
        return 0.0


def score(inputs: dict[str, Any]) -> dict[str, Any]:
    """Inputs: per-dimension signed values in [-1,1] + inputs_status map.

    Returns {total, dimensions: {name: {value, contribution, weight,
    inputs_status}}, weights_version}.
    """
    w = load_weights()
    dims = w.get("dimensions", {})
    status = inputs.get("inputs_status", {}) if isinstance(inputs, dict) else {}
    out: dict[str, Any] = {"dimensions": {}, "total": 0.0, "weights_version": w.get("version", "v1")}
    total = 0.0
    coverage = 0.0
    for name, weight in dims.items():
        try:
            weight_f = float(weight)
        except Exception:
            weight_f = 0.0
        raw = inputs.get(name) if isinstance(inputs, dict) else None
        valid = isinstance(raw,(float,int)) and not isinstance(raw,bool) and math.isfinite(raw) and status.get(name,"ok")=="ok"
        val = _clamp(raw) if valid else None
        contrib = round(val * weight_f * 100.0, 2) if valid else None
        if valid:
            total += val * weight_f
            coverage += weight_f
        out["dimensions"][name] = {
            "value": val,
            "contribution": contrib,
            "weight": weight_f,
            "inputs_status": status.get(name, "ok" if valid else "unavailable"),
        }
    out["total"] = round(total * 100.0, 2) if coverage else None
    out["coverage_weight"] = round(coverage,4)
    out["missing_input_policy"] = "All declared dimensions required for a directional conclusion"
    out["direction"] = "bullish" if total > 0.15 else ("bearish" if total < -0.15 else "neutral")
    if any(v["inputs_status"] != "ok" or v["value"] is None for v in out["dimensions"].values()):
        out["direction"] = "insufficient_evidence"
    return out
