"""
backend/tests/services/kanban/test_bottleneck.py — Tests for bottleneck detector.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from services.kanban.bottleneck import compute_agent_metrics, detect_bottlenecks


class TestComputeAgentMetrics:
    def test_empty_cards(self):
        metrics = compute_agent_metrics([])
        assert metrics == {}

    def test_single_agent(self):
        cards = [
            {"assignee": "Agent 1", "status": "in_progress", "blockers": [], "last_update": "2026-05-19T20:00:00Z"},
            {"assignee": "Agent 1", "status": "done", "blockers": [], "last_update": "2026-05-19T20:00:00Z"},
        ]
        metrics = compute_agent_metrics(cards)
        assert "Agent 1" in metrics
        assert metrics["Agent 1"]["cards_in_progress"] == 1
        assert metrics["Agent 1"]["cards_done"] == 1

    def test_multiple_agents(self):
        cards = [
            {"assignee": "Agent 1", "status": "in_progress", "blockers": [], "last_update": "2026-05-19T20:00:00Z"},
            {"assignee": "Agent 2", "status": "ready", "blockers": [], "last_update": "2026-05-19T20:00:00Z"},
        ]
        metrics = compute_agent_metrics(cards)
        assert len(metrics) == 2

    def test_blocker_count(self):
        cards = [
            {"assignee": "Agent 1", "status": "blocked", "blockers": ["waiting on X", "waiting on Y"], "last_update": "2026-05-19T20:00:00Z"},
        ]
        metrics = compute_agent_metrics(cards)
        assert metrics["Agent 1"]["blocker_count"] == 2
        assert metrics["Agent 1"]["blocker_rate"] == 2.0


class TestDetectBottlenecks:
    def test_no_bottlenecks(self):
        agent_metrics = {
            "Agent 1": {"cards_in_progress": 1, "blocker_rate": 0.1, "last_update_hours_ago": 1},
            "Agent 2": {"cards_in_progress": 1, "blocker_rate": 0.1, "last_update_hours_ago": 2},
        }
        bottlenecks = detect_bottlenecks(agent_metrics)
        assert bottlenecks == []

    def test_high_load_bottleneck(self):
        agent_metrics = {
            "Agent 1": {"cards_in_progress": 10, "blocker_rate": 0.1, "last_update_hours_ago": 1},
            "Agent 2": {"cards_in_progress": 1, "blocker_rate": 0.1, "last_update_hours_ago": 2},
            "Agent 3": {"cards_in_progress": 1, "blocker_rate": 0.1, "last_update_hours_ago": 1},
        }
        bottlenecks = detect_bottlenecks(agent_metrics)
        assert len(bottlenecks) >= 1
        assert bottlenecks[0]["agent"] == "Agent 1"

    def test_stale_agent_bottleneck(self):
        agent_metrics = {
            "Agent 1": {"cards_in_progress": 1, "blocker_rate": 0.0, "last_update_hours_ago": 48},
            "Agent 2": {"cards_in_progress": 1, "blocker_rate": 0.0, "last_update_hours_ago": 1},
        }
        bottlenecks = detect_bottlenecks(agent_metrics)
        assert len(bottlenecks) >= 1

    def test_empty_metrics(self):
        bottlenecks = detect_bottlenecks({})
        assert bottlenecks == []
