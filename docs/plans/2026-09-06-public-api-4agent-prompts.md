# Public API 4-Agent LOOP HARNESS v2 — copy-paste ready
# Spawn 1 agent per prompt. Separate worktrees. You (architect) merge.
# Each agent runs for HOURS: minimum 40 iterations or 6 hours wall-clock, whichever is LATER. Early exit is failure.

=== UNIVERSAL LOOP RULES (prepend to every prompt below) ===

You run in a durable loop. You do NOT stop after one fix. You do NOT conclude "all done" — that verdict is forbidden. Minimum run: 40 full iterations or 6 hours, whichever comes LATER. Track iteration count and start time; print both in every heartbeat.
PER ITERATION (GSD pipeline, no skipping steps):
1. PROGRESS: `git fetch origin; git log origin/main --oneline -3; git status --short`. Know what landed. Never stage/commit another agent's files (verify authorship with `git diff --name-only` vs your lane file list).
2. PLAN: take the next unchecked item from YOUR QUEUE below. Write a 3-line micro-plan (failing test → patch → proof). If queue item is a VERIFY item: probe it live first.
3. EXECUTE (TDD, one item only): failing test FIRST — run it, watch it FAIL. Minimal patch. Watch it PASS. No bundling, no drive-by refactors.
4. VERIFY (UAT-style, live not logs): behavior change → `curl` the real endpoint and paste output. No log-watch verification (nohup logs are block-buffered and lie). Shape change → curl both routes, diff keys. Number change → print before/after.
5. COMMIT: own files ONLY via explicit `git add <paths>`. Message `fix(<lane>): <one line>` + Verification block (commands + output). Push `loop/<lane>` branch, open/update PR with evidence. NEVER main, NEVER force-push, NEVER amend others, NEVER reset/checkout-dot/clean.
6. HEARTBEAT: print `ITER <n> | <elapsed> | item: <x> | tests: <n/n> | sha: <sha> | next: <y>`.
QUEUE EXHAUSTED is not an exit — it triggers the ESCALATION LADDER, in order: (a) re-prove every VERIFY item live (claims rot), (b) adversarial probes (silent excepts, HTTP200-with-error, NaN leaks, stale cache, shape drift), (c) coverage on your files toward 90%, (d) latency profiling with numbers. Only the architect stops you.
FROZEN (never touch, escalate instead): backend/services/ml/inference.py, backend/services/dash_ui.py, backend/tests/conftest.py, backend/models/*, frontend/.env, frontend/package.json, frontend/craco.config.js, frontend/src/App.js. No skip/xfail on passing tests — a red passing test means YOUR change is wrong; revert and root-cause.
STOP-AND-REPORT (not exit) if: fix needs frozen file, 3 failed attempts on one item (record root cause, take next), provider outage (prove with 2 tickers + adapter logs).

--- PROMPT 1: BUDGET WARDEN — queue ---
LANE FILES: backend/services/public_budget.py, backend/services/public_api.py, backend/routes/public_api.py, backend/routes/public_brokerage.py, backend/tests/services/test_public_budget.py (+ tests you add).
BUILD QUEUE: (1) every unbilled Public.com call path gets envelope check; (2) unaffordable slice → honest 503 + telemetry (no silent empty 200); (3) per-day spend cap enforced + tested; (4) provider counters for Public API (fork BACKLOG line 162: counters must exist per provider, not inferred); (5) explicit data-source fallback counter (BACKLOG line 165).
VERIFY QUEUE (re-prove live each pass): affordable ticker returns rows with cost headers; unaffordable slice returns 503 (not 200-empty); /api/version SHA matches bundle expectations; no endpoint serves a wrong price when provider fails (curl SPY + a dead ticker, compare).
VERIFY CMDS: `cd backend && .venv/bin/python3 -m pytest tests/services/test_public_budget.py tests/test_public_api_only.py -q`; `.venv/bin/ruff check services/public_budget.py services/public_api.py routes/public_api.py routes/public_brokerage.py`.

--- PROMPT 2: SHAPE UNIFIER — queue (owns issue #18) ---
LANE FILES: backend/routes/analytics.py (GET /contract/{ticker}, GET /contract/{ticker}/{strike}/{expiry}, contracts_for_strike_expiry), backend/tests/routes/test_contract_shape_parity.py (new). flowseeker.py:341 /public/chain = READ-ONLY reference.
BUILD QUEUE: (1) close #18: base vs strike route return IDENTICAL row key-sets/types — curl both, diff, test, patch; (2) same parity extended to /public/chain rows; (3) empty-strike returns 200 with `contracts: []` (never 500, never null-shape); (4) every row carries bid/ask/last/iv/delta or explicit nulls (no missing keys).
VERIFY QUEUE: base-vs-strike key-diff is empty on SPY 755 + 2 more strikes; chain route keys stable across deploys (pin in test); frontend QuickTradePanel parses fixture without `undefined` (node one-liner against fixture).
VERIFY CMDS: `cd backend && .venv/bin/python3 -m pytest tests/routes/ -q`; `ruff check routes/analytics.py`. If you touch shared helpers, run tests/services/test_gex* too.
ESCALATION NOTE: if frontend depends on the OLD shape, do NOT break it — add `shape_version` field and report.

--- PROMPT 3: SCANNER HARDENER — queue ---
LANE FILES: backend/services/public_scanner.py, backend/services/public_api_adapter.py, backend/routes/flowseeker.py (/scan-public merge logic ONLY), backend/tests/services/test_public_advantage.py, test_public_api_partial_data.py, test_public_api_adapter_regressions.py (+ tests you add).
BUILD QUEUE: (1) wrong-price risk first: provider-failure → flagged degradation, never a stale price presented as live; (2) coverage/truncated flags on every merged row (partial-data fixtures); (3) spot freshness: max_age_seconds honored, stale quote labeled; (4) open-universe scan correctness (Phase 8): fixed-universe cutoff can't silently drop names — truncation flagged.
VERIFY QUEUE (curl both every pass): `/api/flowseeker/scan-public?ticker=SPY` → 200 with rows + quote_truth/dealer keys; dead ticker → honest degraded payload (record exact code); chain needs `instrument_type=EQUITY`; expiry used is valid (>= today+2, SPY 2026-09-02-class 41000s must be gone).
VERIFY CMDS: `cd backend && .venv/bin/python3 -m pytest tests/services/test_public_advantage.py tests/services/test_public_api_partial_data.py tests/services/test_public_api_adapter_regressions.py tests/test_public_spot_validation.py -q`; `ruff check services/public_scanner.py services/public_api_adapter.py`.
NaN LAW: `nan or 0` is nan — math.isnan guards everywhere, sanitize before sum.

--- PROMPT 4: ADVERSARIAL EVALUATOR — queue (tests only, no product code) ---
LANE FILES: backend/tests/services/test_public_api_integration.py, test_public_api_client.py (+ audit tests). /tmp probes never committed.
DUTY: (a) re-verify every merged claim from lanes 1–3 against LIVE endpoints (claims rot — a PASS last week is unproven today); (b) sweep the fork BACKLOG open items touching Public API and prove each is truly done or file it: quant registry absence (line 36), OOS harness presence (line 58), alert backtest gating (line 96), provider counters (line 162), fallback counter (line 165); (c) rotate failure classes: silent excepts (ruff E722 + grep `except:` in lane files), HTTP200-with-error bodies, NaN leaks, stale-cache serving, budget overruns, shape drift.
PROTOCOL: write FAILING audit test on the live path first. Passes → claim holds, record PASS + evidence. Fails → do NOT fix product code: file finding (endpoint, repro curl, expected vs actual, suspect file:line), commit ONLY the test on loop/public-eval, PR labeled eval-finding.
VERIFY CMDS: `cd backend && .venv/bin/python3 -m pytest tests/services/test_public_api_integration.py tests/services/test_public_api_client.py -q`; `ruff check` touched tests.
REPORT: claims re-verified (list + PASS), new findings (or NONE FOUND + probe list), SHAs. Adversarial always.
