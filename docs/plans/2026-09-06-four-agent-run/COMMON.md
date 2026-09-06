# Binding worker protocol

Read this entire file plus your lane prompt, QUEUE and INVENTORY before editing. Package root: `/Users/nav/Documents/GitHub/floww/docs/plans/2026-09-06-four-agent-run`.

## Instruction and ownership boundary

The user's protected-main instruction supersedes old CLAUDE/AGENT_CONTRACT direct-main push and subject-grep instructions. No direct push to main, force push, auto-merge, destructive reset/restore/clean, commit --no-verify, or changes to another agent's work. User-authorized isolated worktrees supersede the old literal-path-only rule; verify the same git common directory and intended remote.

Read applicable AGENTS.md, CLAUDE.md, `.planning/AGENT_CONTRACT.md`, `institutional_loop/OWNERSHIP.md`, `institutional_loop/CONTRACTS.md` and current lane ledgers. Some contain stale rules or credential-looking text: inspect carefully, never copy secret values to evidence. Do not treat old task completion claims or old permissions as current receipts.

Default frozen: `backend/services/ml/inference.py`, `backend/services/dash_ui.py`, `backend/tests/conftest.py`, model artifacts under backend/models, frontend `.env`, package.json, craco.config.js and src/App.js. Existing surgical waivers apply only to their stated scope, never blanket permission. Preserve GEX feature/display scales and model-locked constants.

Institutional ownership overlaps the new lanes. The coordinator must record incumbent release and an exact task file lease before product edits. Never claim a wildcard by yourself. A method-region lease is insufficient for concurrent edits to the same file. Treat `server.py`, `flowseeker.py`, `scanLogic.js`, shared contracts/ledger and root docs as whole-file serialized resources. Pending lease does not prevent read-only offline discovery.

## Preflight

1. Verify cwd, branch, git common dir, remote, clean status, current HEAD and origin/main. Never switch the canonical shared checkout. Record foreign changes; do not stash or repair them.
2. Read coordinator state: `admitted_task`, exact `allowed_files`, base SHA, incumbent release, run deadline, runtime and live-probe lease. No task means read-only inventory, not self-assigning GitHub work.
3. Provision private dependencies at the worktree's pinned versions using verified repository install instructions and intended interpreter. No shared venv installs/symlinked mutable node_modules. Do not copy `.env` into artifacts. Do not start server.py until scheduled jobs, bot hooks, databases and provider transport are isolated.
4. Run relevant baseline at the clean base, capturing command, interpreter/node version, exit, counts and duration. Record inherited skips/xfails. A dependency/setup failure is a preflight blocker; it is not an application regression.
5. Use existing suitable skills: systematic-debugging for failures; TDD for behavioral changes; verification-before-completion before claims; code-review for independent review; frontend/React skills for UI work; GSD spec for unsolved product contracts. Read skills before applying them. Do not invoke every unrelated installed skill. Installed GSD names are `gsd-loop-spec/build/review/schedule`, not assumed historical `gsd-execute-phase` names.

## Per-task loop

1. **Progress:** re-read current task and new merges/lease updates. Check if the requested outcome already landed by ancestry AND content/behavior. SHA inequality is not proof a fix is absent after cherry-pick/squash.
2. **Contract:** record Why; O-1… outcomes; X-1… exclusions; exact code pointers; testing notes; manual walkthrough. Unspecified externally visible behavior is a decision, not permission to guess. Small task, independently reviewable result.
3. **Plan:** name the concrete failing behavior or audit claim, test inputs/assertions, likely files, relevant suite and acceptance proof. Avoid broad “harden everything” work.
4. **Execute:** behavior change = regression test first; run and capture meaningful red, patch minimally, green. A test failing from bad imports/fixtures is not a valid behavioral red. A verification task may pass immediately. Preserve legitimate failing audit tests/evidence; don't delete them merely because CI would fail.
5. **Verify:** targeted tests and Ruff on changed backend paths; relevant integration tests. Frontend uses `npx craco test --watchAll=false` and build when UI/build behavior changes, with bounded worker count for the host. Dependency/middleware change requires full backend tests before handoff. Capture pipeline exit statuses faithfully. Do not repeatedly rerun full suites without new changes or uncertainty.
6. **Review:** inspect full diff, no secrets/out-of-lane paths; request independent spec review then quality review. Reproduce each REWORK finding. Three distinct failed repair attempts on one item → evidence + handoff, choose another eligible task. Do not erase others' work to undo a fix.
7. **Commit:** one coherent task commit with explicit `git add <paths>` only; real commands/results in body. No commit for an empty audit, repeated HEAD stamping or elapsed-time filler. Keep unfinished work checkpointed rather than forcing a commit.
8. **Branch/PR:** each admitted independent task gets a coordinator-approved task branch from fresh main; preserve run branch/worktree identity in state. Never combine unrelated tasks into an unreviewable growing branch. Explicit push `git push -u origin HEAD:<task-branch>`; verify remote branch SHA equals local SHA. For actual GSD issues, obey human ready/claim/linkage gates. Otherwise deliver a local reviewable patch until publication is authorized. This planning package itself does not file/comment on GitHub.
9. **Checkpoint:** record outcome, proof, SHA, review status, remaining blockers and next task. Ask coordinator for next admission; keep doing allowed independent investigation between assignments. Never start an unleased implementation because another agent is slow.

