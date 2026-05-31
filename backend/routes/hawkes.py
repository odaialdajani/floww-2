"""
backend/routes/hawkes.py

Hawkes Process API routes.
Exposes Hawkes process models for trade arrival rate estimation.

Endpoints:
  POST /api/hawkes/{ticker}/fit       — Fit Hawkes process to event times
  GET  /api/hawkes/{ticker}/intensity — Current intensity at latest event
  POST /api/hawkes/{ticker}/simulate  — Simulate event times
  GET  /api/hawkes/{ticker}/state     — Full model state
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import numpy as np
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hawkes", tags=["hawkes"])

# Global registry (ticker -> HawkesProcess)
_hawkes: Dict[str, Any] = {}


def _get_hawkes(ticker: str, mu: float = 1.0, alpha: float = 0.5, beta: float = 1.0):
    if ticker not in _hawkes:
        from services.hawkes_process import HawkesProcess
        _hawkes[ticker] = HawkesProcess(mu=mu, alpha=alpha, beta=beta)
    return _hawkes[ticker]


@router.post("/{ticker}/fit")
async def fit_hawkes(ticker: str, event_times: List[float]):
    """Fit Hawkes process parameters to observed event times."""
    t = ticker.upper()
    if len(event_times) < 2:
        raise HTTPException(400, "Need at least 2 event times")

    hp = _get_hawkes(t)
    result = hp.fit(np.array(event_times))
    return {"ticker": t, **result}


@router.get("/{ticker}/intensity")
async def get_intensity(ticker: str, event_times: List[float] = None):
    """Compute conditional intensity at the latest event time."""
    t = ticker.upper()
    hp = _get_hawkes(t)

    if event_times is None or len(event_times) == 0:
        return {"ticker": t, "intensity": hp.mu, "baseline": hp.mu}

    times = np.array(event_times)
    lam = hp.intensity(times[-1], times)
    return {"ticker": t, "intensity": lam, "baseline": hp.mu}


@router.post("/{ticker}/simulate")
async def simulate_hawkes(ticker: str, T: float = 100.0, n_events: int = 1000):
    """Simulate event times using Ogata's thinning algorithm."""
    t = ticker.upper()
    hp = _get_hawkes(t)
    events = hp.simulate(T=T, n_events=n_events)
    return {"ticker": t, "n_events": len(events), "event_times": events.tolist()}


@router.get("/{ticker}/state")
async def get_hawkes_state(ticker: str):
    """Return full Hawkes process state."""
    t = ticker.upper()
    hp = _get_hawkes(t)
    return {"ticker": t, **hp.get_state()}
