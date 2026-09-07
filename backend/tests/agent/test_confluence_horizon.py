"""Confluence + horizon unit tests (plan v3 L4/L0)."""

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


def test_horizon_slice():
    contracts = [
        {"expiry": "2026-09-08", "strike": 590},
        {"expiry": "2026-09-09", "strike": 590},
        {"expiry": "2026-09-12", "strike": 590},
    ]
    assert normalize_horizon("0DTE") == "0dte"
    assert normalize_horizon("bogus") == "all"
    assert slice_expiries(contracts, "all") == contracts
    assert 1 <= len(slice_expiries(contracts, "0dte")) <= 3
