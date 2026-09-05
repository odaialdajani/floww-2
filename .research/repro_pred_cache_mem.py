"""Measure the actual RSS/heap cost of the unbounded _pred_cache growth."""
from __future__ import annotations

import sys
import tracemalloc
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

import routes.ml_predict_api as api  # noqa: E402

# Realistic result payload, mirroring the real endpoint response shape
# (services/ml_realtime_features.py:467-484 + _get_top_features top_n=10).
def make_result(mt: str) -> dict:
    return {
        "ticker": "SPY",
        "prediction": "UP",
        "confidence": 0.6123,
        "probabilities": {"down": 0.3877, "up": 0.6123},
        "spot": 528.5,
        "model_type": mt,
        "chain_available": True,
        "chain_meta": {
            "num_contracts": 4820,
            "expiries": [f"2026-09-{d:02d}" for d in range(1, 29)],
            "net_gex": 1.23e9,
            "gex_regime": "positive",
            "king_distance_pct": -0.011,
            "iv_skew": 0.032,
            "put_call_oi_ratio": 1.42,
            "put_call_volume_ratio": 0.98,
        },
        "top_features": {f"feat_{i}_name_long": 0.0123456 for i in range(10)},
        "computed_at": "2026-09-04T12:00:00.123456",
    }


for label, keylen in (("default-length key (32 chars)", 32), ("long key (60000 chars)", 60000)):
    api._pred_cache.clear()
    tracemalloc.start()
    base = tracemalloc.take_snapshot()
    N = 2000
    for _ in range(N):
        mt = (uuid.uuid4().hex * (keylen // 32 + 1))[:keylen]
        api._set_cached_prediction(f"SPY:{mt}", make_result(mt))
    after = tracemalloc.take_snapshot()
    grown = sum(s.size_diff for s in after.compare_to(base, "filename"))
    tracemalloc.stop()
    per = grown / N
    print(f"{label}: {N} entries -> {grown/1024/1024:.2f} MB  ({per:,.0f} B/entry)")
    # 60 req/min per-IP rate limit is the only throttle on /api/ml/predict
    print(f"   at the 60 req/min per-IP cap: {per*60*60/1024/1024:.1f} MB/hour, "
          f"{per*60*60*24/1024/1024:.0f} MB/day -> 1 GB in "
          f"{1024*1024*1024/(per*60*60):.1f} hours")
api._pred_cache.clear()
