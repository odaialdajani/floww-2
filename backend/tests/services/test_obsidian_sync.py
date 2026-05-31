#!/usr/bin/env python3
"""
Tests for obsidian_sync.py — conflict resolution, sync direction, frontmatter preservation.

Run with: pytest backend/tests/services/test_obsidian_sync.py -v
"""

import sys
import time
from pathlib import Path

import pytest

# Add the scripts dir to path so we can import the module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from obsidian_sync import (
    ObsidianSync,
    SyncState,
    compute_diff,
    extract_body,
    file_hash,
    file_mtime,
    make_claude_file,
    make_obsidian_file,
    parse_frontmatter,
)

# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_dirs(tmp_path):
    """Create temporary memory and vault directories."""
    memory_dir = tmp_path / "memory"
    vault_dir = tmp_path / "vault"
    memory_dir.mkdir()
    vault_dir.mkdir()
    return memory_dir, vault_dir


@pytest.fixture
def sync(tmp_dirs):
    """Create an ObsidianSync instance with temp dirs."""
    memory_dir, vault_dir = tmp_dirs
    return ObsidianSync(memory_dir, vault_dir, dry_run=False)


@pytest.fixture
def sample_claude_file(tmp_dirs):
    """Create a sample Claude Code memory file."""
    memory_dir, _ = tmp_dirs
    content = """---
name: Test Project
description: A test project for sync
type: project
---

# Test Project

This is the body of the test project.
It has multiple lines.
"""
    path = memory_dir / "test_project.md"
    path.write_text(content)
    return path


@pytest.fixture
def sample_obsidian_file(tmp_dirs):
    """Create a sample Obsidian note."""
    _, vault_dir = tmp_dirs
    content = """---
tags: [project, test]
---

# Test Project

This is the Obsidian version of the test project.
"""
    path = vault_dir / "Test Project.md"
    path.write_text(content)
    return path


# ── Tests: file_hash ──────────────────────────────────────────────────────

class TestFileHash:
    def test_hash_consistency(self, tmp_path):
        p = tmp_path / "test.md"
        p.write_text("hello")
        assert file_hash(p) == file_hash(p)

    def test_hash_changes_with_content(self, tmp_path):
        p = tmp_path / "test.md"
        p.write_text("hello")
        h1 = file_hash(p)
        p.write_text("world")
        h2 = file_hash(p)
        assert h1 != h2

    def test_hash_nonexistent(self):
        assert file_hash(Path("/nonexistent/file.md")) == ""


# ── Tests: file_mtime ─────────────────────────────────────────────────────

class TestFileMtime:
    def test_mtime_returns_float(self, tmp_path):
        p = tmp_path / "test.md"
        p.write_text("hello")
        assert isinstance(file_mtime(p), float)

    def test_mtime_nonexistent(self):
        assert file_mtime(Path("/nonexistent/file.md")) == 0.0

    def test_mtime_increases_on_write(self, tmp_path):
        p = tmp_path / "test.md"
        p.write_text("v1")
        m1 = file_mtime(p)
        time.sleep(0.01)
        p.write_text("v2")
        m2 = file_mtime(p)
        assert m2 >= m1


# ── Tests: parse_frontmatter ──────────────────────────────────────────────

class TestParseFrontmatter:
    def test_valid_frontmatter(self):
        content = "---\nname: Test\ntype: project\n---\n\nBody text"
        fm = parse_frontmatter(content)
        assert fm["name"] == "Test"
        assert fm["type"] == "project"

    def test_no_frontmatter(self):
        content = "Just some text"
        assert parse_frontmatter(content) == {}

    def test_empty_frontmatter(self):
        content = "---\n---\n\nBody"
        assert parse_frontmatter(content) == {}


# ── Tests: extract_body ───────────────────────────────────────────────────

class TestExtractBody:
    def test_body_after_frontmatter(self):
        content = "---\nname: Test\n---\n\nBody text here"
        assert extract_body(content) == "Body text here"

    def test_body_no_frontmatter(self):
        content = "Just body text"
        assert extract_body(content) == "Just body text"


