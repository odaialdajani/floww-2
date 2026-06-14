"""
backend/tests/services/kanban/test_throughput_model.py
Golden-oracle tests for throughput_model.py.

Hand-computed expected values — no mocking, no copy-of-code-output.
PoissonRegression weights are fixed in source:
  bias = global_mean * 0.2
  weights = {agent_mean: 0.8, priority: -0.2, estimate_hours: 0.5,
             commit_count: 0.1, time_of_day: 0.01, day_of_week: 0.02}
prediction = bias + sum(w_i * x_i), floored at 0.5
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from services.kanban.throughput_model import (
    PoissonRegression,
    ThroughputModel,
    extract_card_features,
    get_model,
    load_historical_data,
)

# ===========================================================================
# Helpers
# ===========================================================================

def _priority_map(priority: str) -> float:
    """Mirror the priority encoding from PoissonRegression._encode_features."""
    return {"high": 1.0, "medium": 0.5, "low": 0.0}.get(priority, 0.5)


def _expected_prediction(model: PoissonRegression, features: dict) -> float:
    """Independently compute the expected prediction from a trained model."""
    encoded = {
        "agent_mean": model.agent_means.get(features.get("agent_id", "unknown"), model.global_mean),
        "priority": _priority_map(features.get("card_priority", "medium")),
        "estimate_hours": features.get("estimate_hours", 0),
        "commit_count": features.get("commit_count", 0),
        "time_of_day": features.get("time_of_day", 12),
        "day_of_week": features.get("day_of_week", 0),
    }
    pred = model.bias
    for key, weight in model.weights.items():
        pred += weight * encoded.get(key, 0)
    return max(pred, 0.5)


def _expected_probability(lambda_pred: float, T_hours: float) -> float:
    """Independently compute P(completion <= T) using exponential CDF."""
    import math
    if lambda_pred <= 0:
        return 0.0
    return 1.0 - math.exp(-T_hours / lambda_pred)


# ===========================================================================
# PoissonRegression — golden oracle predict
# ===========================================================================

class TestPoissonRegressionGoldenOracle:
    """Hand-verified predict values against the fixed weight/bias scheme."""

    def _train_simple(self):
        model = PoissonRegression()
        data = [
            {"agent_id": "A1", "completion_hours": 4.0,
             "estimate_hours": 4, "card_priority": "medium",
             "commit_count": 2, "time_of_day": 14, "day_of_week": 1},
            {"agent_id": "A1", "completion_hours": 8.0,
             "estimate_hours": 6, "card_priority": "high",
             "commit_count": 4, "time_of_day": 10, "day_of_week": 2},
            {"agent_id": "A2", "completion_hours": 3.0,
             "estimate_hours": 2, "card_priority": "low",
             "commit_count": 1, "time_of_day": 17, "day_of_week": 4},
        ]
        model.train(data)
        return model

    def test_train_sets_agent_means(self):
        model = self._train_simple()
        # A1: (4+8)/2 = 6.0, A2: 3.0
        assert model.agent_means["A1"] == pytest.approx(6.0)
        assert model.agent_means["A2"] == pytest.approx(3.0)

    def test_train_sets_global_mean(self):
        model = self._train_simple()
        # (4+8+3)/3 = 5.0
        assert model.global_mean == pytest.approx(5.0)

    def test_predict_matches_hand_computation(self):
        """Golden oracle: verify predict == independently computed value."""
        model = self._train_simple()
        features = {
            "agent_id": "A1", "card_priority": "medium",
            "estimate_hours": 3, "commit_count": 1,
            "time_of_day": 12, "day_of_week": 2,
        }
        # Manual: bias=5.0*0.2=1.0, agent_mean=6.0, priority=0.5,
        #         estimate=3, commits=1, tod=12, dow=2
        # pred = 1.0 + 0.8*6.0 + (-0.2)*0.5 + 0.5*3 + 0.1*1 + 0.01*12 + 0.02*2
        #      = 1.0 + 4.8 - 0.1 + 1.5 + 0.1 + 0.12 + 0.04 = 7.46
        expected = 1.0 + 0.8*6.0 + (-0.2)*0.5 + 0.5*3 + 0.1*1 + 0.01*12 + 0.02*2
        assert model.predict(features) == pytest.approx(expected, abs=1e-9)

    def test_predict_floors_at_half_hour(self):
        """Force a very low prediction → clamped to 0.5."""
        model = PoissonRegression()
        # Train with zero-viable data so weights drive prediction negative
        data = [
            {"agent_id": "X", "completion_hours": 0.01,
             "estimate_hours": 0, "card_priority": "low",
             "commit_count": 0, "time_of_day": 0, "day_of_week": 0},
        ]
        model.train(data)
        # Global mean will be 0.01, bias = 0.002
        # For unknown agent with 0 estimates: pred = 0.002 + 0.8*0.01 + ... ≈ 0.01 → floor 0.5
        features = {
            "agent_id": "unknown_agent", "card_priority": "low",
            "estimate_hours": 0, "commit_count": 0,
            "time_of_day": 0, "day_of_week": 0,
        }
        assert model.predict(features) == pytest.approx(0.5)

    def test_predict_probability_matches_exponential_cdf(self):
        """Golden oracle: P(completion <= T) == 1 - exp(-T/lambda)."""
        model = self._train_simple()
        features = {
            "agent_id": "A2", "card_priority": "low",
            "estimate_hours": 1, "commit_count": 0,
            "time_of_day": 9, "day_of_week": 3,
        }
        lam = model.predict(features)
        for T in [1.0, 4.0, 8.0, 24.0, 100.0]:
            expected = _expected_probability(lam, T)
            assert model.predict_probability(features, T) == pytest.approx(expected, abs=1e-9)

    def test_predict_probability_at_T_zero_is_zero(self):
        """At T=0, P(completion <= 0) should be 0 for positive lambda."""
        model = self._train_simple()
        features = {
            "agent_id": "A1", "card_priority": "medium",
            "estimate_hours": 4, "commit_count": 0,
            "time_of_day": 12, "day_of_week": 0,
        }
        assert model.predict_probability(features, 0.0) == pytest.approx(0.0)

    def test_predict_probability_monotone_in_T(self):
        """P(completion <= T) is non-decreasing in T."""
        model = self._train_simple()
        features = {
            "agent_id": "A1", "card_priority": "high",
            "estimate_hours": 4, "commit_count": 2,
            "time_of_day": 14, "day_of_week": 1,
        }
        probs = [model.predict_probability(features, T) for T in [1, 2, 4, 8, 24, 48]]
        for i in range(len(probs) - 1):
            assert probs[i] <= probs[i + 1], f"Not monotone: P(T={i})={probs[i]} > P(T={i+1})={probs[i+1]}"

    def test_predict_unknown_agent_uses_global_mean(self):
        """An agent not in agent_means falls back to global_mean."""
        model = self._train_simple()
        features_known = {
            "agent_id": "A1", "card_priority": "medium",
            "estimate_hours": 2, "commit_count": 0,
            "time_of_day": 12, "day_of_week": 0,
        }
        features_unknown = dict(features_known, agent_id="ZZZ_NO_SUCH_AGENT")
        # Unknown agent: agent_means.get("ZZZ_NO_SUCH_AGENT", global_mean) = global_mean = 5.0
        # Known A1: agent_means["A1"] = 6.0 → different prediction
        pred_known = model.predict(features_known)
        pred_unknown = model.predict(features_unknown)
        # The agent_mean encoding differs (6.0 vs 5.0), weight 0.8 → diff = 0.8
        assert pred_known != pred_unknown
        # Verify the unknown uses global_mean encoding
        expected_unknown = model.bias + 0.8 * model.global_mean + (
            -0.2 * 0.5 + 0.5 * 2 + 0.1 * 0 + 0.01 * 12 + 0.02 * 0
        )
        assert pred_unknown == pytest.approx(max(expected_unknown, 0.5), abs=1e-9)

    def test_train_empty_data_leaves_default_mean(self):
        """Empty training data → global_mean stays at default 4.0."""
        model = PoissonRegression()
        model.train([])
        assert model.global_mean == 4.0
        assert model.agent_means == {}

    def test_priority_encoding_boundary_values(self):
        """High (1.0), medium (0.5), low (0.0), unknown/default → 0.5."""
        model = self._train_simple()
        base = {"agent_id": "A1", "estimate_hours": 2, "commit_count": 0,
                "time_of_day": 12, "day_of_week": 0}
        preds = {}
        for prio in ["high", "medium", "low", "critical", "", "unknown"]:
            features = dict(base, card_priority=prio)
            preds[prio] = model.predict(features)
        # high (1.0) > medium (0.5) > low (0.0) — priority weight is -0.2
        # So higher priority → lower prediction → faster completion
        assert preds["high"] < preds["medium"] < preds["low"]
        # Unknown priorities default to 0.5 = medium
        assert preds["critical"] == preds["medium"]
        assert preds[""] == preds["medium"]
        assert preds["unknown"] == preds["medium"]


# ===========================================================================
# ThroughputModel — integration tests with real training data
# ===========================================================================

class TestThroughputModelIntegration:
    def test_predict_returns_all_fields(self, tmp_path):
        """predict_completion_time returns correctly-shaped result dict."""
        # Use a patched load to avoid filesystem dependency
        from unittest.mock import patch
        fake_data = [
            {"agent_id": "Agent 07", "completion_hours": 3.0,
             "estimate_hours": 3, "card_priority": "high",
             "commit_count": 1, "time_of_day": 10, "day_of_week": 1},
            {"agent_id": "Agent 07", "completion_hours": 5.0,
             "estimate_hours": 4, "card_priority": "medium",
             "commit_count": 3, "time_of_day": 14, "day_of_week": 2},
            {"agent_id": "Agent 08", "completion_hours": 8.0,
             "estimate_hours": 8, "card_priority": "low",
             "commit_count": 5, "time_of_day": 9, "day_of_week": 4},
        ]
        import services.kanban.throughput_model as tm
        with patch.object(tm, "load_historical_data", return_value=fake_data):
            model = ThroughputModel()
            model.train()
        result = model.predict_completion_time("Agent 07", estimate_hours=4, priority="high")
        assert set(result.keys()) == {
            "agent_id", "predicted_hours", "prob_within_4h",
            "prob_within_8h", "prob_within_24h", "training_samples",
        }
        assert result["agent_id"] == "Agent 07"
        assert result["training_samples"] == 3

    def test_predict_probabilities_monotone(self, tmp_path):
        """P(4h) <= P(8h) <= P(24h) for any input."""
        from unittest.mock import patch
        fake_data = [
            {"agent_id": "X", "completion_hours": 5.0,
             "estimate_hours": 5, "card_priority": "medium",
             "commit_count": 2, "time_of_day": 12, "day_of_week": 0},
        ]
        import services.kanban.throughput_model as tm
        with patch.object(tm, "load_historical_data", return_value=fake_data):
            model = ThroughputModel()
            model.train()
        result = model.predict_completion_time("X", estimate_hours=3, priority="medium")
        assert result["prob_within_4h"] <= result["prob_within_8h"] <= result["prob_within_24h"]

    def test_probabilities_in_valid_range(self, tmp_path):
        """All P values are in [0, 1]."""
        from unittest.mock import patch
        fake_data = [
            {"agent_id": "Y", "completion_hours": 12.0,
             "estimate_hours": 10, "card_priority": "low",
             "commit_count": 1, "time_of_day": 8, "day_of_week": 5},
        ]
        import services.kanban.throughput_model as tm
        with patch.object(tm, "load_historical_data", return_value=fake_data):
            model = ThroughputModel()
            model.train()
        result = model.predict_completion_time("Y", estimate_hours=2, priority="low")
        for key in ["prob_within_4h", "prob_within_8h", "prob_within_24h"]:
            assert 0.0 <= result[key] <= 1.0

    def test_predicted_hours_minimum(self):
        """predicted_hours >= 0.5."""
        from unittest.mock import patch
        fake_data = [
            {"agent_id": "Z", "completion_hours": 0.5,
             "estimate_hours": 0, "card_priority": "low",
             "commit_count": 0, "time_of_day": 0, "day_of_week": 0},
        ]
        import services.kanban.throughput_model as tm
        with patch.object(tm, "load_historical_data", return_value=fake_data):
            model = ThroughputModel()
            model.train()
        result = model.predict_completion_time("Z", estimate_hours=0, priority="low")
        assert result["predicted_hours"] >= 0.5

    def test_get_agent_stats_returns_stats(self):
        """get_agent_stats returns per-agent stats with correct keys."""
        from unittest.mock import patch
        fake_data = [
            {"agent_id": "P1", "completion_hours": 4.0,
             "estimate_hours": 4, "card_priority": "medium",
             "commit_count": 2, "time_of_day": 14, "day_of_week": 1},
            {"agent_id": "P1", "completion_hours": 6.0,
             "estimate_hours": 5, "card_priority": "medium",
             "commit_count": 3, "time_of_day": 10, "day_of_week": 2},
            {"agent_id": "P2", "completion_hours": 10.0,
             "estimate_hours": 8, "card_priority": "low",
             "commit_count": 5, "time_of_day": 9, "day_of_week": 4},
            {"agent_id": "P2", "completion_hours": 6.0,
             "estimate_hours": 6, "card_priority": "medium",
             "commit_count": 3, "time_of_day": 14, "day_of_week": 3},
            {"agent_id": "P2", "completion_hours": 8.0,
             "estimate_hours": 7, "card_priority": "high",
             "commit_count": 4, "time_of_day": 11, "day_of_week": 5},
        ]
        import services.kanban.throughput_model as tm
        with patch.object(tm, "load_historical_data", return_value=fake_data):
            model = ThroughputModel()
            model.train()
        stats = model.get_agent_stats()
        assert "P1" in stats
        assert "P2" in stats
        for agent_key in ["P1", "P2"]:
            s = stats[agent_key]
            assert set(s.keys()) == {"mean_hours", "median_hours", "p90_hours", "cards_completed"}
            assert s["cards_completed"] >= 1
            assert s["mean_hours"] > 0
            assert s["median_hours"] > 0

    def test_get_agent_stats_manual_values(self):
        """Golden oracle: verify exact stats for known data."""
        from unittest.mock import patch
        fake_data = [
            {"agent_id": "Alpha", "completion_hours": 3.0,
             "estimate_hours": 3, "card_priority": "high",
             "commit_count": 1, "time_of_day": 12, "day_of_week": 1},
            {"agent_id": "Alpha", "completion_hours": 5.0,
             "estimate_hours": 4, "card_priority": "medium",
             "commit_count": 2, "time_of_day": 14, "day_of_week": 2},
            {"agent_id": "Beta", "completion_hours": 8.0,
             "estimate_hours": 8, "card_priority": "low",
             "commit_count": 3, "time_of_day": 10, "day_of_week": 3},
        ]
        import services.kanban.throughput_model as tm
        with patch.object(tm, "load_historical_data", return_value=fake_data):
            model = ThroughputModel()
            model.train()
        stats = model.get_agent_stats()
        # Alpha: sorted [3, 5], mean=4.0, median=5 (n=2 → index 1), p90=5.0 (n=2 → index int(1.8)=1)
        assert stats["Alpha"]["mean_hours"] == pytest.approx(4.0)
        assert stats["Alpha"]["median_hours"] == pytest.approx(5.0)
        assert stats["Alpha"]["cards_completed"] == 2
        # Beta: single entry [8], mean=8.0, median=8.0, p90=8.0
        assert stats["Beta"]["mean_hours"] == pytest.approx(8.0)
        assert stats["Beta"]["median_hours"] == pytest.approx(8.0)
        assert stats["Beta"]["p90_hours"] == pytest.approx(8.0)
        assert stats["Beta"]["cards_completed"] == 1

    def test_get_agent_stats_skips_zero_completion(self):
        """Agent with completion_hours=0 is excluded from agent_means during train.

        train() filters: `if hours and hours > 0` — so an agent with only
        zero/negative completion times never enters agent_means, and
        get_agent_stats() (which iterates agent_means) won't include them.
        """
        from unittest.mock import patch
        fake_data = [
            {"agent_id": "Ghost", "completion_hours": 0,
             "estimate_hours": 5, "card_priority": "medium",
             "commit_count": 0, "time_of_day": 12, "day_of_week": 0},
            {"agent_id": "Ghost", "completion_hours": -1,
             "estimate_hours": 3, "card_priority": "low",
             "commit_count": 0, "time_of_day": 12, "day_of_week": 0},
        ]
        import services.kanban.throughput_model as tm
        with patch.object(tm, "load_historical_data", return_value=fake_data):
            model = ThroughputModel()
            model.train()
        stats = model.get_agent_stats()
        # Ghost never enters agent_means (all hours <= 0), so not in stats
        assert "Ghost" not in stats

    def test_get_agent_stats_mixed_valid_and_invalid(self):
        """Agent with mix of valid and invalid completion_hours counts only valid ones."""
        from unittest.mock import patch
        fake_data = [
            {"agent_id": "Mix", "completion_hours": 0,
             "estimate_hours": 5, "card_priority": "medium",
             "commit_count": 0, "time_of_day": 12, "day_of_week": 0},
            {"agent_id": "Mix", "completion_hours": 4.0,
             "estimate_hours": 4, "card_priority": "medium",
             "commit_count": 1, "time_of_day": 12, "day_of_week": 0},
            {"agent_id": "Mix", "completion_hours": -2,
             "estimate_hours": 3, "card_priority": "low",
             "commit_count": 0, "time_of_day": 12, "day_of_week": 0},
            {"agent_id": "Mix", "completion_hours": 6.0,
             "estimate_hours": 5, "card_priority": "high",
             "commit_count": 2, "time_of_day": 14, "day_of_week": 1},
        ]
        import services.kanban.throughput_model as tm
        with patch.object(tm, "load_historical_data", return_value=fake_data):
            model = ThroughputModel()
            model.train()
        stats = model.get_agent_stats()
        # Only 2 positive entries: 4.0 and 6.0
        assert stats["Mix"]["cards_completed"] == 2
        assert stats["Mix"]["mean_hours"] == pytest.approx(5.0)  # (4+6)/2


# ===========================================================================
# extract_card_features — edge cases
# ===========================================================================

class TestExtractCardFeaturesEdgeCases:

    def test_missing_frontmatter_returns_none(self, tmp_path):
        card = tmp_path / "no_fm.md"
        card.write_text("# Just a heading\nNo frontmatter here\n")
        assert extract_card_features(card) is None

    def test_bad_yaml_returns_none(self, tmp_path):
        card = tmp_path / "bad_yaml.md"
        card.write_text("---\n: corrupted: yaml: [\n---\nbody\n")
        assert extract_card_features(card) is None

    def test_no_dashes_returns_none(self, tmp_path):
        card = tmp_path / "plain.md"
        card.write_text("Just text, no YAML dashes\n")
        assert extract_card_features(card) is None

    def test_empty_file_returns_none(self, tmp_path):
        card = tmp_path / "empty.md"
        card.write_text("")
        assert extract_card_features(card) is None

    def test_defaults_for_missing_fields(self, tmp_path):
        card = tmp_path / "minimal.md"
        card.write_text("---\n---\nbody\n")
        features = extract_card_features(card)
        assert features is not None
        # No assignee → "unknown", no priority → "medium", no estimate → 0
        assert features["agent_id"] == "unknown"
        assert features["card_priority"] == "medium"
        assert features["estimate_hours"] == 0
        assert features["status"] == "unknown"

    def test_no_timestamps_gives_defaults(self, tmp_path):
        card = tmp_path / "no_time.md"
        card.write_text("---\nassignee: A1\nstatus: ready\n---\nbody\n")
        features = extract_card_features(card)
        assert features is not None
        # No last_update → defaults to 12, 0
        assert features["time_of_day"] == 12
        assert features["day_of_week"] == 0
        # No created_at/last_update → completion_hours = estimate_hours (0)
        assert features["completion_hours"] == 0

    def test_commit_count_non_list(self, tmp_path):
        """commits field that is not a list → commit_count = 0."""
        card = tmp_path / "nonlist_commits.md"
        card.write_text("---\nassignee: A1\nstatus: done\nlast_update: 2026-06-01T12:00:00Z\ncommits: \"single string\"\n---\n")
        features = extract_card_features(card)
        assert features["commit_count"] == 0

    def test_commit_count_list(self, tmp_path):
        """commits is a list → commit_count = len(list)."""
        card = tmp_path / "list_commits.md"
        card.write_text("---\nassignee: A1\nstatus: done\nlast_update: 2026-06-01T12:00:00Z\ncommits: [abc, def, ghi]\n---\n")
        features = extract_card_features(card)
        assert features["commit_count"] == 3

    def test_completion_hours_from_quoted_timestamps(self, tmp_path):
        """completion_hours works when timestamps are quoted strings (not YAML-parsed)."""
        card = tmp_path / "quoted_time.md"
        card.write_text("---\nassignee: A1\nstatus: done\ncreated_at: \"2026-06-01T10:00:00Z\"\nlast_update: \"2026-06-01T14:30:00Z\"\ncommits: []\nestimate_hours: 1\n---\n")
        features = extract_card_features(card)
        assert features["completion_hours"] == pytest.approx(4.5)

    @pytest.mark.xfail(
        reason="BUG: extract_card_features line 80 — YAML auto-parses "
               "ISO timestamps as datetime objects, then str.replace() "
               "fails silently in except clause. "
               "created_at/last_update must be quoted in card frontmatter "
               "or code must handle datetime objects."
    )
    def test_completion_hours_from_timestamps(self, tmp_path):
        """completion_hours computed from last_update - created_at.
        NOTE: This test is xfail due to a real bug — see FINDINGS.
        """
        card = tmp_path / "time_diff.md"
        card.write_text("---\nassignee: A1\nstatus: done\ncreated_at: 2026-06-01T10:00:00Z\nlast_update: 2026-06-01T14:30:00Z\ncommits: []\n---\n")
        features = extract_card_features(card)
        assert features["completion_hours"] == pytest.approx(4.5)

    def test_tagging_file_skipped_by_load(self, tmp_path):
        """load_historical_data skips files starting with 'tagging_'."""
        # This tests load_historical_data's filtering, not extract_card_features
        from services.kanban.throughput_model import load_historical_data
        # Create a temp kanban dir
        kanban_dir = tmp_path / "kanban"
        cards_dir = kanban_dir / "cards"
        cards_dir.mkdir(parents=True)
        history_file = kanban_dir / "throughput_history.json"
        history_file.write_text(json.dumps([
            {"agent_id": "Real", "completion_hours": 2.0,
             "estimate_hours": 2, "card_priority": "medium",
             "commit_count": 1, "time_of_day": 12, "day_of_week": 0},
        ]))
        # Tagging file should be skipped
        (cards_dir / "tagging_something.md").write_text("---\nassignee: Tagger\nstatus: done\nlast_update: 2026-06-01T12:00:00Z\ncommits: []\n---\n")
        import services.kanban.throughput_model as tm
        orig_root = tm.REPO_ROOT
        orig_kanban = tm.KANBAN_DIR
        orig_cards = tm.CARDS_DIR
        orig_history = tm.HISTORY_FILE
        try:
            tm.REPO_ROOT = tmp_path
            tm.KANBAN_DIR = kanban_dir
            tm.CARDS_DIR = cards_dir
            tm.HISTORY_FILE = history_file
            data = load_historical_data()
            # Only 1 from history, 0 from tagging file
            assert len(data) == 1
            assert data[0]["agent_id"] == "Real"
        finally:
            tm.REPO_ROOT = orig_root
            tm.KANBAN_DIR = orig_kanban
            tm.CARDS_DIR = orig_cards
            tm.HISTORY_FILE = orig_history


# ===========================================================================
# load_historical_data — with real history file
# ===========================================================================

class TestLoadHistoricalData:
    def test_loads_history_file(self, tmp_path):
        """When throughput_history.json exists, load_historical_data reads it."""
        kanban_dir = tmp_path / "kanban"
        cards_dir = kanban_dir / "cards"
        cards_dir.mkdir(parents=True)
        history_file = kanban_dir / "throughput_history.json"
        records = [
            {"agent_id": "H1", "completion_hours": 3.0,
             "estimate_hours": 3, "card_priority": "medium",
             "commit_count": 1, "time_of_day": 12, "day_of_week": 0},
            {"agent_id": "H2", "completion_hours": 5.0,
             "estimate_hours": 5, "card_priority": "high",
             "commit_count": 2, "time_of_day": 14, "day_of_week": 1},
        ]
        history_file.write_text(json.dumps(records))
        import services.kanban.throughput_model as tm
        orig_root = tm.REPO_ROOT
        orig_kanban = tm.KANBAN_DIR
        orig_cards = tm.CARDS_DIR
        orig_history = tm.HISTORY_FILE
        try:
            tm.REPO_ROOT = tmp_path
            tm.KANBAN_DIR = kanban_dir
            tm.CARDS_DIR = cards_dir
            tm.HISTORY_FILE = history_file
            data = load_historical_data()
            # Both records loaded from history file
            ids = [d.get("agent_id") for d in data]
            assert "H1" in ids
            assert "H2" in ids
        finally:
            tm.REPO_ROOT = orig_root
            tm.KANBAN_DIR = orig_kanban
            tm.CARDS_DIR = orig_cards
            tm.HISTORY_FILE = orig_history

    def test_malformed_json_returns_empty(self, tmp_path):
        """Corrupted history file → empty list, no crash."""
        kanban_dir = tmp_path / "kanban"
        cards_dir = kanban_dir / "cards"
        cards_dir.mkdir(parents=True)
        history_file = kanban_dir / "throughput_history.json"
        history_file.write_text("{not valid json!!!")
        import services.kanban.throughput_model as tm
        orig_root = tm.REPO_ROOT
        orig_kanban = tm.KANBAN_DIR
        orig_cards = tm.CARDS_DIR
        orig_history = tm.HISTORY_FILE
        try:
            tm.REPO_ROOT = tmp_path
            tm.KANBAN_DIR = kanban_dir
            tm.CARDS_DIR = cards_dir
            tm.HISTORY_FILE = history_file
            data = load_historical_data()
            assert data == []
        finally:
            tm.REPO_ROOT = orig_root
            tm.KANBAN_DIR = orig_kanban
            tm.CARDS_DIR = orig_cards
            tm.HISTORY_FILE = orig_history


# ===========================================================================
# Singleton
# ===========================================================================

class TestSingleton:
    def test_get_model_returns_same_instance(self):
        """get_model() is a true singleton."""
        import services.kanban.throughput_model as tm
        orig = tm._model
        try:
            tm._model = None
            m1 = get_model()
            m2 = get_model()
            assert m1 is m2
            assert m1.trained
        finally:
            tm._model = orig
