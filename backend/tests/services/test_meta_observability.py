"""
backend/tests/services/test_meta_observability.py

Unit tests for meta_observability — anomaly detection on metrics.

Coverage:
    - Feature extraction produces correct shape
    - Training with insufficient data is a no-op
    - Training with sufficient data produces a model
    - Scoring without model returns model_loaded=False
    - Scoring with model returns anomaly_score
    - Synthetic deviation is detected as anomaly
    - State dict is correct
"""

import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture
def detector():
    """Create a fresh MetaAnomalyDetector with no saved model."""
    from services.meta_observability import MetaAnomalyDetector
    with patch.object(MetaAnomalyDetector, '_load_model'):
        d = MetaAnomalyDetector()
        d._model = None
        d._scaler = None
        d._training_data = []
        yield d


@pytest.fixture
def sample_metrics():
    """Normal-looking metrics snapshot."""
    return {
        "ingestion_rate_spy": 100.0,
        "ingestion_rate_qqq": 50.0,
        "queue_depth": 10.0,
        "vpin_spy": 0.45,
        "vpin_qqq": 0.30,
        "p99_latency": 0.05,
        "ws_connections": 3.0,
        "cache_hit_ratio": 0.95,
        "429_count": 0.0,
    }


def test_feature_extraction_shape(detector, sample_metrics):
    features = detector._extract_features(sample_metrics)
    assert len(features) == 11  # 9 metrics + 2 cyclical time features


def test_feature_extraction_values(detector, sample_metrics):
    features = detector._extract_features(sample_metrics)
    assert features[0] == 100.0  # ingestion_rate_spy
    assert features[2] == 10.0   # queue_depth
    assert features[6] == 3.0    # ws_connections


def test_training_insufficient_data(detector, sample_metrics):
    """Training with < 100 samples should be a no-op."""
    for _ in range(50):
        detector.add_training_sample(sample_metrics)
    assert detector._model is None


def test_training_sufficient_data(detector, sample_metrics):
    """Training with >= 100 samples should produce a model."""
    # Add 200 slightly varied samples
    np.random.seed(42)
    for i in range(200):
        m = dict(sample_metrics)
        m["ingestion_rate_spy"] += np.random.normal(0, 5)
        m["queue_depth"] += np.random.normal(0, 2)
        detector.add_training_sample(m)

    # Force train
    detector.train()
    assert detector._model is not None
    assert detector._scaler is not None


def test_scoring_without_model(detector, sample_metrics):
    """Scoring without a trained model should return model_loaded=False."""
    result = detector.score(sample_metrics)
    assert result["model_loaded"] is False
    assert result["is_anomaly"] is False


def test_scoring_with_model(detector, sample_metrics):
    """Scoring with a trained model should return a score."""
    # Train first
    np.random.seed(42)
    for i in range(200):
        m = dict(sample_metrics)
        m["ingestion_rate_spy"] += np.random.normal(0, 5)
        detector.add_training_sample(m)
    detector.train()

    result = detector.score(sample_metrics)
    assert result["model_loaded"] is True
    assert "anomaly_score" in result
    assert isinstance(result["anomaly_score"], float)


def test_synthetic_deviation_detected(detector, sample_metrics):
    """Inject a synthetic deviation → detector should flag it."""
    np.random.seed(42)
    # Train on normal data
    for i in range(300):
        m = dict(sample_metrics)
        m["ingestion_rate_spy"] += np.random.normal(0, 5)
        m["queue_depth"] += np.random.normal(0, 2)
        detector.add_training_sample(m)
    detector.train()

    # Now inject a deviation
    anomalous = dict(sample_metrics)
    anomalous["ingestion_rate_spy"] = 9999.0  # way too high
    anomalous["queue_depth"] = 9999.0

    result = detector.score(anomalous)
    assert result["model_loaded"] is True
    assert result["is_anomaly"] is True


def test_state_dict(detector, sample_metrics):
    """get_state should return correct fields."""
    state = detector.get_state()
    assert "model_loaded" in state
    assert "training_samples" in state
    assert "last_score" in state
    assert "threshold" in state
    assert state["model_loaded"] is False


def test_training_buffer_cap(detector, sample_metrics):
    """Training buffer should cap at _training_max."""
    detector._training_max = 50
    for _ in range(100):
        detector.add_training_sample(sample_metrics)
    assert len(detector._training_data) == 50


def test_add_training_sample_increments(detector, sample_metrics):
    """Each call to add_training_sample should increment the buffer."""
    detector.add_training_sample(sample_metrics)
    assert len(detector._training_data) == 1
    detector.add_training_sample(sample_metrics)
    assert len(detector._training_data) == 2
