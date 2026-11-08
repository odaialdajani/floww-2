# FLOWW autonomous operations implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. The owner has requested autonomous execution; proceed through authorized reversible work and keep external sign-in or hardware dependencies explicit.

**Goal:** Reduce manual session management while producing verified FLOWW research, isolated coding changes and reconciled paper results.

**Architecture:** Reuse Hermes' durable task graph and isolated profiles with a deterministic admission/evidence layer. OpenCode gets scoped coding work; an independent model-free observer detects stale service/task evidence. Liquid Paper is a separately authenticated venue adapter, never a shortcut from a research answer to a real order.

**Tech stack:** Existing Hermes/OpenCode; NVIDIA NIM MiniMax M3.1 Flash; Python standard library; macOS launchd; existing FLOWW backend and tests.

**Spec:** [AUTONOMY-SPEC.md](../../operations/AUTONOMY-SPEC.md).

## Global constraints

- Canonical source `/Users/nav/Documents/GitHub/floww-2`; one integration writer. Preserve protected product lanes, existing dirty files and recovery service `8000`.
- No live trading, paid fallback, model-rate-limit evasion, personal Muse context import or automatic notifications from recovered schedules.
- Local-only task completion is not acceptance. Unknown/stale evidence blocks execution; no arbitrary command endpoint or self-modified permissions.
- Local runtime persists across process restarts and login while the Mac is available; no cloud uptime claim or new sleep blocker.

## Review focus

1. Host is alive but source is stale or worker makes no substantive progress: surface explicit stale identity/evidence rather than green acceptance.
2. Process overlap/crash: one lease, atomic writes, durable task IDs and no duplicate external submission.
3. Hidden native tools, fallback models or personal context: attest final tool schemas and effective model routes before dispatch.
4. Incomplete/stale/zero quote evidence or mismatched venue instrument: refuse fills and preserve the exact reason.
5. Ambiguous submission, unresolved exit, expired mode or pause during execution: reconcile first; no new entries or blind replay.

## Task 1 — Install a bounded independent observer

**Files:** `ops/watchdog.py`, `ops/tests/test_watchdog.py`, `ops/README.md`, launchd template under `ops/`.

**Interface:** `check` returns a timestamped availability/identity receipt; `status` reads it with age; `pause`/`resume` affect this observer only. Runtime state is outside Git under `~/Library/Application Support/FLOWW/operations`.

- [x] Test fixed GET routing, no redirects/proxies, response and deadline limits, malformed and partial response handling, full/short revision comparison and frontend mismatch.
- [x] Test exclusive lease, atomic status, pause before network, finite retention and stale status.
- [x] Implement these checks without any account/provider/model calls or service mutation.
- [x] Run `/usr/bin/python3 -m unittest discover -s ops/tests -v`; obtain independent read-only review.
- [x] Copy tested observer into its runtime; install a 300-second launchd job without KeepAlive retry storms. Run once, inspect the real receipt and verify original service PIDs.
- [x] Stop/pause test in isolated state; verify installed source/runtime hashes and native launchd execution. Observer committed in `c33c45468`; the next natural five-minute run also passed. A full Mac reboot was not performed.

## Task 2 — Prepare native roles and a durable graph

**Files/state:** private fresh Hermes profiles `floww-research`, `floww-audit`; project/board `floww-operations`; redacted setup receipt in the current evidence folder.

**Interface:** five idempotent blocked cards represent connector attestation, research intake, risk/lease/stop composition, coding worker and prospective acceptance. Their bodies identify inputs, dependencies, evidence and limits.

- [x] Back up exact affected config and SQLite stores using a consistent backup.
- [x] Create fresh profiles without cloning personal tokens, memory, channels or skills. Pin the tested NIM model; disable fallback/MoA and unintended auxiliary routes.
- [x] Prove the final native advertised tool list is empty; include native worker auto-injection in the test. If unproven, keep dispatch blocked.
- [x] Create board/project without switching personal defaults or reviving old controllers. Create deduplicated cards with finite runtime and one-attempt circuit breakers.
- [x] Read back IDs, body hashes, blocked state and active-worker count. No worker or schedule is admitted by creating a card.

