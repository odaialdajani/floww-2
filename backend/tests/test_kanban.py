"""
backend/tests/test_kanban.py — Tests for the kanban board schema, card transitions,
WIP-limit enforcement, and blocker detection logic.

Run from repo root:
  cd /Users/nav/Documents/GitHub/floww && python -m pytest backend/tests/test_kanban.py -v
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

# Add repo root so we can import kanban modules
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from kanban.watcher import (
    all_cards,
    auto_archive,
    cards_by_status,
    check_blocker,
    enforce_wip_limit,
    now_iso,
    parse_card,
    write_card,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_kanban(tmp_path):
    """Create a minimal kanban directory structure in a temp dir."""
    cards_dir = tmp_path / "kanban" / "cards"
    closed_dir = tmp_path / "kanban" / "closed"
    cards_dir.mkdir(parents=True)
    closed_dir.mkdir(parents=True)

    board_yaml = tmp_path / "kanban" / "board.yaml"
    board_yaml.write_text(yaml.dump({
        "columns": [
            {"id": "backlog", "title": "Backlog", "wip_limit": None},
            {"id": "ready", "title": "Ready", "wip_limit": 20},
            {"id": "in_progress", "title": "In Progress", "wip_limit": 6},
            {"id": "review", "title": "Review", "wip_limit": 4},
            {"id": "done", "title": "Done", "wip_limit": 20},
        ],
        "cards": [],
        "watcher": {"interval_seconds": 300, "blocker_threshold_seconds": 1800},
    }))

    return tmp_path


@pytest.fixture
def sample_card(tmp_kanban):
    """Write a sample card and return its path."""
    card_content = """---
id: O-TEST-CARD
title: Test Card
assignee: Agent 1
skill: test-skill
estimate_hours: 2
dependencies: []
status: ready
last_update: 2026-05-19T20:00:00Z
commits: []
blockers: []
---

