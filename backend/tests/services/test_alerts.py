"""
tests/services/test_alerts.py

Tests for the alert engine.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.alerts.engine import AlertDefinition, AlertEngine


class TestAlertDefinition:
    """Tests for alert definition parsing."""

    def test_basic_definition(self):
        data = {
            "id": "test_alert",
            "name": "Test Alert",
            "predicate": "gex_total > 1000000",
            "priority": "high",
        }
        defn = AlertDefinition(data)
        assert defn.id == "test_alert"
        assert defn.name == "Test Alert"
        assert defn.predicate == "gex_total > 1000000"
        assert defn.priority == "high"
        assert defn.enabled is True

    def test_ml_enriched(self):
        data = {
            "id": "ml_alert",
            "predicate": "ml.dir_1h_proba > 0.65",
            "ml_enriched": True,
            "ml_model": "direction",
            "ml_threshold": 0.65,
        }
        defn = AlertDefinition(data)
        assert defn.ml_enriched is True
        assert defn.ml_model == "direction"
        assert defn.ml_threshold == 0.65

    def test_default_values(self):
        data = {"id": "minimal", "predicate": "x > 1"}
        defn = AlertDefinition(data)
        assert defn.priority == "medium"
        assert defn.cooldown_minutes == 60
        assert defn.enabled is True
        assert defn.actions == ["log"]


class TestAlertEngine:
    """Tests for the alert engine."""

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db["alerts_history"].insert_one = MagicMock()
        return db

    @pytest.fixture
    def engine(self, mock_db):
        with patch("services.alerts.engine.ALERT_DEFINITIONS_DIR", Path("/nonexistent")):
            return AlertEngine(mock_db)

    def test_load_no_definitions(self, engine):
        """Engine with no YAML files should have no definitions."""
        assert len(engine.definitions) == 0

    def test_evaluate_no_definitions(self, engine):
        """Evaluating with no definitions should return empty."""
        result = engine.evaluate("SPY", {"gex_total": 1000000})
        assert result == []

    def test_simple_predicate_true(self, engine):
        """Simple predicate that evaluates to true."""
        engine.definitions = [
            AlertDefinition({
                "id": "test",
                "predicate": "gex_total > 100",
                "cooldown_minutes": 0,
            })
        ]
        context = {"gex_total": 200}
        result = engine.evaluate("SPY", context)
        assert len(result) == 1
        assert result[0]["id"] == "test"

    def test_simple_predicate_false(self, engine):
        """Simple predicate that evaluates to false."""
        engine.definitions = [
            AlertDefinition({
                "id": "test",
                "predicate": "gex_total > 100",
                "cooldown_minutes": 0,
            })
        ]
        context = {"gex_total": 50}
        result = engine.evaluate("SPY", context)
        assert len(result) == 0

    def test_cooldown_prevents_refire(self, engine):
        """Alert should not fire again during cooldown."""
        engine.definitions = [
            AlertDefinition({
                "id": "test",
                "predicate": "x > 1",
                "cooldown_minutes": 60,
            })
        ]
        context = {"x": 10}

        # First fire
        result1 = engine.evaluate("SPY", context)
        assert len(result1) == 1

        # Second fire (within cooldown)
        result2 = engine.evaluate("SPY", context)
        assert len(result2) == 0

    def test_disabled_alert_does_not_fire(self, engine):
        """Disabled alert should not fire."""
        engine.definitions = [
            AlertDefinition({
                "id": "test",
                "predicate": "x > 1",
                "enabled": False,
                "cooldown_minutes": 0,
            })
        ]
        result = engine.evaluate("SPY", {"x": 10})
        assert len(result) == 0

    def test_multiple_alerts(self, engine):
        """Multiple alerts can fire simultaneously."""
        engine.definitions = [
            AlertDefinition({"id": "a1", "predicate": "x > 1", "cooldown_minutes": 0}),
            AlertDefinition({"id": "a2", "predicate": "y < 10", "cooldown_minutes": 0}),
            AlertDefinition({"id": "a3", "predicate": "z > 100", "cooldown_minutes": 0}),
        ]
        context = {"x": 5, "y": 3, "z": 50}
        result = engine.evaluate("SPY", context)
        assert len(result) == 2  # a1 and a2 fire, a3 doesn't

    def test_persist_alert(self, engine, mock_db):
        """Fired alert should be persisted to MongoDB."""
        engine.definitions = [
            AlertDefinition({
                "id": "test",
                "predicate": "x > 1",
                "cooldown_minutes": 0,
            })
        ]
        engine.evaluate("SPY", {"x": 10})
        mock_db["alerts_history"].insert_one.assert_called_once()

    def test_comparison_operators(self, engine):
        """Test all comparison operators."""
        engine.definitions = [
            AlertDefinition({"id": "gt", "predicate": "x > 5", "cooldown_minutes": 0}),
            AlertDefinition({"id": "gte", "predicate": "x >= 5", "cooldown_minutes": 0}),
            AlertDefinition({"id": "lt", "predicate": "x < 10", "cooldown_minutes": 0}),
            AlertDefinition({"id": "lte", "predicate": "x <= 10", "cooldown_minutes": 0}),
            AlertDefinition({"id": "eq", "predicate": "x == 7", "cooldown_minutes": 0}),
            AlertDefinition({"id": "neq", "predicate": "x != 3", "cooldown_minutes": 0}),
        ]
        # Reset cooldown
        engine._last_fired.clear()
        result = engine.evaluate("SPY", {"x": 7})
        assert len(result) == 6  # All should match x=7

    def test_nested_ml_value(self, engine):
        """Test resolving values from context."""
        engine.definitions = [
            AlertDefinition({
                "id": "prob_test",
                "predicate": "probability > 0.5",
                "cooldown_minutes": 0,
            })
        ]
        engine._last_fired.clear()
        result = engine.evaluate("SPY", {"probability": 0.7})
        assert len(result) == 1
