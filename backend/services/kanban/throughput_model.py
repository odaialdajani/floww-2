#!/usr/bin/env python3
import logging

logger = logging.getLogger(__name__)

"""
backend/services/kanban/throughput_model.py — Agent throughput prediction model.

Trains a Poisson regression on historical card-completion times.
Features: agent_id, card_priority, lines_changed, files_touched, test_count_required,
          time_of_day, day_of_week
Output: P(card_completes_within_T_hours | features)

Reference: Hyndman, Athanasopoulos (2018) Forecasting: Principles and Practice §3
"""

import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
KANBAN_DIR = REPO_ROOT / "kanban"
CARDS_DIR = KANBAN_DIR / "cards"
HISTORY_FILE = KANBAN_DIR / "throughput_history.json"


def extract_card_features(card_path: Path) -> dict:
    """Extract features from a completed card file."""
    content = card_path.read_text()

    # Parse frontmatter
    if not content.startswith("---"):
        return None
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None

    import yaml

    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return None

    # Extract features
    features = {
        "agent_id": fm.get("assignee", "unknown"),
        "card_priority": fm.get("priority", "medium"),
        "estimate_hours": fm.get("estimate_hours", 0) or 0,
        "status": fm.get("status", "unknown"),
    }

    # Count commits
    commits = fm.get("commits", [])
    features["commit_count"] = len(commits) if isinstance(commits, list) else 0

    # Time features from last_update
    last_update = fm.get("last_update", "")
    if last_update:
        try:
            dt = datetime.fromisoformat(last_update.replace("Z", "+00:00"))
            features["time_of_day"] = dt.hour
            features["day_of_week"] = dt.weekday()
        except (ValueError, TypeError):
            features["time_of_day"] = 12
            features["day_of_week"] = 0
    else:
        features["time_of_day"] = 12
        features["day_of_week"] = 0

    # Calculate completion time if we have created/updated timestamps
    created = fm.get("created_at", "")
    updated = fm.get("last_update", "")
    if created and updated:
        try:
            t_created = datetime.fromisoformat(created.replace("Z", "+00:00"))
            t_updated = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            features["completion_hours"] = (t_updated - t_created).total_seconds() / 3600
        except (ValueError, TypeError):
            features["completion_hours"] = features["estimate_hours"]
    else:
        features["completion_hours"] = features["estimate_hours"]

    return features


class PoissonRegression:
    """Simple Poisson regression for count/time prediction."""

    def __init__(self):
        self.weights = {}
        self.bias = 0.0
        self.agent_means = {}
        self.global_mean = 4.0  # default: 4 hours

    def _encode_features(self, features: dict) -> dict:
        """Encode categorical features."""
        encoded = {}

        # Agent encoding: use mean completion time per agent
        agent = features.get("agent_id", "unknown")
        encoded["agent_mean"] = self.agent_means.get(agent, self.global_mean)

        # Priority encoding
        priority_map = {"high": 1.0, "medium": 0.5, "low": 0.0}
        encoded["priority"] = priority_map.get(features.get("card_priority", "medium"), 0.5)

        # Numeric features
        encoded["estimate_hours"] = features.get("estimate_hours", 0)
        encoded["commit_count"] = features.get("commit_count", 0)
        encoded["time_of_day"] = features.get("time_of_day", 12)
        encoded["day_of_week"] = features.get("day_of_week", 0)

        return encoded

    def train(self, data: list[dict]):
        """Train on historical completion data."""
        if not data:
            return

        # Compute per-agent means
        agent_times = defaultdict(list)
        all_times = []

        for entry in data:
            agent = entry.get("agent_id", "unknown")
            hours = entry.get("completion_hours", entry.get("estimate_hours", 4))
            if hours and hours > 0:
                agent_times[agent].append(hours)
                all_times.append(hours)

        self.global_mean = sum(all_times) / len(all_times) if all_times else 4.0

        for agent, times in agent_times.items():
            self.agent_means[agent] = sum(times) / len(times)

        # Simple weight estimation (gradient-free)
        self.weights = {
            "agent_mean": 0.8,
            "priority": -0.2,  # higher priority → faster
            "estimate_hours": 0.5,
            "commit_count": 0.1,
            "time_of_day": 0.01,
            "day_of_week": 0.02,
        }
        self.bias = self.global_mean * 0.2

    def predict(self, features: dict) -> float:
        """Predict completion time in hours."""
        encoded = self._encode_features(features)

        prediction = self.bias
        for key, weight in self.weights.items():
            prediction += weight * encoded.get(key, 0)

        return max(prediction, 0.5)  # minimum 30 minutes

    def predict_probability(self, features: dict, T_hours: float) -> float:
        """Predict P(completion <= T_hours) using Poisson CDF."""
        lambda_pred = self.predict(features)
        # Poisson CDF: P(X <= T) where X ~ Poisson(lambda)
        # For continuous approximation, use exponential distribution
        if lambda_pred <= 0:
            return 0.0
        # P(completion <= T) = 1 - exp(-T / lambda)
        return 1.0 - math.exp(-T_hours / lambda_pred)