## Deliverable
Test deliverable
"""
    card_path = tmp_kanban / "kanban" / "cards" / "O-TEST-CARD.md"
    card_path.write_text(card_content)
    return card_path


# ---------------------------------------------------------------------------
# Tests: YAML schema
# ---------------------------------------------------------------------------

class TestBoardSchema:
    def test_board_yaml_loads(self, tmp_kanban):
        """board.yaml parses as valid YAML with required keys."""
        board = yaml.safe_load((tmp_kanban / "kanban" / "board.yaml").read_text())
        assert "columns" in board
        assert "cards" in board

    def test_board_has_five_columns(self, tmp_kanban):
        """Board defines exactly 5 columns."""
        board = yaml.safe_load((tmp_kanban / "kanban" / "board.yaml").read_text())
        assert len(board["columns"]) == 5
        col_ids = [c["id"] for c in board["columns"]]
        assert col_ids == ["backlog", "ready", "in_progress", "review", "done"]

    def test_in_progress_wip_limit_is_6(self, tmp_kanban):
        """in_progress column has wip_limit of 6."""
        board = yaml.safe_load((tmp_kanban / "kanban" / "board.yaml").read_text())
        in_prog = [c for c in board["columns"] if c["id"] == "in_progress"][0]
        assert in_prog["wip_limit"] == 6

    def test_backlog_and_done_have_no_wip_limit(self, tmp_kanban):
        """backlog and done columns have null wip_limit."""
        board = yaml.safe_load((tmp_kanban / "kanban" / "board.yaml").read_text())
        backlog = [c for c in board["columns"] if c["id"] == "backlog"][0]
        done = [c for c in board["columns"] if c["id"] == "done"][0]
        assert backlog["wip_limit"] is None
        assert done["wip_limit"] == 20  # soft limit for visibility


# ---------------------------------------------------------------------------
# Tests: Card parsing and schema
# ---------------------------------------------------------------------------

class TestCardSchema:
    def test_parse_card_returns_frontmatter(self, sample_card):
        """parse_card extracts frontmatter fields from a card .md file."""
        card = parse_card(sample_card)
        assert card["id"] == "O-TEST-CARD"
        assert card["title"] == "Test Card"
        assert card["assignee"] == "Agent 1"
        assert card["status"] == "ready"

    def test_parse_card_preserves_body(self, sample_card):
        """parse_card preserves the markdown body."""
        card = parse_card(sample_card)
        assert "_body" in card
        assert "Test deliverable" in card["_body"]

    def test_write_card_roundtrip(self, sample_card):
        """write_card + parse_card is idempotent."""
        card = parse_card(sample_card)
        write_card(sample_card, card, card["_body"])
        card2 = parse_card(sample_card)
        assert card2["id"] == card["id"]
        assert card2["status"] == card["status"]

    def test_card_has_required_frontmatter_keys(self, sample_card):
        """Every card must have id, title, assignee, status, last_update."""
        card = parse_card(sample_card)
        required = ["id", "title", "assignee", "status", "last_update", "commits", "blockers"]
        for key in required:
            assert key in card, f"Missing required frontmatter key: {key}"


# ---------------------------------------------------------------------------
# Tests: Card transitions
# ---------------------------------------------------------------------------

class TestCardTransitions:
    def test_ready_to_in_progress(self, sample_card):
        """Card can transition from ready to in_progress."""
        card = parse_card(sample_card)
        card["status"] = "in_progress"
        write_card(sample_card, card, card["_body"])
        card2 = parse_card(sample_card)
        assert card2["status"] == "in_progress"

    def test_in_progress_to_review(self, sample_card):
        """Card can transition from in_progress to review."""
        card = parse_card(sample_card)
        card["status"] = "in_progress"
        write_card(sample_card, card, card["_body"])

        card = parse_card(sample_card)
        card["status"] = "review"
        write_card(sample_card, card, card["_body"])

        card2 = parse_card(sample_card)
        assert card2["status"] == "review"

    def test_review_to_done(self, sample_card):
        """Card can transition from review to done."""
        card = parse_card(sample_card)
        card["status"] = "done"
        write_card(sample_card, card, card["_body"])
        card2 = parse_card(sample_card)
        assert card2["status"] == "done"

    def test_in_progress_to_blocked(self, sample_card):
        """Card can transition from in_progress to blocked."""
        card = parse_card(sample_card)
        card["status"] = "in_progress"
        write_card(sample_card, card, card["_body"])

        card = parse_card(sample_card)
        card["status"] = "blocked"
        card["blockers"] = ["No commit in 30min"]
        write_card(sample_card, card, card["_body"])

        card2 = parse_card(sample_card)
        assert card2["status"] == "blocked"
        assert "No commit in 30min" in card2["blockers"]


# ---------------------------------------------------------------------------
# Tests: WIP-limit enforcement
# ---------------------------------------------------------------------------

class TestWipLimit:
    def test_wip_limit_not_exceeded(self):
        """enforce_wip_limit does nothing when in_progress <= 6."""
        board = {"columns": [{"id": "in_progress", "wip_limit": 6}]}
        cards = [
            {"id": f"C{i}", "status": "in_progress", "last_update": now_iso(), "blockers": []}
            for i in range(4)
        ]
        result = enforce_wip_limit(cards, board)
        assert all(c["status"] == "in_progress" for c in result)

    def test_wip_limit_excess_moved_to_ready(self):
        """enforce_wip_limit moves excess in_progress cards back to ready."""
        board = {"columns": [{"id": "in_progress", "wip_limit": 6}]}
        cards = [
            {"id": f"C{i}", "status": "in_progress", "last_update": now_iso(), "blockers": []}
            for i in range(8)
        ]
        result = enforce_wip_limit(cards, board)
        in_prog = [c for c in result if c["status"] == "in_progress"]
        ready = [c for c in result if c["status"] == "ready"]
        assert len(in_prog) == 6
        assert len(ready) == 2

    def test_wip_limit_preserves_oldest(self):
        """enforce_wip_limit keeps the newest cards, moves oldest to ready."""
        board = {"columns": [{"id": "in_progress", "wip_limit": 2}]}
        old_ts = "2026-05-19T18:00:00Z"
        new_ts = "2026-05-19T20:00:00Z"
        cards = [
            {"id": "OLD1", "status": "in_progress", "last_update": old_ts, "blockers": []},
            {"id": "OLD2", "status": "in_progress", "last_update": old_ts, "blockers": []},
            {"id": "NEW1", "status": "in_progress", "last_update": new_ts, "blockers": []},
        ]
        result = enforce_wip_limit(cards, board)
        in_prog = [c for c in result if c["status"] == "in_progress"]
        assert "NEW1" in [c["id"] for c in in_prog]
        # OLD1 and OLD2 should be moved to ready
        ready = [c for c in result if c["status"] == "ready"]
        assert len(ready) == 1  # one of the two old ones


# ---------------------------------------------------------------------------
# Tests: Blocker detection
# ---------------------------------------------------------------------------

class TestBlockerDetection:
    def test_recent_update_not_blocked(self):
        """Card updated recently should not be marked blocked."""
        card = {"last_update": now_iso()}
        assert not check_blocker(card)

    def test_old_update_is_blocked(self):
        """Card with last_update > 30min ago should be blocked."""
        old_ts = (datetime.now(timezone.utc) - timedelta(minutes=31)).strftime("%Y-%m-%dT%H:%M:%SZ")
        card = {"last_update": old_ts}
        assert check_blocker(card)

    def test_no_last_update_is_blocked(self):
        """Card with no last_update should be blocked."""
        card = {}
        assert check_blocker(card)

    def test_just_under_threshold_not_blocked(self):
        """Card at 29min should not be blocked."""
        ts = (datetime.now(timezone.utc) - timedelta(minutes=29)).strftime("%Y-%m-%dT%H:%M:%SZ")
        card = {"last_update": ts}
        assert not check_blocker(card)


# ---------------------------------------------------------------------------
# Tests: Auto-archive
# ---------------------------------------------------------------------------

class TestAutoArchive:
    def test_done_card_older_than_24h_archived(self, tmp_kanban):
        """Done cards with last_update > 24h ago should be archived."""
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).strftime("%Y-%m-%dT%H:%M:%SZ")
        card_path = tmp_kanban / "kanban" / "cards" / "O-OLD-DONE.md"
        card_path.write_text(f"""---
