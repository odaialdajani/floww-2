"""
backend/tests/routes/test_ml_ensemble_labels.py

Pins the 3-class label contract of GET /api/ml/ensemble.

The inference engine returns prediction in {0: DOWN, 1: HOLD, 2: UP} with a
3-element probabilities list [down, hold, up]. The route must not map these
with binary logic (the round-10 audit found UP(2) rendered as "DOWN" and
HOLD(1) rendered as "UP").
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import services.ml.inference as inference_mod
from routes.ml_predict_api import ensemble_prediction


@dataclass
class _FakeResult:
    ticker: str
    prediction: int
    confidence: float
    probabilities: List[float]
    model_id: str = "SPY_test_v1"
    data_age_sec: float = 1.0
    features_used: List[str] = field(default_factory=list)


class _FakeEngine:
    def __init__(self, result):
        self._result = result

    async def predict(self, ticker: str):
        return self._result


async def _run_with(monkeypatch, result):
    monkeypatch.setattr(inference_mod, "inference_engine", _FakeEngine(result))
    return await ensemble_prediction(tickers="SPY", min_confidence=0.55)


@pytest.mark.asyncio
async def test_up_prediction_labeled_up(monkeypatch):
    """Engine UP (2) must be labeled UP and counted bullish."""
    resp = await _run_with(
        monkeypatch,
        _FakeResult(ticker="SPY", prediction=2, confidence=0.7,
                    probabilities=[0.1, 0.2, 0.7]),
    )
    assert resp["tickers"]["SPY"]["prediction"] == "UP"
    assert resp["tickers"]["SPY"]["probabilities"]["up"] == pytest.approx(0.7)
    assert resp["tickers"]["SPY"]["probabilities"]["down"] == pytest.approx(0.1)
    assert resp["n_bullish"] == 1
    assert resp["n_bearish"] == 0
    assert resp["ensemble_signal"] == "BULLISH"


@pytest.mark.asyncio
async def test_hold_prediction_labeled_hold(monkeypatch):
    """Engine HOLD (1) must be labeled HOLD and counted neither bullish nor bearish."""
    resp = await _run_with(
        monkeypatch,
        _FakeResult(ticker="SPY", prediction=1, confidence=0.6,
                    probabilities=[0.2, 0.6, 0.2]),
    )
    assert resp["tickers"]["SPY"]["prediction"] == "HOLD"
    assert resp["tickers"]["SPY"]["probabilities"]["hold"] == pytest.approx(0.6)
    assert resp["n_bullish"] == 0
    assert resp["n_bearish"] == 0


@pytest.mark.asyncio
async def test_down_prediction_labeled_down(monkeypatch):
    """Engine DOWN (0) must be labeled DOWN and counted bearish."""
    resp = await _run_with(
        monkeypatch,
        _FakeResult(ticker="SPY", prediction=0, confidence=0.8,
                    probabilities=[0.8, 0.1, 0.1]),
    )
    assert resp["tickers"]["SPY"]["prediction"] == "DOWN"
    assert resp["tickers"]["SPY"]["probabilities"]["down"] == pytest.approx(0.8)
    assert resp["n_bearish"] == 1
    assert resp["ensemble_signal"] == "BEARISH"


@pytest.mark.asyncio
async def test_legacy_binary_probabilities_still_work(monkeypatch):
    """A legacy 2-element probability list keeps the old binary mapping."""
    resp = await _run_with(
        monkeypatch,
        _FakeResult(ticker="SPY", prediction=1, confidence=0.6,
                    probabilities=[0.4, 0.6]),
    )
    assert resp["tickers"]["SPY"]["prediction"] == "UP"
    assert resp["tickers"]["SPY"]["probabilities"]["up"] == pytest.approx(0.6)
    assert resp["n_bullish"] == 1
