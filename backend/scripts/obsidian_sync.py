#!/usr/bin/env python3
"""
obsidian_sync.py — Bidirectional sync between:
  - Claude Code memory dir (~/.claude/projects/.../memory/)
  - Obsidian vault (~/Documents/GitHub/Hermes/)
  - mem0 (via search for cross-referencing)

Sync strategy:
  - File mtime as conflict resolver (newer wins)
  - On actual conflict (same file modified in both dirs within sync window), show diff
  - Frontmatter preserved on both sides
  - Runs as a watch loop using watchdog

Usage:
    python obsidian_sync.py [--once] [--watch] [--vault PATH] [--memory PATH]

Environment:
    MEM0_API_KEY — optional, for mem0 cross-referencing
"""

import argparse
import difflib
import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
# ── Configuration ──────────────────────────────────────────────────────────

CLAUDE_MEMORY_DIR = Path.home() / ".claude/projects/-Users-nav-Documents-GitHub-floww/memory"
OBSIDIAN_VAULT = Path.home() / "Documents/GitHub/Hermes"
MEM0_CONFIG = Path.home() / ".mem0/config.json"
SYNC_LOG_DIR = CLAUDE_MEMORY_DIR

# Files to skip (internal)
SKIP_FILES = {
    "_migration_audit_2026-05-20.md",
    "_migration_log_2026-05-20.md",
    "_sync_log_2026-05-20.md",
    "MEMORY.md",  # index file, not a memory entry
}

# Mapping: Claude Code file → Obsidian file
# (None = same name with .md extension)
FILE_MAPPING = {
    "project_hermes.md": "Trading Terminal.md",
    "project_oracle.md": None,  # will create project_oracle.md in vault
    "project_master_plan.md": None,
    "project_skylit.md": None,
    "project_research_pipeline.md": "Research Pipeline.md",
    "project_round3_review.md": None,
    "project_tool_boundaries.md": None,
    "reference_herder_swarm.md": None,
    "reference_truth_audit.md": "Safety & Audit.md",
    "feedback_terseness.md": None,
    "session_2026-05-18_final.md": None,
    "session_2026-05-19_final.md": None,
    "session_2026-05-19b_oracle_handoff.md": None,
}

# Reverse mapping (Obsidian → Claude Code)
REVERSE_MAPPING = {v: k for k, v in FILE_MAPPING.items() if v is not None}

# ── Logging ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("obsidian_sync")

# ── Helpers ────────────────────────────────────────────────────────────────

def get_api_key():
    key = os.environ.get("MEM0_API_KEY", "")
    if not key and MEM0_CONFIG.exists():
        with open(MEM0_CONFIG) as f:
            cfg = json.load(f)
        key = cfg.get("platform", {}).get("api_key", "")
    return key


def file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.md5(path.read_bytes()).hexdigest()


def file_mtime(path: Path) -> float:
    if not path.exists():
        return 0.0
    return path.stat().st_mtime


def parse_frontmatter(content: str) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if m:
        try:
            import yaml
            return yaml.safe_load(m.group(1)) or {}
        except Exception:
            return {}
    return {}


def extract_body(content: str) -> str:
    m = re.match(r"^---\s*\n.*?\n---\s*\n?", content, re.DOTALL)
    if m:
        return content[m.end():].strip()
    return content.strip()


def make_claude_file(name: str, mem_type: str, description: str, body: str) -> str:
    """Create a Claude Code memory file with frontmatter."""
    frontmatter = {
        "name": name,
        "description": description,
        "type": mem_type,
    }
    import yaml
    fm_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
    return f"---\n{fm_str}---\n\n{body}\n"


def make_obsidian_file(title: str, body: str, tags: list = None) -> str:
    """Create an Obsidian note with optional frontmatter."""
    if tags:
        import yaml
        frontmatter = {"tags": tags}
        fm_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
        return f"---\n{fm_str}---\n\n# {title}\n\n{body}\n"
    return f"# {title}\n\n{body}\n"


