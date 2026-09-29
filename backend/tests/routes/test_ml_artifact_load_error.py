"""Model artifacts that cannot be unpickled must fail LOUDLY, not 500.

`_load_model_cached` currently lets any `joblib.load` failure escape as an
unhandled 500 after a multi-second unpickle attempt. The rest of this
route is deliberately careful about exactly that: a feature-schema
mismatch raises a 409 naming the offenders, and non-finite features raise
a 409 too, precisely so a broken serve path cannot be laundered into a
confident wrong number.

An unpicklable artifact is the same class of problem wearing a different
costume, and it should report itself the same way. This wraps the load so
it raises a 503 that names the artifact and the underlying cause, and
caches nothing on failure (so a retrain is picked up on the next request
without needing a restart).

Scope: error surfacing only. No feature math, no gating semantics, no
model selection, no artifact regeneration.
"""
import os

import pytest
from fastapi import HTTPException

from routes import ml_predict_api


def test_load_raises_503_naming_the_artifact(monkeypatch):
    monkeypatch.setattr(ml_predict_api, "_model_cache", {})
    monkeypatch.setattr(os.path, "getmtime", lambda p: 1.0)

    def boom(path):
        raise ModuleNotFoundError("No module named '_loss'")

    import joblib
    monkeypatch.setattr(joblib, "load", boom)

    with pytest.raises(HTTPException) as exc:
        ml_predict_api._load_model_cached("/models/price_model_SPY.joblib")

    err = exc.value
    assert err.status_code == 503
    detail = err.detail
    assert detail["error"] == "model_artifact_unloadable"
    assert "price_model_SPY.joblib" in detail["artifact"]
    # The underlying cause must survive, or the operator cannot act on it.
    assert "_loss" in detail["cause"]
    assert "retrain" in detail["message"].lower()


def test_failed_load_is_not_cached(monkeypatch):
    """A retrained artifact must be picked up without restarting the process."""
    monkeypatch.setattr(ml_predict_api, "_model_cache", {})
    monkeypatch.setattr(os.path, "getmtime", lambda p: 1.0)
    import joblib

    calls = {"n": 0}

    def flaky(path):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ModuleNotFoundError("No module named '_loss'")
        return "recovered-artifact"

    monkeypatch.setattr(joblib, "load", flaky)

    with pytest.raises(HTTPException):
        ml_predict_api._load_model_cached("/models/price_model_SPY.joblib")
    # Second call must retry the file rather than serving a cached failure.
    assert ml_predict_api._load_model_cached("/models/price_model_SPY.joblib") == "recovered-artifact"
    assert calls["n"] == 2


def test_successful_load_is_still_cached(monkeypatch):
    """The mtime-keyed cache must keep working for the normal path."""
    monkeypatch.setattr(ml_predict_api, "_model_cache", {})
    monkeypatch.setattr(os.path, "getmtime", lambda p: 7.0)
    import joblib
    calls = {"n": 0}

    def counting(path):
        calls["n"] += 1
        return "artifact"

    monkeypatch.setattr(joblib, "load", counting)
    assert ml_predict_api._load_model_cached("/models/x.joblib") == "artifact"
    assert ml_predict_api._load_model_cached("/models/x.joblib") == "artifact"
    assert calls["n"] == 1, "unchanged mtime must not re-unpickle"
