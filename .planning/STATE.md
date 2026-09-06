# STATE.md — Confluence Decoder

**Last updated:** 2026-09-06
**Branch:** `phase9/g1-reads-witness` @ 9d3057d (C4 doc-hygiene: corrected from stale main@e94e841)
**Tests:** backend 3 passed, 20 warnings · frontend 56 suites / 409 tests · lane trio 4 suites / 178 tests · craco build clean
**Lint:** ruff (E, E722, F, W, I; ignore E501)

## Project position

Deploy package hardened and ready: Oracle Always Free runbook
(`deploy/free/README.md`), `oracle-setup.sh` + read-only deploy key
`oracle-vm-deploy`, docker-compose stack behind Caddy. **Awaiting Nav's VM
provisioning** — Phase 1 of ROADMAP.md starts the moment the VM exists.

## Current phase

Phase 6 — Backlog Promotion [ACTIVE]. Phase 4 (Tidehunter Pro) is gating-only scaffolding. Phase 3 [CLOSED 2026-08-31]. Phase 5 [COMPLETE 2026-08-31]. Phase 6.2/6.4/6.6 done; 6.1/6.3/6.5 remaining.

## Key context

- Round 9 closed at `4e1c1b8`; Round 10 plan at `docs/ROUND10_PLAN.md`
  (P0.1 conftest waiver applied; P0.2 fetch_spot_and_chains restore and P0.3
  STALE_IMPORT cleanup tracked in Phase 2).
- Forbidden files per CLAUDE.md: `ml/inference.py`, `dash_ui.py`,
  `backend/tests/conftest.py` (R10 waiver), model artifacts under `backend/models/`,
  `frontend/.env`, `package.json`, `craco.config.js`, `frontend/src/App.js`.
- pytest.ini uses `[pytest]` header with asyncio_mode=auto; flaky_env marker
  registered (see `.planning/LEARNINGS.md` for why).
- Codebase intel: `.planning/codebase/` (7 GSD map docs).

## Log

- 2026-08-24 — Ingest-docs bootstrap: PROJECT.md / REQUIREMENTS.md / ROADMAP.md /
  STATE.md / config.json created from curated manifest (8 docs); round transcripts
  excluded as historical noise.
- 2026-09-04 — Phase 9 lane advancing: SHIP polish (COST caption, poll-chain
  integration, costLabel honesty contract, live modal-hook fixtures, HOOKS
  contract), apply-blind backend packets (public-path-budget + B1/B2/B3),
  RFC-3 overview-bar consolidation, phantom-import fix (React.lazy guard),
  CR-002 + CI frontier gate, full stale-number documentation sweep, and CI
  gate hardening (unmask git failures in frontend-fs-integrity). Lane trio
  4 suites / 178 tests green; full frontend 56 suites / 409 tests green;
  backend 3/3 green. Origin/main at e94e841.
- 2026-09-03 — Phase 7 complete (public-api-only + trade-direct): Schwab/Alpha
  Vantage retired (410s, disabled stubs, fail-closed client); new
  /api/public/{bars,history,technical,expirations}; Triad row-click enriched
  with Public OSI+prices → real order path; fallback public→cvserver→yfinance
  reaffirmed. 7.5 (Heatseeker submit in frozen App.js) flagged for Nav.
- 2026-09-03 — Phase 8 complete (open universe + Meridian fixes): PAID gate
  removed, greeks/flow opened, ticker-bar free-text search; Dual-GEX numba
  gamma, IV-Mid reason codes + T floor, Wheel 30s cache + 429 exemption;
  Solstice band behind Signals toggle, grid expand overlay, toolbar buttons
  live. 8.6 (App.js-owned leftovers) flagged for Nav.
- 2026-09-04 — Phase 8 closed out: grid density modes (21-row window /
  full-density overlay, zoom removed), Drilldown purge + info popover,
  Profile volume + node strip, parallel-session reconcile. All suites
  green, origin/main verified, :8000 + :3000 live-verified.