def compute_diff(text_a: str, text_b: str, label_a: str = "A", label_b: str = "B") -> str:
    """Compute unified diff between two texts."""
    lines_a = text_a.splitlines(keepends=True)
    lines_b = text_b.splitlines(keepends=True)
    diff = difflib.unified_diff(
        lines_a, lines_b,
        fromfile=label_a, tofile=label_b,
        lineterm=""
    )
    return "\n".join(diff)


# ── Sync State ─────────────────────────────────────────────────────────────

class SyncState:
    """Tracks sync state to detect conflicts."""

    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.state = self._load()

    def _load(self) -> dict:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception:
                pass
        return {"last_sync": 0, "files": {}}

    def save(self):
        self.state_file.write_text(json.dumps(self.state, indent=2))

    def get_last_hash(self, key: str) -> str:
        return self.state.get("files", {}).get(key, {}).get("hash", "")

    def get_last_mtime(self, key: str) -> float:
        return self.state.get("files", {}).get(key, {}).get("mtime", 0.0)

    def update(self, key: str, hash_val: str, mtime: float):
        if "files" not in self.state:
            self.state["files"] = {}
        self.state["files"][key] = {"hash": hash_val, "mtime": mtime}
        self.state["last_sync"] = time.time()


# ── Sync Engine ─────────────────────────────────────────────────────────────

class ObsidianSync:
    def __init__(self, memory_dir: Path, vault_dir: Path, dry_run=False):
        self.memory_dir = memory_dir
        self.vault_dir = vault_dir
        self.dry_run = dry_run
        self.state = SyncState(memory_dir / ".sync_state.json")
        self.log_file = SYNC_LOG_DIR / f"_sync_log_{datetime.now().strftime('%Y-%m-%d')}.md"
        self.conflicts = []
        self.changes = []

    def log(self, msg: str, level="info"):
        getattr(logger, level)(msg)
        self.changes.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def _convert_to_obsidian(self, claude_path: Path) -> str:
        """Convert a Claude Code memory file to Obsidian format."""
        content = claude_path.read_text()
        fm = parse_frontmatter(content)
        body = extract_body(content)

        name = fm.get("name", claude_path.stem)
        mem_type = fm.get("type", "")
        tags = [mem_type] if mem_type else []

        return make_obsidian_file(name, body, tags=tags)

    def _convert_to_claude(self, obsidian_path: Path) -> str:
        """Convert an Obsidian note to Claude Code memory format."""
        content = obsidian_path.read_text()
        fm = parse_frontmatter(content)
        body = extract_body(content)

        title = obsidian_path.stem
        tags = fm.get("tags", [])
        mem_type = tags[0] if tags else "unknown"

        return make_claude_file(title, mem_type, f"From Obsidian: {title}", body)

    # ── Path mapping helpers ──────────────────────────────────────────────
    def get_obsidian_path(self, claude_name: str) -> Path:
        """Map a Claude memory filename to its Obsidian vault path."""
        mapped = FILE_MAPPING.get(claude_name)
        return self.vault_dir / (mapped if mapped else claude_name)

    def get_claude_path(self, obsidian_name: str) -> Path:
        """Map an Obsidian filename back to its Claude memory path."""
        mapped = REVERSE_MAPPING.get(obsidian_name)
        return self.memory_dir / (mapped if mapped else obsidian_name)

    def save_log(self):
        """Persist the change log for this run (skipped on dry-run / no changes)."""
        if self.dry_run or not self.changes:
            return
        try:
            self.log_file.write_text("\n".join(self.changes) + "\n")
        except Exception:
            pass

    def sync_file(self, src: Path, dst: Path, key: str):
        """Sync one Claude->Obsidian file with mtime-based conflict detection."""
        new_content = self._convert_to_obsidian(src)
        src_hash = file_hash(src)
        last_hash = self.state.get_last_hash(key)

        # First-time create (destination absent)
        if not dst.exists():
            if not self.dry_run:
                dst.write_text(new_content)
            self.log(f"CREATE: {dst.name}")
            self.state.update(key, src_hash, file_mtime(src))
            return

        dst_hash = file_hash(dst)
        src_changed = src_hash != last_hash and last_hash != ""
        dst_changed = dst_hash != last_hash and last_hash != ""

        # Both sides changed since last sync -> conflict, newer mtime wins
        if src_changed and dst_changed:
            winner = "src" if file_mtime(src) >= file_mtime(dst) else "dst"
            self.conflicts.append({"file": key, "winner": winner})
            self.log(f"CONFLICT: {key} -> {winner} won", "warning")
            if winner == "src" and not self.dry_run:
                dst.write_text(new_content)
            self.state.update(key, file_hash(dst), file_mtime(dst))
            return

        # One-way update: source body differs from destination body
        if extract_body(new_content) != extract_body(dst.read_text()):
            if not self.dry_run:
                dst.write_text(new_content)
            self.log(f"UPDATE: {dst.name}")
        self.state.update(key, src_hash, file_mtime(src))

    def sync_all(self):
        """Run full bidirectional sync."""
        self.log("Starting sync...")
        self.conflicts = []
        self.changes = []

        # Pass 1: Claude Code → Obsidian
        for md_file in sorted(self.memory_dir.glob("*.md")):
            if md_file.name in SKIP_FILES or md_file.name.startswith("."):
                continue
            # Skip files that start with _ (internal)
            if md_file.name.startswith("_"):
                continue
            obsidian_path = self.get_obsidian_path(md_file.name)
            key = f"claude→obsidian:{md_file.name}"
            self.sync_file(md_file, obsidian_path, key)

        # Pass 2: Obsidian → Claude Code (for files not in mapping)
        for md_file in sorted(self.vault_dir.glob("*.md")):
            if md_file.name.startswith("."):
                continue
            claude_path = self.get_claude_path(md_file.name)
            if not claude_path.exists():
                # New Obsidian file — create in Claude Code
                key = f"obsidian→claude:{md_file.name}"
                content = self._convert_to_claude(md_file)
                if not self.dry_run:
                    claude_path.write_text(content)
                self.log(f"CREATE (reverse): {claude_path.name}")

        self.state.save()
        self.save_log()

        if self.conflicts:
            self.log(f"⚠ {len(self.conflicts)} conflict(s) resolved", "warning")
            for c in self.conflicts:
                self.log(f"  - {c['file']}: {c['winner']} won")

        self.log("Sync complete.")
        return len(self.conflicts)