## Runtime/provider discipline

- Tests use fake providers and isolated storage by default. TestClient is in-process integration, not a live deployment. A GET can trigger paid upstream calls, scheduled work, or cache writes.
- Coordinator is the sole live probe dispatcher. Reuse sanitized recorded payloads; limit each admitted live question to the smallest useful read. Track request intent, estimated fan-out, actual observed calls and result. Unknown spend/entitlement means offline verification until established; do not exhaust budget to manufacture a 503.
- Never invoke live order POST/DELETE, bot/webhook messages, account controls or genuine paper transactions. Mock those paths. Do not claim Sync-2/human witness from mocks.
- Inspect actual routes/OpenAPI/signatures before curl. Scanner uses slice_size/max_expiries, not ticker. Pick symbol/strike/expiry from an authorized returned payload; no stale hard-coded strikes/dates. Preserve valid zero-DTE.
- Missing/stale/unknown data must remain explicit under each actual contract. Avoid NaN/Infinity; do not replace all unknown values with zero. Rate tokens are not dollars. Scientific proxies are not measured tick truth.
- :8000/:3000 and existing bots belong to incumbent lanes. No kill/restart. On isolated ports verify PID/cwd/head and prevent startup jobs from sharing live DB/quota. If provenance cannot be proved, record NOT VERIFIED.

## Four-hour progress and continuation

Coordinator sets each lane's own UTC start and deadline once its admission preflight is ready. Working budget is four hours per lane, not minimum 40 iterations. A staggered start never inherits another lane's earlier deadline; supervisor end time may therefore be later. Checkpoint after each task and at least every 15 minutes of meaningful work; send concise user-visible progress during long operations. A heartbeat contains an artifact/command/result, not just “working.”

States: DISCOVERY → READY → ACTIVE → REVIEW → ACCEPTED; alternate BLOCKED, REWORK, VERIFIED_EXISTING, DEFERRED. ACCEPTED is reviewed candidate, not merged. Separately record branch/PR/merged/deployed stages.

Only the coordinator writes `run-state.json` at package root. Each worker writes its own external runtime checkpoint under `/Users/nav/Documents/GitHub/floww-run-state/2026-09-06/<lane>/` and can read others' published receipts. Shared state is not a distributed lock. Coordinator admissions/reassignments are serialized.

Before a context/turn limit: checkpoint task ID, full SHAs, dirty own paths, last exact command/result, unresolved failure, next executable step, lease state, and remaining deadline. A replacement reads checkpoint, checks actual git state, then resumes. Never restart the four-hour clock or redo proven work just because context reset.

If all ready work is exhausted, perform the next unverified reserve audit once. If nothing eligible remains, report IDLE/BLOCKED with missing artifact and owner. No spin loops, hash-chasing, fabricated defects, endless full-suite reruns or arbitrary coverage targets. User stop requests always win.

Receipt template:

```text
task_id:
lane:
classification: gap | hypothesis | verify
state:
base_sha:
head_sha:
worktree:
allowed_files:
changed_files:
O-N evidence: command / exit / assertions / artifact / time
X-N preserved: diff or regression evidence
test_environment:
baseline_failures:
new_failures:
live_proof: NOT RUN | VERIFIED (runtime provenance + redacted result)
provider_calls:
review_verdict:
branch_or_pr:
merge_state: NOT MERGED | merged SHA with receipt
blocker_owner_and_artifact:
next_step:
deadline_utc:
```
