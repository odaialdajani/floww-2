"""
backend/routes/ensemble.py

Ensemble toxicity prediction API routes.
Exposes the ToxicityEnsemble for multi-horizon flow toxicity inference.

Endpoints:
  POST /api/ensemble/update — Feed VPIN + QI, get toxicity probabilities
  GET  /api/ensemble/state  — Get ensemble state for a ticker
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ensemble", tags=["ensemble"])

# Global ensemble registry (ticker -> ToxicityEnsemble)
_ensembles: dict[str, Any] = {}


@router.post("/update")
async def update_ensemble(
    ticker: str,
    vpin: float,
    qi: float,
):
    """Feed VPIN + QI to the ensemble and get multi-horizon toxicity probs.

    Returns P(toxic flow) for 1, 5, 15, and 60-minute horizons,
    plus component scores from CNN-AE, statistical, and forecast detectors.
    """
    t = ticker.upper()
    from services.ml_ensemble import ToxicityEnsemble
    if t not in _ensembles:
        _ensembles[t] = ToxicityEnsemble()
    ensemble = _ensembles[t]
    result = ensemble.update(vpin, qi)
    return {"ticker": t, **result}


@router.get("/state")
async def get_ensemble_state(ticker: str):
    """Read existing state without initializing models or adding observations."""
    t = ticker.upper()
    ensemble = _ensembles.get(t)
    if ensemble is None:
        return {"ticker": t, "type": "toxicity_ensemble", "horizons": [1, 5, 15, 60],
                "initialized": False, "status": "uninitialized",
                "reason": "NO_OBSERVATIONS_IN_THIS_PROCESS", "n_score_history": 0,
                "ensemble_probabilities": {}, "component_scores": {}}
    return {"ticker": t, "initialized": True, **ensemble.get_state()}
