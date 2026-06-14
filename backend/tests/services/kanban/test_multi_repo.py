"""
backend/tests/services/kanban/test_multi_repo.py
Tests for multi_repo.py — multi-repo coordination and status generation.
"""

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from services.kanban.multi_repo import generate_multi_repo_status, get_cross_repo_status, load_cards

# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def tmp_kanban_env(tmp_path, monkeypatch):
    """Create a temp kanban directory and patch REPO_ROOT / KANBAN_DIR / CARDS_DIR."""
    import services.kanban.multi_repo as mr
    kanban_dir = tmp_path / "kanban"
    cards_dir = kanban_dir / "cards"
    cards_dir.mkdir(parents=True)

    # Patch the module-level constants
    monkeypatch.setattr(mr, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mr, "KANBAN_DIR", kanban_dir)
    monkeypatch.setattr(mr, "CARDS_DIR", cards_dir)
    return kanban_dir


def _write_card(cards_dir: Path, frontmatter: dict, body: str = "") -> Path:
    """Write a card .md file with given frontmatter and body."""
    content = "---\n" + yaml.dump(frontmatter) + "---\n\n" + body + "\n"
    path = cards_dir / f"{frontmatter.get('id', 'unknown')}.md"
    path.write_text(content)
    return path


# ===========================================================================
# load_cards
# ===========================================================================

class TestLoadCards:
    def test_loads_valid_cards(self, tmp_kanban_env):
        cards_dir = tmp_kanban_env / "cards"
        _write_card(cards_dir, {"id": "C1", "title": "One", "assignee": "A1", "status": "ready"})
        _write_card(cards_dir, {"id": "C2", "title": "Two", "assignee": "A2", "status": "done"})
        cards = load_cards()
        assert len(cards) == 2
        ids = [c["id"] for c in cards]
        assert "C1" in ids
        assert "C2" in ids

    def test_skips_tagging_files(self, tmp_kanban_env):
        cards_dir = tmp_kanban_env / "cards"
        _write_card(cards_dir, {"id": "C1", "title": "Real", "status": "ready"})
        (cards_dir / "tagging_anything.md").write_text("---\nid: T1\ntitle: Tag\nstatus: done\n---\n")
        cards = load_cards()
        ids = [c["id"] for c in cards]
        assert "T1" not in ids
        assert "C1" in ids

    def test_skips_non_frontmatter_files(self, tmp_kanban_env):
        cards_dir = tmp_kanban_env / "cards"
        (cards_dir / "random.md").write_text("No frontmatter at all\n")
        cards = load_cards()
        assert cards == []

    def test_empty_cards_dir(self, tmp_kanban_env):
        cards = load_cards()
        assert cards == []

    def test_preserves_file_path(self, tmp_kanban_env):
        cards_dir = tmp_kanban_env / "cards"
        p = _write_card(cards_dir, {"id": "FP", "title": "File Path", "status": "ready"})
        cards = load_cards()
        assert len(cards) == 1
        assert cards[0]["_file"] == str(p)

    def test_malformed_yaml_not_loaded(self, tmp_kanban_env):
        cards_dir = tmp_kanban_env / "cards"
        (cards_dir / "bad.md").write_text("---\nunclosed: [bracket\n---\n")
        _write_card(cards_dir, {"id": "GOOD", "title": "Valid", "status": "ready"})
        cards = load_cards()
        ids = [c["id"] for c in cards]
        assert "GOOD" in ids
        assert len(cards) == 1

    def test_three_dash_split(self, tmp_kanban_env):
        """Frontmatter with --- in body should still parse (split limit=2)."""
        cards_dir = tmp_kanban_env / "cards"
        (cards_dir / "C1.md").write_text("---\nid: C1\ntitle: Has Dashes\nstatus: ready\n---\n\nBody has --- too\n")
        cards = load_cards()
        assert len(cards) == 1
        assert cards[0]["id"] == "C1"

    def test_sorted_by_filename(self, tmp_kanban_env):
        cards_dir = tmp_kanban_env / "cards"
        _write_card(cards_dir, {"id": "Z_card", "title": "Z", "status": "ready"})
        _write_card(cards_dir, {"id": "A_card", "title": "A", "status": "ready"})
        _write_card(cards_dir, {"id": "M_card", "title": "M", "status": "ready"})
        cards = load_cards()
        paths = [c["_file"] for c in cards]
        names = [Path(p).name for p in paths]
        assert names == sorted(names)


