"""
backend/tests/services/kanban/test_reassigner.py — Tests for dynamic task reassigner.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from kanban.reassigner import (
    compute_agent_load,
    cosine_similarity,
    extract_skills,
    find_reassignments,
    format_proposal,
    run_check,
)


class TestExtractSkills:
    def test_known_skills(self):
        text = "This needs coding-agent and api-builder skills"
        skills = extract_skills(text)
        assert "coding-agent" in skills
        assert "api-builder" in skills

    def test_no_skills(self):
        assert extract_skills("Simple text") == []


class TestCosineSimilarity:
    def test_identical(self):
        assert cosine_similarity("hello world", "hello world") > 0.99

    def test_different(self):
        assert cosine_similarity("hello world", "foo bar") < 0.5

    def test_empty(self):
        assert cosine_similarity("", "hello") == 0.0


class TestComputeAgentLoad:
    def test_basic(self):
        cards = [
            {"assignee": "Agent 1", "status": "in_progress"},
            {"assignee": "Agent 1", "status": "done"},
            {"assignee": "Agent 2", "status": "ready"},
        ]
        load = compute_agent_load(cards)
        assert load["Agent 1"]["in_progress"] == 1
        assert load["Agent 1"]["done"] == 1
        assert load["Agent 1"]["total_active"] == 1
        assert load["Agent 2"]["ready"] == 1
        assert load["Agent 2"]["total_active"] == 1


class TestFindReassignments:
    def test_no_eligible_cards(self):
        cards = [
            {"assignee": "Agent 1", "status": "done", "title": "T1", "id": "T1",
             "skill": "", "_body": "", "_file": "t1.md"},
        ]
        load = {"Agent 1": {"total_active": 5}, "Agent 2": {"total_active": 0}}
        result = find_reassignments("Agent 1", cards, load)
        assert result == []

    def test_no_candidates(self):
        cards = [
            {"assignee": "Agent 1", "status": "ready", "title": "T1", "id": "T1",
             "skill": "", "_body": "", "_file": "t1.md"},
        ]
        load = {"Agent 1": {"total_active": 5}}
        result = find_reassignments("Agent 1", cards, load)
        assert result == []

    def test_synthetic_overload(self):
        cards = [
            {"assignee": "Agent 1", "status": "ready", "title": "Backend API work",
             "id": "T1", "skill": "coding-agent api-builder", "_body": "Build API routes",
             "_file": "t1.md"},
            {"assignee": "Agent 2", "status": "done", "title": "API builder",
             "id": "T2", "skill": "api-builder", "_body": "Built routes",
             "_file": "t2.md"},
        ]
        load = {"Agent 1": {"total_active": 5}, "Agent 2": {"total_active": 1}}
        result = find_reassignments("Agent 1", cards, load)
        assert len(result) >= 1
        assert result[0]["to_agent"] == "Agent 2"

    def test_high_priority_not_reassigned(self):
        cards = [
            {"assignee": "Agent 1", "status": "ready", "title": "Critical fix",
             "id": "T1", "skill": "", "_body": "", "_file": "t1.md", "priority": "high"},
        ]
        load = {"Agent 1": {"total_active": 5}, "Agent 2": {"total_active": 0}}
        result = find_reassignments("Agent 1", cards, load)
        assert result == []


class TestFormatProposal:
    def test_empty(self):
        proposal = format_proposal([], [])
        assert "No reassignments" in proposal

    def test_with_reassignments(self):
        reassignments = [{
            "card_id": "T1", "card_title": "Test",
            "from_agent": "Agent 1", "to_agent": "Agent 2",
            "confidence": 0.75, "reasoning": "Skill match",
            "card_path": "t1.md",
        }]
        proposal = format_proposal(["Agent 1"], reassignments)
        assert "T1" in proposal
        assert "Agent 1" in proposal
        assert "Agent 2" in proposal


class TestRunCheck:
    def test_runs_without_error(self):
        result = run_check(dry_run=True)
        assert "bottlenecks" in result
        assert "reassignments" in result
        assert result["dry_run"] is True