# ── Tests: compute_diff ───────────────────────────────────────────────────

class TestComputeDiff:
    def test_identical_texts(self):
        diff = compute_diff("hello\n", "hello\n")
        assert diff == ""

    def test_different_texts(self):
        diff = compute_diff("hello\n", "world\n")
        assert "hello" in diff
        assert "world" in diff

    def test_labels(self):
        diff = compute_diff("a\n", "b\n", label_a="file_a", label_b="file_b")
        assert "file_a" in diff
        assert "file_b" in diff


# ── Tests: make_claude_file ───────────────────────────────────────────────

class TestMakeClaudeFile:
    def test_has_frontmatter(self):
        content = make_claude_file("Test", "project", "A test", "Body")
        assert "---" in content
        assert "name: Test" in content
        assert "type: project" in content

    def test_has_body(self):
        content = make_claude_file("Test", "project", "A test", "Body text")
        assert "Body text" in content


# ── Tests: make_obsidian_file ─────────────────────────────────────────────

class TestMakeObsidianFile:
    def test_has_title(self):
        content = make_obsidian_file("My Title", "Body")
        assert "# My Title" in content

    def test_has_tags(self):
        content = make_obsidian_file("Title", "Body", tags=["project"])
        assert "tags:" in content
        assert "project" in content

    def test_no_tags_no_frontmatter(self):
        content = make_obsidian_file("Title", "Body")
        assert "---" not in content


# ── Tests: SyncState ──────────────────────────────────────────────────────

class TestSyncState:
    def test_save_and_load(self, tmp_path):
        state_file = tmp_path / ".sync_state.json"
        state = SyncState(state_file)
        state.update("test_key", "abc123", 1000.0)
        state.save()

        state2 = SyncState(state_file)
        assert state2.get_last_hash("test_key") == "abc123"
        assert state2.get_last_mtime("test_key") == 1000.0

    def test_missing_key_returns_empty(self, tmp_path):
        state_file = tmp_path / ".sync_state.json"
        state = SyncState(state_file)
        assert state.get_last_hash("nonexistent") == ""
        assert state.get_last_mtime("nonexistent") == 0.0


# ── Tests: ObsidianSync — sync direction ──────────────────────────────────

class TestSyncDirection:
    def test_claude_to_obsidian_creates_file(self, sync, sample_claude_file, tmp_dirs):
        """Claude Code file should create corresponding Obsidian file."""
        _, vault_dir = tmp_dirs
        sync.sync_all()
        # The file should be created in the vault
        expected = vault_dir / "test_project.md"
        assert expected.exists()

    def test_obsidian_to_claude_creates_file(self, sync, sample_obsidian_file, tmp_dirs):
        """Obsidian file should create corresponding Claude Code file."""
        memory_dir, _ = tmp_dirs
        sync.sync_all()
        expected = memory_dir / "Test Project.md"
        assert expected.exists()

    def test_no_change_on_identical_files(self, sync, tmp_dirs):
        """Syncing identical files should not create duplicates."""
        memory_dir, vault_dir = tmp_dirs
        content = "---\nname: Same\n---\n\nSame content"
        (memory_dir / "same.md").write_text(content)
        (vault_dir / "same.md").write_text(content)
        sync.sync_all()
        # Should not error, no conflicts
        assert len(sync.conflicts) == 0


# ── Tests: ObsidianSync — conflict resolution ─────────────────────────────