Current Task 1 evidence: `/Users/nav/macbook-improvements-20261107/autonomy/watchdog-install/` plus `watchdog-root-tests.txt` and `watchdog-review.md`. The installed launchd job has a verified first healthy sample with matching release identity; original service listeners were unchanged. Task 2 evidence: `autonomy/native-setup/REPORT.md`. Profiles remain held; no board workers were dispatched.

## Task 3 — Admit sanitized research work

- [x] Compile actual saved SPY evidence; preserve stale, missing and unknown clocks. Closed citation/value/unit validation is accepted for retrospective copied facts only.
- [x] Add bounded fixed-route intake, stable observation deduplication, private durable receipts, independent no-tool roles, one POST per role and explicit failure parking.
- [x] Independently repair page-envelope laundering, failed-native acceptance, blocking startup writes and terminal timestamps. Frozen source `78b5d4b6b` accepted; both roles remain held.
- [x] Perform and retain the actual bounded trial: two official POSTs total, no accepted closed JSON. Subsequent offline diagnosis does not identify the original cause. Cost remains unknown.
- [ ] Accept a successful real native pair before installing/scheduling research. No further automatic retry, metadata fetch, thinking-parameter guess or timeout expansion is authorized by a green source test.

Evidence: `/Users/nav/floww-execution-20261107/research/0700/REPORT.md`, its `diagnosis/REPORT.md`, and `reviews/research-2/0700/REVIEW.md` under the same execution root.

## Task 4 — Compose internal execution gates before automation

- [x] Reproduce the original three risk bypasses; preserve their red proof as history, not a standalone release.
- [x] Compose server-only source/confirmation admission with real persisted-policy risk checks before both stage and fill. Missing composition remains denied.
- [x] Require strict positive bid AND ask sizes through supported direct service and runner paths; preserve unknown versus measured zero.
- [x] Add same-account durable execution generation/owner/fence/mode/expiry predicates at Mongo CAS. Supported stop/revoke/takeover acknowledges durable ordering; raw file/callback edits alone are additional preflight checks.
- [x] Preserve immutable funded parent/resolution identity across duplicates, lost acknowledgements, restart, actual valuation and history projection.
- [x] Prepay retained artifact space for exits and eight entry-fill ATTEMPTS. Every new immutable fill parent consumes one attempt, including no-fill/refusal; exact retries do not. No global risk/storage limit was raised.
- [x] Independently close the no-fill retry defect at `dfcae700c`: original failure and 32 independent probes pass. Three actual isolated Mongo CLIs and 12 Mongo write-boundary fault cases pass.
- [x] Root Python 3.12 check: 261 affected paper/lease tests plus 50 subtests pass using isolated test dependencies. The installed app environment was not changed. Hosted/container CI was not run.
- [ ] Commission a real trusted market/calendar/contract/lifecycle/cost adapter and application book before unattended operation. Synthetic factories are not application adapters. No active book, broker flag or venue was activated.

Evidence: `paper/correction-2/REPORT.md`, `reviews/paper-3/0700/REPORT.md`, and `integration/paper-candidate-tests.txt` under `/Users/nav/floww-execution-20261107/`.

## Task 5 — Authenticate and admit Liquid Paper separately

- [x] Complete native OAuth in a fresh held `floww-paper` profile with credentials in its private native store. No personal Muse credentials/history were imported.
- [x] Discover the actual 60-tool catalog. Enable Paper for this dedicated connection and read automation disabled. Preserve the first contradictory portfolio response (`paper=false` after status enabled) and later matching `paper=true` reads.
- [x] Independently accept a current authenticated read-only destination gate and versioned closed venue policy. Preserve the existing simulated position. Order submission is unconditionally denied.
- [ ] Establish server-enforced atomic simulated request/destination binding. The advertised `execute_order` schema has no execution-mode binding; status reads alone do not establish it.
- [ ] Define and verify a separate Liquid instrument/cost/risk policy, durable intent/reconciliation ledger and stop/restart behavior. Internal option sizing is not a perpetual policy.
- [ ] Commission and independently reconcile an explicitly simulated entry/exit only after these gates pass. No orders, closes, resets, deposits, withdrawals or automation policy were submitted.

Evidence: `/Users/nav/floww-execution-20261107/liquid/REPORT.md` and [venue policy](../../operations/LIQUID-PAPER-POLICY.md).

## Task 6 — Add a constrained coding worker

