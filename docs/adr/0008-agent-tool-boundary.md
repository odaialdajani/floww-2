# ADR-0008 — Lodestar agent tool boundary (read-only research)

Status: Accepted
Date: 2026-09-07

## Context

Plan v3 (Lodestar, `i-would-like-to-replicated-stardust.md`) adds an
agentic layer over Solstice + Tidehunter Pro. Three order paths exist
(`CLAUDE.md` money path) plus a fourth order-adjacent module
(`backend/paper_trading.py` `LIVE_TRADING_ENABLED`). One path
(`PublicBroker.place_order`) is ungated and points at the live
`https://api.public.com` gateway. The agent must be useful on day one
without any path to live execution.

## Decision

1. Research tools (`services/agent/tools/**`) are read-only by
   construction: registration refuses `mutating=True`; the catalog has
   no order/liquidation call; proven at the call boundary (patched
   order methods never fire during the golden set), by AST import-walk,
   by lint rule, and by token scan.
2. Live execution lives only in `services/agent/actions/` behind the W6
   seven-gate wall, mounted at `/api/agent-actions/` with
   `Depends(require_api_key)` on every route. Research tools must never
   import the actions package (import-walk test).
3. Asking is key-free on the local app; staging any trade (paper or
   live) requires the server key — same as today's paper auto-trade
   route. `PUBLIC_PATHS` names only explicit agent read subpaths, never
   a bare `/api/agent/` prefix.
4. `agent_weights_*.json` is not a model artifact under ADR-0001 and is
   never read by `services/ml/**` (tested by import-walk).

## Consequences

- A new order path cannot be reached by adding a tool; it requires
  touching `actions/` + router + auth, all gated and reviewed.
- The `sys.modules` import proof is dropped (server imports broker
  modules at startup); the call-boundary + AST proofs replace it.
- W6 additionally records ADR-0009 (live-execution boundary) before
  `FLOWW_ENABLE_LIVE_PUBLIC` is ever set.
