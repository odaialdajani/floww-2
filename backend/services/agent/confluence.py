"""Deterministic confluence scorer (plan v3 L4). The LLM narrates; never invents.

Composition of flow conviction + trinity + regime + GEX posture + VEX/charm
+ ML class (where covered) + vol posture + time_delta direction.
Rule: no fifth scorer — reuse the server-side calibrated score.
"""

from __future__ import annotations

import json
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
    for name, weight in dims.items():
        try:
            weight_f = float(weight)
        except Exception:
            weight_f = 0.0
        val = _clamp(inputs.get(name, 0.0)) if isinstance(inputs, dict) else 0.0
        contrib = round(val * weight_f * 100.0, 2)
        total += val * weight_f
        out["dimensions"][name] = {
            "value": val,
            "contribution": contrib,
            "weight": weight_f,
            "inputs_status": status.get(name, "ok"),
        }
    out["total"] = round(total * 100.0, 2)
    out["direction"] = "bullish" if total > 0.15 else ("bearish" if total < -0.15 else "neutral")
    return out
