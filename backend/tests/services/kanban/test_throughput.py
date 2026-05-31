"""
backend/tests/services/kanban/test_throughput.py — Tests for throughput model.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from services.kanban.throughput_model import PoissonRegression, ThroughputModel, extract_card_features


class TestPoissonRegression:
    def test_train_empty_data(self):
        model = PoissonRegression()
        model.train([])
        assert model.global_mean == 4.0

    def test_train_with_data(self):
        model = PoissonRegression()
        data = [
            {"agent_id": "Agent 1", "completion_hours": 4, "estimate_hours": 4, "card_priority": "medium", "commit_count": 2, "time_of_day": 14, "day_of_week": 1},
            {"agent_id": "Agent 1", "completion_hours": 6, "estimate_hours": 4, "card_priority": "high", "commit_count": 3, "time_of_day": 10, "day_of_week": 2},
            {"agent_id": "Agent 2", "completion_hours": 3, "estimate_hours": 2, "priority": "low", "commit_count": 1, "time_of_day": 16, "day_of_week": 3},
        ]
        model.train(data)
        assert "Agent 1" in model.agent_means
        assert model.agent_means["Agent 1"] == 5.0

    def test_predict_positive(self):
        model = PoissonRegression()
        model.train([
            {"agent_id": "Agent 1", "completion_hours": 4, "estimate_hours": 4, "card_priority": "medium", "commit_count": 2, "time_of_day": 14, "day_of_week": 1},
        ])
        pred = model.predict({"agent_id": "Agent 1", "estimate_hours": 4, "card_priority": "medium", "commit_count": 0, "time_of_day": 12, "day_of_week": 0})
        assert pred > 0

    def test_predict_probability_range(self):
        model = PoissonRegression()
        model.train([
            {"agent_id": "Agent 1", "completion_hours": 4, "estimate_hours": 4, "card_priority": "medium", "commit_count": 2, "time_of_day": 14, "day_of_week": 1},
        ])
        features = {"agent_id": "Agent 1", "estimate_hours": 4, "card_priority": "medium", "commit_count": 0, "time_of_day": 12, "day_of_week": 0}
        prob = model.predict_probability(features, 8.0)
        assert 0 <= prob <= 1

    def test_predict_probability_increases_with_time(self):
        model = PoissonRegression()
        model.train([
            {"agent_id": "Agent 1", "completion_hours": 4, "estimate_hours": 4, "card_priority": "medium", "commit_count": 2, "time_of_day": 14, "day_of_week": 1},
        ])
        features = {"agent_id": "Agent 1", "estimate_hours": 4, "card_priority": "medium", "commit_count": 0, "time_of_day": 12, "day_of_week": 0}
        prob_4h = model.predict_probability(features, 4.0)
        prob_24h = model.predict_probability(features, 24.0)
        assert prob_24h >= prob_4h


class TestThroughputModel:
    def test_train_returns_count(self):
        model = ThroughputModel()
        count = model.train()
        assert count >= 0

    def test_predict_completion_time(self):
        model = ThroughputModel()
        model.train()
        result = model.predict_completion_time("Agent 1", estimate_hours=4, priority="high")
        assert "predicted_hours" in result
        assert "prob_within_4h" in result
        assert "prob_within_8h" in result
        assert "prob_within_24h" in result
        assert result["predicted_hours"] > 0

    def test_get_agent_stats(self):
        model = ThroughputModel()
        model.train()
        stats = model.get_agent_stats()
        assert isinstance(stats, dict)


class TestExtractCardFeatures:
    def test_extract_from_valid_card(self, tmp_path):
        card_content = """---
id: O-TEST
title: Test Card
assignee: Agent 1
estimate_hours: 4
status: done
last_update: 2026-05-19T20:00:00Z
commits: [abc123]
blockers: []
---

## Deliverable
Test
"""
        card_file = tmp_path / "test.md"
        card_file.write_text(card_content)
        features = extract_card_features(card_file)
        assert features is not None
        assert features["agent_id"] == "Agent 1"
        assert features["status"] == "done"

    def test_extract_from_invalid_file(self, tmp_path):
        card_file = tmp_path / "invalid.md"
        card_file.write_text("No frontmatter here")
        features = extract_card_features(card_file)
        assert features is None
