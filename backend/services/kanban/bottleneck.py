#!/usr/bin/env python3
import logging

logger = logging.getLogger(__name__)

"""
backend/services/kanban/bottleneck.py — Bottleneck detector for agent swarm.

Every 30 min: compute per-agent metrics (cards-in-flight, avg-time-per-card,
blocker-rate, push-failure-rate).
Identify bottlenecks: any agent with cards_in_flight > 3× median OR blocker_rate > 2× median.
Surface to ARCHITECT_BRIEF.md.
"""

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
KANBAN_DIR = REPO_ROOT / "kanban"
CARDS_DIR = KANBAN_DIR / "cards"
INCIDENTS_FILE = KANBAN_DIR / "INCIDENTS.md"


def compute_agent_metrics(cards: list[dict]) -> dict:
    """Compute per-agent metrics."""
    agents = defaultdict(lambda: {
        "cards_in_progress": 0,
        "cards_done": 0,
        "cards_blocked": 0,
        "total_cards": 0,
        "avg_completion_hours": 0,
        "blocker_count": 0,
        "last_update_hours_ago": 0,
    })

    now = datetime.now(timezone.utc)

    for card in cards:
        assignee = card.get("assignee", "unknown")
        status = card.get("status", "unknown")
        blockers = card.get("blockers", [])

        agents[assignee]["total_cards"] += 1

        if status == "in_progress":
            agents[assignee]["cards_in_progress"] += 1
        elif status == "done":
            agents[assignee]["cards_done"] += 1
        elif status == "blocked":
            agents[assignee]["cards_blocked"] += 1

        if blockers:
            agents[assignee]["blocker_count"] += len(blockers)

        # Time since last update
        last_update = card.get("last_update", "")
        if last_update:
            try:
                dt = datetime.fromisoformat(last_update.replace("Z", "+00:00"))
                hours_ago = (now - dt).total_seconds() / 3600
                agents[assignee]["last_update_hours_ago"] = max(
                    agents[assignee]["last_update_hours_ago"], hours_ago
                )
            except (ValueError, TypeError):
                pass

    # Compute derived metrics
    for agent, metrics in agents.items():
        total = metrics["total_cards"]
        if total > 0:
            metrics["blocker_rate"] = metrics["blocker_count"] / total
        else:
            metrics["blocker_rate"] = 0

    return dict(agents)


def detect_bottlenecks(agent_metrics: dict) -> list[dict]:
    """Detect bottleneck agents."""
    if not agent_metrics:
        return []

    # Compute medians
    in_progress_values = [m["cards_in_progress"] for m in agent_metrics.values()]
    blocker_rates = [m["blocker_rate"] for m in agent_metrics.values()]

    if not in_progress_values:
        return []

    median_in_progress = sorted(in_progress_values)[len(in_progress_values) // 2]
    median_blocker_rate = sorted(blocker_rates)[len(blocker_rates) // 2]

    bottlenecks = []
    for agent, metrics in agent_metrics.items():
        reasons = []

        if metrics["cards_in_progress"] > 3 * max(median_in_progress, 1):
            reasons.append(
                f"cards_in_flight={metrics['cards_in_progress']} > 3× median={median_in_progress}"
            )

        if metrics["blocker_rate"] > 2 * max(median_blocker_rate, 0.01):
            reasons.append(
                f"blocker_rate={metrics['blocker_rate']:.2f} > 2× median={median_blocker_rate:.2f}"
            )

        if metrics["last_update_hours_ago"] > 24:
            reasons.append(
                f"stale: last update {metrics['last_update_hours_ago']:.0f}h ago"
            )

        if reasons:
            bottlenecks.append({
                "agent": agent,
                "reasons": reasons,
                "metrics": metrics,
            })

    return bottlenecks


def run_bottleneck_check() -> dict:
    """Run full bottleneck check. Returns report data."""
    cards = load_cards()
    agent_metrics = compute_agent_metrics(cards)
    bottlenecks = detect_bottlenecks(agent_metrics)
    report = format_bottleneck_report(bottlenecks, agent_metrics)

    return {
        "bottlenecks": bottlenecks,
        "agent_metrics": agent_metrics,
        "report": report,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


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


def format_bottleneck_report(bottlenecks: list[dict], agent_metrics: dict) -> str:
    """Format bottleneck report for ARCHITECT_BRIEF.md."""
    lines = [
        f"## Bottleneck Report — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]

    if not bottlenecks:
        lines.append("No bottlenecks detected. All agents within normal parameters.")
    else:
        lines.append(f"**{len(bottlenecks)} bottleneck(s) detected:**")
        lines.append("")
        for b in bottlenecks:
            lines.append(f"### {b['agent']}")
            for reason in b["reasons"]:
                lines.append(f"- ⚠ {reason}")
            lines.append("")

    # Summary table
    lines.append("### Agent Metrics Summary")
    lines.append("")
    lines.append("| Agent | In Progress | Done | Blocked | Blocker Rate | Last Update |")
    lines.append("|-------|-------------|------|---------|--------------|-------------|")
    for agent, m in sorted(agent_metrics.items()):
        last = f"{m['last_update_hours_ago']:.0f}h ago" if m['last_update_hours_ago'] else "N/A"
        lines.append(
            f"| {agent} | {m['cards_in_progress']} | {m['cards_done']} | "
            f"{m['cards_blocked']} | {m['blocker_rate']:.2f} | {last} |"
        )
    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    result = run_bottleneck_check()
    logger.info(result["report"])
    logger.info(f"\nBottlenecks: {len(result['bottlenecks'])}")
    for b in result["bottlenecks"]:
        logger.info(f"  {b['agent']}: {', '.join(b['reasons'])}")