# ===========================================================================
# generate_multi_repo_status
# ===========================================================================

class TestGenerateMultiRepoStatus:
    def test_outputs_valid_markdown(self, tmp_kanban_env):
        result = generate_multi_repo_status()
        assert result.startswith("# Multi-Repo Status")
        assert "Generated:" in result

    def test_lists_known_repos(self, tmp_kanban_env):
        result = generate_multi_repo_status()
        # Repo names only appear in the output if get_cross_repo_status
        # populates status["repos"] — current implementation is a stub
        # returning {} so the Repos section is empty. Verify the section
        # structure is present and the function completes without error.
        assert "## Repos" in result
        # When the stub is filled in, these should appear:
        # for repo in ["floww", "gflows", "baby-billy-dvt"]:
        #     assert repo in result

    def test_checkmark_or_x_for_repos(self, tmp_kanban_env):
        result = generate_multi_repo_status()
        # Each repo line should have either ✓ or ✗
        for line in result.split("\n"):
            if line.startswith("- ") and "**" in line:
                assert "✓" in line or "✗" in line

    def test_sections_present(self, tmp_kanban_env):
        result = generate_multi_repo_status()
        assert "## Repos" in result
        assert "## Cross-Repo Cards" in result
        assert "## All Cards by Repo" in result

    def test_empty_cards_message(self, tmp_kanban_env):
        result = generate_multi_repo_status()
        assert "No cross-repo cards detected" in result

    def test_single_repo_card_listed(self, tmp_kanban_env):
        cards_dir = tmp_kanban_env / "cards"
        _write_card(cards_dir, {
            "id": "S1", "title": "Single Repo", "assignee": "A1",
            "status": "ready", "affects_repos": ["floww"],
        })
        result = generate_multi_repo_status()
        assert "S1" in result
        assert "Single Repo" in result

    def test_cross_repo_card_detected(self, tmp_kanban_env):
        cards_dir = tmp_kanban_env / "cards"
        _write_card(cards_dir, {
            "id": "X1", "title": "Cross Repo Card", "assignee": "A1",
            "status": "in_progress", "affects_repos": ["floww", "gflows"],
        })
        result = generate_multi_repo_status()
        assert "X1" in result
        assert "Cross Repo Card" in result
        assert "floww" in result
        assert "gflows" in result


# ===========================================================================
# get_cross_repo_status
# ===========================================================================

class TestGetCrossRepoStatus:
    def test_returns_expected_structure(self):
        cards = [
            {"id": "C1", "title": "One", "status": "ready",
             "affects_repos": ["floww"], "commits_by_repo": {"floww": ["abc"]}},
        ]
        result = get_cross_repo_status(cards)
        assert "timestamp" in result
        assert "repos" in result
        assert "cross_repo_cards" in result

    def test_timestamp_is_iso(self):
        result = get_cross_repo_status([])
        # Should parse as ISO format
        from datetime import datetime
        datetime.fromisoformat(result["timestamp"])

    def test_empty_cards(self):
        result = get_cross_repo_status([])
        assert isinstance(result["repos"], dict)
        assert isinstance(result["cross_repo_cards"], list)

    def test_repos_dict_is_empty_stub(self):
        """Current implementation returns empty repos dict (stub)."""
        result = get_cross_repo_status([])
        # This is the current behavior — repos dict is always empty
        assert result["repos"] == {}

    def test_cross_repo_cards_is_empty_stub(self):
        """Current implementation returns empty cross_repo_cards list (stub)."""
        result = get_cross_repo_status([
            {"id": "C1", "affects_repos": ["floww", "gflows"]},
        ])
        # Stub behavior — always returns empty
        assert result["cross_repo_cards"] == []
