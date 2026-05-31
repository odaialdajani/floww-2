"""
backend/tests/services/kanban/test_rebalancer.py — Tests for capacity rebalancer.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from services.kanban.rebalancer import compute_tfidf_similarity, extract_skills_from_text, recommend_reassignment


class TestExtractSkills:
    def test_extract_known_skills(self):
        text = "This card needs coding-agent and api-builder skills"
        skills = extract_skills_from_text(text)
        assert "coding-agent" in skills
        assert "api-builder" in skills

    def test_no_skills(self):
        text = "Simple text with no skill keywords"
        skills = extract_skills_from_text(text)
        assert skills == []


class TestTfidfSimilarity:
    def test_identical_texts(self):
        score = compute_tfidf_similarity("hello world", "hello world")
        assert score > 0.99

    def test_different_texts(self):
        score = compute_tfidf_similarity("hello world", "foo bar")
        assert score < 0.5

    def test_empty_text(self):
        score = compute_tfidf_similarity("", "hello")
        assert score == 0.0


class TestRecommendReassignment:
    def test_no_cards(self):
        recs = recommend_reassignment("Agent 1", [], {})
        assert recs == []

    def test_no_candidates(self):
        cards = [{"assignee": "Agent 1", "status": "in_progress", "title": "Test", "id": "T1", "skill": "", "_body": ""}]
        recs = recommend_reassignment("Agent 1", cards, {"Agent 1": {"cards_in_progress": 5}})
        assert recs == []

    def test_synthetic_bottleneck(self):
        cards = [
            {"assignee": "Agent 1", "status": "in_progress", "title": "Backend API work", "id": "T1", "skill": "coding-agent api-builder", "_body": "Build API routes"},
            {"assignee": "Agent 2", "status": "done", "title": "API builder", "id": "T2", "skill": "api-builder", "_body": "Built routes"},
        ]
        agent_metrics = {
            "Agent 1": {"cards_in_progress": 5},
            "Agent 2": {"cards_in_progress": 0},
        }
        recs = recommend_reassignment("Agent 1", cards, agent_metrics)
        assert len(recs) >= 1
        assert recs[0]["to_agent"] == "Agent 2"
