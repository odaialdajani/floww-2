"""Agent C: staged-calibration status accessor for D's C11 health section.

Replaces health's lazy read of the private _calibration_blob (see
routes/health.py "pending C accessor" note) with an explicit fail-open
accessor. D wires the health side.
"""
import time

import pytest

from routes import flowseeker as fs


def test_accessor_reports_staged_blob():
    fs._calibration_blob = (time.time(), {"stage": 1, "n": 80,
                                          "method_note": "decile",
                                          "model": {"kind": "decile"}})
    try:
        out = fs.get_calibration_status()
        assert out["stage"] == 1
        assert out["n"] == 80
        assert out["model_kind"] == "decile"
        assert 0 <= out["age_s"] < 5
    finally:
        fs._calibration_blob = None


def test_accessor_fail_open_without_blob():
    fs._calibration_blob = None
    out = fs.get_calibration_status()
    assert out["stage"] == 0
    assert out["n"] == 0
    assert out["age_s"] is None
    assert "uncalibrated" in out["method_note"]
