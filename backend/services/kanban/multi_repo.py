#!/usr/bin/env python3
"""
backend/services/kanban/multi_repo.py — Multi-repo coordination.

Nav has multiple projects (floww, gflows, baby-billy-dvt).
Some kanban cards span repos. Schema extension: cards can declare
`affects_repos: [floww, gflows]`; watcher monitors all listed repos.
Cross-repo SWARM_STATUS.md aggregates state from all.
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
KANBAN_DIR = REPO_ROOT / "kanban"
CARDS_DIR = KANBAN_DIR / "cards"

def load_cards() -> list[dict]:
    """Load all card files."""
    import yaml

    cards = []
    for f in sorted(CARDS_DIR.glob("*.md")):
        if f.name.startswith("tagging_"):
            continue
        try:
            content = f.read_text()
            if not content.startswith("---"):
                continue
            parts = content.split("---", 2)
            if len(parts) < 3:
                continue
            fm = yaml.safe_load(parts[1]) or {}
            fm["_file"] = str(f)
            cards.append(fm)
        except Exception:
            continue
    return cards



REPO_ROOT = Path(__file__).resolve().parent.parent.parent

logger = logging.getLogger(__name__)

# Known project repos
PROJECT_REPOS = {
    "floww": REPO_ROOT,
    "gflows": Path.home() / "Documents" / "GitHub" / "gflows",
    "baby-billy-dvt": Path.home() / "Documents" / "GitHub" / "baby-billy-dvt",
}


def generate_multi_repo_status() -> str:
    """Generate multi-repo status markdown."""
    cards = load_cards()
    status = get_cross_repo_status(cards)

    lines = [
        "# Multi-Repo Status",
        f"Generated: {status['timestamp']}",
        "",
        "## Repos",
        "",
    ]

    for name, info in status["repos"].items():
        exists = "✓" if info["exists"] else "✗"
        lines.append(f"- {exists} **{name}**: {info['path']}")

    lines.extend(["", "## Cross-Repo Cards", ""])

    if status["cross_repo_cards"]:
        for card in status["cross_repo_cards"]:
            lines.append(f"### {card['title']} (`{card['id']}`)")
            lines.append(f"- **Status:** {card['status']}")
            lines.append(f"- **Repos:** {', '.join(card['affects_repos'])}")
            for repo, commits in card["commits_by_repo"].items():
                lines.append(f"  - {repo}: {len(commits)} commits")
            lines.append("")
    else:
        lines.append("No cross-repo cards detected.")

    lines.extend(["", "## All Cards by Repo", ""])

    # Group cards by repo
    repo_cards = defaultdict(list)
    for card in cards:
        affects = card.get("affects_repos", ["floww"])
        for repo in affects:
            repo_cards[repo].append(card)

    for repo_name in sorted(repo_cards.keys()):
        lines.append(f"### {repo_name}")
        for card in repo_cards[repo_name]:
            cid = card.get("id", "?")
            title = card.get("title", "?")
            cstatus = card.get("status", "?")
            lines.append(f"- `{cid}` {title} ({cstatus})")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    logger.info(generate_multi_repo_status())


def get_cross_repo_status(cards: list[dict]) -> dict:
    """Get cross-repo status for all cards."""
    _status = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repos": {},
        "cross_repo_cards": [],
    }
