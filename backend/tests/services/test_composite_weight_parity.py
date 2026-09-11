"""Composite weight parity: the 5-component split must stay mirrored.

`composite_flow_score` and `composite_confidence` duplicate the weight
constants by design (no coupling between synthesiser and bootstrap), with
comments in both files requiring synchronised updates. This guard fails
if either side drifts or the weights stop summing to 1.0. No formula
change — the test only pins the invariant the comments already declare.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import services.composite_confidence as cc  # noqa: E402
import services.composite_flow_score as cfs  # noqa: E402

NAMES = ("_W_ILLIQUIDITY", "_W_TOXICITY", "_W_DISLOCATION",
         "_W_DIRECTION", "_W_SENTIMENT")


def _weights(mod):
    return [getattr(mod, name) for name in NAMES]


def test_weights_mirrored_across_modules():
    assert _weights(cfs) == _weights(cc)


def test_weights_sum_to_one():
    assert sum(_weights(cfs)) == 1.0
    assert sum(_weights(cc)) == 1.0


def test_docstring_names_all_five_components():
    """The module docstring formula must describe the code's 5 weights."""
    doc = cfs.__doc__ or ""
    for token in ("0.25", "0.20", "0.10", "sentiment"):
        assert token in doc, f"docstring stale: missing {token!r}"
