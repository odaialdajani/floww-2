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
  `r15/evidence/public_matrix_v1.json` (27 ops, regenerated after fix).
  Improvement pass: stale `public_capability.py:37` prose FIXED (text-only,
  `"gated LIVE — POST /api/public/order, FLOWW_ENABLE_LIVE_PUBLIC==1"`; no test
  or frontend asserted the old string). Bandit clean on all touched files.
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
- [DONE] R15-6 Exact-head backend receipt + combined-candidate acceptance —
  `docs/solstice/SPARK_R15_RECEIPT.md`; PR94 CI green on exact head; Zed PR95
  audited + scratch suites green; superseded by §13: COMBINED PR96 MERGED.

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

## 8. Improvement pass (2 Oct 2026, Zed still down)

1. `public_capability.py:37` stale prose FIXED (text-only truth fix; behavior
   identical; matrix JSON regenerated to match). `SPARK_R15_PUBLIC_MATRIX.md`
   updated.
2. Bandit medium-gate run over all touched backend files: CLEAN.
3. Env skew noted: local venv has `pandas-market-calendars` 5.4.0 while
   `backend/requirements.txt` pins 4.6.1. The XNYS session gate uses only
   stable `get_calendar/schedule` APIs; no code change, disclosed here and in
   the receipt. Zed/Nav: align the pin only via the owned dependency lane
   (frontend/dependency edits belong to Zed; backend pins need operator review).

## 9. Second improvement pass (2 Oct 2026, Zed still down)

- [DONE] R15-7 Operator commissioning policy + rollback —
  `docs/solstice/SPARK_R15_COMMISSIONING.md` (activation prerequisites, exact
  reversible steps, kill-switch drill, what commissioning never grants; policy
  only, nothing performed). Complements Zed's `COMMISSIONING_PACKAGE.md`
  (read-only here) for the R15 additions.
- [DONE] R15-8 Lodestar brief handoff spec — `docs/solstice/SPARK_R15_BRIEF_HANDOFF.md`
  + `r15/evidence/lodestar_brief_v1.json` (exact backend fields, freshness/
  refusal semantics, explicit non-claims; model config stays with Zed).
- [DONE] R15-9 Network boundary pin — `backend/tests/solstice/test_r15_network_boundary.py`
  (4 tests): new lifecycle/producer/fetch/route modules carry no ambient network
  imports, no direct broker/HTTP construction, adapter use inside the fetch seam
  only, no venue-flag reads in the lifecycle. First run caught two over-broad
  test tokens (fixed in the test, not the product).
- [DONE] R15-10 Outcome census re-run — `docs/solstice/SPARK_R15_CENSUS.md`
  (read-only): configured store is `:memory:`/`durable:false` (clear refusal),
  tracked DBs hold 0 solstice rows, all flags unset. Verdict unchanged:
  INSUFFICIENT EVIDENCE.

## 10. Third improvement pass (2 Oct 2026, Zed still down)

Lifecycle transitions the prompt requires but the first cut left as refusal-only:
- [DONE] `cancel(intent_id, broker)` — exits need no arming and ignore the
  entry pause by design; `CANCEL_PENDING`/empty answers stay non-terminal
  (pending is NOT canceled), so new entries stay blocked until final reconcile.
- [DONE] `supersede(old, new, ...)` — the intentional transition for changed
  orders: cancel-old-first, enter-new-only-on-CANCELED, parent-linked, fresh
  broker identity; pending old blocks with `SUPERSEDE_BLOCKED` (no double entry).
  In-place `replace` stays refused.
- [DONE] `require_fresh_preflight` submit gate → `STALE_PREFLIGHT` without a
  cached intent+ctx estimate; `has_fresh_preflight` helper; preflight receipt
  now reports `intent_hash` (pure digest) + `ctx_fingerprint` separately.
- [DONE] Producer `_seen` fast-path bounded (`_SEEN_MAX=10000`, oldest-first
  prune); DB recheck still covers restarts/evictions (regression test).
- Structural non-merges documented in §7 stand (different domains/jobs/files).

## 11. Re-verification + combined-candidate check (3 Oct 2026)

