"""
backend/tests/routes/test_ml_predict_cache.py

Pins the caching contract of GET /api/ml/predict/{ticker}:

1. Within the 60s TTL, a repeat request must be served from the prediction
   cache (no feature recompute, no model reload). The cache helpers existed
   (_get/_set_cached_prediction) but were never wired — round-10 audit.
2. The joblib model load must be cached keyed on (path, mtime): same mtime
   loads once; an mtime bump forces a reload (fresh retrain picked up).
3. The prediction cache key must include model_type (gbm vs logistic must
   not collide).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import routes.ml_predict_api as api
import services.ml_realtime_features as feats_mod


class _FakeModel:
    def predict(self, X):
        return np.array([1])

    def predict_proba(self, X):
        return np.array([[0.4, 0.6]])


class _Counters:
    def __init__(self):
        self.compute_calls = 0
        self.load_calls = 0


@pytest.fixture()
def fakes(monkeypatch):
    """Stub the feature computation, filesystem, and joblib load."""
    counters = _Counters()

    async def fake_compute(ticker: str):
        counters.compute_calls += 1
        return {
            "features": {"rsi_14": 55.0, "net_gex": 1.0e9},
            "feature_names": ["rsi_14", "net_gex"],
            "spot": 500.0,
            "chain_available": True,
            "chain_meta": {},
            "computed_at": "2026-07-20T00:00:00+00:00",
        }

    monkeypatch.setattr(feats_mod, "compute_features_async", fake_compute)

    real_exists = os.path.exists
    real_getmtime = os.path.getmtime

    def fake_exists(p):
        s = str(p)
        if s.endswith("price_model_SPY.joblib"):
            return True
        if s.endswith("price_scaler_SPY.joblib") or s.endswith("meta_SPY.json"):
            return False
        return real_exists(p)

    def fake_getmtime(p):
        if str(p).endswith("price_model_SPY.joblib"):
            return 1000.0
        return real_getmtime(p)

    monkeypatch.setattr(os.path, "exists", fake_exists)
    monkeypatch.setattr(os.path, "getmtime", fake_getmtime)

    import joblib

    def fake_load(p):
        counters.load_calls += 1
        return _FakeModel()

    monkeypatch.setattr(joblib, "load", fake_load)

    # Isolate module-level caches between tests
    api._pred_cache.clear()
    if hasattr(api, "_model_cache"):
        api._model_cache.clear()
    yield counters
    api._pred_cache.clear()
    if hasattr(api, "_model_cache"):
        api._model_cache.clear()


@pytest.mark.asyncio
async def test_repeat_request_hits_prediction_cache(fakes):
    """Second identical request inside the TTL must not recompute or reload."""
    r1 = await api.predict_direction("SPY", model_type="gbm")
    r2 = await api.predict_direction("SPY", model_type="gbm")

    assert r1["prediction"] == r2["prediction"]
    assert fakes.compute_calls == 1, "features recomputed despite fresh cache"
    assert fakes.load_calls == 1, "model reloaded despite fresh cache"


@pytest.mark.asyncio
async def test_prediction_cache_keyed_by_model_type(fakes):
    """gbm and logistic must not share a cache entry."""
    await api.predict_direction("SPY", model_type="gbm")
    r2 = await api.predict_direction("SPY", model_type="logistic")

    assert fakes.compute_calls == 2
    assert r2["model_type"] == "logistic"


@pytest.mark.asyncio
async def test_model_reloaded_when_mtime_changes(fakes, monkeypatch):
    """A retrain (new file mtime) must invalidate the cached model."""
    path = "whatever/price_model_SPY.joblib"
    api._load_model_cached(path)
    api._load_model_cached(path)
    assert fakes.load_calls == 1, "same mtime must load from cache"

    real_getmtime = os.path.getmtime

    def bumped(p):
        if str(p).endswith("price_model_SPY.joblib"):
            return 2000.0
        return real_getmtime(p)

    monkeypatch.setattr(os.path, "getmtime", bumped)
    api._load_model_cached(path)
    assert fakes.load_calls == 2, "mtime bump must force a reload"
