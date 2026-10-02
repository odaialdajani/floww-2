# MUSE_STATE — Spark Muse 1.3 FLOWW backend + execution harness (new lane)

Owner: Spark (Muse Spark 1.3). Zed (GPT-6.1-Sol/xhigh) is lead architect,
frontend/Lodestar owner and final integration owner. Coordination via
checkpoints/PR receipts only. No direct messages, no new agents/threads/schedules.

## 0. Packet + R14 receipt verification (2 Oct 2026)

- Attached packet files `Spark-Muse-1.3-Xhigh-FLOWW-Integration-Harness.md` and
  `FLOWW-Shared-Integration-Contract.md` were NOT found in repo, worktrees,
  or /tmp (searched by name + content). The prompt body itself is treated as
  the harness; no contract is invented. Shared-contract version is therefore
  `unverified-packet-missing`; repo contracts below are the source of truth.
- `origin/main` = `1530ccd7f52a0de03512f383283463525a44134b` (PR92 merge,
  2026-10-02T03:12Z). `git fetch` clean, no drift. Matches harness baseline.
- PR92 state MERGED, mergeCommit `1530ccd7`, mergedAt 2026-10-02T03:12:24Z —
  a real merged receipt, not a bare populated SHA.
- PR93 OPEN/unmerged at `2f134e035bfecb1c8b1f289eb8c11b972ca334ac`, six doc-only
  commits on `solstice/spark-closeout` touching `docs/solstice/MUSE_STATE.md`
  only. Preserved, untouched.
- Historical closeout evidence retained by reference:
  `solstice/spark-closeout:docs/solstice/MUSE_STATE.md` §§1–16 (M1 operational
  truth, M2 37 focused + 530 solstice + restart/migration/lock proofs, M3
  47 lineage checks, M4 zero-durable census + runnable protocol, M5 handoff
  contract, fixture sha256 `8fefacf5…`, protected 71/71). Not re-claimed here;
  re-executed only where changed code warrants it.
- Worktrees preserved, none reset: main checkout (`solstice/r11-opus`
  @ `9a6c0295` + pre-existing dirty files, untouched), `spark-closeout`
  (`2f134e03`), `zed-solstice-r13` (`37a7e715`), `zed-solstice-r14`
  (`2bc1f03e` + dirty ZED_STATE + untracked `.final-acceptance/`),
  `zed-integration-20261002` (`1530ccd7` + untracked `.integration-reference/`),
  `/private/tmp/floww2-head`, `/Users/nav/.cline/audit-fixes`,
  `/Users/nav/.worktrees/cmd-c0-20260928070352`. No reset/clean/force-push.
- This lane: branch `solstice/spark-floww-backend` from exact `origin/main`,
  worktree `.worktrees/spark-floww-backend`. Clean at creation; protected
  manifest 71/71 git-hash identical at base (verified via
  `/usr/bin/git hash-object` per manifest line).
- Main-checkout dirty files preserved, never staged: `.mcp.json`,
  `docs/solstice/r12/SPARK_STATE.md`, `frontend/.gitignore`,
  `frontend/package-lock.json`, `frontend/package.json`, `frontend/yarn.lock`,
  `kanban/BOTTLENECK_ALERTS.md`, untracked `.worktrees/`,
  `frontend/.storybook/`, `SolsticeStatusStrip.stories.jsx`,
  `vitest.config.mjs`.

## 1. Single-writer ownership (this lane)

- Spark writes: `docs/solstice/MUSE_STATE.md` (this file); `docs/solstice/SPARK_*`
  evidence notes; `backend/services/public_*` (data/brokerage/execution
  services outside agent tree); `backend/routes/public_brokerage.py` +
  `backend/routes/public_api.py` hardening (no new live path); recorder/DuckDB/
  replay producers (`heatmap_history.py` price-path seam reuse only, no schema
  break); new `backend/services/solstice_price_producer.py`;
  new `backend/services/public_execution_lifecycle.py`; episode/outcome/research
  code + focused tests; versioned fixtures under `docs/solstice/r15/evidence/`
  (new dir, Spark-owned).
