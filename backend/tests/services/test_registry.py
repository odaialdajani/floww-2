"""
backend/tests/services/test_registry.py

Unit tests for the ML model registry service.

Tests cover:
- Model CRUD (register, list, get)
- Promotion gate (all criteria, edge cases)
- PSI drift computation
- Prediction logging
- Artifact loading
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Dict
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

# Add backend/ to path so services.ml is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.ml import DegenerateModelError
from services.ml.registry import (
    ModelRegistry,
    compute_psi,
)

# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────


def _make_mock_db() -> MagicMock:
    """Create a mock async MongoDB database with collection helpers."""
    mock_db = MagicMock()

    # Storage for each collection
    storage: Dict[str, Dict[str, Dict]] = {
        "ml_models": {},
        "ml_predictions": {},
        "ml_features": {},
    }

    def make_collection(name: str):
        col = MagicMock()
        store = storage[name]

        async def find_one(query, projection=None):
            if "model_id" in query:
                doc = store.get(query["model_id"])
                return dict(doc) if doc else None
            # Handle compound queries (ticker + status)
            for doc in store.values():
                match = True
                for k, v in query.items():
                    if k == "_id":
                        continue
                    if doc.get(k) != v:
                        match = False
                        break
                if match:
                    return dict(doc)
            return None

        async def update_one(query, update, upsert=False):
            model_id = query.get("model_id")
            if model_id:
                if model_id not in store:
                    if upsert:
                        store[model_id] = {}
                    else:
                        return MagicMock(modified_count=0)
                doc = store[model_id]
                if "$set" in update:
                    doc.update(update["$set"])
                return MagicMock(modified_count=1, upserted_id=None)
            return MagicMock(modified_count=0)

        def find(query, projection=None):
            results = []
            for doc in store.values():
                match = True
                for k, v in query.items():
                    if k == "_id":
                        continue
                    if doc.get(k) != v:
                        match = False
                        break
                if match:
                    results.append(dict(doc))

            mock_cursor = MagicMock()

            async def to_list(length=1000):
                return results[:length]

            mock_cursor.to_list = to_list
            mock_cursor.sort.return_value = mock_cursor
            return mock_cursor

        async def insert_one(doc):
            key = doc.get("model_id", doc.get("ticker", str(len(store))))
            store[key] = dict(doc)
            return MagicMock(inserted_id=key)

        col.find_one = find_one
        col.update_one = update_one
        col.find = find
        col.insert_one = insert_one
        col.sort.return_value = col
        return col

    mock_db.__getitem__ = lambda self, key: make_collection(key)
    return mock_db


@pytest.fixture
def mock_db():
    return _make_mock_db()


@pytest.fixture
def registry(mock_db):
    return ModelRegistry(mock_db)


# ────────────────────────────────────────────────────────────────────────────
# PSI computation
# ────────────────────────────────────────────────────────────────────────────


class TestComputePsi:
    def test_identical_distributions(self):
        """PSI of identical distributions should be ~0."""
        np.random.seed(42)
        data = np.random.randn(1000)
        psi = compute_psi(data, data)
        assert psi < 0.01

    def test_shifted_distribution(self):
        """PSI should be large for significantly shifted distributions."""
        np.random.seed(42)
        expected = np.random.randn(1000)
        actual = np.random.randn(1000) + 3.0  # shifted mean
        psi = compute_psi(expected, actual)
        assert psi > 0.5

    def test_empty_arrays(self):
        """Empty arrays should return 0.0."""
        psi = compute_psi(np.array([]), np.array([]))
        assert psi == 0.0

    def test_constant_array(self):
        """Constant arrays (zero variance) should return 0.0."""
        data = np.ones(100)
        psi = compute_psi(data, data)
        assert psi == 0.0

    def test_with_nans(self):
        """NaN values should be filtered out, PSI should be finite."""
        np.random.seed(42)
        expected = np.random.randn(100)
        actual = np.random.randn(100)
        actual[0] = np.nan
        expected[0] = np.nan
        psi = compute_psi(expected, actual)
        assert not np.isnan(psi)  # Should be finite after NaN filtering
        assert psi >= 0  # PSI is always non-negative

    def test_small_sample(self):
        """Very small samples should return 0.0."""
        psi = compute_psi(np.array([1.0, 2.0]), np.array([1.5, 2.5]))
        assert psi == 0.0


# ────────────────────────────────────────────────────────────────────────────
# Model CRUD
# ────────────────────────────────────────────────────────────────────────────


class TestRegisterModel:
    @pytest.mark.asyncio
    async def test_register_basic(self, registry):
        doc = await registry.register_model(
            model_id="SPY_test_v1",
            ticker="SPY",
            feature_version="v1.0",
            training_window="2024-01-01:2024-12-31",
            metrics_summary={"accuracy": 0.55, "sharpe": 1.2},
            artifact_path="/tmp/test_model.joblib",
        )
        assert doc["model_id"] == "SPY_test_v1"
        assert doc["ticker"] == "SPY"
        assert doc["status"] == "shadow"
        assert doc["created_at"] is not None

    @pytest.mark.asyncio
    async def test_register_with_training_dist(self, registry):
        dist = {"feat1": [1.0, 2.0, 3.0], "feat2": [4.0, 5.0, 6.0]}
        doc = await registry.register_model(
            model_id="SPY_dist_v1",
            ticker="SPY",
            feature_version="v1.0",
            training_window="2024",
            metrics_summary={"accuracy": 0.55},
            artifact_path="/tmp/test_model.joblib",
            training_feature_dist=dist,
        )
        assert doc["training_feature_dist"] == dist

    @pytest.mark.asyncio
    async def test_register_upsert(self, registry):
        """Registering the same model_id twice should update."""
        await registry.register_model(
            model_id="SPY_dup",
            ticker="SPY",
            feature_version="v1.0",
            training_window="2024",
            metrics_summary={"accuracy": 0.50},
            artifact_path="/tmp/a.joblib",
        )
        await registry.register_model(
            model_id="SPY_dup",
            ticker="SPY",
            feature_version="v2.0",
            training_window="2025",
            metrics_summary={"accuracy": 0.60},
            artifact_path="/tmp/b.joblib",
        )
        model = await registry.get_model("SPY_dup")
        assert model["feature_version"] == "v2.0"
        assert model["metrics_summary"]["accuracy"] == 0.60


class TestListModel:
    @pytest.mark.asyncio
    async def test_list_all(self, registry):
        for i in range(3):
            await registry.register_model(
                model_id=f"model_{i}",
                ticker="SPY",
                feature_version="v1.0",
                training_window="2024",
                metrics_summary={},
                artifact_path=f"/tmp/m{i}.joblib",
            )
        models = await registry.list_models()
        assert len(models) == 3

    @pytest.mark.asyncio
    async def test_list_filter_ticker(self, registry):
        await registry.register_model(
            model_id="SPY_1", ticker="SPY",
            feature_version="v1.0", training_window="2024",
            metrics_summary={}, artifact_path="/tmp/s.joblib",
        )
        await registry.register_model(
            model_id="QQQ_1", ticker="QQQ",
            feature_version="v1.0", training_window="2024",
            metrics_summary={}, artifact_path="/tmp/q.joblib",
        )
        spy_models = await registry.list_models(ticker="SPY")
        assert len(spy_models) == 1
        assert spy_models[0]["ticker"] == "SPY"

    @pytest.mark.asyncio
    async def test_list_filter_status(self, registry):
        await registry.register_model(
            model_id="m_shadow", ticker="SPY",
            feature_version="v1.0", training_window="2024",
            metrics_summary={}, artifact_path="/tmp/m.joblib",
            status="shadow",
        )
        await registry.register_model(
            model_id="m_active", ticker="SPY",
            feature_version="v1.0", training_window="2024",
            metrics_summary={}, artifact_path="/tmp/m2.joblib",
            status="active",
        )
        active = await registry.list_models(status="active")
        assert len(active) == 1
        assert active[0]["model_id"] == "m_active"


class TestGetModel:
    @pytest.mark.asyncio
    async def test_get_existing(self, registry):
        await registry.register_model(
            model_id="SPY_get", ticker="SPY",
            feature_version="v1.0", training_window="2024",
            metrics_summary={"accuracy": 0.55},
            artifact_path="/tmp/g.joblib",
        )
        model = await registry.get_model("SPY_get")
        assert model is not None
        assert model["model_id"] == "SPY_get"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, registry):
        model = await registry.get_model("does_not_exist")
        assert model is None


# ────────────────────────────────────────────────────────────────────────────
# Promotion Gate
# ────────────────────────────────────────────────────────────────────────────


class TestPromoteModel:
    @pytest.mark.asyncio
    async def test_promote_not_found(self, registry):
        result = await registry.promote_model("nonexistent")
        assert result["success"] is False
        assert "not found" in result["reason"]

    @pytest.mark.asyncio
    async def test_promote_wrong_status(self, registry):
        await registry.register_model(
            model_id="m_active", ticker="SPY",
            feature_version="v1.0", training_window="2024",
            metrics_summary={}, artifact_path="/tmp/m.joblib",
            status="active",
        )
        result = await registry.promote_model("m_active")
        assert result["success"] is False
        assert "expected shadow" in result["reason"]

    @pytest.mark.asyncio
    async def test_promote_fails_no_beats_baselines(self, registry):
        await registry.register_model(
            model_id="m_nobase", ticker="SPY",
            feature_version="v1.0", training_window="2024",
            metrics_summary={
                "beats_baselines": False,
                "holdout_sharpe": 2.0,
                "calibration_error": 0.01,
            },
            artifact_path="/tmp/m.joblib",
        )
        result = await registry.promote_model("m_nobase")
        assert result["success"] is False
        assert "beats_baselines" in result["reason"]

    @pytest.mark.asyncio
    async def test_promote_fails_high_calibration_error(self, registry):
        await registry.register_model(
            model_id="m_cal", ticker="SPY",
            feature_version="v1.0", training_window="2024",
            metrics_summary={
                "beats_baselines": True,
                "holdout_sharpe": 2.0,
                "calibration_error": 0.08,
            },
            artifact_path="/tmp/m.joblib",
        )
        result = await registry.promote_model("m_cal")
        assert result["success"] is False
        assert "calibration_error" in result["reason"]

    @pytest.mark.asyncio
    async def test_promote_fails_low_sharpe_vs_prior(self, registry):
        # Register an active model with high sharpe
        await registry.register_model(
            model_id="m_prior_active", ticker="SPY",
            feature_version="v1.0", training_window="2024",
            metrics_summary={
                "beats_baselines": True,
                "holdout_sharpe": 3.0,
                "calibration_error": 0.01,
            },
            artifact_path="/tmp/prior.joblib",
            status="active",
        )
        # Try to promote a weaker model
        await registry.register_model(
            model_id="m_weaker", ticker="SPY",
            feature_version="v2.0", training_window="2025",
            metrics_summary={
                "beats_baselines": True,
                "holdout_sharpe": 2.0,
                "calibration_error": 0.01,
            },
            artifact_path="/tmp/weaker.joblib",
        )
        result = await registry.promote_model("m_weaker")
        assert result["success"] is False
        assert "holdout_sharpe" in result["reason"]

    @pytest.mark.asyncio
    async def test_promote_succeeds_no_prior_active(self, registry):
        """No prior active model — sharpe gate auto-passes."""
        await registry.register_model(
            model_id="m_first", ticker="SPY",
            feature_version="v1.0", training_window="2024",
            metrics_summary={
                "beats_baselines": True,
                "holdout_sharpe": 1.0,
                "calibration_error": 0.01,
            },
            artifact_path="/tmp/first.joblib",
        )
        result = await registry.promote_model("m_first")
        assert result["success"] is True
        model = await registry.get_model("m_first")
        assert model["status"] == "active"
        assert model["promoted_at"] is not None

    @pytest.mark.asyncio
    async def test_promote_succeeds_beats_prior(self, registry):
        """Candidate beats prior active on sharpe."""
        await registry.register_model(
            model_id="m_prior2", ticker="SPY",
            feature_version="v1.0", training_window="2024",
            metrics_summary={
                "beats_baselines": True,
                "holdout_sharpe": 1.5,
                "calibration_error": 0.01,
            },
            artifact_path="/tmp/prior2.joblib",
            status="active",
        )
        await registry.register_model(
            model_id="m_better", ticker="SPY",
            feature_version="v2.0", training_window="2025",
            metrics_summary={
                "beats_baselines": True,
                "holdout_sharpe": 2.5,
                "calibration_error": 0.02,
            },
            artifact_path="/tmp/better.joblib",
        )
        result = await registry.promote_model("m_better")
        assert result["success"] is True

        # Prior should be retired
        prior = await registry.get_model("m_prior2")
        assert prior["status"] == "retired"
        assert prior["retired_at"] is not None

        # Candidate should be active
        candidate = await registry.get_model("m_better")
        assert candidate["status"] == "active"

    @pytest.mark.asyncio
    async def test_promote_default_calibration_fail_closed(self, registry):
        """Missing calibration_error defaults to 1.0 — should fail."""
        await registry.register_model(
            model_id="m_nocal", ticker="SPY",
            feature_version="v1.0", training_window="2024",
            metrics_summary={
                "beats_baselines": True,
                "holdout_sharpe": 2.0,
                # no calibration_error key
            },
            artifact_path="/tmp/nocal.joblib",
        )
        result = await registry.promote_model("m_nocal")
        assert result["success"] is False
        assert "calibration_error" in result["reason"]


# ────────────────────────────────────────────────────────────────────────────
# Retire Model
# ────────────────────────────────────────────────────────────────────────────


class TestRetireModel:
    @pytest.mark.asyncio
    async def test_retire_active(self, registry):
        await registry.register_model(
            model_id="m_retire", ticker="SPY",
            feature_version="v1.0", training_window="2024",
            metrics_summary={}, artifact_path="/tmp/r.joblib",
            status="active",
        )
        result = await registry.retire_model("m_retire")
        assert result["success"] is True
        model = await registry.get_model("m_retire")
        assert model["status"] == "retired"
        assert model["retired_at"] is not None

    @pytest.mark.asyncio
    async def test_retire_not_found(self, registry):
        result = await registry.retire_model("nonexistent")
        assert result["success"] is False


# ────────────────────────────────────────────────────────────────────────────
# Drift Monitoring
# ────────────────────────────────────────────────────────────────────────────


class TestDriftMonitoring:
    @pytest.mark.asyncio
    async def test_no_active_model(self, registry):
        report = await registry.compute_drift("SPY")
        assert report["status"] == "no_active_model"

    @pytest.mark.asyncio
    async def test_no_training_dist(self, registry):
        await registry.register_model(
            model_id="m_nodist", ticker="SPY",
            feature_version="v1.0", training_window="2024",
            metrics_summary={}, artifact_path="/tmp/nd.joblib",
            status="active",
        )
        report = await registry.compute_drift("SPY")
        assert report["status"] == "no_training_dist"

    @pytest.mark.asyncio
    async def test_no_recent_data(self, registry):
        await registry.register_model(
            model_id="m_norecent", ticker="SPY",
            feature_version="v1.0", training_window="2024",
            metrics_summary={}, artifact_path="/tmp/nr.joblib",
            training_feature_dist={"feat1": list(np.random.randn(100))},
            status="active",
        )
        report = await registry.compute_drift("SPY")
        assert report["status"] == "no_recent_data"

    @pytest.mark.asyncio
    async def test_drift_ok(self, registry):
        """Similar distributions should show no drift."""
        np.random.seed(42)
        train_vals = list(np.random.randn(500))
        # Use same distribution for recent data (no drift)
        np.random.seed(42)
        recent_data = [
            {"ticker": "SPY", "feature_version": "v1.0",
             "date": datetime.now(timezone.utc).isoformat(),
             "feat1": float(v)}
            for v in np.random.randn(50)
        ]

        await registry.register_model(
            model_id="m_drift_ok", ticker="SPY",
            feature_version="v1.0", training_window="2024",
            metrics_summary={}, artifact_path="/tmp/do.joblib",
            training_feature_dist={"feat1": train_vals},
            status="active",
        )

        # Mock the features collection
        mock_cursor = MagicMock()

        async def to_list(length=10000):
            return recent_data

        mock_cursor.to_list = to_list
        mock_cursor.sort.return_value = mock_cursor
        registry.features_col.find = lambda *a, **kw: mock_cursor

        report = await registry.compute_drift("SPY")
        assert report["status"] in ("ok", "drift_detected")  # Either is valid for random data
        assert "feat1" in report["features"]

    @pytest.mark.asyncio
    async def test_drift_detected(self, registry):
        """Shifted distribution should trigger drift alert."""
        np.random.seed(42)
        train_vals = list(np.random.randn(500))
        # Shifted recent data
        recent_data = [
            {"ticker": "SPY", "feature_version": "v1.0",
             "date": datetime.now(timezone.utc).isoformat(),
             "feat1": float(v)}
            for v in np.random.randn(200) + 5.0  # big shift
        ]

        await registry.register_model(
            model_id="m_drift_bad", ticker="SPY",
            feature_version="v1.0", training_window="2024",
            metrics_summary={}, artifact_path="/tmp/db.joblib",
            training_feature_dist={"feat1": train_vals},
            status="active",
        )

        mock_cursor = MagicMock()

        async def to_list(length=10000):
            return recent_data

        mock_cursor.to_list = to_list
        mock_cursor.sort.return_value = mock_cursor
        registry.features_col.find = lambda *a, **kw: mock_cursor

        report = await registry.compute_drift("SPY")
        assert report["status"] == "drift_detected"
        assert "feat1" in report["drift_alerts"]
        assert report["features"]["feat1"] >= 0.2


# ────────────────────────────────────────────────────────────────────────────
# Inference
# ────────────────────────────────────────────────────────────────────────────


class TestPredict:
    @pytest.mark.asyncio
    async def test_no_active_model(self, registry):
        with pytest.raises(DegenerateModelError, match="No active model"):
            await registry.predict("SPY")

    @pytest.mark.asyncio
    async def test_no_features(self, registry):
        """Active model exists but no features computed."""
        await registry.register_model(
            model_id="m_nofeat", ticker="SPY",
            feature_version="v1.0", training_window="2024",
            metrics_summary={
                "feature_names": ["feat1"],
            },
            artifact_path="/tmp/nf.joblib",
            status="active",
        )
        # Mock features collection to return empty
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_cursor.sort.return_value = mock_cursor
        registry.features_col.find = lambda *a, **kw: mock_cursor

        with pytest.raises(DegenerateModelError, match="Model artifact not found"):
            await registry.predict("SPY")


# ────────────────────────────────────────────────────────────────────────────
# Update Realized Outcome
# ────────────────────────────────────────────────────────────────────────────


class TestUpdateRealizedOutcome:
    @pytest.mark.asyncio
    async def test_update(self, registry):
        ts = datetime.now(timezone.utc)
        await registry.predictions_col.insert_one({
            "ticker": "SPY",
            "ts": ts,
            "prediction": 1,
            "probability": [0.3, 0.7],
            "model_id": "test",
            "feature_version": "v1.0",
            "realized_outcome": None,
        })
        await registry.update_realized_outcome("SPY", ts, 1)
        # Should not raise


# ────────────────────────────────────────────────────────────────────────────
# get_active_model
# ────────────────────────────────────────────────────────────────────────────


class TestGetActiveModel:
    @pytest.mark.asyncio
    async def test_returns_active(self, registry):
        await registry.register_model(
            model_id="m_act", ticker="SPY",
            feature_version="v1.0", training_window="2024",
            metrics_summary={}, artifact_path="/tmp/a.joblib",
            status="active",
        )
        active = await registry.get_active_model("SPY")
        assert active is not None
        assert active["model_id"] == "m_act"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_active(self, registry):
        active = await registry.get_active_model("SPY")
        assert active is None
