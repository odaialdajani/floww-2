"""
backend/routes/anomaly.py

Anomaly Detection API routes.
Exposes the 1D-CNN Autoencoder flow toxicity anomaly detector.

Endpoints:
  GET  /api/anomaly/{ticker}        — Current anomaly state
  POST /api/anomaly/{ticker}/update — Feed new (VPIN, QI) observation
  GET  /api/anomaly/{ticker}/status — Model status and configuration
  POST /api/anomaly/{ticker}/load   — Load trained checkpoint for ticker
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/anomaly", tags=["anomaly"])

# Global anomaly detector registry (ticker -> FlowAnomalyDetector)
_detectors: Dict[str, Any] = {}

# Global ensemble registry (ticker -> ToxicityEnsemble)
_ensembles: Dict[str, Any] = {}

# Path to trained model checkpoints
MODEL_BASE_PATH = Path(__file__).resolve().parents[2] / "project_oracle" / "models"


def _get_detector(ticker: str, seq_len: int = 50, latent_dim: int = 8, device: str = "cpu"):
    """Get or create an anomaly detector for the given ticker."""
    if ticker not in _detectors:
        from services.anomaly_detector import HAS_TORCH, FlowAnomalyDetector
        _detectors[ticker] = FlowAnomalyDetector(
            seq_len=seq_len, latent_dim=latent_dim, ticker=ticker, device=device
        )
        # Auto-load trained checkpoint if available
        ckpt_path = MODEL_BASE_PATH / "anomaly_detector_v1.pt"
        if ckpt_path.exists() and HAS_TORCH:
            try:
                import torch
                checkpoint = torch.load(str(ckpt_path), map_location=device)
                _detectors[ticker].load_checkpoint(checkpoint)
                logger.info(f"Loaded trained checkpoint for {ticker}: {ckpt_path}")
            except Exception as e:
                logger.warning(f"Failed to load checkpoint for {ticker}: {e}")
    return _detectors[ticker]


@router.get("/ensemble")
async def get_ensemble_prediction(
    ticker: str,
    horizon_minutes: int = Query(default=15, ge=1, le=1440),
):
    """Get ensemble toxicity prediction for a given horizon.
    Returns P(toxic flow in next N minutes) from the calibrated ensemble.
    """
    t = ticker.upper()
    from services.ml_ensemble import ToxicityEnsemble
    if t not in _ensembles:
        _ensembles[t] = ToxicityEnsemble()
    ensemble = _ensembles[t]
    state = ensemble.get_state()
    return {"ticker": t, "horizon_minutes": horizon_minutes, **state}


@router.post("/ensemble/update")
async def update_ensemble(
    ticker: str,
    vpin: float,
    qi: float,
):
    """Feed VPIN + QI to the ensemble and get multi-horizon toxicity probs.

    Returns P(toxic flow) for 1, 5, 15, and 60-minute horizons,
    plus component scores from CNN-AE, statistical, and forecast detectors.
    """
    import logging as _log
    _log.getLogger(__name__).info(f"update_ensemble CALLED: ticker={ticker}")
    t = ticker.upper()
    from services.ml_ensemble import ToxicityEnsemble
    if t not in _ensembles:
        _ensembles[t] = ToxicityEnsemble()
    ensemble = _ensembles[t]
    result = ensemble.update(vpin, qi)
    return {"ticker": t, **result}


@router.get("/ensemble/state")
async def get_ensemble_state(ticker: str):
    """Get full ensemble state including calibration and history."""
    t = ticker.upper()
    from services.ml_ensemble import ToxicityEnsemble
    if t not in _ensembles:
        _ensembles[t] = ToxicityEnsemble()
    return {"ticker": t, **_ensembles[t].get_state()}


@router.get("/{ticker}")
async def get_anomaly_state(ticker: str):
    """Return the current anomaly detection state."""
    t = ticker.upper()
    detector = _get_detector(t)
    return detector.get_state()


@router.post("/{ticker}/update")
async def update_anomaly(ticker: str, vpin: float, qi: float):
    """Feed a new (VPIN, QI) observation and get anomaly score."""
    t = ticker.upper()
    detector = _get_detector(t)
    result = detector.update(vpin, qi)
    return {"ticker": t, **result}


@router.get("/{ticker}/status")
async def get_detector_status(ticker: str):
    """Return model configuration and buffer status."""
    t = ticker.upper()
    detector = _get_detector(t)
    return detector.get_state()


@router.post("/{ticker}/load")
async def load_trained_model(
    ticker: str,
    model_path: str = Query(default="", description="Path to .pt checkpoint file"),
    device: str = Query(default="cpu"),
):
    """Load a trained checkpoint for the given ticker."""
    t = ticker.upper()
    from services.anomaly_detector import HAS_TORCH
    if not HAS_TORCH:
        raise HTTPException(503, "PyTorch not available")

    import torch

    ckpt_path = Path(model_path) if model_path else MODEL_BASE_PATH / "anomaly_detector_v1.pt"
    if not ckpt_path.exists():
        raise HTTPException(404, f"Checkpoint not found: {ckpt_path}")

    detector = _get_detector(t)
    try:
        checkpoint = torch.load(str(ckpt_path), map_location=device)
        detector.load_checkpoint(checkpoint)
        return {"status": "loaded", "ticker": t, "path": str(ckpt_path)}
    except Exception as e:
        raise HTTPException(500, f"Failed to load checkpoint: {e}")
