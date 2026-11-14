# Phase 3 — Public API Data Layer

## Phase Overview

**Goal:** Wire PublicBroker (from `/Users/nav/backend/`) into floww as the PRIMARY data source for options chains + spot prices. Replace cvserver as primary chain source. Fallback chain: Public API → cvserver → yfinance + Databento. Tidehunter Pro is Phase 4 only.

**Status:** COMPLETE — delivered 2026-08-31. This checklist's TODO labels below are retained
as the original plan and are not current execution status; see `.planning/CURRENT.md` and
`.planning/ROADMAP.md` for the current product and runtime state.

**Source of truth:** `.planning/PHASE3_PUBLIC_API_PLAN.md`, `.planning/DATA_SOURCES.md`, `.planning/AGENT_CONTRACT.md`

## Requirements (traced from ROADMAP.md §3)

| Ticket | Requirement | Owner | Status |
|---|---|---|---|
| 3.1 | Public API key confirmed | — | DONE |
| 3.2 | Copy PublicBroker → floww backend | Historical | DONE |
| 3.3 | Add PUBLIC_API_KEY to .env + .env.example | Historical | DONE |
| 3.4 | Modify fetch_spot_and_chains_merged() priority | Historical | DONE |
| 3.5 | Create /api/public/chain/{ticker} + /api/public/quotes/{ticker} | Historical | DONE |
| 3.6 | Tests: chain + fallback routing | Historical | DONE |
| 3.7 | Update INTEGRATIONS.md docs | Historical | DONE |
| 3.8 | Frontend wiring (Solstice/Triad) | Historical | DONE |
| 3.9 | Phase tracking | Historical | DONE |

## Verification Loop

1. Unit tests: `python3 -m pytest tests/services/test_public_api_integration.py -v` (≥5 tests, must fail before fix, pass after)
2. Integration test: curl `/api/public/chain/SPY` returns structured chain data
3. ruff: `ruff check backend/services/public_api.py backend/routes/public_api.py`
4. No existing tests broken: `pytest -q` ≥ 4546 passed

## Key Decisions

- Connection model: COPY (not import) — two separate repos
- PublicBroker data shape must be adapted to match cvserver_client.py output format for backward compatibility with existing consuming code
- New routes under /api/public/ namespace — does NOT change existing /api/chain route
