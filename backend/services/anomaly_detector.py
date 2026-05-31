"""
backend/services/anomaly_detector.py

1D-CNN Autoencoder for flow toxicity anomaly detection.
Ingests VPIN and Quote Imbalance time series to flag toxic flow anomalies.

Architecture:
- Encoder: 1D conv layers compressing temporal patterns
- Bottleneck: dense latent representation
- Decoder: 1D transposed conv layers reconstructing input
- Anomaly score: reconstruction error (MSE)
- Threshold: adaptive based on rolling error distribution

References:
- Ozbayoglu, A.M. et al. (2020). "Deep Learning for Financial Applications."
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Any, Dict

import numpy as np

import services.observability as obs_metrics

logger = logging.getLogger(__name__)

# PyTorch is optional — gracefully degrade if not available
try:
    import torch
    import torch.nn as nn
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    logger.warning("PyTorch not available — anomaly detector will use statistical fallback")


if HAS_TORCH:
    class Conv1DAutoencoder(nn.Module):
        """1D-CNN Autoencoder for time-series anomaly detection."""

        def __init__(self, input_channels: int = 2, seq_len: int = 50, latent_dim: int = 8):
            super().__init__()
            self.seq_len = seq_len
            self.input_channels = input_channels

            # Encoder
            self.encoder = nn.Sequential(
                nn.Conv1d(input_channels, 16, kernel_size=5, padding=2),
                nn.ReLU(),
                nn.MaxPool1d(2),
                nn.Conv1d(16, 8, kernel_size=3, padding=1),
                nn.ReLU(),
                nn.MaxPool1d(2),
                nn.Flatten(),
            )

            # Compute flattened size after conv layers
            # After 2 maxpool layers: seq_len -> seq_len//4
            flat_size = 8 * (seq_len // 4)

            self.fc_encode = nn.Linear(flat_size, latent_dim)
            self.fc_decode = nn.Linear(latent_dim, flat_size)

            # Decoder
            self.decoder = nn.Sequential(
                nn.Unflatten(1, (8, seq_len // 4)),
                nn.ConvTranspose1d(8, 16, kernel_size=2, stride=2),
                nn.ReLU(),
                nn.ConvTranspose1d(16, input_channels, kernel_size=2, stride=2),
            )

        def forward(self, x):
            encoded = self.encoder(x)
            latent = self.fc_encode(encoded)
            decoded = self.fc_decode(latent)
            reconstructed = self.decoder(decoded)
            # Pad or trim to exactly match input size
            if reconstructed.shape[-1] < self.seq_len:
                pad_size = self.seq_len - reconstructed.shape[-1]
                reconstructed = torch.nn.functional.pad(reconstructed, (0, pad_size))
            elif reconstructed.shape[-1] > self.seq_len:
                reconstructed = reconstructed[..., :self.seq_len]
            return reconstructed, latent


class StatisticalAnomalyDetector:
    """Fallback anomaly detector when PyTorch is not available.

    Uses z-score based detection on reconstruction error proxy
    (rolling mean absolute deviation of the input features).
    """

    def __init__(self, window: int = 100, threshold_sigma: float = 2.5):
        self.window = window
        self.threshold_sigma = threshold_sigma
        self._errors: deque = deque(maxlen=window)

    def update(self, features: np.ndarray) -> Dict[str, Any]:
        """Compute anomaly score from features (VPIN, QI)."""
        # Use mean absolute deviation as proxy for reconstruction error
        score = float(np.mean(np.abs(features - np.mean(features))))
        self._errors.append(score)

        if len(self._errors) < 10:
            return {"anomaly_score": score, "is_anomaly": False, "threshold": 0.0}

        errors = np.array(self._errors)
        mean_err = np.mean(errors)
        std_err = np.std(errors)
        threshold = mean_err + self.threshold_sigma * std_err
        is_anomaly = score > threshold

        return {
            "anomaly_score": round(score, 6),
            "is_anomaly": bool(is_anomaly),
            "threshold": round(threshold, 6),
            "zscore": round((score - mean_err) / std_err, 4) if std_err > 1e-12 else 0.0,
        }


class RegimeAwareThreshold:
    """Three-regime threshold adapter based on 30-day realized vol percentile.

    Regimes:
        calm   (vol < 33rd pct)  → 99th-pct reconstruction error threshold
        active (33rd–95th)       → 95th-pct
        urgent (vol > 95th pct)  → 90th-pct
    """

    REGIMES = ["calm", "active", "urgent"]
    PERCENTILES = {"calm": 99, "active": 95, "urgent": 90}

    def __init__(self, window: int = 500):
        self._errors: deque = deque(maxlen=window)
        self._vol_history: deque = deque(maxlen=window * 2)

    def update(self, error: float, realized_vol: float = 0.0) -> Dict[str, Any]:
        """Update with new error and vol, return regime + threshold."""
        self._errors.append(error)
        if realized_vol > 0:
            self._vol_history.append(realized_vol)

        if len(self._errors) < 20:
            return {"regime": "warming_up", "threshold": float("inf"), "percentile_used": 0,
                    "is_anomaly": False, "zscore": 0.0}

        errors = np.array(self._errors)

        # Determine regime from vol percentile
        if len(self._vol_history) >= 20:
            vols = np.array(self._vol_history)
            vol_pct = float(np.mean(vols <= realized_vol)) * 100 if realized_vol > 0 else 50.0
            if vol_pct < 33:
                regime = "calm"
            elif vol_pct < 95:
                regime = "active"
            else:
                regime = "urgent"
        else:
            regime = "active"  # default

        pct = self.PERCENTILES[regime]
        threshold = float(np.percentile(errors, pct))
        is_anomaly = error > threshold

        return {
            "regime": regime,
            "threshold": round(threshold, 8),
            "percentile_used": pct,
            "is_anomaly": bool(is_anomaly),
            "zscore": round((error - np.mean(errors)) / (np.std(errors) + 1e-12), 4),
        }

    def get_state(self) -> Dict[str, Any]:
        return {
            "regime": "active",  # simplified
            "n_errors": len(self._errors),
            "n_vol": len(self._vol_history),
        }


class FlowAnomalyDetector:
    """Flow toxicity anomaly detector with optional 1D-CNN autoencoder.

    Uses 1D-CNN Autoencoder when PyTorch is available,
    falls back to statistical method otherwise.
    """

    def __init__(self, seq_len: int = 50, latent_dim: int = 8,
                 threshold_sigma: float = 2.5, device: str = "cpu",
                 ticker: str = ""):
        self.seq_len = seq_len
        self.latent_dim = latent_dim
        self.threshold_sigma = threshold_sigma
        self.device = device
        self.ticker = ticker

        # Rolling buffer for input features: (VPIN, QI)
        self._buffer: deque = deque(maxlen=seq_len)
        self._errors: deque = deque(maxlen=500)

        # Regime-aware threshold
        self._regime_threshold = RegimeAwareThreshold(window=500)
        self._current_regime = "active"

        if HAS_TORCH:
            self.model = Conv1DAutoencoder(
                input_channels=2, seq_len=seq_len, latent_dim=latent_dim
            ).to(device)
            self.model.eval()
            self._optimizer = torch.optim.Adam(self.model.parameters(), lr=1e-3)
            self._trained = False
            self._train_every = 50  # retrain every N updates
            self._update_count = 0
        else:
            self.model = None
            self._fallback = StatisticalAnomalyDetector(window=seq_len, threshold_sigma=threshold_sigma)
            self._trained = False
            self._update_count = 0

    def update(self, vpin: float, qi: float) -> Dict[str, Any]:
        """Add a new (VPIN, QI) observation and compute anomaly score."""
        self._buffer.append([vpin, qi])
        self._update_count += 1

        if len(self._buffer) < self.seq_len:
            result = {
                "anomaly_score": 0.0,
                "is_anomaly": False,
                "status": "warming_up",
                "buffer_fill": len(self._buffer) / self.seq_len,
            }
        elif HAS_TORCH and self.model is not None:
            result = self._torch_update()
        else:
            features = np.array(self._buffer)
            result = self._fallback.update(features)

        # Emit Prometheus metrics
        if self.ticker:
            score = result.get("anomaly_score", 0.0)
            obs_metrics.anomaly_score.labels(ticker=self.ticker).set(score)
            if result.get("is_anomaly", False):
                obs_metrics.anomaly_detected_total.inc()

        return result

    def _torch_update(self) -> Dict[str, Any]:
        """PyTorch-based anomaly detection."""
        import torch

        # Prepare input: (1, channels, seq_len)
        data = np.array(self._buffer, dtype=np.float32).T  # (2, seq_len)
        x = torch.tensor(data).unsqueeze(0).to(self.device)

        # Periodic training
        if self._update_count % self._train_every == 0:
            self._train_step(x)

        with torch.no_grad():
            reconstructed, latent = self.model(x)
            error = torch.mean((x - reconstructed) ** 2).item()

        self._errors.append(error)

        # Adaptive threshold
        if len(self._errors) >= 20:
            errors = np.array(self._errors)
            mean_err = np.mean(errors)
            std_err = np.std(errors)
            threshold = mean_err + self.threshold_sigma * std_err
            _is_anomaly = error > threshold
            _zscore = (error - mean_err) / std_err if std_err > 1e-12 else 0.0
        else:
            threshold = float("inf")
            _is_anomaly = False
            _zscore = 0.0

        # Regime-aware threshold
        regime_result = self._regime_threshold.update(error)
        self._current_regime = regime_result["regime"]

        return {
            "anomaly_score": round(error, 8),
            "is_anomaly": regime_result["is_anomaly"],
            "threshold": regime_result["threshold"],
            "zscore": regime_result["zscore"],
            "latent_norm": round(torch.norm(latent).item(), 4),
            "trained": self._trained,
            "status": "active",
            "regime": self._current_regime,
            "regime_threshold_used": regime_result["percentile_used"],
        }

    def _train_step(self, x: "torch.Tensor"):
        """Single training step on current buffer."""
        import torch.nn.functional as F

        self.model.train()
        self._optimizer.zero_grad()
        reconstructed, _ = self.model(x)
        loss = F.mse_loss(reconstructed, x)
        loss.backward()
        self._optimizer.step()
        self.model.eval()
        self._trained = True

    def get_state(self) -> Dict[str, Any]:
        return {
            "model_type": "cnn_autoencoder" if HAS_TORCH else "statistical_fallback",
            "seq_len": self.seq_len,
            "latent_dim": self.latent_dim,
            "buffer_fill": len(self._buffer) / self.seq_len,
            "n_errors": len(self._errors),
            "trained": self._trained,
            "ticker": self.ticker,
            "threshold_sigma": self.threshold_sigma,
        }

    def load_checkpoint(self, checkpoint: dict) -> None:
        """Load a trained checkpoint into the model.

        Args:
            checkpoint: dict with keys 'model_state_dict', 'config', 'threshold'
        """

        if not HAS_TORCH or self.model is None:
            logger.warning("Cannot load checkpoint: PyTorch not available")
            return

        config = checkpoint.get("config", {})
        # Verify config matches
        if config.get("seq_len") != self.seq_len:
            logger.warning(f"Checkpoint seq_len={config.get('seq_len')} != detector seq_len={self.seq_len}")
        if config.get("latent_dim") != self.latent_dim:
            logger.warning(f"Checkpoint latent_dim={config.get('latent_dim')} != detector latent_dim={self.latent_dim}")

        self.model.load_state_dict(checkpoint["model_state_dict"])
        self.model.eval()
        self._trained = True

        # Restore threshold if available
        threshold_info = checkpoint.get("threshold", {})
        if threshold_info:
            self._errors.clear()
            # Seed the error distribution from the training threshold
            mean_err = threshold_info.get("mean_error", 0.0)
            std_err = threshold_info.get("std_error", 0.0)
            # Populate with synthetic errors around the training distribution
            synthetic_errors = np.random.normal(mean_err, std_err, 100)
            for e in synthetic_errors:
                self._errors.append(float(e))

        logger.info(f"Loaded checkpoint for {self.ticker}: trained={self._trained}, "
                     f"threshold={threshold_info.get('threshold', 'N/A')}")
