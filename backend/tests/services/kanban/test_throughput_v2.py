"""
backend/tests/services/kanban/test_throughput_v2.py — Tests for throughput model v2.
"""
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.predict_throughput import (
    EnsembleRegressor,
    check_drift,
    extract_features,
)


class TestEnsembleRegressor:
    def test_train_empty(self):
        model = EnsembleRegressor()
        model.train([])
        assert model.global_mean == 4.0
        assert not model.trained

    def test_train_with_data(self):
        model = EnsembleRegressor()
        data = [
            {"agent": "Agent 1", "estimate_hours": 4, "priority": "medium",
             "n_commits": 2, "n_blockers": 0, "hour": 14, "day_of_week": 1,
             "completion_hours": 4.0},
            {"agent": "Agent 1", "estimate_hours": 4, "priority": "high",
             "n_commits": 3, "n_blockers": 0, "hour": 10, "day_of_week": 2,
             "completion_hours": 6.0},
            {"agent": "Agent 2", "estimate_hours": 2, "priority": "low",
             "n_commits": 1, "n_blockers": 0, "hour": 16, "day_of_week": 3,
             "completion_hours": 3.0},
        ]
        model.train(data, epochs=10)
        assert model.trained
        assert "Agent 1" in model.agent_means
        assert model.agent_means["Agent 1"] == 5.0

    def test_predict_positive(self):
        model = EnsembleRegressor()
        data = [
            {"agent": "Agent 1", "estimate_hours": 4, "priority": "medium",
             "n_commits": 2, "n_blockers": 0, "hour": 14, "day_of_week": 1,
             "completion_hours": 4.0},
        ]
        model.train(data, epochs=5)
        result = model.predict({
            "agent": "Agent 1", "estimate_hours": 4, "priority": "medium",
            "n_commits": 0, "n_blockers": 0, "hour": 12, "day_of_week": 0,
        })
        assert result["predicted_hours"] > 0
        assert "confidence_low" in result
        assert "confidence_high" in result
        assert "prob_within_4h" in result
        assert "prob_within_8h" in result
        assert "prob_within_24h" in result

    def test_prob_within_increases(self):
        model = EnsembleRegressor()
        data = [
            {"agent": "Agent 1", "estimate_hours": 4, "priority": "medium",
             "n_commits": 2, "n_blockers": 0, "hour": 14, "day_of_week": 1,
             "completion_hours": 4.0},
        ]
        model.train(data, epochs=5)
        feat = {"agent": "Agent 1", "estimate_hours": 4, "priority": "medium",
                "n_commits": 0, "n_blockers": 0, "hour": 12, "day_of_week": 0}
        r4 = model.predict(feat)
        assert r4["prob_within_24h"] >= r4["prob_within_8h"] >= r4["prob_within_4h"]

    def test_sub_model_predictions(self):
        model = EnsembleRegressor()
        data = [
            {"agent": "Agent 1", "estimate_hours": 4, "priority": "medium",
             "n_commits": 2, "n_blockers": 0, "hour": 14, "day_of_week": 1,
             "completion_hours": 4.0},
        ]
        model.train(data, epochs=5)
        result = model.predict({
            "agent": "Agent 1", "estimate_hours": 4, "priority": "medium",
            "n_commits": 0, "n_blockers": 0, "hour": 12, "day_of_week": 0,
        })
        assert "sub_model_predictions" in result
        assert "poisson" in result["sub_model_predictions"]
        assert "exponential" in result["sub_model_predictions"]
        assert "gamma" in result["sub_model_predictions"]

    def test_get_agent_stats(self):
        model = EnsembleRegressor()
        data = [
            {"agent": "Agent 1", "estimate_hours": 4, "priority": "medium",
             "n_commits": 2, "n_blockers": 0, "hour": 14, "day_of_week": 1,
             "completion_hours": 4.0},
            {"agent": "Agent 1", "estimate_hours": 6, "priority": "high",
             "n_commits": 3, "n_blockers": 0, "hour": 10, "day_of_week": 2,
             "completion_hours": 6.0},
        ]
        model.train(data, epochs=5)
        with patch("scripts.predict_throughput.load_history", return_value=data):
            stats = model.get_agent_stats()
        assert "Agent 1" in stats
        assert stats["Agent 1"]["cards_completed"] == 2
        assert stats["Agent 1"]["mean_hours"] == 5.0

    def test_accuracy_metric(self):
        model = EnsembleRegressor()
        data = [
            {"agent": "Agent 1", "estimate_hours": 4, "priority": "medium",
             "n_commits": 2, "n_blockers": 0, "hour": 14, "day_of_week": 1,
             "completion_hours": 4.0},
        ]
        model.train(data, epochs=5)
        assert 0 <= model.train_accuracy_20pct <= 1


class TestExtractFeatures:
    def test_done_card(self, tmp_path):
        card_content = """---
id: O-TEST
title: Test Card
assignee: Agent 1
estimate_hours: 4
priority: medium
status: done
created_at: 2026-05-19T18:00:00Z
last_update: 2026-05-19T22:00:00Z
commits: [abc123]
blockers: []
---

## Deliverable
Test
"""
        card_file = tmp_path / "test.md"
        card_file.write_text(card_content)
        card = {"_file": str(card_file)}
        # parse_card is tested indirectly
        from scripts.predict_throughput import parse_card
        parsed = parse_card(card_file)
        assert parsed is not None
        features = extract_features(parsed)
        assert features is not None
        assert features["agent"] == "Agent 1"
        assert features["completion_hours"] == 4.0

    def test_non_done_card_returns_none(self, tmp_path):
        card_content = """---
id: O-TEST
title: Test Card
assignee: Agent 1
status: in_progress
---

Test
"""
        card_file = tmp_path / "test.md"
        card_file.write_text(card_content)
        from scripts.predict_throughput import parse_card
        parsed = parse_card(card_file)
        features = extract_features(parsed)
        assert features is None


class TestDriftDetection:
    def test_no_drift(self, tmp_path):
        model = EnsembleRegressor()
        data = [
            {"agent": "Agent 1", "estimate_hours": 4, "priority": "medium",
             "n_commits": 2, "n_blockers": 0, "hour": 14, "day_of_week": 1,
             "completion_hours": 4.0},
        ]
        model.train(data, epochs=5)
        model.train_mape = 0.05

        with patch("scripts.predict_throughput.load_history", return_value=data):
            result = check_drift(model, threshold_mape=0.20)
        assert not result["drift_detected"]
        assert result["current_mape"] < 0.20

    def test_drift_detected(self, tmp_path):
        model = EnsembleRegressor()
        model.trained = True
        model.train_mape = 0.05
        model.global_mean = 4.0
        model.agent_means = {"Agent 1": 4.0}
        model.feature_weights = {
            "agent_mean": 0.8, "estimate": 0.5, "priority": -0.2,
            "commits": 0.05, "blockers": 0.3, "hour": 0.02, "dow": 0.01,
        }
        model.bias = 0.8
        # Data with very different completion times -> high MAPE
        data = [
            {"agent": "Agent 1", "estimate_hours": 4, "priority": "medium",
             "n_commits": 2, "n_blockers": 0, "hour": 14, "day_of_week": 1,
             "completion_hours": 100.0},  # way off from prediction
        ]
        with patch("scripts.predict_throughput.load_history", return_value=data):
            result = check_drift(model, threshold_mape=0.20)
        assert result["drift_detected"]
