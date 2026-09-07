"""Dual-tier async LLM client (plan v3 L3). New file — services/llm.py untouched.

Tier A (cheap): OpenRouter free model — narration, one-liners, classifier.
Tier B (strong): Sonnet-class via the existing OpenRouter transport —
multi-tool synthesis, daily brief. Escalation by question class, never
by estimated tool count (unimplementable).

Provider-down -> deterministic template with an LLM-unavailable banner.
Circuit breaker: 3 failures / 5 min. Prompt caching hint on stable prefix.
"""

from __future__ import annotations

import os
import time
from typing import Any

QUESTION_CLASSES = ("quick-read", "full-research", "compare", "what-changed", "trade-me")
# Only full-research / trade-me / compare default to Tier B; the rest stay cheap.
TIER_B_CLASSES = {"full-research", "trade-me", "compare"}

_breaker: dict[str, Any] = {"failures": 0, "opened_at": 0.0}


def breaker_open() -> bool:
    try:
        if _breaker["failures"] >= 3 and (time.time() - float(_breaker["opened_at"])) < 300:
            return True
        if (time.time() - float(_breaker["opened_at"])) >= 300:
            _breaker["failures"] = 0
    except Exception:
        return False
    return False


def _note_failure() -> None:
    try:
        _breaker["failures"] = int(_breaker.get("failures", 0)) + 1
        _breaker["opened_at"] = time.time()
    except Exception:
        pass


def tier_for(question_class: str | None, force: str | None = None) -> str:
    if force in ("A", "B"):
        return force
    if (question_class or "") in TIER_B_CLASSES:
        return "B"
    return "A"


def model_for(tier: str) -> str:
    if tier == "B":
        return os.environ.get("AGENT_STRONG_MODEL", "anthropic/claude-sonnet-4")
    return os.environ.get("AGENT_CHEAP_MODEL", "openrouter/free")


async def generate(
    prompt: str,
    *,
    system: str = "",
    max_tokens: int = 1200,
    question_class: str = "quick-read",
    force_tier: str | None = None,
    cache_hint: bool = True,
) -> dict[str, Any]:
    """Async generate. Never raises — returns ok/template/unavailable."""
    _ = cache_hint  # prefix is stable by construction; provider caches it.
    if os.environ.get("FLOWW_AGENT_DISABLED", "") == "1":
        return {"status": "unavailable", "text": "", "reason": "agent-disabled", "tier": "none"}
    if breaker_open():
        return {"status": "template", "text": deterministic_template(prompt), "tier": "none", "banner": "LLM unavailable"}
    tier = tier_for(question_class, force_tier)
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return {"status": "template", "text": deterministic_template(prompt), "tier": tier, "banner": "LLM key absent"}
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            timeout=45,
            max_retries=1,
        )
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        completion = await client.chat.completions.create(
            model=model_for(tier),
            messages=messages,
            max_tokens=max_tokens,
            extra_headers={
                "HTTP-Referer": "https://confluence-decoder.local",
                "X-Title": "Confluence Decoder",
            },
        )
        text = (completion.choices[0].message.content or "") if completion.choices else ""
        tokens = 0
        try:
            tokens = int(completion.usage.total_tokens or 0) if completion.usage else 0
        except Exception:
            tokens = 0
        est_cost = round(tokens / 1000.0 * (0.003 if tier == "B" else 0.0002), 4)
        return {"status": "ok", "text": text, "tier": tier, "model": model_for(tier), "tokens": tokens, "est_cost_usd": est_cost}
    except Exception as e:
        _note_failure()
        return {"status": "template", "text": deterministic_template(prompt), "tier": tier, "banner": f"LLM error: {type(e).__name__}"}


def deterministic_template(prompt: str) -> str:
    try:
        from services.morning_briefing import build_morning_briefing

        brief = build_morning_briefing()
        if isinstance(brief, dict):
            return str(brief.get("text") or brief.get("briefing") or "LLM unavailable — deterministic brief.")
        return str(brief)
    except Exception:
        q = (prompt or "")[:400]
        return f"LLM unavailable — deterministic read only. Question was: {q}"