- Zed writes (read-only here, never edited): `frontend/`; 
  `backend/services/agent/**`; `backend/routes/agent.py`; `docs/solstice/ZED_STATE.md`,
  `COMMISSION.md`, `COMMISSIONING_PACKAGE.md`, `RUN_STATE.md`; `kanban/`;
  friend files (TideHunter/Flowseeker), frozen ML artifacts, watchdog.
- Shared-file rule: Spark is default writer for `server.py` mounts and shared
  schemas/registries, BUT this increment makes ZERO shared-file edits to avoid
  needing a Zed ack mid-lane. New services are unmounted (import-only,
  default-off); the exact mount patch is published as a proposal in
  `docs/solstice/SPARK_R15_MOUNT_PROPOSAL.md` for Zed's final review.
  `backend/services/public_capability.py` stale prose (place_order "no route")
  is a Spark-owned truth fix queued as READY item 1b, not yet applied.

## 2. Route + auth audit (verified at exact base `1530ccd7`, code-read)

- `backend/routes/public_brokerage.py` IS mounted: `server.py:3668-3670`
  `app.include_router(public_brokerage_router, prefix="/api")` with router
  prefix `/public` → live paths `GET /api/public/portfolio|orders|account`,
  `POST /api/public/order`, `POST /api/public/order/{id}/cancel`.
- `backend/routes/public_api.py` mounted at `/api/public` (`chain|quotes|bars|
  history`) alongside brokerage routes. No collision (distinct subpaths).
- Auth: every brokerage endpoint requires master key (`Depends(require_api_key)`;
  401 without/mismatch). Global `auth_middleware→verify_api_key` is fail-closed
  503 when unconfigured; `research_path` bypass is scoped to `/api/agent/*` only
  — `POST /api/solstice/outcomes/close` and all `/api/public/*` stay gated.
- Live gate: `POST /api/public/order` validates (422 on bad quantity/price)
  FIRST, then `_require_live_trading_enabled()` → 403 `live_trading_disabled`
  unless `FLOWW_ENABLE_LIVE_PUBLIC` is exactly `"1"`. Broker is never touched
  while disarmed (pinned by `test_live_submission_refuses_before_any_broker_access`).
  Authenticated cancellation remains available while disarmed (intentional).
