"""Adversarial repro: unbounded _pred_cache growth via ?model_type=<arbitrary>.

Exercises the REAL HTTP path (FastAPI Query validation included) with the real
router object from routes.ml_predict_api. Only the live-data dependencies
(feature computation + joblib artifact load) are stubbed, because MongoDB /
Schwab are unavailable in this environment. Nothing about the cache logic is
stubbed.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

import joblib  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import routes.ml_predict_api as api  # noqa: E402
import services.ml_realtime_features as feats_mod  # noqa: E402


class _FakeModel:
    feature_importances_ = np.array([0.7, 0.3])

    def predict(self, X):
        return np.array([1])

    def predict_proba(self, X):
        return np.array([[0.4, 0.6]])


async def fake_compute(ticker: str):
    return {
        "features": {"rsi_14": 55.0, "net_gex": 1.0e9},
        "feature_names": ["rsi_14", "net_gex"],
        "spot": 500.0,
        "chain_available": True,
        # realistic payload size: chain_meta on the real endpoint carries chain
        # metadata; keep it small so the count, not the size, is what we measure
        "chain_meta": {"n_strikes": 240, "expiries": ["2026-09-05", "2026-09-12"]},
        "computed_at": "2026-09-04T00:00:00+00:00",
    }


feats_mod.compute_features_async = fake_compute

_real_exists = os.path.exists


def fake_exists(p):
    s = str(p)
    if s.endswith("price_model_SPY.joblib"):
        return True
    if s.endswith("price_scaler_SPY.joblib") or s.endswith("meta_SPY.json"):
        return False
    return _real_exists(p)


os.path.exists = fake_exists
joblib.load = lambda p: _FakeModel()

app = FastAPI()
app.include_router(api.router)
client = TestClient(app)

print("cache size at start:", len(api._pred_cache))

# --- Attack loop: same ticker, random model_type, 500 requests -------------
accepted = 0
for _ in range(500):
    mt = uuid.uuid4().hex  # arbitrary 32-char string, no enum/regex to stop it
    r = client.get(f"/api/ml/predict/SPY?model_type={mt}")
    if r.status_code == 200:
        accepted += 1

print("HTTP 200 responses:", accepted)
print("cache size after 500 distinct model_type values:", len(api._pred_cache))
print("sample keys:", list(api._pred_cache)[:2])

# --- Does an expired entry ever get evicted? ------------------------------
import time  # noqa: E402

api._pred_cache_ttl_sec = 1
before = len(api._pred_cache)
client.get("/api/ml/predict/SPY?model_type=ttl_probe")
time.sleep(1.2)
stale = api._get_cached_prediction("SPY:ttl_probe")
print("after TTL expiry, _get_cached_prediction returns:", stale)
print("cache size after expiry:", len(api._pred_cache), "(was", before, "+1 =", before + 1, ")")
print("expired key still resident:", "SPY:TTL_PROBE" in api._pred_cache or "SPY:ttl_probe".upper() in api._pred_cache)

# --- Does an unusually long model_type get rejected? ----------------------
huge = "A" * 60_000  # httpx caps the query component at 65536 chars client-side
r = client.get("/api/ml/predict/SPY", params={"model_type": huge})
print("100k-char model_type -> HTTP", r.status_code, "| cache size:", len(api._pred_cache))

# --- Payload weight per entry --------------------------------------------
import pickle  # noqa: E402

one = next(iter(api._pred_cache.values()))
print("bytes per cached entry (pickled, stub payload):", len(pickle.dumps(one)))
