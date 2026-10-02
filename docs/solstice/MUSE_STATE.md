# MUSE_STATE — Spark Muse 1.3 post-R14 closeout lane (complementary to Zed)

Owner: Spark (Muse Spark 1.3). Zed owns frontend design/components/styles/mounts,
visual acceptance, and its active Lodestar/Public integration files.
Coordination mechanism: this file + `docs/solstice/ZED_STATE.md` + existing
kanban/watchdog files. No new task platform created.

## 1. Reconciliation (2 Oct 2026, first session)

- Remote `origin/main`: `1530ccd7f52a0de03512f383283463525a44134b` (PR92 merge,
  2026-10-02T03:12:24Z). Matches harness baseline exactly.
- Candidate ancestry preserved: `2bc1f03e` is the merge's first-parent-side head;
  `HEAD..origin/main` from the stale checkout showed exactly the 10 PR91+PR92
  commits, zero surprises. No new commits since `1530ccd7` (`git fetch` clean).
- Open PRs: none (`gh pr list` empty; PR92 newest, MERGED).
- Worktrees: main checkout `/Users/nav/Documents/GitHub/floww-2`
  (`solstice/r11-opus` @ `9a6c0295`, = PR90 merge, already on main — the
  "ahead 1" is the merge commit itself, no unique unpublished commits);
  `.worktrees/zed-solstice-r13` (`37a7e715`), `.worktrees/zed-solstice-r14`
  (`2bc1f03e` + dirty `ZED_STATE.md` + untracked `.final-acceptance/`);
  `/private/tmp/floww2-head` (detached `9a6c0295`); `/Users/nav/.cline/audit-fixes`;
  `/Users/nav/.worktrees/cmd-c0-20260928070352`. All preserved, none touched.
- Main-checkout dirty files (preserved, NOT mine, never staged):
  `.mcp.json`, `docs/solstice/r12/SPARK_STATE.md` (prior Spark checkpoint),
  `frontend/.gitignore`, `frontend/package-lock.json`, `frontend/package.json`,
  `frontend/yarn.lock` (Zed frontend lane), `kanban/BOTTLENECK_ALERTS.md`
  (watchdog-owned), untracked `.worktrees/`, `frontend/.storybook/`,
  `SolsticeStatusStrip.stories.jsx`, `vitest.config.mjs` (Zed storybook work).
- My lane: branch `solstice/spark-closeout` from exact `origin/main`,
  worktree `.worktrees/spark-closeout`. Clean except this file when committed.
- PR92 receipt read (PR body + 6 commits + file list). `ZED_STATE.md` on main
  holds pre-merge PENDING language superseded by the merged receipt; the old
  queue is NOT reopened. Protected manifest: `docs/solstice/r11/PROTECTED_MANIFEST.txt`
  (71 paths). TideHunterPro/Tide/Flowseeker read-only (crontab line observed only).

## 2. Accepted path ownership (Spark)

- OWN (edit): `docs/solstice/MUSE_STATE.md` (this file); new closeout notes under
  `docs/solstice/` prefixed `SPARK_`; backend operational/research closeout
  modules ONLY where a proven gap exists + their focused tests.
- READ-ONLY (verify against, never edit without handoff): `docs/solstice/COMMISSION.md`,
  `COMMISSIONING_PACKAGE.md`, `RUN_STATE.md`, `ZED_STATE.md`, `r12/SPARK_STATE.md`,
  `r11/PROTECTED_MANIFEST.txt`, all `frontend/` + Zed worktree files,
  `kanban/BOTTLENECK_ALERTS.md`, `.mcp.json`, TideHunterPro/Tide/Flowseeker,
  frozen model artifacts and CLAUDE.md-forbidden files.
- BLOCKED on ownership (work elsewhere until handed over): any edit to
  COMMISSIONING_PACKAGE/COMMISSION/RUN_STATE (Zed-touched in PR92, sole-owner
  lane); any shared schema/route/registry change (coordinate with Zed first).

## 3. Queue ledger (requirement → producer → consumer/storage → evidence → status)

- PR89–92 engineering queue (exposure/replay admission, contracts, windows,
  VEX/Charm envelopes, review/outcome paths) → producers/recorders/projections
  on main → mounted drawer/context + stored records → PR92 receipt: main
  CI/CD36959134781 + lint36959134795 SUCCESS, backend 7070/38 skips, frontend
  121 suites/1035 tests + build, truth 226/0, silent 347 files, API 373 paths,
  protected 71/71 → DONE (inherited; historical results for exact main, not
  re-claimed for this branch).
