"""Confluence + horizon unit tests (plan v3 L4/L0)."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from services.agent.access.horizon import normalize_horizon, slice_expiries
from services.agent.confluence import load_weights, score


def test_weights_versioned():
    w = load_weights()
    assert "dimensions" in w and "version" in w


def test_score_direction():
    bull = score({"flow": 1, "structure": 1, "microstructure": 1, "ml": 1, "vol": 1, "time_delta": 1})
    assert bull["direction"] == "bullish" and bull["total"] > 0
    bear = score({"flow": -1, "structure": -1, "microstructure": -1, "ml": -1, "vol": -1, "time_delta": -1})
    assert bear["direction"] == "bearish"


def test_missing_inputs_are_not_healthy_zeroes():
    reading = score({"flow": 0.8})
    assert reading["total"] == 20
    assert reading["coverage_weight"] == 0.25
    assert reading["dimensions"]["structure"]["value"] is None
    assert reading["direction"] == "insufficient_evidence"
    assert score({})["total"] is None
    assert score({"flow": float("nan")})["total"] is None


def test_horizon_slice():
    contracts = [
        {"expiry": "2026-09-08", "strike": 590},
        {"expiry": "2026-09-09", "strike": 590},
        {"expiry": "2026-09-12", "strike": 590},
    ]
    assert normalize_horizon("0DTE") == "0dte"
    with pytest.raises(ValueError):
        normalize_horizon("bogus")
    assert slice_expiries(contracts, "all") == contracts
    assert slice_expiries(contracts, "0dte", now=datetime(2026, 9, 11, 11, tzinfo=ZoneInfo("America/New_York"))) == []
