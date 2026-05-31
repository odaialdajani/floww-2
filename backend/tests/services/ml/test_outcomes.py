"""
tests/services/ml/test_outcomes.py

Tests for the realized outcome attachment service.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.ml.outcomes import (
    _try_underlying_bars,
    attach_realized_outcomes,
    compute_rolling_accuracy,
    fetch_next_day_outcome,
)


def make_mock_col():
    """Create a mock collection with properly chained async methods."""
    col = MagicMock()

    # Build the chain: find().sort().limit().to_list()
    mock_cursor = AsyncMock()
    mock_limited = MagicMock()
    mock_limited.to_list = mock_cursor
    mock_sorted = MagicMock()
    mock_sorted.limit.return_value = mock_limited
    col.find.return_value.sort.return_value = mock_sorted

    col.find_one = AsyncMock(return_value=None)
    col.update_one = AsyncMock()
    col.insert_one = AsyncMock()
    col.count_documents = AsyncMock(return_value=0)
    col.aggregate = AsyncMock()
    return col, mock_cursor


@pytest.fixture
def mock_col():
    return make_mock_col()


@pytest.fixture
def mock_db(mock_col):
    col, _ = mock_col
    db = MagicMock()
    collections = {
        "ml_predictions": col,
        "underlying_bars": col,
    }
    db.__getitem__ = lambda self, key: collections.get(key, col)
    for k, v in collections.items():
        db[k] = v
    return db


class TestFetchNextDayOutcome:
    @pytest.mark.asyncio
    async def test_empty_data(self):
        mock_data = MagicMock()
        mock_data.empty = True
        with patch("services.ml.outcomes.yf.download", return_value=mock_data):
            result = await fetch_next_day_outcome("SPY", "2024-01-14T10:00:00")
            assert result is None

    @pytest.mark.asyncio
    async def test_yfinance_error(self):
        with patch("services.ml.outcomes.yf.download", side_effect=Exception("network")):
            result = await fetch_next_day_outcome("SPY", "2024-01-14T10:00:00")
            assert result is None


class TestTryUnderlyingBars:
    @pytest.mark.asyncio
    async def test_successful_fallback(self):
        col, cursor = make_mock_col()
        db = MagicMock()
        db.__getitem__ = lambda self, key: col

        cursor.return_value = [
            {"date": "2024-01-16", "open": 450.0, "close": 452.0, "high": 453.0, "low": 449.0}
        ]
        result = await _try_underlying_bars(db, "SPY", "2024-01-15T10:00:00")
        assert result is not None
        assert result["realized_label"] == 1
        assert result["data_source"] == "underlying_bars"

    @pytest.mark.asyncio
    async def test_no_bars(self):
        col, cursor = make_mock_col()
        db = MagicMock()
        db.__getitem__ = lambda self, key: col

        cursor.return_value = []
        result = await _try_underlying_bars(db, "SPY", "2024-01-15T10:00:00")
        assert result is None

    @pytest.mark.asyncio
    async def test_zero_prices(self):
        col, cursor = make_mock_col()
        db = MagicMock()
        db.__getitem__ = lambda self, key: col

        cursor.return_value = [{"date": "2024-01-16", "open": 0, "close": 0, "high": 0, "low": 0}]
        result = await _try_underlying_bars(db, "SPY", "2024-01-15T10:00:00")
        assert result is None


class TestAttachRealizedOutcomes:
    @pytest.mark.asyncio
    async def test_no_pending(self):
        col, cursor = make_mock_col()
        db = MagicMock()
        db.__getitem__ = lambda self, key: col

        cursor.return_value = []
        result = await attach_realized_outcomes(db)
        assert result == 0

    @pytest.mark.asyncio
    async def test_skips_recent(self):
        col, cursor = make_mock_col()
        db = MagicMock()
        db.__getitem__ = lambda self, key: col

        recent_ts = datetime.now(timezone.utc) - timedelta(hours=2)
        cursor.return_value = [
            {"_id": "p1", "ticker": "SPY", "ts": recent_ts.isoformat(), "prediction": 1}
        ]
        result = await attach_realized_outcomes(db)
        assert result == 0

    @pytest.mark.asyncio
    async def test_skips_missing_fields(self):
        col, cursor = make_mock_col()
        db = MagicMock()
        db.__getitem__ = lambda self, key: col

        old_ts = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        cursor.return_value = [
            {"_id": "p1", "ticker": "", "ts": old_ts, "prediction": 1},
            {"_id": "p2", "ticker": "SPY", "ts": "", "prediction": 1},
        ]
        result = await attach_realized_outcomes(db)
        assert result == 0


class TestComputeRollingAccuracy:
    @pytest.mark.asyncio
    async def test_no_predictions(self):
        col = MagicMock()
        col.aggregate.return_value.to_list = AsyncMock(return_value=[])
        db = MagicMock()
        db.__getitem__ = lambda self, key: col

        result = await compute_rolling_accuracy(db, "SPY")
        assert result["n_predictions"] == 0
        assert result["accuracy"] is None

    @pytest.mark.asyncio
    async def test_with_outcomes(self):
        col = MagicMock()
        col.aggregate.return_value.to_list = AsyncMock(
            return_value=[{"n_total": 100, "n_with_outcome": 80, "n_correct": 55, "avg_return": 0.15}]
        )
        db = MagicMock()
        db.__getitem__ = lambda self, key: col

        result = await compute_rolling_accuracy(db, "SPY")
        assert result["n_predictions"] == 100
        assert result["n_with_outcomes"] == 80
        assert result["accuracy"] == 0.6875

    @pytest.mark.asyncio
    async def test_aggregation_error(self):
        col = MagicMock()
        col.aggregate.side_effect = Exception("db error")
        db = MagicMock()
        db.__getitem__ = lambda self, key: col

        result = await compute_rolling_accuracy(db, "SPY")
        assert result["n_predictions"] == 0
