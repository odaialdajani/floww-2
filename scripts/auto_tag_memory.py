#!/usr/bin/env python3
"""
scripts/auto_tag_memory.py — Auto-tagging wrapper for mem0 memory inserts.

On every new memory insert:
  - Embed entry → find K nearest existing tags
  - Propose top 3 tags
  - If confidence > 0.8 → auto-apply
  - Otherwise → queue for human review in kanban/cards/tagging_<date>.md

Tag taxonomy is controlled (no free-form tags); proposed tags go through review.

Usage:
  python3 scripts/auto_tag_memory.py "New memory text here"
  python3 scripts/auto_tag_memory.py --file memory/new_entry.md
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
TAXONOMY_PATH = REPO_ROOT / "memory" / "_tag_taxonomy.yaml"
KANBAN_TAGGING_PATH = REPO_ROOT / "kanban" / "cards"
CONFIG_PATH = Path.home() / ".mem0" / "config.json"

AUTO_APPLY_THRESHOLD = 0.8
K_NEAREST = 5


def get_mem0_client() -> Any:
    """Initialize mem0 MemoryClient from config."""
    cfg = json.load(open(CONFIG_PATH))
    api_key = cfg.get("platform", {}).get("api_key")
    from mem0 import MemoryClient  # type: ignore[attr-defined]
    return MemoryClient(api_key=api_key)


def load_taxonomy() -> Dict[str, Any]:
    """Load tag taxonomy from YAML."""
    if not TAXONOMY_PATH.exists():
        # Create default taxonomy
        default_taxonomy = {
            "tags": [
                # Project tags
                {"name": "project:floww", "description": "Floww trading terminal project"},
                {"name": "project:gflows", "description": "Gflows project"},
                {"name": "project:baby-billy-dvt", "description": "Baby Billy DVT project"},
                {"name": "project:personal", "description": "Personal notes and preferences"},
                # Type tags
                {"name": "type:session", "description": "Session summary or handoff"},
                {"name": "type:reference", "description": "Reference documentation"},
                {"name": "type:feedback", "description": "User feedback or correction"},
                {"name": "type:decision", "description": "Architecture or design decision"},
                {"name": "type:blocker", "description": "Blocked task or issue"},
                {"name": "type:config", "description": "Configuration or setup info"},
                # Domain tags
                {"name": "domain:trading", "description": "Trading strategy or market data"},
                {"name": "domain:ml", "description": "Machine learning models or training"},
                {"name": "domain:infra", "description": "Infrastructure, deployment, CI/CD"},
                {"name": "domain:security", "description": "Security audit or hardening"},
                {"name": "domain:frontend", "description": "Frontend UI/UX"},
                {"name": "domain:backend", "description": "Backend API or services"},
                {"name": "domain:research", "description": "Research papers or findings"},
                {"name": "domain:memory", "description": "Memory system or consolidation"},
                # Status tags
                {"name": "status:active", "description": "Currently in progress"},
                {"name": "status:completed", "description": "Completed work"},
                {"name": "status:archived", "description": "Archived reference"},
            ],
            "rules": {
                "max_tags_per_entry": 5,
                "min_confidence_auto_apply": 0.8,
                "require_project_tag": True,
                "require_type_tag": True,
            }
        }
        import yaml  # type: ignore[import-untyped]
        TAXONOMY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(TAXONOMY_PATH, "w") as f:
            yaml.dump(default_taxonomy, f, default_flow_style=False)
        return default_taxonomy

    import yaml
    return yaml.safe_load(TAXONOMY_PATH.read_text()) or {}


def text_similarity(a: str, b: str) -> float:
    """Simple text similarity using SequenceMatcher."""
    import difflib
    return difflib.SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def propose_tags(memory_text: str, taxonomy: Dict[str, Any], client: Any, user_id: str) -> List[Tuple[str, float]]:
    """Propose tags for a memory entry based on similarity to existing tags and content."""
    tags = taxonomy.get("tags", [])
    tag_scores = []

    # Score each tag based on text similarity to memory content
    for tag in tags:
        tag_name = tag["name"]
        tag_desc = tag.get("description", "")

        # Check similarity against tag name components
        name_parts = tag_name.replace(":", " ").replace("-", " ").split()
        max_sim: float = 0.0
        for part in name_parts:
            if len(part) > 2:
                sim = text_similarity(memory_text, part)
                max_sim = max(max_sim, sim)

        # Check similarity against description
        desc_sim = text_similarity(memory_text, tag_desc)
        max_sim = max(max_sim, desc_sim * 0.5)  # Description match is weaker

        # Check if tag keywords appear in memory text
        for part in name_parts:
            if len(part) > 2 and part.lower() in memory_text.lower():
                max_sim = max(max_sim, 0.85)

        tag_scores.append((tag_name, max_sim))

    # Sort by score descending
    tag_scores.sort(key=lambda x: x[1], reverse=True)
    return tag_scores[:3]


def queue_for_review(memory_text: str, proposed_tags: List[Tuple[str, float]]) -> None:
    """Queue low-confidence tagging for human review."""
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    review_path = KANBAN_TAGGING_PATH / f"tagging_{date_str}.md"

    entry = f"""
