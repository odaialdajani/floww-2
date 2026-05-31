#!/usr/bin/env python3
import logging

logger = logging.getLogger(__name__)

"""
backend/services/kanban/rebalancer.py — Capacity rebalancing recommender.

When bottleneck detected: recommend which cards to reassign + to which agent.
Reassignment scoring: match card.required_skills to agent.skills (TF-IDF over
historical commit messages); prefer agents with cards_in_flight < median.
Output: kanban/REBALANCE_PROPOSAL.md for Nav to chop.

Reference: Brooks (1975) The Mythical Man-Month — Brooks's Law
"""

import math
from collections import Counter
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
KANBAN_DIR = REPO_ROOT / "kanban"
CARDS_DIR = KANBAN_DIR / "cards"
REBALANCE_FILE = KANBAN_DIR / "REBALANCE_PROPOSAL.md"


def extract_skills_from_text(text: str) -> list[str]:
    """Extract skill keywords from text."""
    skill_keywords = [
        "coding-agent", "api-builder", "architecture-diagram", "dspy",
        "evaluating-llms", "academic-verify", "jupyter", "arxiv",
        "duckduckgo", "arxiv-watcher", "godmode", "agent-hardening",
        "obsidian", "mem0", "honcho-memory", "kanban-orchestrator",
        "kanban-codex", "confluence-decoder", "debugging", "test-runner",
        "spike", "writing-plans", "requesting-code-review",
    ]
    text_lower = text.lower()
    return [s for s in skill_keywords if s in text_lower]


def compute_tfidf_similarity(text_a: str, text_b: str) -> float:
    """Compute TF-IDF cosine similarity between two texts."""
    words_a = text_a.lower().split()
    words_b = text_b.lower().split()

    if not words_a or not words_b:
        return 0.0

    # Term frequencies
    tf_a = Counter(words_a)
    tf_b = Counter(words_b)

    # Vocabulary
    vocab = set(words_a) | set(words_b)

    # TF-IDF vectors (simplified: no IDF since we only have 2 docs)
    vec_a = [tf_a.get(w, 0) / len(words_a) for w in vocab]
    vec_b = [tf_b.get(w, 0) / len(words_b) for w in vocab]

    # Cosine similarity
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a * a for a in vec_a))
    mag_b = math.sqrt(sum(b * b for b in vec_b))

    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def recommend_reassignment(bottleneck_agent: str, cards: list[dict],
                           agent_metrics: dict) -> list[dict]:
    """Recommend card reassignments for a bottleneck agent."""
    recommendations = []

    # Find cards assigned to bottleneck agent that are in_progress or ready
    bottleneck_cards = [
        c for c in cards
        if c.get("assignee") == bottleneck_agent and c.get("status") in ("in_progress", "ready")
    ]

    if not bottleneck_cards:
        return recommendations

    # Find candidate agents (not bottleneck, below median load)
    median_load = 1
    if agent_metrics:
        loads = [m.get("cards_in_progress", 0) for m in agent_metrics.values()]
        if loads:
            median_load = sorted(loads)[len(loads) // 2]

    candidate_agents = [
        agent for agent, metrics in agent_metrics.items()
        if agent != bottleneck_agent
        and metrics.get("cards_in_progress", 0) <= median_load
    ]

    if not candidate_agents:
        candidate_agents = [a for a in agent_metrics if a != bottleneck_agent]

    # For each card, find best candidate
    for card in bottleneck_cards:
        card_text = f"{card.get('title', '')} {card.get('skill', '')} {card.get('_body', '')}"
        card_skills = extract_skills_from_text(card_text)

        best_agent = None
        best_score = -1

        for agent in candidate_agents:
            # Get agent's historical cards for skill matching
            agent_cards = [c for c in cards if c.get("assignee") == agent]
            agent_text = " ".join(
                f"{c.get('title', '')} {c.get('skill', '')}" for c in agent_cards
            )
            agent_skills = extract_skills_from_text(agent_text)

            # Skill overlap score
            if card_skills and agent_skills:
                overlap = len(set(card_skills) & set(agent_skills))
                skill_score = overlap / max(len(card_skills), 1)
            else:
                skill_score = 0

            # Text similarity
            text_score = compute_tfidf_similarity(card_text, agent_text)

            # Prefer less loaded agents
            load = agent_metrics.get(agent, {}).get("cards_in_progress", 0)
            load_score = 1.0 / (1 + load)

            # Combined score
            score = skill_score * 0.5 + text_score * 0.3 + load_score * 0.2

            if score > best_score:
                best_score = score
                best_agent = agent

        if best_agent and best_score > 0.1:
            recommendations.append({
                "card_id": card.get("id", "unknown"),
                "card_title": card.get("title", ""),
                "from_agent": bottleneck_agent,
                "to_agent": best_agent,
                "confidence": round(best_score, 2),
                "reasoning": f"Skill overlap + low load ({agent_metrics.get(best_agent, {}).get('cards_in_progress', 0)} cards)",
            })

    return recommendations


def run_rebalancer(bottleneck_data: dict) -> dict:
    """Run rebalancer for detected bottlenecks."""
    cards = load_cards()
    recommendations = []

    for bottleneck in bottleneck_data.get("bottlenecks", []):
        recs = recommend_reassignment(
            bottleneck["agent"], cards, bottleneck_data.get("agent_metrics", {})
        )
        recommendations.extend(recs)

    if recommendations:
        # Group by bottleneck
        proposal_parts = []
        for bottleneck in bottleneck_data.get("bottlenecks", []):
            bottleneck_recs = [r for r in recommendations if r["from_agent"] == bottleneck["agent"]]
            if bottleneck_recs:
                proposal_parts.append(format_rebalance_proposal(bottleneck_recs, bottleneck))

        proposal = "\n\n".join(proposal_parts)
        REBALANCE_FILE.write_text(proposal + "\n")
    else:
        proposal = ""
        if REBALANCE_FILE.exists():
            REBALANCE_FILE.unlink()

    return {
        "recommendations": recommendations,
        "proposal": proposal,
        "proposal_file": str(REBALANCE_FILE) if recommendations else None,
    }


if __name__ == "__main__":
    # Test with current state
    from services.kanban.bottleneck import run_bottleneck_check

    bottleneck_data = run_bottleneck_check()
    result = run_rebalancer(bottleneck_data)

    logger.info(f"Recommendations: {len(result['recommendations'])}")
    for rec in result["recommendations"]:
        logger.info(f"  {rec['card_id']}: {rec['from_agent']} → {rec['to_agent']} "
              f"(conf: {rec['confidence']})")

def format_rebalance_proposal(recommendations: list[dict], bottleneck: dict) -> str:
    """Format rebalance proposal for Nav."""
    _lines = [
        f"# Rebalance Proposal — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        f"**Bottleneck:** {bottleneck['agent']}",
        f"**Reasons:** {', '.join(bottleneck['reasons'])}",
        "",
        f"**Recommendations:** {len(recommendations)}",
        "",
    ]