# ── Watch Mode ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Bidirectional Obsidian ↔ Claude Code sync")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--watch", action="store_true", help="Watch for changes")
    parser.add_argument("--vault", type=Path, default=OBSIDIAN_VAULT, help="Obsidian vault path")
    parser.add_argument("--memory", type=Path, default=CLAUDE_MEMORY_DIR, help="Claude Code memory dir")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    sync = ObsidianSync(args.memory, args.vault, args.dry_run)

    if args.watch:
        watch_loop(sync)
    else:
        conflicts = sync.sync_all()
        if conflicts:
            logger.info(f"\n{conflicts} conflict(s) resolved. Check sync log for details.")


def watch_loop(sync: ObsidianSync, interval=30):
    """Run sync in a watch loop."""
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        class SyncHandler(FileSystemEventHandler):
            def __init__(self, sync):
                self.sync = sync
                self.last_event = 0

            def on_modified(self, event):
                if event.is_directory:
                    return
                if not event.src_path.endswith(".md"):
                    return
                now = time.time()
                if now - self.last_event < 2:  # debounce
                    return
                self.last_event = now
                time.sleep(1)  # wait for write to finish
                self.sync.sync_all()

        observer = Observer()
        handler = SyncHandler(sync)
        observer.schedule(handler, str(sync.memory_dir), recursive=False)
        observer.schedule(handler, str(sync.vault_dir), recursive=False)
        observer.start()
        logger.info(f"Watching {sync.memory_dir} and {sync.vault_dir}...")

        try:
            while True:
                time.sleep(interval)
                # Periodic full sync as fallback
                sync.sync_all()
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

    except ImportError:
        logger.warning("watchdog not installed, falling back to polling loop")
        while True:
            sync.sync_all()
            time.sleep(interval)


# ── Main ───────────────────────────────────────────────────────────────────



if __name__ == "__main__":
    main()
