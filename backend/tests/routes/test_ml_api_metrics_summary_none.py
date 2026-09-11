"""Regression: a stored model doc with metrics_summary=None must not 500.

`dict.get(key, default)` only returns the default when the key is ABSENT. A
model document that stores an explicit `metrics_summary: null` therefore
yielded `None.get("feature_names", ...)` → AttributeError. In
`get_ensemble` that call site sits OUTSIDE any try/except, so the endpoint
answered HTTP 500 instead of a score.

Ported from the upstream fork's fix and pinned here. This test FAILS against
`model_doc.get("metrics_summary", {}).get(...)` and PASSES against
`(model_doc.get("metrics_summary") or {}).get(...)`.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from routes import ml_api  # noqa: E402


def _features_df() -> pd.DataFrame:
    """12 numeric feature columns so the >= 10 available-features gate passes."""
    return pd.DataFrame({f"f{i}": [float(i), float(i) + 1.0] for i in range(12)})


@pytest.mark.asyncio
async def test_ensemble_survives_null_metrics_summary():
    model_doc = {
        "model_id": "SPY_test_model",
        "feature_version": "v1",
        # The whole point: an explicit null, not a missing key.
        "metrics_summary": None,
    }

    class _Model:
        def predict_proba(self, X):
            return [[0.4, 0.6]]

    registry = AsyncMock()
    registry._load_active_artifact = AsyncMock(return_value=(_Model(), None, model_doc))
    registry._compute_latest_features = AsyncMock(return_value=_features_df())

    with patch.object(ml_api, "_get_registry", AsyncMock(return_value=registry)):
        out = await ml_api.get_ensemble("SPY", horizon_minutes=15)

    # The call must complete and produce a real payload rather than raising
    # AttributeError up into a 500.
    assert isinstance(out, dict)
    assert out.get("ticker") == "SPY"


def test_source_has_no_unsafe_metrics_summary_get():
    """Guard the pattern itself so the fix cannot be silently reverted."""
    src = Path(ml_api.__file__).read_text(encoding="utf-8")
    assert 'get("metrics_summary", {})' not in src, (
        'routes/ml_api.py must use (model_doc.get("metrics_summary") or {}) — '
        "the two-arg .get default does not fire on a stored null."
    )
