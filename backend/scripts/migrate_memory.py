#!/usr/bin/env python3
"""
migrate_memory.py — Migrate Claude Code memory + PLUR engrams to mem0.

Uses the mem0 Python SDK directly for reliable API calls.

Usage:
    python migrate_memory.py [--dry-run] [--source claude|plur|all]

Environment:
    MEM0_API_KEY — mem0 Platform API key (or reads from ~/.mem0/config.json)
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
# ── Paths ──────────────────────────────────────────────────────────────────

CLAUDE_MEMORY_DIR = Path.home() / ".claude/projects/-Users-nav-Documents-GitHub-floww/memory"
PLUR_ENGRAMS_FILE = Path.home() / "Documents/GitHub/plur/.plur/engrams.yaml"
OBSIDIAN_VAULT = Path.home() / "Documents/GitHub/Hermes"
MEM0_CONFIG = Path.home() / ".mem0/config.json"
LOG_FILE = CLAUDE_MEMORY_DIR / "_migration_log_2026-05-20.md"

# ── Helpers ────────────────────────────────────────────────────────────────

def get_api_key():
    key = os.environ.get("MEM0_API_KEY", "")
    if not key and MEM0_CONFIG.exists():
        with open(MEM0_CONFIG) as f:
            cfg = json.load(f)
        key = cfg.get("platform", {}).get("api_key", "")
    if not key:
        logger.warning("ERROR: MEM0_API_KEY not found.")
        sys.exit(1)
    return key


def get_user_id():
    if MEM0_CONFIG.exists():
        with open(MEM0_CONFIG) as f:
            cfg = json.load(f)
        return cfg.get("defaults", {}).get("user_id", "user_c778280e23af")
    return "user_c778280e23af"


def make_memory_text(name: str, description: str, body: str) -> str:
    """Build a clean memory text from Claude Code memory file."""
    parts = []
    if name:
        parts.append(f"## {name}")
    if description:
        parts.append(f"**Description:** {description}")
    if body:
        parts.append(body)
    return "\n\n".join(parts)


# -- mem0 SDK wrapper ---------------------------------------------------------

class Mem0Migrator:
    def __init__(self, api_key: str, user_id: str):
        self.api_key = api_key
        self.user_id = user_id
        self.client = None
        self._init_client()

    def _init_client(self):
        try:
            from mem0 import MemoryClient
            self.client = MemoryClient(api_key=self.api_key)
            logger.info("mem0 client initialized (Platform mode)")
        except Exception as e:
            logger.warning(f"ERROR initializing mem0 client: {e}")
            sys.exit(1)

    def add(self, text: str, categories: list = None, metadata: dict = None, dry_run=False) -> dict:
        if dry_run:
            logger.info(f"  [DRY-RUN] {text[:80]}...")
            return {"status": "dry_run", "id": "dry-run"}

        try:
            result = self.client.add(
                messages=[{"role": "user", "content": text}],
                user_id=self.user_id,
                categories=categories or {},
                metadata=metadata or {},
            )
            return {"status": "success", "result": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def search(self, query: str, limit=3) -> list:
        try:
            results = self.client.search(
                query=query,
                user_id=self.user_id,
                limit=limit,
            )
            return results if isinstance(results, list) else results.get("results", results.get("data", []))
        except Exception:
            return []

    def is_duplicate(self, text: str, threshold=0.85) -> bool:
        results = self.search(text[:100], limit=3)
        for r in results:
            score = r.get("score", 0)
            if score >= threshold:
                return True
        return False

    def count_memories(self) -> int:
        try:
            results = self.client.get_all(user_id=self.user_id, limit=1)
            if isinstance(results, dict):
                return results.get("total", len(results.get("results", results.get("data", []))))
            return len(results) if isinstance(results, list) else 0
        except Exception:
            return -1


# -- Migration Logic ----------------------------------------------------------


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


def migrate_claude_memory(migrator: Mem0Migrator, dry_run=False) -> dict:
    stats = {"total": 0, "added": 0, "skipped": 0, "errors": 0, "files": []}
    skip_files = {"_migration_audit_2026-05-20.md", "_migration_log_2026-05-20.md"}

    md_files = sorted(CLAUDE_MEMORY_DIR.glob("*.md"))

    for md_file in md_files:
        if md_file.name in skip_files or md_file.name.startswith("_"):
            continue

        stats["total"] += 1
        content = md_file.read_text()
        fm = parse_frontmatter(content)
        body = extract_body(content)

        name = fm.get("name", md_file.stem)
        mem_type = fm.get("type", "unknown")
        description = fm.get("description", "")

        memory_text = make_memory_text(name, description, body)
        categories = [mem_type] if mem_type != "unknown" else []
        metadata = {
            "source": "claude-code",
            "file": md_file.name,
            "type": mem_type,
            "migrated_at": datetime.now().isoformat()
        }

        logger.info(f"[{stats['total']}] {md_file.name} ({mem_type})")

        # Duplicate check
        if not dry_run:
            try:
                existing = migrator.search(name, limit=2)
                if existing and existing[0].get("score", 0) > 0.9:
                    logger.info(f"  SKIP: duplicate (score={existing[0].get('score', 0):.2f})")
                    stats["skipped"] += 1
                    stats["files"].append({"file": md_file.name, "status": "skipped"})
                    continue
            except Exception:
                pass

        result = migrator.add(memory_text, categories=categories, metadata=metadata, dry_run=dry_run)

        if result.get("status") in ("success", "dry_run"):
            stats["added"] += 1
            stats["files"].append({"file": md_file.name, "status": "added"})
            logger.info("  OK")
        else:
            stats["errors"] += 1
            stats["files"].append({"file": md_file.name, "status": "error", "error": result.get("error", "")})
            logger.warning(f"  FAIL: {result.get('error', 'unknown')}")

        if not dry_run:
            time.sleep(0.5)

    return stats


def migrate_plur_engrams(migrator: Mem0Migrator, dry_run=False) -> dict:
    import yaml

    stats = {"total": 0, "added": 0, "skipped": 0, "errors": 0, "duplicates": 0}

    if not PLUR_ENGRAMS_FILE.exists():
        logger.warning("WARNING: PLUR engrams file not found.")
        return stats

    with open(PLUR_ENGRAMS_FILE) as f:
        data = yaml.safe_load(f)

    engrams = data.get("engrams", [])
    stats["total"] = len(engrams)
    logger.info(f"\nMigrating {len(engrams)} PLUR engrams...")

    for i, eng in enumerate(engrams):
        eng_id = eng.get("id", f"unknown-{i}")
        statement = (eng.get("statement", "") or "").strip()
        abstract = (eng.get("abstract", "") or "").strip()
        summary = (eng.get("summary", "") or "").strip()
        tags_list = eng.get("tags", []) or []
        eng_type = eng.get("type", "")
        domain = eng.get("domain", "")

        memory_text = statement or abstract or summary
        if not memory_text or len(memory_text) < 10:
            stats["skipped"] += 1
            continue

        categories = ["plur"] + [str(t) for t in tags_list[:3]]
        if eng_type:
            categories.append(eng_type)

        metadata = {
            "source": "plur",
            "engram_id": eng_id,
            "type": eng_type,
            "domain": domain,
            "scope": eng.get("scope", ""),
            "migrated_at": datetime.now().isoformat()
        }

        # Duplicate check
        if not dry_run:
            try:
                if migrator.is_duplicate(memory_text, threshold=0.85):
                    stats["duplicates"] += 1
                    continue
            except Exception:
                pass

        result = migrator.add(memory_text, categories=categories, metadata=metadata, dry_run=dry_run)

        if result.get("status") in ("success", "dry_run"):
            stats["added"] += 1
            if i % 10 == 0 or dry_run:
                logger.info(f"  [{i+1}/{len(engrams)}] Added: {eng_id}")
        else:
            stats["errors"] += 1
            logger.warning(f"  [{i+1}/{len(engrams)}] ERROR: {eng_id}")

        if not dry_run:
            time.sleep(0.3)

    return stats


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Migrate memory systems to mem0")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source", choices=["claude", "plur", "all"], default="all")
    args = parser.parse_args()

    api_key = get_api_key()
    user_id = get_user_id()

    logger.info(f"Migration starting — user_id: {user_id}, dry_run: {args.dry_run}\n")

    migrator = Mem0Migrator(api_key, user_id)

    log_lines = ["# Migration Log — 2026-05-20\n"]
    start_count = migrator.count_memories()
    logger.info(f"Starting mem0 count: {start_count}\n")

    if args.source in ("claude", "all"):
        logger.info("=" * 60)
        logger.info("PHASE 1: Claude Code Memory → mem0")
        logger.info("=" * 60)
        claude_stats = migrate_claude_memory(migrator, args.dry_run)
        logger.info(f"\nClaude Code: {claude_stats['total']} files, {claude_stats['added']} added, "
              f"{claude_stats['skipped']} skipped, {claude_stats['errors']} errors")
        log_lines.append("\n## Claude Code Memory\n")
        log_lines.append(f"- Total files: {claude_stats['total']}")
        log_lines.append(f"- Added: {claude_stats['added']}")
        log_lines.append(f"- Skipped: {claude_stats['skipped']}")
        log_lines.append(f"- Errors: {claude_stats['errors']}")

    if args.source in ("plur", "all"):
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 2: PLUR Engrams → mem0")
        logger.info("=" * 60)
        plur_stats = migrate_plur_engrams(migrator, args.dry_run)
        logger.info(f"\nPLUR: {plur_stats['total']} engrams, {plur_stats['added']} added, "
              f"{plur_stats['duplicates']} duplicates, {plur_stats['skipped']} skipped, "
              f"{plur_stats['errors']} errors")
        log_lines.append("\n## PLUR Engrams\n")
        log_lines.append(f"- Total: {plur_stats['total']}")
        log_lines.append(f"- Added: {plur_stats['added']}")
        log_lines.append(f"- Duplicates: {plur_stats['duplicates']}")
        log_lines.append(f"- Skipped: {plur_stats['skipped']}")
        log_lines.append(f"- Errors: {plur_stats['errors']}")

    end_count = migrator.count_memories()
    logger.info(f"\nEnding mem0 count: {end_count}")
    log_lines.append("\n## Summary\n")
    log_lines.append(f"- Starting count: {start_count}")
    log_lines.append(f"- Ending count: {end_count}")

    if not args.dry_run:
        LOG_FILE.write_text("\n".join(log_lines))
        logger.info(f"Log: {LOG_FILE}")

    logger.info("\nDone.")


if __name__ == "__main__":
    main()
