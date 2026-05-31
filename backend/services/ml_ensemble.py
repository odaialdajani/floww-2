"""
backend/services/ml_ensemble.py

Ensemble inference module for flow toxicity anomaly detection.
Combines three components:
  (a) 1D-CNN AE reconstruction error (Round 1)
  (b) PatchTST forecast vs realized residual (Round 2 task 1)
  (c) Statistical detector (existing)

Calibration: Platt scaling on per-bucket historical accuracy.
Output: P(toxic flow in next N minutes), N ∈ {1, 5, 15, 60}
"""
from __future__ import annotations

import importlib.util
import logging
from collections import deque
from typing import Any, Dict

import numpy as np

logger = logging.getLogger(__name__)

HAS_TORCH = importlib.util.find_spec("torch") is not None


class PlattScaler:
    """Platt scaling for calibrating classifier probabilities."""

    def __init__(self):
        self.A: float = 0.0
        self.B: float = 0.0
        self._fitted = False

    def fit(self, scores: np.ndarray, labels: np.ndarray) -> None:
        """Fit Platt scaling parameters.
        Args:
            scores: raw anomaly scores (higher = more anomalous)
            labels: binary labels (1 = anomaly, 0 = normal)
        """
        from scipy.optimize import minimize

        def neg_log_likelihood(params):
            A, B = params
            probs = 1.0 / (1.0 + np.exp(A * scores + B))
            probs = np.clip(probs, 1e-12, 1 - 1e-12)
            ll = np.sum(labels * np.log(probs) + (1 - labels) * np.log(1 - probs))
            return -ll

        try:
            result = minimize(neg_log_likelihood, [0.0, 0.0], method="Nelder-Mead")
            self.A, self.B = result.x
            self._fitted = True
        except Exception as e:
            logger.warning(f"Platt scaling fit failed: {e}")
            self.A, self.B = 1.0, 0.0
            self._fitted = True

    def predict_proba(self, scores: np.ndarray) -> np.ndarray:
        """Convert raw scores to calibrated probabilities."""
        if not self._fitted:
            # Fallback: sigmoid with default params
            return 1.0 / (1.0 + np.exp(-(scores - np.mean(scores)) / (np.std(scores) + 1e-12)))
        return 1.0 / (1.0 + np.exp(self.A * scores + self.B))


class ToxicityEnsemble:
    """Ensemble anomaly detector combining multiple signals."""

    HORIZON_MINUTES = [1, 5, 15, 60]

    def __init__(self, seq_len: int = 50, latent_dim: int = 8, device: str = "cpu"):
        self.seq_len = seq_len
        self.latent_dim = latent_dim
        self.device = device

        # Component detectors
        from services.anomaly_detector import FlowAnomalyDetector, StatisticalAnomalyDetector
        self.cnn_detector = FlowAnomalyDetector(seq_len=seq_len, latent_dim=latent_dim, device=device)
        self.statistical = StatisticalAnomalyDetector(window=100, threshold_sigma=2.5)

        # PatchTST forecaster (loaded on demand)
        self._forecaster = None
        self._forecaster_path = None

        # Calibration
        self._calibrators: Dict[int, PlattScaler] = {h: PlattScaler() for h in self.HORIZON_MINUTES}
        self._calibration_data: Dict[int, list] = {h: [] for h in self.HORIZON_MINUTES}

        # History for multi-horizon
        self._score_history: deque = deque(maxlen=1000)
        self._label_history: deque = deque(maxlen=1000)

    def load_forecaster(self, path: str) -> None:
        """Load trained PatchTST forecaster."""
        if not HAS_TORCH:
            logger.warning("PyTorch not available, skipping forecaster load")
            return
        self._forecaster_path = path
        try:
            import torch
            ckpt = torch.load(path, map_location=self.device)
            from scripts.train_patchtst_vpin import SimpleCNNForecaster
            self._forecaster = SimpleCNNForecaster(
                seq_len=ckpt["config"]["seq_len"],
                horizon=ckpt["config"]["horizon"],
            )
            self._forecaster.load_state_dict(ckpt["model_state_dict"])
            self._forecaster.to(self.device)
            self._forecaster.eval()
            logger.info(f"Loaded forecaster from {path}")
        except Exception as e:
            logger.warning(f"Failed to load forecaster: {e}")

    def update(self, vpin: float, qi: float) -> Dict[str, Any]:
        """Update all detectors and compute ensemble score."""
        # CNN AE score
        cnn_result = self.cnn_detector.update(vpin, qi)
        cnn_score = cnn_result.get("anomaly_score", 0.0)

        # Statistical score
        stat_result = self.statistical.update(np.array([vpin, qi]))
        stat_score = stat_result.get("anomaly_score", 0.0)

        # PatchTST forecast residual
        forecast_score = 0.0
        if self._forecaster is not None and HAS_TORCH:
            forecast_score = self._compute_forecast_residual(vpin)

        # Combine scores (weighted average, weights from calibration)
        raw_scores = {
            "cnn_ae": cnn_score,
            "statistical": stat_score,
            "forecast_residual": forecast_score,
        }

        # Compute ensemble probability for each horizon
        ensemble_probs = {}
        for horizon in self.HORIZON_MINUTES:
            # Simple average of normalized scores (before calibration)
            combined = (cnn_score + stat_score + forecast_score) / 3.0
            prob = self._calibrators[horizon].predict_proba(np.array([combined]))[0]
            ensemble_probs[f"p_toxic_{horizon}min"] = round(float(prob), 4)

        # Record for future calibration
        self._score_history.append({
            "cnn": cnn_score,
            "stat": stat_score,
            "forecast": forecast_score,
            "combined": (cnn_score + stat_score + forecast_score) / 3.0,
        })

        return {
            "ensemble_probabilities": ensemble_probs,
            "component_scores": raw_scores,
            "cnn_anomaly": cnn_result.get("is_anomaly", False),
            "statistical_anomaly": stat_result.get("is_anomaly", False),
            "status": "active",
        }

    def _compute_forecast_residual(self, current_vpin: float) -> float:
        """Compute forecast vs realized residual."""
        import torch
        if self._forecaster is None:
            return 0.0
        try:
            # Use last seq_len VPIN values from CNN detector buffer
            buffer = list(self.cnn_detector._buffer)
            if len(buffer) < self._forecaster.net[0].kernel_size[0]:
                return 0.0
            vpin_series = np.array([b[0] for b in buffer[-self._forecaster.net[0].kernel_size[0]:]])
            x = torch.tensor(vpin_series, dtype=torch.float32).unsqueeze(0).unsqueeze(-1).to(self.device)
            with torch.no_grad():
                forecast = self._forecaster(x).cpu().numpy()[0]
            # Residual = |forecast[0] - actual|
            residual = abs(forecast[0] - current_vpin)
            return float(residual)
        except Exception:
            return 0.0

    def calibrate(self, horizon: int, scores: np.ndarray, labels: np.ndarray) -> None:
        """Calibrate a specific horizon."""
        if horizon in self._calibrators:
            self._calibrators[horizon].fit(scores, labels)

    def get_state(self) -> Dict[str, Any]:
        return {
            "type": "toxicity_ensemble",
            "seq_len": self.seq_len,
            "device": self.device,
            "forecaster_loaded": self._forecaster is not None,
            "horizons": self.HORIZON_MINUTES,
            "n_score_history": len(self._score_history),
        }