- M1 closeout docs + operational truth → this file + §4–5 below → read-only
  probes + code inspection at exact head → DONE after this checkpoint commit
  (doc-only; package historical table verified, discrepancies recorded, no
  package edit — ownership with Zed lane).
- M2 durable recorder preflight/recovery → `heatmap_history.py`,
  `recorder_health.py`, `duckdb_engine.py`, existing restart/restore/fallback/
  locking tests → temp-DB dry-run packet → READY (gap check not yet run).
- M3 review→episode→price-path→outcome lineage → `solstice_review.py`,
  `episode_policy.py`, `solstice_labels.py`, `heatmap_history.outcome_close_tick`,
  `routes/solstice.py outcomes/close` → READY (trace not yet run).
- M4 reproducible research prep → existing replay/ablation harness +
  `FROZEN_PROTOCOL.md` + `scripts/r14_fixture.py`/`r14_answer.py` → READY
  (valid-session census not yet run; insufficient-evidence outcome allowed).
- M5 Zed handoff/integration review → field/availability contract + fixture IDs
  for admitted wall/windows/review/outcomes → READY, coordinated (no Zed-owned
  edits; verify producer→record→projection→consumer after Zed publishes diff).
- External (not engineering): SPX entitlement, durable activation/service auth,
  participant study, empirical multi-session validation, data rights →
  BLOCKED (external dependencies; prep scripts/checklists only, no messages,
  no simulated participants, no gate removal).

## 4. M1 operational truth (verified at exact head `1530ccd7`, 2 Oct 2026)

Config-table verification (package §1 vs code — historical table is a
build-time-recording description, NOT an activation recipe):
- Storage path `$DUCKDB_PATH` unset → `:memory:`: CONFIRMED
  (`duckdb_engine._open_shared_db`, `heatmap_history.recorder_status`;
  unusable path falls back to memory, never claims durable).
- Proposed durable path `~/floww-data/solstice.duckdb`: proposal only. `ls`
  shows NO `~/floww-data/`; nothing in code defaults to it.
- `SCHEMA_VERSION = "2"`: CONFIRMED (`heatmap_history.py:27`; additive
  `ADD COLUMN IF NOT EXISTS` migrations; `heatmap_snapshot.SCHEMA_VERSION`
  is a separate envelope version, not the recorder schema).
- `cadence_s=300` manifest default: CONFIRMED (`routes/solstice.py:230`).
- "Enable flag: None yet" reads as the build-piggyback recorder (writes ride
  heatmap builds under the single-writer lock — accurate). Two REAL flags
  exist beside it: `FLOWW_RECORDER_WORKER` (S4 capture loop; NO production
  caller of `register_capture` — only tests — so production state is
  `absent`) and `SOLSTICE_OUTCOME_WORKER` (outcome tick, default-off,
  `server.py:2733` + default-disabled test). Package §1 omits
  `FLOWW_RECORDER_WORKER`; recorded here, package untouched (Zed-owned).
- Request budget: package "10 req/s baseline with headroom" CONFIRMED
  (`public_budget.py:20-21`: 10/s documented, refill 8/s, capacity 60,
  max inflight 4).
- Health schema: package §3 `{durable, mode, tables, latest_snapshot,
  checked_at}` is a SIMPLIFICATION. Actual route returns the full store packet
  (`durable/mode/backing/path/tables/note`) + `latest_snapshot` + `checked_at`
  + a `capture` block (version/worker_state/worker_enabled/interval/
  registered/last_capture/counters/errors/stop_recovery). Superset, not a
  mismatch in behavior; do not treat the package line as the schema.
- Price paths caller-supplied until a scheduled price-path recorder is
  commissioned: CONFIRMED (`outcomes_close` takes `body.paths`;
  `price_paths_v1` + `outcome_close_tick` exist; scheduler tick is the gated
  worker). Episodeless → `NEED_EPISODE` pending, never labeled: CONFIRMED.
  Same-bar dual barrier → `simultaneous_unknown`: CONFIRMED
  (`solstice_labels.py`).