- CLAUDE.md money-path prose ("PublicBroker.place_order UNGATED, currently
  unreachable, dead code") is STALE: the gated route calls
  `broker.place_order` when armed. The code truth (gated + reachable via HTTP)
  governs; the doc fix is queued, doc untouched in this increment.
- Alpaca PAPER (`routes/alpaca.py` → paper host, safe by construction) and
  `OrderRouter` (Alpaca paper only, Schwab removed, `allow_market` default-deny,
  reachable from Discord bot) are unchanged and unowned here. No venue flag
  touched; `FLOWW_ENABLE_LIVE_PUBLIC`, `FLOWW_RECORDER_WORKER`,
  `SOLSTICE_OUTCOME_WORKER`, `DUCKDB_PATH` all unset in this shell (OFF).
- Low-level adapters stay data-only: `public_api_adapter.py` exposes no
  order method (pinned by `test_adapter_has_no_order_method`). No MCP execution
  tools exposed to browser/Lodestar. No parallel unguarded endpoint introduced.

## 3. Durable + price-path gap (verified, not yet fixed)

- Store: `duckdb_engine._open_shared_db` (`DUCKDB_PATH` unset → `:memory:`),
  `heatmap_history.recorder_status` reports `durable=false/mode=memory` honestly;
  bad path falls back to memory, never claims durable. Schema v2 with additive
  `ADD COLUMN IF NOT EXISTS` migrations. Single-writer `threading.Lock` on all
  writer paths; multi-process writers NOT proven safe (documented, not tested
  as safe).
- Capture job: `recorder_health.py` (`FLOWW_RECORDER_WORKER`, default-off,
  `register_capture` has NO production caller — only tests — so production
  state is `absent`; `worker_state` absent/wired_off/active reported separately
  from store durability). `SOLSTICE_OUTCOME_WORKER` default-off (`server.py`).
- Price paths: storage seam exists (`record_price_path` append-only, no dedup,
  non-finite rejected; `price_paths_since` ordered; `outcome_close_tick` pure
  of stored data, skips decisions without stored paths; `POST outcomes/close`
  takes caller-supplied paths). NO scheduler feeds `price_paths_v1` anywhere in
  the tree — the genuinely missing default-off producer (caller paths only).
- Replay: `replay_snapshot` (available-at join), `session_manifest` (gaps),
  `compare_snapshots`, `GET /replay|manifest`, `recorder_health` — intact per
  R14. Second-process reopen with identical digests was proven in closeout
  resweep on throwaway DBs; production store has zero durable admitted records
  (tracked DBs hold 0 solstice rows; vertical fixture self-declares synthetic).

## 4. Execution lifecycle gap (verified, not yet fixed)

- `PublicBroker.place_order` mints one UUID per call (idempotency key present
  at transport), `cancel_order` empty-body → `CANCEL_PENDING` (never called
  canceled), `_parse_order` preserves bracket/open-close/averagePrice/legs/raw.
  Route-level validation + kill-switch exist, but there is NO versioned
  immutable intent, NO server-validated approval bound to intent hash, NO
  ownership (`PUBLIC_NATIVE_AGENT` vs `FLOWW_BACKEND`), NO preflight/budget/
  tick/margin policy enforcement, NO ambiguous-response reconciliation by
  orderId, NO restart reconcile-before-entry, NO protection lifecycle.
  `execution_engine.py` (Almgren-Chriss/Kyle/Hasbrouck) is quant math, not a
  Public lifecycle. `execution_doctrine.py` is node/R:R doctrine, not an
  approval record. This lane implements the missing deterministic lifecycle as
  a pure service (no new route, no live calls, fixture-driven).

## 5. New READY queue (base `1530ccd7`, contract versions pinned)

Contract versions: `metric-record.v1`, `solstice-metric-contract.v1`,
`formula gex.v2`, `outcome.v1`, `policy research_barriers.v1`,
`setup_review.v1` (read-only), `abl.v1`, `recorder-health.v1`, `movers.v2`,
`calendar.v1`, NEW `price-path-producer.v1`, NEW `execution-intent.v1`.

- [DONE] R15-1 Public capability + auth truth matrix — `docs/solstice/SPARK_R15_PUBLIC_MATRIX.md` +
  `r15/evidence/public_matrix_v1.json` (27 ops). Stale `public_capability.py:37`
  prose noted, fix deferred to Zed-acked follow-up (zero behavior edits here).
- [DONE] R15-2 Default-off scheduled price-path producer —
  `backend/services/solstice_price_producer.py` + 17 tests +
  `backend/services/solstice_price_fetch.py` (real Public-quote seam) +
  `backend/routes/solstice_price_paths.py` (read-only status/points) +
  `backend/tests/solstice/test_r15_price_wiring.py` (7 tests) +
  `r15/evidence/price_path_swing5m_v1.json` (digest `146ebfa4e0be`).
  Hole-fix pass: gaps double-count removed (regression test pins cumulative ==
  sum of receipts); producer WIRED into server lifespan default-off (was absent,
  now `wired_off` with OFF receipt); `server.py` mount + lifespan is the only
  shared-file edit (writer Spark, Zed ack pending).
- [DONE] R15-3 Deterministic Public execution lifecycle —
  `backend/services/public_execution_lifecycle.py` + 20 tests +
  `r15/evidence/execution_intent_v1.json` (`in_5c8c5dcd3b07`). 20/20 pass;
  no live orders, no flag change, no new route.
  Hole-fix pass: preflight cache now keyed intent_hash + market-ctx fingerprint
  with 60s TTL (same-intent/moved-market refreshes; regression test); optional
  `context_hash` binding → `CONTEXT_CHANGED`; `submit(..., require_approval)`
  enforces server-bound approval (`APPROVAL_INVALID`, production opt-in, tests
  default validation-only); new `reconcile_all` for restart-before-entry.
- [DONE] R15-4 Account/portfolio/journal/protection/expiry contracts —
  `docs/solstice/SPARK_R15_ACCOUNT_CONTRACTS.md` (read-only shapes + refusal codes).
- [DONE] R15-5 Outcome linkage + frozen prospective research protocol —
  `docs/solstice/SPARK_R15_OUTCOME_PROTOCOL.md` (FROZEN_PROTOCOL untouched,
  zero durable records = insufficient evidence).
- [IN_PROGRESS] R15-6 Exact-head backend receipt + combined-candidate acceptance —
  `docs/solstice/SPARK_R15_RECEIPT.md` (refresh pending for hole-fix head);
  PR94 OPEN (review only). Evidence: `tests/solstice/` 574 passed from `backend/`;
  new focused 44 passed; brokerage gates 32 passed; truth 227/0; ruff clean;
  silent 351 OK; API 375 paths (+2 read-only). Next: refresh receipt, commit,
  push PR94, participate in Zed's isolated verification (Zed paused — proceed,
  ack pending).

