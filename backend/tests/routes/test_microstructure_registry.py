"""Microstructure readers must reuse canonical state and avoid cold allocations."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.mark.asyncio
async def test_unseen_anomaly_ticker_does_not_allocate_detector(monkeypatch):
    import routes.microstructure as microstructure
    import services.anomaly_detector as anomaly_detector

    created = []
    monkeypatch.setattr(anomaly_detector, "FlowAnomalyDetector", lambda: created.append(True))
    microstructure._anomaly_detectors.clear()

    result = await microstructure.anomaly_endpoint("UNSEEN-SYMBOL")

    assert created == []
    assert result["status"] == "no_data"
    assert result["ticker"] == "UNSEEN-SYMBOL"


def test_microstructure_vpin_uses_canonical_ingestion_registry(monkeypatch):
    import routes.microstructure as microstructure
    import routes.vpin as vpin

    canonical_engine = object()
    requested = []

    def get_engine(ticker):
        requested.append(ticker)
        return canonical_engine

    monkeypatch.setattr(vpin, "_get_engine", get_engine)
    assert microstructure._get_vpin_engine("spy") is canonical_engine
    assert requested == ["SPY"]
