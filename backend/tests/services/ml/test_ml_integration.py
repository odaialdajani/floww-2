"""
backend/tests/services/ml/test_ml_integration.py

Integration tests for the ML pipeline.
- Verifies every PRODUCTION model file on disk loads and has .predict
- Verifies each model's manifest has required fields
- Smoke-tests the InferenceEngine contract and 3-class prediction system
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import joblib
import pytest


def _models_dir() -> Path:
    here = Path(__file__).resolve()
    return here.parents[3] / "models"


def _production_models() -> list[Path]:
    """Return production model files (_production.joblib, not _rf_ or price_model)."""
    models_dir = _models_dir()
    return sorted([
        f for f in models_dir.glob("*_production.joblib")
        if "_scaler" not in f.name
    ])


def _find_manifest(model_path: Path) -> Path | None:
    for suffix in ("_manifest.json", "_meta.json"):
        cand = model_path.with_name(model_path.stem + suffix)
        if cand.exists():
            return cand
    return None


def _load_model(model_path: Path):
    """Load a model, handling both raw sklearn and dict-artifact formats."""
    artifact = joblib.load(str(model_path))
    if isinstance(artifact, dict) and "model" in artifact:
        return artifact["model"]
    return artifact


ALL_MODELS = _production_models()


@pytest.mark.parametrize("model_file", ALL_MODELS, ids=[p.name for p in ALL_MODELS])
def test_model_loads_with_joblib(model_file):
    model = _load_model(model_file)
    assert model is not None
    assert hasattr(model, "predict"), f"{model_file.name} has no .predict"


@pytest.mark.parametrize("model_file", ALL_MODELS, ids=[p.name for p in ALL_MODELS])
def test_manifest_exists_for_model(model_file):
    manifest = _find_manifest(model_file)
    assert manifest is not None, f"{model_file.name} has no manifest"


REQUIRED_FIELDS = {"feature_names", "ticker"}


@pytest.mark.parametrize("model_file", ALL_MODELS, ids=[p.name for p in ALL_MODELS])
def test_manifest_has_required_fields(model_file):
    manifest = _find_manifest(model_file)
    if manifest is None:
        pytest.skip("no manifest")
    with open(manifest) as f:
        data = json.load(f)
    missing = REQUIRED_FIELDS - set(data.keys())
    assert not missing, f"{model_file.name} missing: {missing}"


@pytest.mark.parametrize("model_file", ALL_MODELS, ids=[p.name for p in ALL_MODELS])
def test_manifest_feature_count_matches_model(model_file):
    model = _load_model(model_file)
    manifest = _find_manifest(model_file)
    if manifest is None:
        pytest.skip("no manifest")
    with open(manifest) as f:
        data = json.load(f)
    manifest_n = len(data.get("feature_names", []))
    model_n = getattr(model, "n_features_in_", None)
    if model_n is None:
        pytest.skip("n_features_in_ unavailable")
    assert manifest_n == model_n


def test_registry_exists():
    from services.ml.inference import MODEL_REGISTRY
    assert isinstance(MODEL_REGISTRY, dict)
    assert len(MODEL_REGISTRY) >= 4


def test_registry_tickers_have_models_on_disk():
    from services.ml.inference import MODEL_REGISTRY
    models_dir = _models_dir()
    for ticker, entry in MODEL_REGISTRY.items():
        if isinstance(entry, tuple):
            model_file = Path(entry[0])
        else:
            model_file = Path(entry)
        if not model_file.is_absolute():
            model_file = models_dir / model_file.name
        if not model_file.exists():
            ticker_models = list(models_dir.glob(f"{ticker}_*.joblib"))
            assert ticker_models, f"{ticker} in MODEL_REGISTRY but no model on disk"


@pytest.fixture(autouse=True)
def mock_external_modules():
    motor_mock = types.ModuleType("motor")
    motor_mock.motor_asyncio = types.ModuleType("motor.motor_asyncio")
    motor_mock.motor_asyncio.AsyncIOMotorClient = type("FakeClient", (), {})
    sys.modules["motor"] = motor_mock
    sys.modules["motor.motor_asyncio"] = motor_mock.motor_asyncio
    dm = types.ModuleType("dotenv")
    dm.load_dotenv = lambda *a, **kw: None
    sys.modules["dotenv"] = dm
    yield
    for k in list(sys.modules):
        if k.startswith(("motor", "dotenv")):
            sys.modules.pop(k, None)


def test_class_labels_3way():
    from services.ml.inference import CLASS_LABELS
    assert isinstance(CLASS_LABELS, dict)
    assert set(CLASS_LABELS.keys()) == {0, 1, 2}
    assert CLASS_LABELS[0] == "DOWN"
    assert CLASS_LABELS[1] == "HOLD"
    assert CLASS_LABELS[2] == "UP"


def test_strong_confidence_threshold():
    from services.ml.inference import STRONG_CONFIDENCE
    assert 0.5 < STRONG_CONFIDENCE < 1.0


def test_map_binary_to_3way_strong_bullish():
    from services.ml.inference import UP, _map_binary_to_3way
    pred, probs = _map_binary_to_3way(1, [0.2, 0.8])
    assert pred == UP
    assert abs(probs[2] - 0.8) < 0.01
    assert abs(sum(probs) - 1.0) < 0.01


def test_map_binary_to_3way_strong_bearish():
    from services.ml.inference import DOWN, _map_binary_to_3way
    pred, probs = _map_binary_to_3way(0, [0.9, 0.1])
    assert pred == DOWN
    assert abs(probs[0] - 0.9) < 0.01
    assert abs(sum(probs) - 1.0) < 0.01


def test_map_binary_to_3way_hold_zone():
    from services.ml.inference import HOLD, _map_binary_to_3way
    pred, probs = _map_binary_to_3way(1, [0.45, 0.55])
    assert probs[1] >= 0.0
    assert abs(sum(probs) - 1.0) < 0.01
    assert all(0 <= p <= 1 for p in probs)


def test_prediction_result_dataclass():
    from services.ml.inference import PredictionResult
    r = PredictionResult(
        ticker="SPY", prediction=2, confidence=0.8,
        probabilities=[0.1, 0.1, 0.8],
        model_id="test", features_used=["a"],
        feature_values={"a": 0.5}, timestamp="2026-05-26"
    )
    assert r.prediction == 2
    assert r.gex_signal is None


def test_gex_snapshot_dataclass():
    from services.ml.inference import GEXSnapshot
    g = GEXSnapshot(ticker="SPY", date="2026-05-26", net_gex=-1.5e9,
                    regime="NEGATIVE", spot=740.0)
    assert g.regime == "NEGATIVE"