External BLOCKED (not engineering): SPX entitlement, licensed feeds, operator
risk limits, Public native activation, participant recruitment, durable
activation/service auth, real-money commissioning policy sign-off (Zed final
review). Default-off implementation, migrations, fixtures, deterministic tests
and frontend-consumable contracts are owned now; activation/live orders/worker
start/flag changes/deployments/restarts remain unauthorized.

## 6. Activation + next action

Activation: OFF. No deployment, restart, daemon startup, capture/outcome/price-path
worker activation, orders, credential changes, retraining, messages, or paid calls.
All worker flags unset (verified in-process); new producer flag
`FLOWW_PRICE_PATH_PRODUCER` defaults OFF (status route reports `absent`/`wired_off`).

## 7. Hole-fix pass (2 Oct 2026, Zed paused — credits out)

Skills read: `frontend` (design/composition guidelines; applied as
frontend-consumable contract discipline — explicit loading/empty/partial/stale/
error states, no blank-as-zero — already the matrix/refusal shape). Remaining
installed skills (`front2`, `gsd-loop-*`, `jfej`, `readmegrill`,
`source-command-mesh-sync`, `customize-opencode`) have no bearing on this
backend lane; superpowers-style TDD/systematic-debugging/verification discipline
from CLAUDE.md was followed manually (failing tests first, full-gate reruns).

Holes found + fixed (all with regression tests, no live calls, no activation):
1. Producer cumulative `gaps` double-counted (inline + end-of-tick mirror).
   Fixed to inline-once; `test_cumulative_counters_equal_sum_of_tick_receipts_no_double_count`.
2. Preflight cache keyed on intent_hash only → stale estimate reused after a
   market move. Now intent_hash + ctx fingerprint (quotes/account/session) with
   60s TTL; `test_preflight_expires_on_market_move_not_just_intent_change`.
3. No `CONTEXT_CHANGED` enforcement (prompt requirement). Optional
   `context_hash` binding on both sides; mismatch refuses; unbound intents keep
   backward-compatible behavior; new test.
4. No approval gate on `submit` (prompt: client boolean is not authorization).
   New opt-in `submit(..., approval, require_approval, approval_scope)` →
   `APPROVAL_INVALID`; persisted on the record; default validation-only so
   intent logic stays pinnable; `test_submit_with_required_approval_enforces_binding`.
5. No bulk restart reconcile (prompt: reconcile open/unknown before new entry).
   New `reconcile_all(broker)` (read-only, truthful); tested.
6. Producer registered nowhere in production (worker_state `absent` forever).
   Wired into server lifespan default-off + read-only status/points routes
   (`solstice_price_fetch.py` real adapter seam, `solstice_price_paths.py`,
   7 wiring tests). Production now reports `wired_off` + OFF receipt instead of
   `absent`. Shared-file edit limited to `server.py` mounts/lifespan (writer:
   Spark, Zed ack pending); no submission path; `docs/api` regenerated 373→375.
7. Duplicates audit: storage stays append-only by design (ordering/gaps belong
   to labeling); producer dedups exact `(ticker, at_ts)` via in-process set +
   DB existence check (restart-safe); intent resubmission reuses broker orderId +
   payload (single broker call pinned); no duplicate polling paths added (one
   fetch per symbol per 300s tick, budget-debited, session-gated before any call).

Duplicates intentionally NOT merged: `execution_engine.py` (equities
Almgren-Chriss) vs `public_execution_lifecycle.py` (Public options intent
lifecycle) are different domains; `recorder_health` worker vs price-path worker
are separate jobs with separate flags/states; `routes/solstice.py` untouched
(new status lives in its own router file).

Next exact action: refresh `SPARK_R15_RECEIPT.md` counts, commit hole-fix pass,
push PR94 (no merge/deploy/activate), continue combined-candidate readiness
until Zed returns or genuine external input is required.
