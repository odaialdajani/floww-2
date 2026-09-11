"""Provenance registry for production signal bands and weights.

Status "pinned": a test fails if the value moves (test_path names it).
Status "claimed": source documents the value, but a behavioral boundary pin
has not been verified. Related test files are navigation, not pinning evidence.
Neither status is proof of empirical calibration; see unpinned().
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

_BANDS: list[dict[str, Any]] = [
    {
        "signal": "amihud",
        "parameter": "bands",
        "value": [1e-7, 1e-5],
        "basis": "Code states bands re-normalised for the chain-snapshot "
                 "proxy scale (option volume x spot), several orders above "
                 "the paper's 1e-9..1e-6 calibration.",
        "status": "claimed",
        "code_ref": "services/amihud_illiquidity.py:47",
        "test_path": None,
        "related_test_path": "tests/test_amihud_illiquidity.py",
    },
    {
        "signal": "kyle_lambda",
        "parameter": "bands",
        "value": [0.001, 0.005],
        "basis": "Code states bands calibrated against published Kyle-lambda "
                 "values for liquid US-equity markets with [:1] normalisation.",
        "status": "claimed",
        "code_ref": "services/kyle_lambda.py:41",
        "test_path": None,
        "related_test_path": "tests/test_kyle_lambda.py",
    },
    {
        "signal": "composite",
        "parameter": "weights",
        "value": [0.25, 0.20, 0.25, 0.20, 0.10],
        "basis": "5-component split mirrored in composite_confidence. "
                 "Mirror agreement does not establish empirical calibration.",
        "status": "claimed",
        "code_ref": "services/composite_flow_score.py:179",
        "test_path": None,
    },
    {
        "signal": "momentum",
        "parameter": "extreme_bands",
        "value": [20, 80],
        "basis": "Fixed 0-100 score extremes; detector fires outside 20/80.",
        "status": "claimed",
        "code_ref": "alert_engine.py:113",
        "test_path": None,
        "related_test_path": "tests/test_unit.py",
    },
    {
        "signal": "volume_spike",
        "parameter": "multiplier_floor_band",
        "value": [3.0, 50, 0.02],
        "basis": "3x prior volume, 50-contract floor, +/-2% of spot band.",
        "status": "claimed",
        "code_ref": "alert_engine.py:110",
        "test_path": None,
        "related_test_path": "tests/test_alert_engine_volume_spike.py",
    },
    {
        "signal": "vex_scale",
        "parameter": "convention_factor",
        "value": "spot^2 * 0.01",
        "basis": "Documented factor between the GEX-parity display scale and "
                 "the per-unit-sigma scale; a dimensional relationship, not "
                 "an empirical calibration artifact.",
        "status": "claimed",
        "code_ref": "services/gex_vex_calculator.py:64",
        "test_path": None,
    },
    {
        "signal": "fragility",
        "parameter": "weights",
        "value": [0.25, 0.20, 0.25, 0.15, 0.15],
        "basis": "Component weights stated inline with no calibration "
                 "artifact attached.",
        "status": "claimed",
        "code_ref": "services/liquidity_metrics.py:113",
        "test_path": None,
    },
    {
        "signal": "fragility",
        "parameter": "bands",
        "value": [33, 66],
        "basis": "NORMAL/ELEVATED/CRISIS cutoffs stated inline with no "
                 "calibration artifact attached.",
        "status": "claimed",
        "code_ref": "services/liquidity_metrics.py:192",
        "test_path": None,
    },
    {
        "signal": "gex_plus",
        "parameter": "bands",
        "value": [5e9, 1e9, -1e8, -5e8],
        "basis": "Dollar-regime cutoffs stated inline with no calibration "
                 "artifact attached.",
        "status": "claimed",
        "code_ref": "services/gex_vex_calculator.py:99",
        "test_path": None,
    },
]


def list_bands() -> list[dict[str, Any]]:
    """All registered bands in registry order."""
    return deepcopy(_BANDS)


def unpinned() -> list[dict[str, Any]]:
    """Bands with no pinning test: the calibration work queue."""
    return deepcopy([b for b in _BANDS if b["status"] != "pinned"])


def get_band(signal: str, parameter: str) -> dict[str, Any]:
    """Full record for one band; raises KeyError when unknown."""
    for band in _BANDS:
        if band["signal"] == signal and band["parameter"] == parameter:
            return deepcopy(band)
    raise KeyError(f"unknown band {signal}:{parameter}")
