---
name: sweep
description: "Find, fix, and check code issues in one chosen FLOWW2 area when the user asks for $sweep or /sweep. Use --scan-only to report issues without changing code."
---

# FLOWW2 scoped sweep

Scan one chosen area of FLOWW2, fix confirmed issues within the authorized scope, then try to disprove the fixes. This command does not start a sweep merely because someone asks about installing it. `--scan-only` ends after findings and changes no code.

## Choose the target

- An explicit target after `$sweep` or `/sweep` is the scope. Resolve its actual files before starting.
- Without a target, including a bare `--scan-only`, ask: "What should I sweep?" Use the available choice dialog:
  - **Changed work (Recommended)** — "Check your latest edits." Include changed, staged and untracked `.py`, `.js` and `.jsx` code under `backend/` and `frontend/src/`; apply all exclusions below.
  - **Files or an area** — "Check the part you name." Accept a named target and resolve it to concrete files.
  - **A recent change** — "Check one saved set of edits." Inspect `git log --oneline -8`, ask which commit, and filter its diff to project source.

Include direct callers and occurrences of the same pattern only within allowed project source. Do not silently broaden to the whole repository. Empty scope means report that there is nothing to check and stop. A whole-app sweep requires the user to name that scope explicitly; it still follows all exclusions.

## Read current project rules

Read root `AGENTS.md`, `CLAUDE.md`, and applicable nested `AGENTS.md` files. Consult `.planning/AGENT_CONTRACT.md` for local constraints, with higher-priority instructions and current owner rules taking precedence. Its historical process, interpreter, order-path and test claims need current verification. Read only the relevant accepted decision in `docs/adr/` when touching calculation policy, model promotion, provider routing, backtests, access controls or test expectations.

Confirm the repository root with `git rev-parse --show-toplevel` and inspect `git status --short` before editing. On this machine the intended tree is `C:/Users/DARK HERO/Desktop/FLOWW2.0`. Preserve existing edits and untracked files. Other work outside the assigned scope is left alone; it does not authorize unrelated changes.

## Allowed and protected scope

Project source: `backend/`, `frontend/src/`, `qc/`, `scripts/`, `deploy/`, `.github/workflows/` and `rust/decoder-core/`. Inspect current versions and actual callers; do not reuse old file counts or assume React, Python or Cargo versions from another project.

Never scan, edit or send helpers into `data/github-repos/`, the stale parallel `app/`, dependency folders (`backend/.venv/`, `backend/.venv313/`, `frontend/node_modules/` and other local environments), model artifacts (`backend/models/`, top-level `models/`, `project_oracle/models/`), saved data, caches, reports, screenshots, lockfiles or old agent prompt packs. Their bundled rules do not govern this project. Documentation may be read for an applicable decision; edit it only when an authorized code fix makes it inaccurate.

Flag protected-file issues, but edit only with the explicit permission or task-specific waiver required by current owner rules: `backend/services/ml/inference.py`, `backend/services/dash_ui.py`, `backend/tests/conftest.py`, model artifacts, `frontend/.env`, `frontend/package.json`, `frontend/craco.config.js` and `frontend/src/App.js`. Historical waivers are not blanket permission. Continue independent allowed work while a protected change awaits a decision.

## Find issues using evidence

Use focused searches and actual callers. For relevant code relationships, use CodeGraph or graphify only when the corresponding index already exists. Do not create or rebuild an index for a sweep.

For a large target, use available collaboration tools with `explorer` agents, one per independent area, within the available concurrency limit. Small targets can be checked directly. This command explicitly authorizes this delegation when invoked. Give every helper the exact scope, exclusions, relevant owner rules and current diff. Require each finding to include a source location, literal snippet and a reproducible failure or concrete explanation of the failing input.

Look for:

- Wrong displayed calculations, missing values turned into zero, stale data labeled fresh, invented historical observations, expiry/time/unit mismatches, lost saved state, unreachable controls and misleading success states.
- Blocking work in asynchronous requests, unawaited work, unbounded reads or caches, repeated remote calls, unnecessary model loads and avoidable option-chain or rendering work. Confirm independence and provider pacing before recommending parallel requests.
- Query interpolation, unsafe inputs, secret exposure, silent exceptions, shared-state races and reconnect failures. A provider account lock is an external failure to handle; verify it before blaming code.
- Effect/fetch loops, missing abort/cleanup, excessive shared subscriptions and errors visible only in the browser console. Check the installed frontend version and actual component behavior.
- Repeated logic, unused code and real lint violations. Inspect current lint settings and accepted prior sweep decisions before labeling an intentional design a defect.