- Packet files STILL absent (repo/worktree-wide search, 3 Oct) — prompt body
  remains the harness; no contracts invented.
- No `origin/main` drift (still `1530ccd7`). PR93 still OPEN doc-only.
- PR94 CI ran on the EXACT lane head `1fdf403d` (run 37061874706): backend-tests
  PASS, docker-build PASS, frontend-build PASS, ruff PASS. Hosted exact-head
  evidence; full `tests/` + coverage ran in CI, not just the local Solstice slice.
- Zed published PR95 DRAFT (`solstice/zed-integration-20261002` @ `483704fc`,
  "grounded frontend and disarmed Public handoff"). Overlap audit (77 files):
  ZERO file overlap with this lane (all Zed-owned: agent tree, frontend,
  `FLOWW_INTEGRATION_CONTRACT.md`, `integration/`, ZED_STATE, scripts). No
  shared-file conflict from either side; my only shared edit stays `server.py`
  mounts/lifespan (Zed ack still pending).
- Zed-diff audit (read-only): no new order-submission path (only a mocked GET
  `/api/public/orders` fixture with null money + PARTIAL shape — matches my
  contracts); no auth/gate edits; Alpaca PAPER labeling + Public gate explicitly
  preserved; backend entry unavailable in their UI pending accepted producers.
  No price-paths route references yet — my routes are additive, nothing to break.
- Scratch combined verification (read-only worktree `/tmp/zed-combined` @
  `483704fc`, thrown away after): Zed's 4 agent suites (native_handoff,
  plan_draft, exact_contract_admission, codex_model) → **46 passed** with this
  repo's venv. Their `solstice-display.v1.json` carries `source_fixture`+sha,
  `snapshotId`, OSI/strike/expiry, zero bid/ask (quote-free display fixture —
  consistent with `MISSING_QUOTE_SIDES` refusal, not a conflict).
- Verdict at the time: lanes compatible AND independently green; integration
  proof required Zed's merge + a combined-head CI run. (Superseded by §13:
  combined PR96 merged with all gates green.) A green backend lane alone was
  never claimed as integrated UI proof.

## 12. API-doc boundary decision (3 Oct 2026, Nav authorized Spark takeover)

Zed's review asked: authorize Zed to regenerate ONLY `docs/api/openapi.json` +
`docs/api/README.md` with the existing generator, or Spark takes the boundary.
Decision (Nav: "take over, finish everything"): **Spark takes it.** Writer:
Spark; exact boundary: run `python3 qc/audit/generate_api_docs.py` on the
combined head, commit ONLY those two generated files — no runtime
schema/registry/server/route change, all Spark and Zed paths preserved.
Verified: diff is exactly the `/api/agent/handoffs` GET/POST surface (Zed's
owned agent route, untouched); 375→376 paths; `--check` passes. Zed's
checkpoint need not change; disagreement can still be posted on PR94/96.

## 13. Combined merge record (3 Oct 2026, Nav: "take over, finish everything")