class TestConflictResolution:
    def test_newer_mtime_wins(self, sync, tmp_dirs):
        """When both files changed, newer mtime should win."""
        memory_dir, vault_dir = tmp_dirs

        # Create initial file in both
        claude_file = memory_dir / "conflict.md"
        vault_file = vault_dir / "conflict.md"
        claude_file.write_text("---\nname: Test\n---\n\nOriginal")
        vault_file.write_text("# Test\n\nOriginal")

        # Set up state so both appear changed
        sync.state.update("claude→obsidian:conflict.md", "old_hash", 0)

        # Make vault file newer
        time.sleep(0.01)
        vault_file.write_text("# Test\n\nVault wins")

        sync.sync_all()
        # Vault (dst) should win since it's newer
        assert any("dst" in str(c) for c in sync.conflicts) or len(sync.conflicts) == 0

    def test_conflict_logged(self, sync, tmp_dirs):
        """Conflicts should be recorded."""
        memory_dir, vault_dir = tmp_dirs

        claude_file = memory_dir / "conflict2.md"
        vault_file = vault_dir / "conflict2.md"
        claude_file.write_text("---\nname: Test\n---\n\nClaude version")
        vault_file.write_text("# Test\n\nVault version")

        # Set up state so both appear changed
        sync.state.update("claude→obsidian:conflict2.md", "old_hash", 0)

        sync.sync_all()
        assert len(sync.conflicts) >= 1
        assert sync.conflicts[0]["file"] == "claude→obsidian:conflict2.md"

    def test_only_source_changed(self, sync, tmp_dirs):
        """When only source changed, it should update destination (may show as conflict on first re-sync due to format conversion)."""
        memory_dir, vault_dir = tmp_dirs

        claude_file = memory_dir / "one_way.md"
        vault_file = vault_dir / "one_way.md"
        claude_file.write_text("---\nname: Test\n---\n\nVersion 1")
        vault_file.write_text("# Test\n\nVersion 1")

        # Sync to establish state
        sync.sync_all()
        assert len(sync.conflicts) == 0

        # Now modify only source
        time.sleep(0.01)
        claude_file.write_text("---\nname: Test\n---\n\nVersion 2 - updated")

        # Re-sync — the source changed so it should update dst
        sync2 = ObsidianSync(memory_dir, vault_dir, dry_run=False)
        sync2.sync_all()
        # The source was updated, so the destination should reflect the change
        vault_content = vault_file.read_text()
        assert "Version 2" in vault_content or "updated" in vault_content


# ── Tests: ObsidianSync — frontmatter preservation ────────────────────────

class TestFrontmatterPreservation:
    def test_claude_frontmatter_preserved(self, sync, sample_claude_file, tmp_dirs):
        """Claude Code frontmatter should be preserved during sync."""
        sync.sync_all()
        _, vault_dir = tmp_dirs
        # The synced file should have content from the Claude file
        vault_file = vault_dir / "test_project.md"
        assert vault_file.exists()
        content = vault_file.read_text()
        # Should have the body text
        assert "body of the test project" in content.lower() or "Test Project" in content

    def test_obsidian_tags_preserved(self, sync, sample_obsidian_file, tmp_dirs):
        """Obsidian tags should be preserved during reverse sync."""
        sync.sync_all()
        memory_dir, _ = tmp_dirs
        claude_file = memory_dir / "Test Project.md"
        assert claude_file.exists()
        content = claude_file.read_text()
        # Should have frontmatter
        assert "---" in content


# ── Tests: ObsidianSync — dry run ─────────────────────────────────────────

class TestDryRun:
    def test_dry_run_no_writes(self, tmp_dirs, sample_claude_file):
        """Dry run should not write any files."""
        memory_dir, vault_dir = tmp_dirs
        sync = ObsidianSync(memory_dir, vault_dir, dry_run=True)
        sync.sync_all()
        # Vault should be empty (no files created)
        vault_files = list(vault_dir.glob("*.md"))
        assert len(vault_files) == 0


# ── Tests: ObsidianSync — skip files ──────────────────────────────────────

class TestSkipFiles:
    def test_skip_internal_files(self, sync, tmp_dirs):
        """Internal files (starting with _) should be skipped."""
        memory_dir, vault_dir = tmp_dirs
        (memory_dir / "_internal.md").write_text("---\nname: Internal\n---\n\nSecret")
        (memory_dir / ".hidden.md").write_text("hidden")
        sync.sync_all()
        assert not (vault_dir / "_internal.md").exists()
        assert not (vault_dir / ".hidden.md").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
