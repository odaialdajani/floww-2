#!/usr/bin/env python3
"""
scripts/generate_capacity_report.py — Weekly capacity report generator.

Summarizes predicted vs actual throughput.
Recommends adjustments for next week.
Writes to kanban/CAPACITY_REPORT.md.

Usage:
  python3 scripts/generate_capacity_report.py
  python3 scripts/generate_capacity_report.py --week 2026-W21
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parent.parent
KANBAN_DIR = REPO_ROOT / "kanban"
CARDS_DIR = KANBAN_DIR / "cards"
CLOSED_DIR = KANBAN_DIR / "closed"
REPORT_FILE = KANBAN_DIR / "CAPACITY_REPORT.md"
HISTORY_FILE = KANBAN_DIR / "throughput_history.json"


def load_all_cards() -> List[Dict[str, Any]]:
    cards = []
    for f in sorted(CARDS_DIR.glob("*.md")):
        if f.name.startswith("tagging_") or f.name.startswith("folder_") or f.name.startswith("agent9_"):
            continue
        try:
            content = f.read_text(encoding="utf-8")
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

    if CLOSED_DIR.exists():
        for date_dir in CLOSED_DIR.iterdir():
            if date_dir.is_dir():
                for f in date_dir.glob("*.md"):
                    try:
                        content = f.read_text(encoding="utf-8")
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


def get_week_bounds(week_str: Optional[str] = None) -> Tuple[datetime, datetime]:
    """Return (start, end) for the given ISO week or current week."""
    if week_str:
        # Parse YYYY-WNN
        parts = week_str.split("-W")
        year = int(parts[0])
        week = int(parts[1])
        start = datetime.strptime(f"{year}-W{week:02d}-1", "%Y-W%W-%w").replace(tzinfo=timezone.utc)
    else:
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)

    end = start + timedelta(days=7)
    return start, end


def filter_cards_by_week(cards: List[Dict[str, Any]], start: datetime, end: datetime) -> List[Dict[str, Any]]:
    """Filter cards updated within the week window."""
    result = []
    for card in cards:
        updated = card.get("last_update", "")
        if updated:
            try:
                dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                if start <= dt < end:
                    result.append(card)
            except (ValueError, TypeError):
                continue
    return result


def compute_weekly_stats(cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    stats = {
        "total_cards": len(cards),
        "done": 0,
        "in_progress": 0,
        "ready": 0,
        "blocked": 0,
        "by_agent": defaultdict(lambda: {"done": 0, "in_progress": 0, "total": 0}),
        "completion_times": [],
    }

    for card in cards:
        status = card.get("status", "unknown")
        agent = card.get("assignee", "unknown")

        stats["by_agent"][agent]["total"] += 1  # type: ignore[index]

        if status == "done":
            stats["done"] += 1  # type: ignore[operator]
            stats["by_agent"][agent]["done"] += 1  # type: ignore[index]
            # Compute completion time
            created = card.get("created_at", "")
            updated = card.get("last_update", "")
            if created and updated:
                try:
                    t0 = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    t1 = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    hours = (t1 - t0).total_seconds() / 3600
                    stats["completion_times"].append(hours)  # type: ignore[attr-defined]
                except (ValueError, TypeError):
                    pass
        elif status == "in_progress":
            stats["in_progress"] += 1  # type: ignore[operator]
            stats["by_agent"][agent]["in_progress"] += 1  # type: ignore[index]
        elif status == "ready":
            stats["ready"] += 1  # type: ignore[operator]
        elif status == "blocked":
            stats["blocked"] += 1  # type: ignore[operator]

    return stats


def generate_report(week_str: Optional[str] = None) -> str:
    start, end = get_week_bounds(week_str)
    week_label = start.strftime("%Y-W%W")

    all_cards = load_all_cards()
    week_cards = filter_cards_by_week(all_cards, start, end)
    stats = compute_weekly_stats(week_cards)

    # Load history for comparison
    prev_comparison = ""
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text())
            prev_done = sum(1 for h in history if h.get("status") == "done")
            if prev_done > 0:
                delta = stats["done"] - prev_done
                sign = "+" if delta >= 0 else ""
                prev_comparison = f" ({sign}{delta} vs last week)"
        except (json.JSONDecodeError, IOError):
            pass

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Weekly Capacity Report — {week_label}",
        f"Generated: {now}",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total cards touched | {stats['total_cards']} |",
        f"| Completed | {stats['done']}{prev_comparison} |",
        f"| In progress | {stats['in_progress']} |",
        f"| Ready (awaiting) | {stats['ready']} |",
        f"| Blocked | {stats['blocked']} |",
        f"| Completion rate | {stats['done'] / max(stats['total_cards'], 1) * 100:.0f}% |",
        "",
    ]

    # Completion time stats
    if stats["completion_times"]:
        times = sorted(stats["completion_times"])
        n = len(times)
        avg = sum(times) / n
        median = times[n // 2]
        p90 = times[int(n * 0.9)] if n > 1 else times[0]
        lines.extend([
            "## Completion Times",
            "",
            f"| Stat | Hours |",
            f"|------|-------|",
            f"| Average | {avg:.1f} |",
            f"| Median | {median:.1f} |",
            f"| P90 | {p90:.1f} |",
            f"| Min | {times[0]:.1f} |",
            f"| Max | {times[-1]:.1f} |",
            "",
        ])

    # Per-agent breakdown
    lines.extend([
        "## Per-Agent Throughput",
        "",
        f"| Agent | Done | In Progress | Total | Completion Rate |",
        f"|-------|------|-------------|-------|-----------------|",
    ])
    for agent in sorted(stats["by_agent"].keys()):
        s = stats["by_agent"][agent]
        rate = s["done"] / max(s["total"], 1) * 100
        lines.append(f"| {agent} | {s['done']} | {s['in_progress']} | {s['total']} | {rate:.0f}% |")
    lines.append("")

    # Recommendations
    lines.extend([
        "## Recommendations",
        "",
    ])

    recommendations = []

    # Check for low completion rate
    if stats["total_cards"] > 0 and stats["done"] / stats["total_cards"] < 0.5:
        recommendations.append(
            "- **Low completion rate** — consider reducing WIP limit or adding capacity"
        )

    # Check for blocked cards
    if stats["blocked"] > 0:
        recommendations.append(
            f"- **{stats['blocked']} blocked card(s)** — run `python3 kanban/bottleneck_detector.py` to identify root causes"
        )

    # Check for overloaded agents
    for agent, s in stats["by_agent"].items():
        if s["in_progress"] > 3:
            recommendations.append(
                f"- **{agent} has {s['in_progress']} in-progress cards** — consider reassigning low-priority tasks"
            )

    # Check for stale ready cards
    if stats["ready"] > 5:
        recommendations.append(
            f"- **{stats['ready']} cards awaiting dispatch** — increase swarm capacity or prioritize"
        )

    if not recommendations:
        recommendations.append("- All metrics within normal parameters. No action needed.")

    lines.extend(recommendations)
    lines.append("")

    # Model health
    model_file = KANBAN_DIR / "ml_models" / "throughput_v1.pkl"
    drift_log = KANBAN_DIR / "drift_log.json"
    lines.extend([
        "## Model Health",
        "",
    ])
    if model_file.exists():
        lines.append(f"- Throughput model: trained ({model_file.stat().st_size // 1024}KB)")
    else:
        lines.append("- Throughput model: **not trained** — run `python3 scripts/predict_throughput.py --train`")

    if drift_log.exists():
        try:
            drift = json.loads(drift_log.read_text())
            if drift:
                latest = drift[-1]
                status = "⚠ DRIFTED" if latest.get("drift_detected") else "✓ OK"
                lines.append(f"- Drift check: {status} (MAPE: {latest.get('current_mape', 'N/A')})")
        except json.JSONDecodeError:
            lines.append("- Drift check: log corrupted")

    lines.extend([
        "",
        "---",
        f"*Next report: {end.strftime('%Y-%m-%d')} (Monday)*",
    ])

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Weekly capacity report")
    parser.add_argument("--week", type=str, default=None, help="ISO week (e.g. 2026-W21)")
    args = parser.parse_args()

    report = generate_report(args.week)
    REPORT_FILE.write_text(report + "\n", encoding="utf-8")
    print(f"Report written to {REPORT_FILE}")
    print(report)


if __name__ == "__main__":
    main()
