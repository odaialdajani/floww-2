"""Lodestar agentic layer — package root.

W1+W2 (plan v3): tool registry + evidence ledger + dual-tier LLM client +
reasoning loop + confluence scorer + claims + transport + UI.

Read-only by construction for research tools (see tools/ + tests).
Live execution lives only in actions/ behind W6 gates — never imported
by research tools.
"""

from services.agent.registry import get_tool, list_tools

__all__ = ["get_tool", "list_tools"]