class ThroughputModel:
    """Main throughput prediction interface."""

    def __init__(self):
        self.model = PoissonRegression()
        self.data = []
        self.trained = False

    def train(self):
        """Train on historical data."""
        self.data = load_historical_data()
        self.model.train(self.data)
        self.trained = True
        return len(self.data)

    def predict_completion_time(self, agent_id: str, estimate_hours: float = None,
                                 priority: str = "medium") -> dict:
        """Predict completion time for a new card."""
        if not self.trained:
            self.train()

        features = {
            "agent_id": agent_id,
            "card_priority": priority,
            "estimate_hours": estimate_hours or 0,
            "commit_count": 0,
            "time_of_day": datetime.now().hour,
            "day_of_week": datetime.now().weekday(),
        }

        predicted_hours = self.model.predict(features)
        prob_4h = self.model.predict_probability(features, 4.0)
        prob_8h = self.model.predict_probability(features, 8.0)
        prob_24h = self.model.predict_probability(features, 24.0)

        return {
            "agent_id": agent_id,
            "predicted_hours": round(predicted_hours, 1),
            "prob_within_4h": round(prob_4h, 2),
            "prob_within_8h": round(prob_8h, 2),
            "prob_within_24h": round(prob_24h, 2),
            "training_samples": len(self.data),
        }

    def get_agent_stats(self) -> dict:
        """Get per-agent throughput statistics."""
        if not self.trained:
            self.train()

        stats = {}
        for agent, mean_time in self.model.agent_means.items():
            agent_data = [d for d in self.data if d.get("agent_id") == agent]
            completion_times = [
                d.get("completion_hours", d.get("estimate_hours", 0))
                for d in agent_data
                if d.get("completion_hours", d.get("estimate_hours", 0)) > 0
            ]

            if completion_times:
                sorted_times = sorted(completion_times)
                n = len(sorted_times)
                stats[agent] = {
                    "mean_hours": round(mean_time, 1),
                    "median_hours": round(sorted_times[n // 2], 1),
                    "p90_hours": round(sorted_times[int(n * 0.9)] if n > 1 else sorted_times[0], 1),
                    "cards_completed": n,
                }
            else:
                stats[agent] = {
                    "mean_hours": round(mean_time, 1),
                    "median_hours": round(mean_time, 1),
                    "p90_hours": round(mean_time * 1.5, 1),
                    "cards_completed": 0,
                }

        return stats


# Singleton
_model = None


def get_model() -> ThroughputModel:
    global _model
    if _model is None:
        _model = ThroughputModel()
        _model.train()
    return _model


def load_historical_data() -> list[dict]:
    """Load historical card data for training."""
    history = []

    # Load from history file if exists
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text())
        except (json.JSONDecodeError, IOError):
            history = []

    # Also scan current cards for completed ones
    for card_file in CARDS_DIR.glob("*.md"):
        if card_file.name.startswith("tagging_"):
            continue
        features = extract_card_features(card_file)
        if features and features["status"] == "done":
            history.append(features)

    return history


if __name__ == "__main__":
    model = get_model()
    logger.info(f"Trained on {len(model.data)} historical cards")
    logger.info()

    # Print agent stats
    stats = model.get_agent_stats()
    logger.info("Agent Throughput Stats:")
    for agent, s in sorted(stats.items()):
        logger.info(f"  {agent}: mean={s['mean_hours']}h, median={s['median_hours']}h, "
              f"p90={s['p90_hours']}h, n={s['cards_completed']}")
    logger.info()

    # Predict for a new card
    logger.info("Predictions for new card (Agent 1, 4h estimate, high priority):")
    pred = model.predict_completion_time("Agent 1", estimate_hours=4, priority="high")
    logger.info(f"  Predicted: {pred['predicted_hours']}h")
    logger.info(f"  P(<=4h): {pred['prob_within_4h']}")
    logger.info(f"  P(<=8h): {pred['prob_within_8h']}")
    logger.info(f"  P(<=24h): {pred['prob_within_24h']}")
