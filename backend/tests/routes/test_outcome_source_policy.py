"""Historical outcome reads must respect the selected market-data source."""

import time
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from routes import flowseeker as fs
from services import flow_calibration as fc
from services import flow_outcomes as fo


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["public", "PUBLIC", None, "", "  "])
@pytest.mark.parametrize("operation", ["outcomes", "model", "refresh"])
async def test_public_only_refuses_legacy_cache_fetch_and_fit(monkeypatch, mode, operation):
    if mode is None:
        monkeypatch.delenv("FLOWW_MARKET_DATA_PROVIDER", raising=False)
    else:
        monkeypatch.setenv("FLOWW_MARKET_DATA_PROVIDER", mode)
    monkeypatch.setattr(fs, "_outcome_cache", {"60:2": (time.time(), {"source": "cron", "per_rule": {"WHALE": {}}})})
    read = MagicMock(return_value=[{"under": "SPY"}])
    fetch = MagicMock(side_effect=AssertionError("legacy market read forbidden"))
    fit = MagicMock(side_effect=AssertionError("legacy fit forbidden"))
    monkeypatch.setattr(fo, "read_alert_history", read)
    monkeypatch.setattr(fo, "fetch_bars_yfinance", fetch)
    monkeypatch.setattr(fc, "fit_calibration", fit)
    with pytest.raises(HTTPException) as blocked:
        if operation == "outcomes":
            await fs.alert_outcomes(days=60, horizon=2, sigma_k=0.75, min_alerts=5)
        elif operation == "model":
            await fs.calibration_model()
        else:
            await fs.alert_outcomes_refresh(days=60, horizon=2)
    assert blocked.value.status_code == 503
    assert "Public-only" in blocked.value.detail
    read.assert_not_called()
    fetch.assert_not_called()
    fit.assert_not_called()


@pytest.mark.asyncio
async def test_explicit_legacy_mode_retains_cached_outcome_fields(monkeypatch):
    monkeypatch.setenv("FLOWW_MARKET_DATA_PROVIDER", "legacy")
    stored = {"source": "cron", "per_rule": {"WHALE": {"n_measured": 20, "precision": 0.6}}, "horizon_sessions": 2}
    monkeypatch.setattr(fs, "_outcome_cache", {"60:2": (time.time(), stored)})
    fetch = MagicMock(side_effect=AssertionError("cache hit must not fetch"))
    monkeypatch.setattr(fo, "fetch_bars_yfinance", fetch)
    result = await fs.alert_outcomes(days=60, horizon=2, sigma_k=0.75, min_alerts=5)
    assert result["per_rule"] == stored["per_rule"]
    assert result["source"] == "cron"
    assert result["ok"] is True
    fetch.assert_not_called()


@pytest.mark.asyncio
async def test_explicit_legacy_mode_retains_model_computation(monkeypatch):
    monkeypatch.setenv("FLOWW_MARKET_DATA_PROVIDER", "legacy")
    alerts = [{"under": "SPY"}]
    labels = [{"under": "SPY", "hit": True}]
    monkeypatch.setattr(fo, "read_alert_history", MagicMock(return_value=alerts))
    fetch = MagicMock(return_value={"SPY": [("2026-09-10", 500.0)]})
    fit = MagicMock(return_value={"stage": 0, "n": 1, "method_note": "Too few"})
    monkeypatch.setattr(fo, "fetch_bars_yfinance", fetch)
    monkeypatch.setattr(fo, "label_alerts", MagicMock(return_value=labels))
    monkeypatch.setattr(fo, "rule_value_table", MagicMock(return_value={}))
    monkeypatch.setattr(fc, "fit_calibration", fit)
    monkeypatch.setattr(fc, "predict_p_move", MagicMock(return_value=None))
    result = await fs.calibration_model()
    assert result["stage"] == 0
    assert result["n"] == 1
    assert result["method_note"] == "Too few"
    assert fetch.call_count == 2
    fit.assert_called_once_with(labels)