- [x] Verify native v2 deny boundaries, empty MCP/external plugins and exact pinned tool schemas.
- [x] Complete the actual isolated arithmetic canary: two official NIM generations, only the approved file changed, independent AST and six numeric checks passed. Original service `49374` preserved.
- [x] Close six independently reproduced boundaries: canonical ownership, safe file snapshots, full tool catalog, duplicate security headers, replayed release markers and encoding headers. Two correction rounds; final independent GO at `0ec14f561`.
- [x] Integrate reviewable commits and retain offline/native receipts. No extra model calls were used for these corrections.
- [ ] Admit a real product task/dispatcher separately. The fixed arithmetic fixture is not a persistent or general product writer, publication authority or release approval.

Evidence: `coding/0700/REPORT.md`, `coding/0700/correction-2/REPORT.md`, and `reviews/coding-3/0700/REPORT.md` under `/Users/nav/floww-execution-20261107/`.

## Task 7 — Repair retired model jobs deliberately

- [x] Back up/classify all seven model-driven jobs and repair only the four previously accepted reminder model pins. Schedules, payloads, delivery and historical errors were preserved; no replay occurred.
- [x] Review the remaining three jobs and exact skills. `deal-scraper` inherits broad artifact-writing tools; `Dashboard Updates` writes cross-project trackers/notes and has broad delivery; `Morning Briefing` attaches personal context and external delivery. Review receipt: `jobs/review.json` in the current execution root.
- [x] Supply bounded per-job source/effect/delivery contracts and no-delivery fixtures; `ops/legacy_job_preview.py` passes five checks on Python 3.9/3.12. Native source authentication and restoring inference remain open. They remain enabled with retired pins, unchanged; they are not described as paused or repaired.
- [ ] Observe a successful natural run before claiming delivery. Never replay missed external actions.
- [x] Preserve Muse personal work and original personal/deal/medical history and credentials.

## Task 8 — Operate and measure

- [x] Add and independently review a model-free consolidated receipt. It reads only fixed private review metadata and observer status; all action capabilities are false.
- [x] Install the hash-verified collector with a 300-second launchd interval, no KeepAlive, no RunAtLoad and no notifications. Manual and natural native runs publish expected blocked state; no worker or order is admitted.
- [x] Show source/native/runtime scopes, last-review ages, refusal codes and nullable metrics. Unknown cost and ledger state stay unknown; stale evidence becomes unknown.
- [x] Preserve confirmed failures as scoped regression checks. Permission/risk/model-budget changes remain separate reviewed changes.
- [ ] Collect empirical accepted-output/intervention/cost/rollback measurements. The fields exist; unknown measurements are not fabricated.
- [ ] Complete the frozen research and prospective paper gates over actual future sessions, including losses, exclusions, zero-trade days and unresolved exits. Source tests do not prove an edge.

Evidence: `/Users/nav/floww-execution-20261107/status/0700/` and the installed private `~/Library/Application Support/FLOWW/operations/operations-status.json`.

## Current completion limits

The guarded SDK research helper remains parked. The later user-authorized Desktop investigation is a separate native workflow; see the continuation below. Real internal source admission, atomic Liquid Paper binding, a separate venue policy/ledger, broader coding dispatch, three legacy job contracts, future market sessions and full historical acceptance remain open. Time Machine still has no writable supported destination. The user's later terminal handoff reported all 25 hooks trusted, including Ralph; this continuation changed no trust settings and did not bypass the earlier Computer Use denial.

The paired premium app remains release `3948b9c715c687ad89839ed884040c7dc7e8cced` on 3000/8213. These operations and unmounted internal-paper changes do not claim a new application release. Original 8000, active stores, rollback releases and the 450-row history queue remain retained. Full execution receipt: `/Users/nav/floww-execution-20261107/REPORT.md`.

## November 7 continuation evidence

Current receipt: `/Users/nav/floww-continuation-20261107/REPORT.md`.

- Task 3: minimal deterministic copied-fact view, durable shared daily four-pair
  prepayment/circuit and all offline/rejection diagnostics independently accepted.
  New two-request trial has explicit ReadTimeout evidence, no accepted facts;
  circuit parked, trial paused, no collector installation.
