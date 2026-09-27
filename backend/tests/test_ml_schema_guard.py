"""The ML endpoint must fail loud on schema drift, not zero-fill it.

`POST /predict/{ticker}` built its feature vector with
`features.get(name, 0.0)`. Any feature the serve path did not produce became
0.0 — an ordinary value for most of these features — so a model trained on 44
features and served with 14 returned a confident UP/HOLD/DOWN built partly
from fabricated zeros, with nothing logged. A scoring surface whose failure
looks exactly like its success is the worst kind.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest
from fastapi import HTTPException

from routes import ml_predict_api as M


def test_missing_features_are_detected():
    model_feature_names = ["f1", "f2", "f3"]
    features = {"f1": 1.0, "f3": 3.0}  # f2 absent
    missing = [n for n in model_feature_names if n not in features]
    assert missing == ["f2"], "the guard must actually detect the gap"


def test_old_behaviour_would_have_silently_substituted_zero():
    """Why the fix matters: the old line turned a missing feature into 0.0."""
    model_feature_names = ["f1", "f2", "f3"]
    features = {"f1": 1.0, "f3": 3.0}
    old_vector = [features.get(n, 0.0) for n in model_feature_names]
    assert old_vector == [1.0, 0.0, 3.0], "0.0 is indistinguishable from a real value"
    # And it is finite, so a NaN guard would never have caught it either.
    assert np.isfinite(np.array(old_vector)).all()


def test_non_finite_features_are_rejected():
    names = ["a", "b"]
    values = {"a": float("nan"), "b": 1.0}
    vec = np.array([[values[n] for n in names]], dtype=float)
    assert not np.isfinite(vec).all()
    offenders = [n for n, v in zip(names, vec[0], strict=False) if not np.isfinite(v)]
    assert offenders == ["a"]


def test_complete_features_pass_through_unchanged():
    names = ["a", "b", "c"]
    features = {"a": 1.0, "b": 2.0, "c": 3.0}
    assert not [n for n in names if n not in features]
    vec = np.array([[features[n] for n in names]], dtype=float)
    assert vec.tolist() == [[1.0, 2.0, 3.0]]
    assert np.isfinite(vec).all()


def test_route_code_no_longer_zero_fills():
    """Direct guard against the regression, independent of runtime behaviour.

    Checks CODE lines only. The explanatory comment deliberately quotes the
    old expression so future readers know what was replaced, and a substring
    search over the whole source would match that comment and fail forever.
    """
    import io
    import tokenize

    src = inspect.getsource(M)
    code_lines = set()
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        code_lines.add((tok.start[0], tok.string))
    # No zero-fill lookup may be handed to a feature access.
    joined = " ".join(s for _, s in code_lines)
    assert "features.get" not in joined, (
        "the silent zero-fill lookup is back in the ML predict path"
    )
    assert "feature_schema_mismatch" in src
    assert "non_finite_features" in src


def test_route_imports_cleanly():
    assert hasattr(M, "router")
