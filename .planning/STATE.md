# STATE.md — Confluence Decoder

**Last updated:** 2026-09-04
**Branch:** `main` @ 343e2f9 (docs(backlog): mark K1 stranded perf fixes as landed (a2f0532))
**Tests:** backend collects clean, 0 collection errors — `cd backend && ./.venv313/Scripts/python.exe -m pytest --collect-only -q`. Do not quote a fixed total: on 2026-09-04 the same command returned 4581 and then 4608 within one session as concurrent work landed a new test file and edited `pytest.ini`. Pass/skip counts need MongoDB on :27017 — `cd backend && ./.venv313/Scripts/python.exe -m pytest -q` · frontend 280 passed / 280 total across 44 suites — `cd frontend && CI=true npx craco test --watchAll=false` (green 2026-09-04)
**Lint:** ruff per `backend/pyproject.toml` — select E, F, W, I, B, UP, SIM; ignore E501, SIM102, SIM108, SIM117; line-length 120; target py313; excludes `.venv`, `services/ml/inference.py`, `services/dash_ui.py`, `tests/conftest.py`. CI pins `ruff==0.15.22`; ruff is not installed locally.

## Project position

Deploy package hardened and ready: Oracle Always Free runbook
(`deploy/free/README.md`), `oracle-setup.sh` + read-only deploy key
`oracle-vm-deploy`, docker-compose stack behind Caddy. **Awaiting Nav's VM
provisioning** — Phase 1 of ROADMAP.md starts the moment the VM exists.

## Current phase

Phase 6 — Backlog Promotion [ACTIVE]. Phase 4 (Tidehunter Pro) is [GATED] gating-only scaffolding. Phase 3 [CLOSED 2026-08-31]. Phase 5 [COMPLETE 2026-08-31]. Phase 6 sub-status, all four partial: 6.1 (`/metrics` route + request-latency/error counters live; Mongo pool metrics, Public API/cvserver provider counters and an explicit fallback counter still missing); 6.2 (`/api/backtest/run` live, `/api/backtest/report/{ticker}` still missing); 6.4 (`/api/quant/signals` + `/api/quant/full` live, but no per-signal health/status field and no factor/z-score normalization); 6.6 (ADR-0002…0006 written, deployment-policy ADR + backend/frontend-coupling ADR + ADR-0007 still unwritten). 6.3 and 6.5 not started.

## Key context

- Round 9 closed at `4e1c1b8`. `docs/ROUND10_PLAN.md` is CLOSED / HISTORICAL — not the
  live queue. Its P0 block shipped (P0.1 conftest waiver applied; P0.2
  `fetch_spot_and_chains` restored; P0.3 STALE_IMPORT cleanup) and is recorded in
  ROADMAP Phase 2. Any P1/P2 item from that file that is still wanted must be
  re-promoted into a ROADMAP phase. Live queue = `.planning/ROADMAP.md`.
- Forbidden files per CLAUDE.md: `ml/inference.py`, `dash_ui.py`,
  `backend/tests/conftest.py` (R10 waiver), model artifacts under `backend/models/`,
  `frontend/.env`, `package.json`, `craco.config.js`, `frontend/src/App.js`.
- `backend/pytest.ini` is the pytest config — pytest reports `configfile: pytest.ini`
  under `rootdir: backend`. It uses a `[pytest]` header with asyncio_mode=auto and
  registers the flaky_env marker (see `.planning/LEARNINGS.md` for why). pytest.ini
  outranks pyproject.toml, so a `[tool.pytest.ini_options]` block in
  `backend/pyproject.toml` would be dead config; the working tree has removed that
  block and left a comment saying so.
- Codebase intel: `.planning/codebase/` (7 GSD map docs).

## Log

- 2026-08-24 — Ingest-docs bootstrap: PROJECT.md / REQUIREMENTS.md / ROADMAP.md /
  STATE.md / config.json created from curated manifest (8 docs); round transcripts
  excluded as historical noise.
- 2026-08-31 — Phase 3 closed, Phase 5 complete (all 4 tickets delivered). 7 files
  damaged by commit 79b047e (ROADMAP.md shred to 7 lines) — restored + all stale
  kanban/planning docs refreshed.
- 2026-09-04 — Doc-truth pass: STATE.md had two contradicting header blocks with
  different backend pass counts — collapsed to one, and the counts were replaced with
  the commands that produce them (both old numbers came from `backend/.venv/bin/python3`,
  an interpreter that does not exist on this box, so neither was reproducible).
  ROADMAP Phase 4 re-marked [GATED] to match its own PLAN.md; 6.2/6.4/6.6 headers
  corrected to [PARTIAL]; ADR references re-checked against `docs/adr/`.
  `docs/ROUND10_PLAN.md` marked CLOSED/HISTORICAL.
- 2026-09-04 (repair pass) — Fixed defects the first doc-truth pass left behind.
  `/metrics` is real: `prometheus_metrics()` in `backend/server.py`
  (`@app.get("/metrics")`) serving `services/observability.py`; ROADMAP 6.1 flipped from
  "no `/metrics` endpoint exists yet" to [PARTIAL], and STATE + BACKLOG now say the same
  thing. ROADMAP 6.4's "signal health/status per ticker" box UNCHECKED — neither
  `routes/quant.py` nor `routes/quant_full.py` has a health/status/active key, and
  `/api/quant/full` has no `count`. All `server.py:<line>` citations replaced with symbol
  names — the quant-router mount lines ROADMAP cited had already drifted by ~32 lines.
  BACKLOG K4's `continue-on-error` item closed: the mask is gone from
  `.github/workflows/ci.yml` in the working tree (still uncommitted). Pointers to
  `docs/ROUND10_PLAN.md` in ROADMAP + STATE now call it CLOSED / HISTORICAL. Phase
  status re-checked against every directory in `.planning/phases/`: Phase 4 [GATED] and
  Phase 5 [COMPLETE] match their PLAN.md; Phase 3's PLAN.md is stale (still
  "PLANNING → EXECUTION" with tickets TODO) while the code and commit 94c3c89 say
  CLOSED — flagged in ROADMAP, PLAN.md itself was out of lane.
  Backend collection re-verified with
  `cd backend && ./.venv313/Scripts/python.exe -m pytest --collect-only -q`: 0 errors,
  but the total moved from 4581 to 4608 mid-session (another lane added
  `backend/tests/test_check_silent_excepts.py` and edited `backend/pytest.ini`), so the
  headline no longer pins a number.
