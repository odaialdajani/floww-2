"""Scalar/serialization boundary checks (Command Code C1.6).

Module-boundary rule under test: numeric outputs are normalized once where
appropriate. Scalars, arrays, nonfinite inputs, and JSON must behave
explicitly. Invalid values are never silently converted to zero.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from domain.numeric_boundary import (  # noqa: E402
    coerce_scalar,
    normalize_array,
)


def test_plain_floats_pass_through_unchanged():
    assert coerce_scalar(1.25) == 1.25
    assert type(coerce_scalar(1.25)) is float


def test_numpy_scalars_normalize_once_at_boundary():
    np = pytest.importorskip("numpy")
    assert type(coerce_scalar(np.float64(1.25))) is float
    assert coerce_scalar(np.float64(1.25)) == 1.25


@pytest.mark.parametrize("bad", [None, "bad", float("nan"), float("inf"), True, False])
def test_invalid_scalars_stay_missing_not_zero(bad):
    assert coerce_scalar(bad) is None


def test_arrays_preserve_missingness_elementwise():
    np = pytest.importorskip("numpy")
    got = normalize_array([1.0, np.float64(2.0), None, float("nan"), "bad"])
    assert got[0] == 1.0
    assert got[1] == 2.0
    assert all(type(v) is float for v in got[:2])
    assert got[2:] == [None, None, None]


def test_boundary_output_is_json_safe():
    payload = {
        "scalar": coerce_scalar(1.5),
        "missing": coerce_scalar(float("nan")),
        "array": normalize_array([1.0, None]),
        "nonfinite": coerce_scalar(math.inf),
    }
    safe = json.loads(json.dumps(payload, allow_nan=False))
    assert safe == {"scalar": 1.5, "missing": None, "array": [1.0, None], "nonfinite": None}