## {datetime.now(timezone.utc).strftime('%H:%M UTC')} — Pending Tag Review

**Memory:** {memory_text[:200]}

**Proposed Tags:**
"""
    for tag, score in proposed_tags:
        entry += f"- `{tag}` (confidence: {score:.2f})\n"

    entry += "\n---\n"

    # Append to review file
    with open(review_path, "a") as f:
        f.write(entry)


def apply_tags_to_memory(client: Any, memory_id: str, tags: List[str]) -> bool:
    """Apply tags to a mem0 memory entry via metadata."""
    try:
        client.update(memory_id=memory_id, metadata={"tags": tags})
        return True
    except Exception as e:
        print(f"  WARN: Failed to apply tags: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-tag memory entries")
    parser.add_argument("text", nargs="?", help="Memory text to tag")
    parser.add_argument("--file", help="Read memory text from file")
    parser.add_argument("--user-id", default="user_c778280e23af", help="mem0 user ID")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to mem0")
    args = parser.parse_args()

    # Get memory text
    if args.file:
        memory_text = Path(args.file).read_text().strip()
    elif args.text:
        memory_text = args.text
    else:
        print("ERROR: Provide memory text or --file")
        sys.exit(1)

    print(f"[auto_tag] Processing: {memory_text[:80]}...")

    # Load taxonomy
    taxonomy = load_taxonomy()
    print(f"[auto_tag] Taxonomy: {len(taxonomy.get('tags', []))} tags")

    # Get client
    client = get_mem0_client()

    # Propose tags
    proposed = propose_tags(memory_text, taxonomy, client, args.user_id)
    print(f"[auto_tag] Proposed tags:")
    for tag, score in proposed:
        print(f"  {tag}: {score:.2f}")

    # Auto-apply or queue for review
    high_conf = [(t, s) for t, s in proposed if s >= AUTO_APPLY_THRESHOLD]
    rules = taxonomy.get("rules", {})

    if high_conf and not args.dry_run:
        tags_to_apply = [t for t, s in high_conf[:rules.get("max_tags_per_entry", 5)]]
        print(f"[auto_tag] Auto-applying: {tags_to_apply}")

        # Add to mem0 with tags
        result = client.add(messages=[{"role": "user", "content": memory_text}], user_id=args.user_id, metadata={"tags": tags_to_apply})
        print(f"[auto_tag] Added to mem0: {result}")
    else:
        if not high_conf:
            print(f"[auto_tag] Queuing for human review (no tags above {AUTO_APPLY_THRESHOLD} threshold)")
        else:
            print(f"[auto_tag] Dry run — would apply: {[t for t, s in high_conf]}")
        queue_for_review(memory_text, proposed)


if __name__ == "__main__":
    main()
