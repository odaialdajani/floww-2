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

**Files to create:** `ops/research_intake.py`, `ops/tests/test_research_intake.py`; task contract under `docs/operations/`.

**Interface:** `compile_snapshot(saved_input, decision_time)` returns a bounded versioned observation packet; `validate_research(packet, response)` returns accepted evidence fields or precise refusal codes. A model output is always `review_only` and `executable=false`.

- [x] Added meaningful input/citation/refusal tests. Independent review reproduced extras-only-clock and timezone-overflow defects; regressions and fixes pass. Current operations suite: 58 tests on Python 3.9.6, including 32 intake cases.
- [x] Built pure intake from the actual saved-observation endpoint shape; three retained SPY rows compile with stale/unknown clocks and no execution admission. No scanner refresh, alert-processing route or auto-clone/auto-port job ran.
- [ ] Give no-tool research and audit sessions separate packets, pinned model, finite input/output/time budgets and no automatic fallback. Record actual call outcome/usage; unavailable quota parks work.
- [x] Deterministically validate IDs, copied numeric fields, units and citations in a closed facts-only envelope. Independent code review and actual saved-data receipt passed; fabricated numeric values and confidence are refused. This does not claim native narrative/model research acceptance.
- [ ] Promote only this card when source, tests, native tool envelope and observed outputs pass; retain all raw evidence outside active context.

## Task 4 — Compose internal execution gates before automation

**Files to inspect/change only after caller review:** `backend/services/agent/paper/runner.py`, `risk.py`, `execution.py`, `guarded_repository.py`, `service.py`, `observation_service.py`, `risk_assessment.py` and `backend/services/execution_lease.py`, plus their exact callers/tests. Preserve the separate mounted Public and Alpaca account gates.

**Interface:** trusted policy/observation admission must precede BOTH order staging and filling; the persistent book/lease/stop status governs restart admission.

- [x] Reproduced three stage/fill risk bypasses in an isolated worktree, with 100 other tests and 50 subtests passing. Proof-only branch commit `4f86311ce` is intentionally red and must not merge. Production order modules are unchanged; trusted evidence-reader and funded assessment/commit recovery contracts remain required.
- [ ] Reject stale/missing/zero-size quotes, caller-supplied equity, reused side events and missing trusted policy before every write.
- [ ] Complete one simulated entry/exit/cash reconciliation, restart with an unresolved exit and verify entries stay blocked.
- [ ] Exercise duplicate fills, concurrent owners, lost lease, shutdown, pause and cash/P&L arithmetic independently.
- [ ] Run affected backend suites, independent accounting review and rollback proof. Keep separate from the real account routes and current active stores.

## Task 5 — Authenticate and admit Liquid Paper separately

**Files to create after tool discovery:** `ops/liquid_paper_adapter.py`, `ops/tests/test_liquid_paper_adapter.py`, versioned venue policy under `docs/operations/`.

**Interface:** `attest_destination()` supplies current simulated account/mode/instrument capability evidence. `submit_paper(intent, attestation)` requires fresh mode evidence, deterministic policy and a persisted idempotency record; an ambiguous result becomes reconciliation-required.

- [ ] Connect the official Computer MCP in a dedicated execution profile; keep OAuth credentials in its native store. Sign-in is an external dependency until observed.
- [ ] Discover actual read/mode/paper order tools. Prove Paper mode and simulated destination; do not infer it from a browser banner or an older Co-Invest review link.
- [ ] Define a separate Liquid instrument/cost/risk policy from verified supported markets. Do not reuse option sizing or map an option ID to a perpetual.
- [ ] Test unknown/live/expired mode, arbitrary destination, unsupported instrument, duplicate request, stop, timeout-after-send and restart before any submission.
- [ ] Execute only the explicitly simulated commissioning case, reconcile entry/exit/balance and independently audit the venue ledger. Leave any unsupported capability blocked and named.

## Task 6 — Add a constrained coding worker

**Files to create:** reviewed OpenCode v2 agent/config template under `ops/templates/`, task contract and `ops/tests/test_coding_admission.py`.

**Interface:** a task declares base SHA, allowed paths, isolated checkout, acceptance commands and an artifact/commit output. Admission rejects dirty/in-use destinations and unproven permission schemas.

- [x] Tested installed OpenCode 2.2.5 in a credential-free private sandbox: native parser accepted one deny-all agent, no MCP/external plugins; native permission checks refused ten operation classes despite a permissive session overlay. This is a deny-all admission canary, not an active coding worker. Native NIM/tool/output/retry commissioning remains below.
- [ ] Deny account/order/credential tools, outside-workspace writes, arbitrary MCP tools, publication and service control. Verify an attempted out-of-scope operation is refused.
- [ ] Run one bounded canary change in an isolated fixture repo. Require actual tests and changed-path comparison, then a fresh reviewer.
- [ ] Cap corrections at three and return only the failing unit. Create a reviewable commit; use the existing managed updater only after product checks and rollback proof.

## Task 7 — Repair the retired model jobs deliberately

**State:** the seven enabled model-driven GLM jobs listed in `native-capabilities.md`; the eighth obsolete label is on a healthy `no_agent` script.

- [x] Preserved consistent before state and classified all seven model-driven jobs without executing their prompts/scripts or sending a message.
- [x] Replace only the retired model field in the four classified reminder jobs through supported scheduling APIs. Field diffs show provider, schedule, payload, destination, next fire, enabled state and historical errors unchanged; no execution or replay occurred. Receipt: `/Users/nav/macbook-improvements-20261107/autonomy/reminder-model-repair/receipt.json`.
- [ ] Review source/artifact effects before repairing `deal-scraper` and `Dashboard Updates`; review external delivery/session/skill scope before `Morning Briefing`. These three remain enabled and unchanged, not paused. Do not treat a repaired pin as delivery proof.
- [ ] Do not replay missed external actions. Test a no-delivery fixture; observe the next natural run before claiming repair.
- [ ] Keep Muse personal work separate; migrate no personal history into FLOWW.

## Task 8 — Operate and measure

- [ ] Daily local receipt: admitted/active/blocked tasks, last substantive progress, accepted tests, refused evidence, unresolved paper positions, costs and next required action.
- [ ] Track accepted output per intervention/cost, first-pass acceptance, repeat failures and rollback frequency. More parallel sessions is not the target metric.
- [ ] Only accepted, independently checked failures may propose a permanent constraint/test; permission/risk/budget changes require a separate reviewed change.
- [ ] Run the frozen research and prospective paper gates from the spec over actual future sessions. Publish losses, exclusions and zero-trade days beside gains.

## External dependencies and completion limits

Liquid OAuth and simulated-destination tooling; a writable Time Machine destination; future market sessions; native worker/tool and coding permission commissioning. Firewall is now enabled and verified through native settings. Full historical row acceptance and profitability remain open. The implementation receipt records which boxes actually passed; this plan is not evidence that unchecked tasks ran.