Rank by consequence: high for wrong trader numbers, corruption, silent loss, crashes, security or weakened order safeguards; medium for degraded behavior on empty data, missing providers, reconnects or load; low for bounded cleanup. Do not inflate a stylistic preference into a bug.

Preserve the separate display and model-feature GEX scales and locked model constants described in `CLAUDE.md`. Unifying them requires an approved migration and retraining plan. Do not add frontend lint/build settings or change frozen configuration as incidental cleanup.

## Fix and challenge

Deduplicate confirmed findings. Fix bugs and safety faults first, then consequential speed issues, repeated work and bounded cleanup. `--scan-only` stops here with a report and applies no fixes.

When delegating fixes, use `worker` agents with explicit file ownership. Tell them they are not alone in the codebase, must preserve other edits, and must accommodate concurrent changes. Do not expand their scope.

Before deleting unused code, check references across allowed project code, route registrations, tests, scripts, the roadmap, relevant approved plans and future-use comments. Keep code that has callers or planned use. Add a meaningful failing regression check for behavior changes, reproduce the failure, apply the fix, then confirm that the check passes. Never weaken, skip or mark a previously passing test as expected to fail.

Have a fresh `explorer` review each consequential fix to disprove correctness, completeness and missed related occurrences. If delegation is unavailable, do a separate fresh pass with that sole goal and report the limitation. Recheck the affected behavior after any correction.

## Protect running work and trading data

Keep background Windows commands hidden using the project guidance: Node child_process with an explicit executable, argument array, `windowsHide: true`, piped output, preserved working directory and exit status.

Before editing source, inspect whether an existing job watches the selected files and would reload or restart after a write. If applying a fix would disturb that job, prepare a reviewable patch in temporary storage and leave its live source intact until the owner explicitly authorizes applying it. Do not create another project checkout or change the canonical working tree as a workaround. Do not stop, restart, replace or move an existing FLOWW2, ODZ or Codex job. Before any authorized service launch, inspect current listeners and process identities. The October recovery record names the original service on 8000, the repaired service on 8001 and frontend on 3000; those are dated references. Preserve the original recovery service until every old decision has been exported and the export verified. Do not restart it to load a sweep fix. Use isolated stores and separate ports for authorized review work.

No paper/live orders, trading activation, new account connections or paid feeds are authorized by a sweep. Preserve default-deny order checks and paper hosts. Before touching order-related code, inspect all actual callers and relevant safety tests; never trust an old unreachable-route claim. Keep market-data reads separate from order submission and research answers.

Never read or print ignored secret settings as sweep evidence. Keep credentials out of chat, logs, tracked files, test fixtures and screenshots. Use sanitized configuration examples. Preserve unknown, stale, incomplete and unavailable states and original observation times. Never invent missing historical nodes or claim trading value from successful tests.

## Validate the affected work

Match checks to what changed. Do not run the entire app suite for a documentation-only edit. For broad changes or release preparation, read the actual `.github/workflows/ci.yml` and report any checks not run.

- Backend: inspect intended local interpreters (`backend/.venv313/Scripts/python.exe` and `backend/.venv/Scripts/python.exe`), available test tools, `backend/pytest.ini`, `backend/pyproject.toml`, `Dockerfile.backend` and shipped Python pins. Use a verified interpreter from `backend/` for `python -m pytest <relevant tests>` and `python -m ruff check <changed Python files>`. Check compatibility with the shipped version. Storage-dependent tests require available isolated storage; never use active user records. Do not install or upgrade project tools silently to mask a failed check.
- Frontend: read current `frontend/package.json` scripts. Run targeted `npm test -- --watchAll=false` with `CI=true` set through the hidden launcher, and `npm run build` when relevant. Do not invent a lint script or assume TypeScript.
- Rust: only if `rust/decoder-core/` changed, use its current crate checks from that directory, including `cargo check` and relevant tests. Do not copy Orderflow workspace commands.
- Screen or user-flow changes: exercise the real browser with representative inputs, saved state and failure states. Builds and health responses alone do not prove the flow works. Preserve existing jobs; check safely on isolated review services when required.

Investigate failed checks. Separate confirmed regressions from reproduced existing failures and unavailable prerequisites. Never reuse old test counts, fabricate output, or claim remote checks passed from local runs.

## Report

Keep actual evidence and unresolved findings available in the review output. The chat reply is short plain trader English followed by one `Next:` line. State material failed or unrun checks and protected-file decisions. No commit, push, merge, deployment or sweeping cleanup is authorized unless the user explicitly requests it.