- Task 4: bounded stored Public adapter, exact owner/source intent and stage/fill
  lineage, external-access-disabled reader, strict missing/zero handling and
  fresh signed fill selection independently accepted as source only. A complete
  synthetic roundtrip passes. Production authority/units/lifecycle/costs/marks
  and application book wiring remain uncommissioned.
- Task 6: one actual product task admitted through an ID-consumption ledger and
  immutable external checker. Model-produced receipt edit passes 772 checks and
  equals the root fix. Whole native completion still fails its deadline; the
  general dispatcher remains open. Both live admissions stay consumed.
- Task 7: local no-delivery contracts/fixtures delivered. Original broad jobs
  remain unchanged; authenticated native readers and natural delivery unverified.
- Task 8: receipt prioritizes precise prerequisites, all capabilities false.
  Combined check is 203 operations tests + 323 paper/lease/source tests + 50
  subtests. No hosted CI or whole-app suite is claimed in this continuation.

Independent rejections and their reproductions remain in `reviews/`; corrections
are permanent regression tests, not rewritten history. No actual orders or
profitability results were produced. The 450 historical rows are retained and
are not blanket accepted. Time Machine lacks a writable destination. The earlier
Ralph warning is historical; the later handoff reported trust complete.

## November 7 late native Desktop continuation

Evidence root: `/Users/nav/floww-heatmap-agents-20261107/`.

- The actual working Hermes Desktop was used with NVIDIA MiniMax M3.1 Flash.
  It inspected the served FLOWW browser and produced a retained-SPY report,
  distinguishing the different current-request snapshot. Record its final
  native status and independent content verdict separately from file creation.
- The closed retained task now rejects arbitrary investigator rationales before
  auditor construction. Stream refusals are permanent through conflicting
  terminal events; the later signal-origin patch preserves a marker through SDK
  error translation. Frozen independent reviews accepted the exact changes.
  The earlier HTTP200/incomplete-stream trial remains failed, with cause unknown,
  two consumed pair IDs, no audit request and no reset of its parked circuit.
- A fresh canonical native audit draft was actually attested with zero tools,
  explicit NVIDIA/MiniMax, one turn and profile-following off. Empty toolsets
  alone did not exclude MCP; the supported exclusion and actual catalog check
  did. One turn remains distinct from one HTTP request and SSE stop/DONE proof.
- The new deterministic stored-event monitor passed 53 focused checks and 18
  independent probes. Root installed its reviewed copies and commissioned only
  native `--no-agent` job `eaa6e27b396c`: five-minute cadence, 96 checks, local,
  no catch-up. Its first natural run completed at 23:00:47 New York. Existing
  role stops/control/circuit remain authoritative; recurring inference, event
  consumption/shared reservation and fresh heatmap coverage remain open.
- AskFlow chart binding was independently reviewed and integrated. All 2,910
  frontend tests passed; production and isolated fixture builds passed. Both
  layouts, saved/missing scope and a changed selected UTC cursor passed the
  compiled browser fixture. The product-only release `4a6cb4944` is live with
  the same backend tree as `3948b9c71`; all 35 served files match. Live Stock
  loaded 70 candles in both layouts and refused its genuinely missing saved
  scope. Market raw/adjusted axes were visually aligned in Chrome Guest.
- Closed backup and disposable recovery verified all six stores and all 15
  original journal observations inside the current 45. The generated 2.50 GiB
  restore-test data copy was removed only after rehashing the retained 13-file
  closed backup. Actual available space increased by 2,684,764,160 bytes.
  Receipts, original proof, backup, live stores and rollback remain retained.
- The nine-page Skylit review maps ten checks to exact retained evidence.
  It does not establish proprietary-model equivalence or a profitable signal.
  The native Liquid Computer supports execution, but its reviewed perpetual
  mutations still lack verified atomic simulated-destination binding. No venue
  order or policy mutation was submitted.
- OpenBot was cloned and reviewed without installing/deploying its stack. The
  observed Nous account had no instance/balance and required funding. No paid
  cloud worker was created. Local native scheduling requires this Mac/gateway;
  hosted inference does not confer cloud process uptime.

See [native operations](../../operations/HERMES-DESKTOP-OPERATIONS.md) and
[monitor contract](../../operations/NATIVE-MONITOR.md). Remaining gates retain
their exact owners and evidence; neither the 450-row queue nor prospective
profitability is marked complete by this continuation.