- Combined PR96 (`solstice/combined-integration-20261002`) MERGED at
  `df1bf1ce` (2026-10-03T01:35Z) after ALL gates green on the exact head:
  ruff PASS (incl. API-doc gate at 376 paths), backend-tests PASS (18m27s),
  frontend-build PASS, docker-build PASS. Draft→ready→merge by Spark under
  explicit Nav takeover authorization (Zed's lane was DRAFT/HOLD on the doc gate).
- Merge contents: Spark lane (8 commits: producer, lifecycle, contracts,
  hole-fix passes) + Zed integration (grounded frontend, disarmed Public
  handoff, native bridge) + Spark-taken API-doc regen (375→376, `/api/agent/
  handoffs` surface only). No force-push; normal merge commit.
- Post-merge `origin/main` (`df1bf1ce`): protected manifest 71/71 identical
  (verified via `git rev-parse origin/main:<path>` per line). Main CI/CD+lint
  triggered on the merge head (pending at record time — re-check before claiming
  main-green).
- Activation state: OFF (all worker/venue flags unset; no deployment, restart,
  daemon, order, credential, retraining, message, or paid call by this lane).
  Empirical outcomes: still INSUFFICIENT EVIDENCE (zero durable admitted
  records). Nothing in this merge commissions live trading or claims edge.
- Remaining BLOCKED_EXTERNAL: SPX entitlement, licensed feeds, operator risk
  limits + fixed account policy, Public native activation, participant study,
  empirical 30–60 sessions, data rights, durable production capture with
  admitted records, Nav visual review, real-money commissioning record.
- Next: watch main CI to green; close PR94 as superseded; resume only on new
  owned work or genuine external input.

## 14. Post-merge verify + fix pass (3 Oct 2026 — "make sure it's all good")

Main `df1bf1ce` verified: protected 71/71, API 376 paths incl. handoffs,
main lint SUCCESS (main CI/CD still running at record time).
- [DONE] R15-11 Terminal-cancel guard — `cancel()` on FILLED/REJECTED/CANCELED
  refuses `already-terminal` with zero broker calls; `supersede()` on terminal
  blocks without entry. Tested incl. no-call assertion.
- [DONE] R15-12 Durable-write failure paths — `register_store` refuses dead
  handles (prior store kept); create-path write failure → `STORE_UNAVAILABLE`
  before any broker call; post-receipt failure flagged `persist_error`
  (heals via recover+reconcile). Tested all three.

## 15. CI timeout analysis + follow-up PR97 (3 Oct 2026)

- Commit `6262d06c` backend-tests run 37084772976: NOT a test failure — the job
  hit the 15-minute action timeout AFTER the suite finished: **7135 passed,
  38 skipped, coverage 69.50%** (gate is 60%). Zero failures; badge red on time,
  not on correctness. Later heads with the same code passed fully (PR96 combined
  backend-tests 18m27s SUCCESS).
- Lesson recorded honestly: the full suite is outgrowing the 15-min job budget
  (53278 statements, 69% coverage). Splitting the job or raising the timeout is
  a CI-owned change (devops lane) — not smuggled in here.
- Follow-up PR97 (`solstice/spark-floww-backend` @ `ec155778`, R15-11/R15-12 +
  §14 record): review-only; merge only on green CI + Nav standing authorization.

## 16. PR97 merge record (3 Oct 2026 — CI trigger anomaly)

- Hosted CI never fired for PR97's head (`feccbd89`): two pushes + PR open +
  close/reopen produced zero workflow runs (verified via run list, check-runs
  API, and `gh pr checks`). Cause undiagnosed from here — possibly an
  Actions-side delivery/quota issue; repo workflow config untouched (out of
  scope). This is recorded as an operational anomaly, not as a gate pass.
- Substitute gate (same commands CI runs, local Mongo UP, exact head):
  full `pytest tests/ -q --tb=short --cov=. -m "not flaky_env"` →
  **7050 passed, 37 skipped, coverage 68.78%** (gate 60%), 0 failures.
  Plus: solstice 597, ruff clean, truth 227/0, silent 351 OK, API 376 current,
  protected 71/71.
- Merge proceeds under Nav's explicit standing "finish everything, no
  blocking" directive, on this evidence. Revert path: single merge commit.
  (Resolution note: origin/main's §12 API-doc decision, which this lane's §§13–16
  already assume, is retained above as §12; no content lost on either side.)

## 17. R16 READY queue (3 Oct 2026 — second prompt cycle, packet fully read)

Base: `origin/main` `08f3793c` (PR98 merge). Lane: `solstice/spark-r16` (clean,
protected 71/71 at base). Main CI/CD on base still running at publication;
main lint SUCCESS; prior head fully green. Zed working again: no new published
diff (their 3 branch commits are docs/evidence-only vs main; all their code is
integrated). Packet now fully read: both harnesses, shared contract, Triad
contract, prompt library, toolbox (skimmed for backend relevance), START-HERE.

Contract versions (unchanged + new): `execution-intent.v1`,
`execution-receipt.v1`, `price-path-producer.v1`, `outcome.v1`, `abl.v1`,
`recorder-health.v1`, `calendar.v1`, NEW `intent-draft.v1`, NEW `budget-check.v1`.

- [READY] R16-1 Cross-process same-intent guard — owned:
  `backend/services/public_execution_lifecycle.py` (DB-backed submit dedup when
  a store is registered) + focused tests (two instances, one file DB —
  second submit reuses orderId, single broker call). Contract unchanged.
  Evidence: new tests + full R15 focused rerun. Next: implement first.
- [READY] R16-2 Affordability gate — owned: lifecycle `INSUFFICIENT_BUDGET`
  refusal (intent budget total vs ctx buying_power) + brief-spec row + tests.
  Prompt-library requirement: unaffordable → no place. Next: after R16-1.
- [READY] R16-3 Fill/remaining reporting + draft registry — owned: reconcile
  reports `filled_quantity`/`remaining_quantity` via `_rget`; advisory
  `intent-draft.v1` states DRAFT→REVIEWED→PREFLIGHTED→AWAITING (linked by
  intent_hash; submit stays independent) + tests. Next: after R16-2.
- [READY] R16-4 Brief-spec extension — owned:
  `docs/solstice/SPARK_R15_BRIEF_HANDOFF.md` (spread limits, session-loss cap,
  consecutive-bid-check params, affordability) + fixture row. Docs-only.
  Next: after R16-3.
- [READY] R16-5 Receipt + combined acceptance — owned: `SPARK_R16_RECEIPT.md`
  (new), PR (review-only), Zed combined verification. BLOCKED_EXTERNAL on Zed
  merge; proceed to open PR only. Next: last.

## 18. R16-6 submit-ownership lock (3 Oct 2026)

- [DONE] Single-process atomic submit: idempotent/overlap/insert under
  `_SUBMIT_LOCK` (no awaits inside); 5-thread same-instant test places exactly
  once (stable 3/3). Cross-process races stay documented residual (advisory
  DB guard + broker orderId truth). Multi-process DuckDB writers still NOT
  claimed safe — single-writer lifecycle only.

## 19. R16-7 disarmed-supersede guard + PR101 audit (3 Oct 2026, Zed active)

- [DONE] Disarmed `supersede()` refuses BEFORE cancelling (a refused transition
  never strands a cancelled order with no replacement); zero-call assertion.
- PR101 (`combined-r16`, all 4 hosted gates green) audited read-only: it carries
  my R16 content verbatim (lifecycle + tests + fixture identical; receipt copy
  is one commit stale: 602/40 vs current 604/43). No hostile edits, no gate
  weakening — staleness only. Merge decision stays with Nav/Zed; my lane does
  not touch their branch.

## 20. R17 READY queue (3 Oct 2026 — Zed combined report answered)

Base: `origin/main` `6eaa3343` (PR102 merge). Lane: `solstice/spark-r17` (clean,
protected 71/71 at base). Zed's new report verified: e5ee1404 green everywhere,
replay defects fixed in Zed-owned `solsticeReplay.js`, API-doc blocker closed by
Spark-taken regen (376 paths on main). Remaining Spark-assigned gaps from that
report are taken as the queue below. Packet + Triad + prompt-library deltas
absorbed (intent states, affordability, session caps, brief rows — R16 did most;
this queue finishes the rest).

Contract versions: `execution-intent.v1`, `execution-receipt.v1`,
`intent-draft.v1`, `price-path-producer.v1`, NEW `coverage-read.v1`.

- [DONE] R17-1 Stored-session enumeration — owned: read-only
  `GET /api/solstice/price-paths/sessions?ticker=` (stored NY session days +
  per-day snapshot counts, gaps via existing manifest). No writes. Evidence: 6-test file green with sessions/comparable/expiries.
- [DONE] R17-2 Admitted expiry-range query — owned: read-only
  `GET /api/solstice/price-paths/expiries?ticker=&min_dte=14&max_dte=60`
  (listed expirations + DTE + ADMITTED/excluded + reasons; existing `dte≤30`
  display filter in `market_data.py` untouched). Reuses cached adapter fetch.
  Evidence: window verdicts incl. 0DTE BELOW_WINDOW + 502 path.
- [DONE] R17-3 Comparable-pair admission verdict — owned: read-only
  `GET /api/solstice/price-paths/comparable?baseline_id=&snapshot_id=`
  running the exact `check_window_comparability` gate over two replayed stored
  snapshots (IDENTITY_UNDECLARED/SESSION_ROLL/OUT_OF_ORDER preserved).
  Evidence: TICKER_MISMATCH/SESSION_ROLL/OUT_OF_ORDER/NO_BASELINE pinned.
- [DONE] R17-4 Receipt + PR + Zed re-verification — owned: `SPARK_R17_RECEIPT.md`,
  PR (review-only), Zed-branch overlap recheck. Receipt updated with actual
  hosted results (see §21). PR103 OPEN, all four hosted gates green at
  `611f3c2f`. Merge decision with Nav/Zed — BLOCKED_EXTERNAL there.

## 21. Session checkpoint (3 Oct 2026 — packet re-verification + queue close)

Resume-prompt cycle: harness + shared contract re-read from
`/Users/nav/Documents/Codex/2026-10-02/he/outputs/`.

- R14 receipt VERIFIED: `solstice/spark-closeout` @ `2f134e03`,
  `docs/solstice/MUSE_STATE.md` §16 — 530 Solstice tests + 37 focused,
  restart/migration/lock/lineage proofs executed on throwaway file DBs,
  fixture digest `8fefacf5…`, zero durable admitted records, activation OFF.
  Held as historical per packet rule (no unchanged resweep re-run).
- Drift: `origin/main` advanced from packet baseline `1530ccd7` to
  `6eaa3343` via Spark lane PRs 96/98/99/102 (R15 producer/lifecycle,
  R16 submit lock + fills/drafts/guards). PR93 (R14 closeout docs) still
  OPEN/unmerged at `2f134e03` — its §16 content lives only on that branch.
  Zed lanes (PR100/101 combined) carry this lane's content verbatim; audited
  §19. No unaccounted remote commits.
- Harness 6-item queue status (all engineering DONE on main/PR103):
  1. Public matrix/auth — R15: `SPARK_R15_PUBLIC_MATRIX.md` + 27-op JSON,
     auth fail-closed proven. DONE.
  2. Default-off price-path producer — `services/solstice_price_producer.py`
     (`price-path-producer.v1`, `FLOWW_PRICE_PATH_PRODUCER` default-off,
     swing-only 300s, XNYS-gated, budget-aware) + second-process reopen
     proof (`test_second_process_reopens_file_db_with_identical_paths_and_replay`)
     + migration/restart/contention tests. DONE. Admitted production records
     = external (activation).
  3. Immutable intents/execution lifecycle —
     `services/public_execution_lifecycle.py` (`execution-intent.v1`,
     `intent-draft.v1`, Decimal-exact, approval-bound, submit lock,
     disarmed-supersede guard, read-only reconcile). DONE. Live = external.
  4. Account/portfolio/protection/expiry contracts —
     `SPARK_R15_ACCOUNT_CONTRACTS.md`, R17 `coverage-read.v1` routes. DONE.
  5. Outcome protocol — `SPARK_R15_OUTCOME_PROTOCOL.md`; zero durable
     records → INSUFFICIENT EVIDENCE; 30–60 sessions = collection target,
     not edge proof. DONE protocol, empirics external.
  6. Exact-head receipt + combined acceptance — PR103 all gates green;
     combined merge decision with Nav/Zed. BLOCKED_EXTERNAL only there.
- Supplied to Zed (via this checkpoint): contract versions
  `execution-intent.v1`, `execution-receipt.v1`, `intent-draft.v1`,
  `price-path-producer.v1`, `coverage-read.v1`, `outcome.v1`, `abl.v1`,
  `recorder-health.v1`, `calendar.v1`, `budget-check.v1`; routes
  `GET /api/solstice/price-paths/{status,points,sessions,expiries,comparable}`;
  fixtures `r15/evidence/` (`price_path_swing5m_v1.json` `146ebfa4e0be`,
  `execution_intent_v1.json` `in_5c8c5dcd3b07`, `lodestar_brief_v1.json`);
  honest net outcomes = INSUFFICIENT EVIDENCE, no edge claim.
- Activation state: OFF. No flag/order/service/credential changes this
  session. Protected 71/71 untouched; no Zed-owned file touched (PR103 diff:
  6 Spark-owned paths only).
- Next exact action: none READY-owned remains. Await Nav/Zed merge decision
  on PR103 (and PR93 closeout docs), then combined exact-head acceptance
  with Zed's lane head. True external blockers unchanged: SPX entitlement,
  licensed feeds, fixed account/risk policy, Public native activation,
  participant recruitment, durable production capture, real-money record,
  Nav visual review.

## 22. Take-over sweep (3 Oct 2026 — Cline assumes the Muse lane)

Nav handed the lane over; packet re-read from
`/Users/nav/Documents/Codex/2026-10-02/he/outputs/FLOWW-Zed-Spark-Muse-Integration-Packet`.
Sweep verified the §21/R17 claims at the exact head `611f3c2f`:

- Local (Python 3.14.6, disclosed): r17 **6 passed**; r17+wiring **14 passed**;
  `ruff check` touched files clean; `openapi.json` 376→**379** purely additive
  (added `/api/solstice/price-paths/{sessions,expiries,comparable}`, removed
  none); `docs/api/README.md` 387→390, solstice group 20→23.
- Hosted PR103 gates all **PASS** at `611f3c2f`: backend-tests + frontend-build
  + docker-build (run 37096664993), ruff (run 37096665007). PR100 and PR101
  hosted checks also all PASS (previously pending in Zed's report).
- PR truth: PR99 MERGED `bec8ac8c`; PR102 MERGED `53d2a051`; `origin/main` =
  `6eaa3343`. PR93 still OPEN `2f134e03`. PR101 MERGEABLE/CLEAN; PR101's 20
  files, PR102's 4 files and this lane's 6 files are pairwise disjoint — no
  merge conflict.
- Protection: `git diff --name-only 6eaa3343..611f3c2f` is exactly the 6
  Spark-owned paths — no frontend, agent-tree, TideHunter/Flowseeker, frozen
  artifact or watchdog files touched. Worktree dirty files were limited to the
  two Muse-owned docs; committed this pass.
- Hole found (flagged, Zed-owned docs untouched): the combined candidate
  `dcbc1492` (PR101) predates PR102's `90f96227` disarmed-supersede fix —
  tested SHA `e5ee1404` does not include it, so "backend matches the tested
  candidate" is stale vs `main` `6eaa3343`. Combined acceptance must re-sync
  at `main` + Zed head `75c160c2` and re-verify before PR100/PR101 merge.
- Activation state: OFF unchanged. No flags, orders, services, credentials or
  paid calls. `market_data.py` `dte≤30` display filter and the unfiltered
  `dte_max` expiry-count loading both unchanged (distinct constraints).
- Next exact action: Nav/Zed merge decision on PR103 (and PR93 closeout docs);
  Zed re-syncs the combined acceptance at `6eaa3343` + `75c160c2`.

## 23. Take-over pass 2 (3 Oct 2026 — Zed's residual producer requests)

Zed's PR103 comment (mrbeast1179-sketch, candidate `4bcc6f39` = main
`6eaa3343` + PR101 `dcbc1492` + frozen PR103 `611f3c2f`) asked for three
concrete producer items and an in-checkpoint acknowledgement. Acknowledged
here as READY-owned engineering, not solely external:

1. [DONE this pass] Session-index normalization: `/sessions` now attributes
   days by the stored `asof_ts` timestamp prefix — the SAME attribution the
   owning `session_manifest`/`compare_snapshots` match with `LIKE day%` — and
   reports ET-normalized `ny_date` (null when non-uniform) plus an
   `overnight` flag for exactly the offset/naive cases. Overnight/offset
   fixtures pinned (02:00Z crossing ET midnight; naive 00:30 adopting the
   owning UTC convention; ET-local never flags).
2. [DONE this pass] Expiries range completion: reversed bounds refuse 422
   `REVERSED_WINDOW` before any fetch; owning display envelope (`dte le=30`,
   `market_data.py`) projected per row as `display_envelope` — a DIFFERENT
   constraint from the admitted 14–60 policy window; honest `coverage` block
   (requested/n_listed/n_display_envelope/listing_capped/lower+upper edge
   observed) replaces the silent firstN verdict; listings default 6→12,
   le 12→16 (budget 2+N fail-closed, CAPACITY 60). Both refusals now return
   structured JSONResponse bodies — the app's global exception handler
   stringifies dict details (server.py:231), which would bury the refusal
   code in a repr string; server.py itself untouched (shared-file protocol).
3. [DONE this pass] Authenticated/default-deny stored approvals/preflight +
   account-wide limits/native/open/unknown inventory/protection/recovery
   boundary: new read-only `lifecycle_inventory()` in
   `public_execution_lifecycle.py` (known/open/UNKNOWN records with
   conservative protection truth, draft stages, native workflows, redacted
   preflight counts, honest recovery boundary — storeless is never claimed as
   no-orders-open; account-wide limits UNSET) served by the new
   `GET /api/public/execution-lifecycle/inventory` on the already-mounted
   public_brokerage router — authenticated via `require_api_key`
   (503 unconfigured / 401 bad key), NO server.py edit, no live path, no
   recovery executed, no broker call. 5 focused tests green.

Verification (exact head, Python 3.14.6, disclosed): r17 9 tests + wiring 8 =
**17 passed**; lifecycle inventory 5 + existing lifecycle 42 = **47 passed**;
ruff touched files clean; openapi regenerated 379→**380** paths (+1
inventory route, purely additive); protected 71/71 and Zed-owned files
untouched.

Coordination note: PR103 carries `gsd:escalated` (gsd-loop review pass: no
linked issue — the repo has issues disabled; non-`gsd/NNN-*` branch → labels
only, no verdict posted, per the review playbook). The label is honest: the
merge decision is Nav's; remove it when linkage exists. Zed's combined
candidate froze `611f3c2f`; new lane heads require re-composition before the
combined acceptance.

- Activation state: OFF. No flags/orders/services/credentials/paid calls.
  All three of Zed's residual producer requests are now DONE engineering;
  the harness 6-item queue remains complete.
- Next exact action: combined exact-head acceptance with Zed's re-composed
  lane head (Zed's candidate froze `611f3c2f`; re-compose at this lane head),
  plus the Nav/Zed merge decision on PR103/PR101/PR100 and PR93 closeout
  docs. True externals unchanged.

## 24. Hardening pass (3 Oct 2026 — "continue, no duplicates, reverify, improve")

Duplicate audit (code-read, no new abstraction): `recorder_health`
(register_capture/start_worker for the capture job) vs
`solstice_price_producer` (same names for the price-path job) are separate
jobs with separate flags/states — not merged. `execution_engine.py`
(equities Almgren-Chriss math) vs `public_execution_lifecycle.py` (Public
options intent lifecycle) are different domains — not merged.
`routes/solstice.py` untouched; new reads live in `routes/solstice_price_paths.py`
only. No duplicate polling path added (one fetch per symbol per tick).

Holes found + fixed (TDD: 4 failing first, then green; all Spark-owned,
no shared-file edit, no route surface change, no activation):
1. `supersede()` bypassed approval/preflight gates and cancelled before
   checking: new params `approval/require_approval/approval_scope/
   require_fresh_preflight`, deterministic gates pre-validated on the final
   candidate (with `supersedes`) BEFORE any cancel — a refused transition
   never strands a cancelled order. Pinned by 2 tests (old stays OPEN,
   zero new broker calls on refusal).
2. `lifecycle_inventory()` counted memory drafts only: now unions durable
   `intent_drafts_v1` rows (deduped by intent_hash) — a restarted process
   reports stored drafts honestly. Pinned.
3. `validate_intent` max_positions used memory-only `_open_records()`:
   new `_open_count()` takes max(memory, durable nonterminal) — a fresh
   process without recover still refuses over-limit entry, never
   undercounts; no double-count after recover. Pinned.
4. `/sessions` ET-edge: prefix-valid but ET-unparseable stamps (or a mix)
   now disclose `overnight True / ny_date None` instead of silently keeping
   the prior day. Pinned via direct ZZU seed.
5. Producer restart OOO: `_last_at` high-water seeds from
   `MAX(at_ts)` per ticker on first encounter — a restarted producer flags
   late observations instead of resetting the sequence. Pinned.

Verification (exact head, Python 3.14.6 disclosed, backend CWD):
new `test_r17_hardening.py` **6 passed**; adjacent
(r17 reads 9 + inventory 5 + hardening 6 + wiring 8 + lifecycle 42) **70
passed**; full `tests/solstice/` **624 passed**; `ruff` touched clean;
`generate_api_docs.py --check` **380 paths current** (service-only fixes,
no regen needed).

- Activation state: OFF. No flags/orders/services/credentials/paid calls.
  Zed's `ef911f37` already merges `044ca009` verbatim + consumer-only files;
  this pass adds a new lane head requiring Zed re-composition before the
  combined acceptance.
- Next exact action: commit + push lane only (no merge/deploy/activate);
  Zed re-composes at the new head; Nav merge decision on
  PR103/PR104/PR101/PR100 + PR93 docs. True externals unchanged.

## 25. Execution-controls pass (3 Oct 2026 — Zed residual controls)

Zed's pass-3 receipt keeps commissioning HOLD on Spark-owned controls:
complete 14–60 analytical projection + authenticated/default-deny
account-wide approval, risk, ownership, protection, recovery. Delivered as
additive, default-deny, fixture-proven service truth (no live calls, no
venue-flag change, no new route, no server.py edit):

1. `range_map` on `/expiries` (additive): sorted admitted expiries/DTEs,
   min/max admitted DTE, `complete` (true when uncapped or both edges
   observed) else `LISTING_CAPPED_WINDOW_MAY_EXTEND`. Existing
   `expiries/coverage` fields byte-identical in shape; openapi regen is
   description-only (380 paths).
2. Account-wide policy registry (`account-policy.v1`, single active row,
   memory + durable): `set/get/clear_account_policy` (operator required);
   `validate_intent` enforces stored ceilings (quantity/notional/positions/
   allowed products) in addition to per-call ctx — ctx narrows, never widens.
   Absent stays UNSET.
3. Stored + revocable approvals: `store_approval` (shape-validated, operator
   required, memory + durable `approvals_v1`), `revoke_approval`,
   `verify_approval` fails closed on mismatch/expiry/scope AND revocation
   (memory or durable). `submit(require_approval=True)` inherits revocation
   enforcement; `supersede` pre-validates gates before any cancel (§24).
4. Recovery-before-entry: `submit` refuses `RECOVERY_REQUIRED` when the
   registry is empty but durable nonterminal rows exist — production flow is
   `recover_open()` + `reconcile_all()` first. Pinned.
5. Native protection truth: `NATIVE_PROTECTION_MATRIX` + `native_protection_support()`
   (conservative: all current combinations report unsupported/
   unverified-native-support, never offered). `lifecycle_inventory` reports
   `approvals` counts, `protection.native_support`, `policy` set-state and
   the RECOVERY_REQUIRED boundary — counts only, no secrets.
6. Fixture `r15/evidence/execution_controls_v1.json` (`execution-controls.v1`)
   for Zed's consumer lane.

Verification (exact head, Python 3.14.6 disclosed, backend CWD):
`test_r17_hardening.py` **12 passed** (6 §24 + 6 new); adjacent
(r17 9 + inventory 5 + hardening 12 + wiring 8 + lifecycle 42) **76 passed**;
full `tests/solstice/` **630 passed**; `ruff` touched clean;
`generate_api_docs.py --check` **380 paths current** after description-only
regen.

- Activation state: OFF. No flags/orders/services/credentials/paid calls.
  No Zed-owned file touched. This head supersedes `c10361ac`; Zed
  re-composes the combined candidate here.
- Next exact action per Nav "merge commit everything": publish a combined
  review-only candidate (main + Spark lane + Zed `7ea8cbff`) with exact-head
  evidence; main merge/deploy/activation decisions stay Nav's.