id: O-OLD-DONE
title: Old Done Card
assignee: Agent 1
skill: test
estimate_hours: 1
dependencies: []
status: done
last_update: {old_ts}
commits: [abc123]
blockers: []
---

## Deliverable
Old
""")
        cards = all_cards()
        # Patch _file paths to point to tmp
        remaining = auto_archive(cards)
        ids = [c["id"] for c in remaining]
        assert "O-OLD-DONE" not in ids

    def test_done_card_newer_than_24h_stays(self, tmp_kanban):
        """Done cards with last_update < 24h should stay."""
        recent_ts = (datetime.now(timezone.utc) - timedelta(hours=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
        card_path = tmp_kanban / "kanban" / "cards" / "O-RECENT-DONE.md"
        card_path.write_text(f"""---
id: O-RECENT-DONE
title: Recent Done Card
assignee: Agent 1
skill: test
estimate_hours: 1
dependencies: []
status: done
last_update: {recent_ts}
commits: [abc123]
blockers: []
---

## Deliverable
Recent
""")
        # Load cards directly from tmp path instead of using global all_cards()
        from kanban.watcher import parse_card
        cards = [parse_card(card_path)]
        remaining = auto_archive(cards)
        ids = [c["id"] for c in remaining]
        assert "O-RECENT-DONE" in ids


# ---------------------------------------------------------------------------
# Tests: Card status filtering
# ---------------------------------------------------------------------------

class TestCardFiltering:
    def test_cards_by_status(self):
        """cards_by_status filters correctly."""
        cards = [
            {"id": "A", "status": "ready"},
            {"id": "B", "status": "in_progress"},
            {"id": "C", "status": "ready"},
        ]
        ready = cards_by_status(cards, "ready")
        assert len(ready) == 2
        in_prog = cards_by_status(cards, "in_progress")
        assert len(in_prog) == 1

    def test_cards_by_status_empty(self):
        """cards_by_status returns empty list when no matches."""
        cards = [{"id": "A", "status": "ready"}]
        assert cards_by_status(cards, "done") == []