Live observed state (read-only GETs + process/env inspection; nothing started,
restarted, or written by this lane):
- Env (this shell): `DUCKDB_PATH`, `FLOWW_RECORDER_WORKER`,
  `SOLSTICE_OUTCOME_WORKER` all UNSET → defaults: memory, off, off.
- Running backend PID 57475, started 09:55 local, CWD
  `/Users/nav/Documents/GitHub/floww-2/backend` (main checkout,
  pre-PR91/92 tree `9a6c0295` + dirty files — NOT current main; dated
  observation, others' process, untouched).
- Its `/api/health`: healthy (duckdb healthy, public_api healthy/key
  configured, Alpha Vantage disabled/retired, websocket 0 conns, breaker closed).
- Its `/api/solstice/recorder_health`: `durable=false`, `mode/backing=memory`,
  `path=":memory:"`, 30 tables, latest SPY `snap_b0ebb115de4d7071` asof
  2026-10-02T15:41:16Z (fresh in-memory snapshots landing); `capture`:
  `worker_state=absent`, `worker_enabled=false`, `capture_registered=false`,
  all counters 0. No capture worker, no durable store, no activation.
- Tracked data files `backend/data/gflows.duckdb` (1MB) +
  `data/research_kg.duckdb` (23MB) are committed binaries UNRELATED to the
  solstice recorder (which is `:memory:` when `DUCKDB_PATH` unset).
- launchd `com.confluence-decoder` (RunAtLoad, KeepAlive false): loaded, NOT
  running (no PID, last exit 0); points at `.hermes/...start.sh`, workdir main
  checkout. Pre-existing operator machinery, untouched.
- crontab: no solstice capture entry. Only trading-adjacent line is the
  Tidehunter nightly refresh pointing at dead path
  `/Users/nav/Documents/GitHub/floww/backend` (read-only observation, no fix —
  Tidehunter lane is read-only).
- COMMISSION/RUN_STATE dated probes (23–25 Sep 2026, SPY/level-2/OI/Greek-time
  findings, R7/R8 ledgers) retained as HISTORICAL observations; R14 boundary
  notes qualify them (no renewed live acceptance, no reprobe, no orders).

## 5. Remaining capabilities (owner + evidence required)

1. Durable capture/service activation → owner: Nav (authorization) + operator;
   evidence: restart proof (§5 of package) recorded in approval request. NOT DONE.
2. Scheduled price-path recorder → owner: unassigned; evidence: commissioned
   producer + `price_paths_v1` fill + worker close rate. NOT DONE (caller paths only).
3. SPX index-chain entitlement → owner: Nav/vendor support; evidence: vendor
   answer + bounded read-only commissioning check (`SPX_FOLLOWUP.md` draft
   unsent). BLOCKED.
4. Participant/human study → owner: Nav/participants; evidence: identified
   source/fixture/tasks/responses/confidence/consent (selftest 25/25 is
   plumbing only). BLOCKED.
5. Empirical multi-session validation (30–60 sessions) → owner: collection
   process (post-activation); evidence: measured fills/costs, preserved
   censoring, no synthetic profitability. BLOCKED (no valid-session census yet;
   M4 will report insufficient-evidence + runnable protocol if absent).
6. Zed frontend/Lodestar-Public integration + human visual review → owner: Zed/Nav;
   evidence: Zed's published diff + Nav review. Separate lane, verified on read.

Activation state: OFF. No deployment, restart, daemon startup, capture/outcome
worker activation, orders, credential changes, retraining, messages, or paid calls
by this lane. `SOLSTICE_OUTCOME_WORKER`/`FLOWW_RECORDER_WORKER` untouched (unset).

## 6. Assumptions / next action / handoff

- Assumptions: harness baseline SHAs trusted after independent `git fetch` +
  log/diff verification; PR-body CI links taken as published evidence (main CI
  re-inspection deferred to pre-merge gate); running dev server is another
  party's process (observed, not owned).
- Next exact action: commit this file on `solstice/spark-closeout`, push branch
  for review, then M2 gap check (read existing restart/restore/fallback/locking
  tests + R14 readiness evidence before adding anything; temp DBs only).
- Handoff needs: none blocking. Note for Zed: `FLOWW_RECORDER_WORKER` absent in
  production tree (no `register_capture` caller) — only relevant if your lane
  wires a capture path; shared schema/route changes need coordination first.
