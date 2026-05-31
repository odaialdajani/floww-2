"""
tests/services/ml/test_retrain.py

Tests for the auto-retrain orchestrator.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.ml.retrain import RetrainOrchestrator


@pytest.fixture
def mock_col():
    """Create a mock collection with async find_one."""
    col = MagicMock()
    col._find_one_return = None

    async def mock_find_one(*args, **kwargs):
        return col._find_one_return

    col.find_one = mock_find_one
    col.insert_one = AsyncMock()
    col.update_one = AsyncMock()
    return col


@pytest.fixture
def mock_db(mock_col):
    db = MagicMock()
    collections = {
        "ml_retrain": mock_col,
        "ml_models": mock_col,
        "ml_predictions": mock_col,
        "snapshots": mock_col,
        "gex_enhanced_snapshots": mock_col,
    }
    db.__getitem__ = lambda self, key: collections.get(key, mock_col)
    for k, v in collections.items():
        db[k] = v
    return db


@pytest.fixture
def orchestrator(mock_db):
    return RetrainOrchestrator(mock_db)


class TestIsRetrainInFlight:
    @pytest.mark.asyncio
    async def test_no_active_retrain(self, orchestrator, mock_col):
        mock_col._find_one_return = None
        result = await orchestrator.is_retrain_in_flight("SPY")
        assert result is False

    @pytest.mark.asyncio
    async def test_active_retrain_exists(self, orchestrator, mock_col):
        mock_col._find_one_return = {"ticker": "SPY", "status": "running"}
        result = await orchestrator.is_retrain_in_flight("SPY")
        assert result is True

    @pytest.mark.asyncio
    async def test_pending_retrain_exists(self, orchestrator, mock_col):
        mock_col._find_one_return = {"ticker": "SPY", "status": "pending"}
        result = await orchestrator.is_retrain_in_flight("SPY")
        assert result is True


class TestIsRetrainOnCooldown:
    @pytest.mark.asyncio
    async def test_no_recent_retrain(self, orchestrator, mock_col):
        mock_col._find_one_return = None
        result = await orchestrator.is_retrain_on_cooldown("SPY")
        assert result is False

    @pytest.mark.asyncio
    async def test_recent_retrain_exists(self, orchestrator, mock_col):
        mock_col._find_one_return = {
            "ticker": "SPY",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        result = await orchestrator.is_retrain_on_cooldown("SPY")
        assert result is True


class TestDetectDrift:
    @pytest.mark.asyncio
    async def test_no_drift(self, orchestrator):
        with patch("services.ml.registry.ModelRegistry") as MockRegistry:
            mock_registry = AsyncMock()
            mock_registry.compute_drift.return_value = {
                "status": "ok",
                "n_recent_samples": 50,
                "features": {"feat1": 0.1},
            }
            MockRegistry.return_value = mock_registry
            result = await orchestrator.detect_drift("SPY")
            assert result["drift_detected"] is False
            assert result["n_samples"] == 50

    @pytest.mark.asyncio
    async def test_drift_detected(self, orchestrator):
        with patch("services.ml.registry.ModelRegistry") as MockRegistry:
            mock_registry = AsyncMock()
            mock_registry.compute_drift.return_value = {
                "status": "drift_detected",
                "n_recent_samples": 50,
                "features": {"feat1": 0.3, "feat2": 0.1},
            }
            MockRegistry.return_value = mock_registry
            result = await orchestrator.detect_drift("SPY")
            assert result["drift_detected"] is True
            assert result["n_drift"] == 1

    @pytest.mark.asyncio
    async def test_no_active_model(self, orchestrator):
        from services.ml import DegenerateModelError
        with patch("services.ml.registry.ModelRegistry") as MockRegistry:
            mock_registry = AsyncMock()
            mock_registry.compute_drift.side_effect = DegenerateModelError("no active model")
            MockRegistry.return_value = mock_registry
            result = await orchestrator.detect_drift("SPY")
            assert result["drift_detected"] is False


class TestExtractSnapshotFeatures:
    def test_valid_snapshot(self, orchestrator):
        snapshot = {
            "spot": 450.0, "ts": "2024-01-15T10:00:00",
            "total_gex": 1000000, "net_gex": -500000,
            "king_strike": 450, "king_gex": 200000,
            "top_floor": 445, "top_ceiling": 455,
            "num_strikes": 100, "regime": "POSITIVE",
            "strikes_compact": [
                {"strike": 445, "gex": 100000},
                {"strike": 450, "gex": 200000},
                {"strike": 455, "gex": -150000},
            ],
        }
        result = orchestrator._extract_snapshot_features(snapshot)
        assert result is not None
        assert result["spot"] == 450.0
        assert result["regime_positive"] == 1.0
        assert result["regime_negative"] == 0.0

    def test_no_spot(self, orchestrator):
        result = orchestrator._extract_snapshot_features({"spot": 0})
        assert result is None

    def test_negative_regime(self, orchestrator):
        snapshot = {"spot": 450.0, "ts": "2024-01-15", "regime": "NEGATIVE", "strikes_compact": []}
        result = orchestrator._extract_snapshot_features(snapshot)
        assert result["regime_positive"] == 0.0
        assert result["regime_negative"] == 1.0

    def test_no_strikes_compact(self, orchestrator):
        snapshot = {"spot": 450.0, "ts": "2024-01-15", "regime": "POSITIVE"}
        result = orchestrator._extract_snapshot_features(snapshot)
        assert result["gex_mean"] == 0.0


class TestCheckAndRetrain:
    @pytest.mark.asyncio
    async def test_skips_when_in_flight(self, orchestrator, mock_col):
        mock_col._find_one_return = {"status": "running"}
        result = await orchestrator.check_and_retrain("SPY")
        assert result["action"] == "in_flight"

    @pytest.mark.asyncio
    async def test_no_drift_no_action(self, orchestrator, mock_col):
        mock_col._find_one_return = None
        with patch.object(orchestrator, "detect_drift", return_value={"drift_detected": False, "n_samples": 10}):
            result = await orchestrator.check_and_retrain("SPY")
            assert result["action"] == "no_drift"
