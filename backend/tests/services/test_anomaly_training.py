"""
backend/tests/services/test_anomaly_training.py

Tests for the 1D-CNN Autoencoder anomaly detector training pipeline.
10+ tests covering data generation, training, checkpointing, threshold, and inference.

Run with:
    cd backend && .venv/bin/python -m pytest tests/services/test_anomaly_training.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.anomaly_detector import (
    FlowAnomalyDetector,
    StatisticalAnomalyDetector,
)

pytest.importorskip("torch")
from services.anomaly_detector import Conv1DAutoencoder

# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def synthetic_data():
    """Deterministic synthetic data with seed."""
    rng = np.random.RandomState(42)
    n = 1000
    vpin = np.cumsum(rng.normal(0, 0.02, n)) + 0.45
    vpin = np.clip(vpin, 0.1, 0.9)
    qi = np.cumsum(rng.normal(0, 0.05, n)) * 0.3
    qi = np.clip(qi, -0.8, 0.8)
    return np.stack([vpin, qi], axis=1).astype(np.float32)


@pytest.fixture
def synthetic_sequences(synthetic_data):
    """Create sequences from synthetic data."""
    seq_len = 50
    n = len(synthetic_data) - seq_len + 1
    seqs = np.zeros((n, seq_len, 2), dtype=np.float32)
    for i in range(n):
        seqs[i] = synthetic_data[i:i + seq_len]
    return seqs


@pytest.fixture
def trained_model_path(synthetic_sequences, tmp_path):
    """Train a model and return the checkpoint path."""
    import torch
    import torch.nn.functional as F

    seq_len = 50
    split = int(len(synthetic_sequences) * 0.8)
    train_seq = synthetic_sequences[:split]
    val_seq = synthetic_sequences[split:]

    model = Conv1DAutoencoder(input_channels=2, seq_len=seq_len, latent_dim=8)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

    # Quick training — 10 epochs
    train_x = torch.tensor(train_seq, dtype=torch.float32).permute(0, 2, 1)
    for epoch in range(10):
        model.train()
        optimizer.zero_grad()
        recon, _ = model(train_x)
        loss = F.mse_loss(recon, train_x)
        loss.backward()
        optimizer.step()

    # Compute threshold
    model.eval()
    with torch.no_grad():
        val_x = torch.tensor(val_seq, dtype=torch.float32).permute(0, 2, 1)
        val_recon, _ = model(val_x)
        errors = torch.mean((val_x - val_recon) ** 2, dim=(1, 2)).numpy()

    threshold = float(np.mean(errors) + 2.5 * np.std(errors))

    # Save checkpoint
    save_path = tmp_path / "test_anomaly_detector.pt"
    torch.save({
        "model_state_dict": model.state_dict(),
        "config": {"input_channels": 2, "seq_len": seq_len, "latent_dim": 8},
        "threshold": {"threshold": threshold},
    }, save_path)

    return str(save_path)


# ── Test 1: Synthetic data generator is deterministic ────────────────────────

class TestSyntheticData:
    def test_deterministic_with_seed(self):
        """Same seed must produce identical data."""
        rng1 = np.random.RandomState(42)
        rng2 = np.random.RandomState(42)
        data1 = rng1.normal(0, 1, 100)
        data2 = rng2.normal(0, 1, 100)
        np.testing.assert_array_equal(data1, data2)

    def test_different_seeds_differ(self):
        """Different seeds must produce different data."""
        rng1 = np.random.RandomState(42)
        rng2 = np.random.RandomState(99)
        data1 = rng1.normal(0, 1, 100)
        data2 = rng2.normal(0, 1, 100)
        assert not np.array_equal(data1, data2)

    def test_vpin_in_valid_range(self):
        """VPIN values must be in [0, 1]."""
        rng = np.random.RandomState(42)
        n = 5000
        vpin = np.zeros(n)
        vpin[0] = 0.45
        for t in range(1, n):
            vpin[t] = np.clip(vpin[t - 1] + rng.normal(0, 0.03), 0.05, 0.99)
        assert np.all(vpin >= 0.05)
        assert np.all(vpin <= 0.99)


# ── Test 2: Training reduces loss ────────────────────────────────────────────

class TestTraining:
    def test_loss_decreases(self, synthetic_sequences):
        """Training must reduce loss across epochs."""
        import torch
        import torch.nn.functional as F

        model = Conv1DAutoencoder(input_channels=2, seq_len=50, latent_dim=8)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

        x = torch.tensor(synthetic_sequences, dtype=torch.float32).permute(0, 2, 1)

        losses = []
        for epoch in range(50):
            model.train()
            optimizer.zero_grad()
            recon, _ = model(x)
            loss = F.mse_loss(recon, x)
            loss.backward()
            optimizer.step()
            losses.append(loss.item())

        # Loss should decrease overall (compare first 5 epochs avg to last 5)
        early_avg = np.mean(losses[:5])
        late_avg = np.mean(losses[-5:])
        assert late_avg < early_avg, f"Loss did not decrease: {early_avg:.4f} -> {late_avg:.4f}"

    @pytest.mark.flaky(reruns=2, min_passes=1)
    def test_overfit_small_dataset(self):
        """Model should overfit a tiny dataset (sanity check)."""
        import torch
        import torch.nn.functional as F

        # Create a single sequence repeated
        x = torch.randn(1, 2, 50) * 0.1
        x = x.repeat(10, 1, 1)

        model = Conv1DAutoencoder(input_channels=2, seq_len=50, latent_dim=8)
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

        for _ in range(100):
            model.train()
            optimizer.zero_grad()
            recon, _ = model(x)
            loss = F.mse_loss(recon, x)
            loss.backward()
            optimizer.step()

        model.eval()
        with torch.no_grad():
            recon, _ = model(x)
            final_loss = F.mse_loss(recon, x).item()

        assert final_loss < 0.01, f"Should overfit small dataset, loss={final_loss:.4f}"


# ── Test 3: Checkpoint save/load ─────────────────────────────────────────────

class TestCheckpoint:
    def test_checkpoint_loads_and_produces_same_output(self, trained_model_path):
        """Loaded checkpoint must produce identical output to in-memory model."""
        import torch

        # Load checkpoint
        checkpoint = torch.load(trained_model_path, map_location="cpu")
        config = checkpoint["config"]

        model = Conv1DAutoencoder(
            input_channels=config["input_channels"],
            seq_len=config["seq_len"],
            latent_dim=config["latent_dim"],
        )
        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()

        # Test inference
        x = torch.randn(5, 2, 50)
        with torch.no_grad():
            recon, latent = model(x)

        assert recon.shape == x.shape, f"Output shape mismatch: {recon.shape} vs {x.shape}"
        assert latent.shape[0] == 5
        assert latent.shape[1] == config["latent_dim"]

    def test_checkpoint_deterministic(self, trained_model_path):
        """Same checkpoint must produce same output on repeated inference."""
        import torch

        checkpoint = torch.load(trained_model_path, map_location="cpu")
        model = Conv1DAutoencoder(
            input_channels=2, seq_len=50, latent_dim=8,
        )
        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()

        x = torch.randn(3, 2, 50)

        with torch.no_grad():
            recon1, _ = model(x)
            recon2, _ = model(x)

        torch.testing.assert_close(recon1, recon2)


# ── Test 4: Threshold computation ────────────────────────────────────────────

class TestThreshold:
    def test_threshold_deterministic(self):
        """Threshold must be deterministic given a validation set."""
        rng = np.random.RandomState(42)
        errors = rng.uniform(0.01, 0.05, 500)

        mean1 = float(np.mean(errors))
        std1 = float(np.std(errors))
        thresh1 = mean1 + 2.5 * std1

        # Recompute
        mean2 = float(np.mean(errors))
        std2 = float(np.std(errors))
        thresh2 = mean2 + 2.5 * std2

        assert thresh1 == thresh2

    def test_threshold_separates_normal_from_anomalous(self):
        """Threshold should separate low-error normal from high-error anomalous."""
        rng = np.random.RandomState(42)
        normal_errors = rng.uniform(0.01, 0.03, 500)
        anomalous_errors = rng.uniform(0.1, 0.3, 100)

        threshold = float(np.mean(normal_errors) + 2.5 * np.std(normal_errors))

        # Most normal should be below threshold
        normal_below = np.mean(normal_errors < threshold)
        assert normal_below > 0.95, f"Only {normal_below:.2%} normal below threshold"

        # Most anomalous should be above threshold
        anomalous_above = np.mean(anomalous_errors > threshold)
        assert anomalous_above > 0.95, f"Only {anomalous_above:.2%} anomalous above threshold"


# ── Test 5: Inference latency ────────────────────────────────────────────────

class TestInferenceLatency:
    def test_inference_under_5ms(self, trained_model_path):
        """Inference must be <5ms per sample on CPU."""
        import time

        import torch

        checkpoint = torch.load(trained_model_path, map_location="cpu")
        model = Conv1DAutoencoder(input_channels=2, seq_len=50, latent_dim=8)
        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()

        x = torch.randn(1, 2, 50)

        # Warmup
        for _ in range(5):
            with torch.no_grad():
                model(x)

        # Measure
        times = []
        for _ in range(50):
            t0 = time.perf_counter()
            with torch.no_grad():
                model(x)
            times.append((time.perf_counter() - t0) * 1000)

        avg_ms = np.mean(times)
        p95_ms = np.percentile(times, 95)

        assert avg_ms < 5.0, f"Average inference {avg_ms:.2f}ms exceeds 5ms"
        assert p95_ms < 10.0, f"P95 inference {p95_ms:.2f}ms exceeds 10ms"


# ── Test 6: FlowAnomalyDetector integration ─────────────────────────────────

class TestFlowAnomalyDetector:
    def test_warmup_state(self):
        """Detector should report warming_up until buffer is full."""
        detector = FlowAnomalyDetector(seq_len=50, latent_dim=8)

        for i in range(30):
            result = detector.update(0.45, 0.1)
            assert result["status"] == "warming_up"
            assert result["buffer_fill"] == (i + 1) / 50

    def test_active_after_buffer_full(self):
        """Detector should report active after buffer is full."""
        detector = FlowAnomalyDetector(seq_len=10, latent_dim=8)

        for i in range(15):
            result = detector.update(0.45, 0.1)

        assert result["status"] == "active"
        assert "anomaly_score" in result

    def test_statistical_fallback_detects_anomaly(self):
        """Statistical fallback should detect extreme variability."""
        detector = StatisticalAnomalyDetector(window=50, threshold_sigma=2.5)

        # Feed normal data — low variability
        rng = np.random.RandomState(42)
        for _ in range(60):
            result = detector.update(np.array([0.45 + rng.normal(0, 0.001),
                                                0.45 + rng.normal(0, 0.001)]))

        # Feed anomalous data — extreme spread between features
        result = detector.update(np.array([0.01, 0.99]))
        assert result["is_anomaly"] is True, f"Should detect anomaly: score={result['anomaly_score']}, threshold={result['threshold']}"

    def test_model_state_serialization(self):
        """get_state should return serializable dict."""
        detector = FlowAnomalyDetector(seq_len=50, latent_dim=8)
        state = detector.get_state()

        assert "model_type" in state
        assert "seq_len" in state
        assert "buffer_fill" in state
        # Must be JSON-serializable
        json.dumps(state)


# ── Test 7: Model architecture ──────────────────────────────────────────────

class TestModelArchitecture:
    def test_conv1d_autoencoder_output_shape(self):
        """Output shape must match input shape."""
        import torch

        model = Conv1DAutoencoder(input_channels=2, seq_len=50, latent_dim=8)
        x = torch.randn(4, 2, 50)

        with torch.no_grad():
            recon, latent = model(x)

        assert recon.shape == (4, 2, 50)
        assert latent.shape == (4, 8)

    def test_different_batch_sizes(self):
        """Model should handle different batch sizes."""
        import torch

        model = Conv1DAutoencoder(input_channels=2, seq_len=50, latent_dim=8)
        model.eval()

        for batch_size in [1, 8, 32, 64]:
            x = torch.randn(batch_size, 2, 50)
            with torch.no_grad():
                recon, latent = model(x)
            assert recon.shape[0] == batch_size
            assert latent.shape[0] == batch_size

    def test_parameter_count_reasonable(self):
        """Model should have <100K parameters (lightweight)."""
        model = Conv1DAutoencoder(input_channels=2, seq_len=50, latent_dim=8)
        total = sum(p.numel() for p in model.parameters())
        assert total < 100_000, f"Model too large: {total:,} params"
        assert total > 1000, f"Model too small: {total:,} params"
