# /sweep-wide — Whole-Repo Deep Clean (floww / Confluence Decoder)

The wide cousin of `/sweep`. `/sweep` and `/verify` scan ONE chosen scope; `/sweep-wide` sweeps the
**entire project source tree** — `backend/`, `frontend/src/`, `scripts/`, `qc/`, `deploy/`,
`.github/workflows/`, `rust/decoder-core/` — hunting bugs, hot-path waste, duplication, and law
violations, then fixes them, attacks its own fixes, simplifies, and validates against this repo's own
gates.

Deep and expensive, so it runs as a **Workflow** (loop-until-dry finders → adversarial verify → tiered
fixes). Invoking `/sweep-wide` is the opt-in to that Workflow.

---

## Step 0 — Load the laws (never skip)

Read these three, in this order, and treat them as binding for the whole run:

1. `CLAUDE.md` (repo root) — the project's law file.
2. `.planning/AGENT_CONTRACT.md` — **wins over CLAUDE.md and over your spawn prompt** where they
   conflict, with two carve-outs (both law files were written on a macOS machine):
   - Contract §1 ("the only clone is `/Users/nav/Documents/GitHub/floww`; if `pwd` doesn't end in
     `Documents/GitHub/floww` → STOP and re-cd") is **superseded**. `C:\Users\DARK HERO\Desktop\
     FLOWW2.0` is the working tree. Do not stop.
   - Contract §7 / CLAUDE.md ("always `backend/.venv/bin/python3`") is **superseded**. Use
     `backend/.venv313/Scripts/python.exe`.

   Everything else in the contract still wins.
3. `.planning/STATE.md` + `.planning/ROADMAP.md` — the active GSD phase, so you know what is in
   flight and what is intentionally unfinished.
4. `docs/adr/` — 6 **Accepted** architecture decision records. These are already-litigated rules, not
   suggestions. In particular ADR-0001 (model promotion gates, implemented in
   `backend/services/ml/gate.py`), ADR-0002 (data-source policy behind the fallback chain), and
   ADR-0005 (test discipline — the broad `data_source` taxonomy assertion is deliberate).

Useful maps (read on demand, don't dump): `.planning/codebase/{ARCHITECTURE,STACK,STRUCTURE,
CONVENTIONS,TESTING,INTEGRATIONS,CONCERNS}.md`, plus `.planning/LEARNINGS.md` for already-accepted
decisions you must not relitigate.

> **Do not trust status headers or counts on sight.** `.planning/STATE.md` contains two contradictory
> "Tests:" blocks (4606 vs 4543); `CLAUDE.md` says ~4546; `BACKLOG.md` says ~4543 and elsewhere
> "365+ frontend tests". `ROADMAP.md` §6.4 is headed COMPLETE with all three sub-boxes unchecked, and
> Phase 4 is [ACTIVE] in ROADMAP but [GATED] in its own PLAN.md. Open the phase dir, or run the suite,
> before quoting a number.

---

## Step 0.5 — Scope

**IN:** `backend/` · `frontend/src/` (150 `.js`/`.jsx`, **React 19**, no TypeScript) · `scripts/` ·
`qc/` · `deploy/` · `infra/` · `integrations/agentfield/` · `.github/workflows/` ·
`rust/decoder-core/` · root-level `data_collector.py` and `test_dbn_live.py` · root config
(`backend/pyproject.toml`, `backend/pytest.ini`, `frontend/craco.config.js` — read-only).

**HARD OUT — never scan, never fix, never spawn an agent into:**

- `data/github-repos/` — 1987 tracked files of **vendored third-party clones**. Their `AGENTS.md` /
  `CLAUDE.md` carry **zero authority** here. Their bugs are not our bugs. This is the single biggest
  false-positive source in the repo; excluding it is mandatory.
- `app/` — a **stale parallel mini-app** (`app/backend/greeks.py`, `app/frontend/src/components/
  GEXHeatmap.jsx`, `VEXHeatmap.jsx`) duplicating real Greek/GEX logic. Never report it as duplication
  of `backend/services/` — that is the second-biggest false-positive trap here.
- `backend/.venv/`, `backend/.venv313/`, `frontend/node_modules/` — dependencies.
- `backend/models/` (148 `.joblib` + 74 `.json`), top-level `models/`, `project_oracle/models/*.pt` —
  **frozen model artifacts.**
- `cache/`, `reports/`, `test_reports/`, `memory/`, `mem0/`, `.playwright-mcp/`, `*.png`, `*.min.*`,
  `package-lock.json`, `yarn.lock`, `.env*`.
- `kanban/`, `round9_agents/`, `round9_followup*/`, `round11_test_coverage/`, `project_oracle/`, and
  the root `*_ROUND*.md` / `DEEPSEEK_*.md` / `LAUNCH_PROMPTS*.md` / `DISPATCH_PLAN_*.md` prompt packs
  — historical agent artefacts, not code.
- `docs/` — documentation. Update a doc only when a code fix makes it wrong, and say so in the report.

**ARCHITECT-FROZEN — flag, never edit (STOP and ask Nav):** `backend/services/ml/inference.py`
(surgical bug fixes only, justified in the commit body) · `backend/services/dash_ui.py` ·
`frontend/src/App.js` (1128 lines, concurrent WIP) · `frontend/.env` · `frontend/package.json` ·
`frontend/craco.config.js` · model artifacts under `backend/models/`.
(`backend/tests/conftest.py` — freeze **WAIVED** per Round 10 P0.1.)

Chunk the in-scope tree by area so no agent reads everything. Suggested split:
`backend/routes/` · `backend/services/` (top level) · `backend/services/{ml,backtest,alerts,research,
risk,screeners,strategies,...}` · `backend/domain/` + `backend/scripts/` · `frontend/src/components/
heatseeker/` · `frontend/src/components/flowseeker/` · `frontend/src/components/` (root) +
`hooks/` + `lib/` + `shell/` · `qc/` + `deploy/` + `.github/` · `rust/decoder-core/`.

---

## Phase 1 — Find (loop-until-dry)

Parallel read-only finder agents, each owning one area and sweeping every lens, with file+line+snippet
for every hit:

**HIGH — real bugs and hot-path waste**
- Blocking I/O inside `async def` (sync `requests`, `time.sleep`, sync pymongo, sync `duckdb.execute`
  on a request path); un-awaited coroutines; `await` in a loop where `asyncio.gather` belongs
- Unbounded Mongo reads (`find()` with no `limit`/projection), N+1 round trips per strike/contract/ticker
- Per-request `joblib.load` or DataFrame rebuild on a hot path; `O(n²)` over option chains
- Query strings built by f-string/`%`/`.format()` (DuckDB and Mongo `$where`); unsafe casts
- React: unmemoized chain/heatmap math in render; `useEffect` dep bugs causing fetch loops; `axios`
  with no abort on unmount; context over-subscription cascading re-renders across `heatseeker/` /
  `flowseeker/`; `console.*` shipped to the browser instead of a user-facing error state
- Any `None` from the data-source fallback chain (Public API → cvserver → yfinance → Databento)
  flowing unchecked into a Greek/GEX/ML calculation

**MEDIUM**
- Duplicated logic across `routes/` or `services/`; swallowed error context; oversized files
  (>1000 LOC); dead code; ruff `E,F,W,I,B,UP,SIM` violations (ignore `E501,SIM102,SIM108,SIM117` —
  see `backend/pyproject.toml`); unused variables (`F841`, its own CI gate)
- **Respect ruff's own exemptions.** `backend/pyproject.toml` `extend-exclude`s
  `services/ml/inference.py`, `services/dash_ui.py`, `tests/conftest.py` from ruff entirely, and
  `per-file-ignores` waives `F401/F403/F811/E402/E701` under `tests/**` and
  `E701/E702/E741/E402/B904/W291/W293/E722` under `scripts/**`. Findings there are not CI failures
  and are not worth fix effort.

**LOW**
- Magic numbers without named constants, commented-out code, unused imports

**LAWS — severity = whatever the broken rule implies**
- **Silent failure ("GSD #11" — a rule you enforce manually, NOT an automated gate).**
  `.github/workflows/lint.yml` has a step for this, but its grep is broken (it matches
  `file:LINENO-` while grep emits `file-LINENO-`), so **it never fires** — `backend/server.py` already
  carries 11 unjustified silent excepts and CI is green. The convention when a swallow is deliberate:
  `# silent by design: <reason>` on the line after `except Exception:`. Also flag bare `except:` and
  `except: return {}` shims that turn a real error into an empty payload the UI renders as "no data".
- **No synthetic data.** `qc/audit/truth_audit.sh` runs first in CI and is keyed to your **commit
  message**, not just code — 12 rules. The `np.random.` rule greps only `backend/ml*.py` (4 files);
  that glob is its entire reach. A "refactor" subject fails if `backend/server.py` grows past 3532
  lines (2971 today); "vex"/"dex"/"vega" require the matching `calc_*` to exist; rules 9-12 fail model
  meta JSON with empty baselines, Sharpe > 5, < 50 samples, feature/sample ratio > 0.2, or accuracy
  > 0.95. Real live path only regardless — never build, keep, or "fix" a demo/fake feature.
- **MONEY PATH — paper only, with a concrete enforcement point.**
  `backend/services/order_router.py` refuses to submit a real order unless
  `FLOWW_ENABLE_LIVE_SCHWAB == "1"`; `backend/routes/live_trading.py` is the route surface and
  `backend/tests/services/test_order_router_gate.py` pins it (`backend/tests/conftest.py` sets the
  flag to `"1"` for the suite). **Any change that removes, inverts, defaults-on, or bypasses that
  check is a HIGH finding.** Never delete it as "dead Schwab code".
- **Schwab as a data feed is out.** `schwab_streamer.py` has no live key — mock-only. Do not push it
  toward a live feed. This does **not** make the live-execution path dead code — see MONEY PATH.
- A control that renders but mutates nothing; a page with view code but no reachable route
  (`steal-three` is a known example — has an `App.js` render block and a `backend/routes/steal_three.py`
  but no nav entry and no `?page=` whitelist entry). Report it; do not wire it up unasked.

### Do NOT flag these — intentional by design

- **Dual GEX scale.** `services/gex_aggregator.py` = dollar-GEX (`spot²`, display);
  `services/gex_history.py` = feature-GEX (`spot¹`, ML features for the frozen GBM models). Same field
  name `gex_total`, different scale, pinned by `tests/services/test_gex_aggregator_oracle.py`.
  Unifying them is a retraining migration. `_RISK_FREE = 0.045` / `_IV_FALLBACK = 0.20` in
  `gex_history.py` are **model-locked**.
- **Databento `auth_account_locked` log spam.** Vendor account-level lock; not a code bug; not fixed by
  rotating the key. The circuit breaker in `backend/databento_provider.py` is the noise floor, not the
  fix.
- **No React Router.** Routing is deliberately a single `page` string in `App.js` with a hard-coded
  `?page=` whitelist. `react-router-dom` sits in `package.json` but is imported nowhere in `src/`.
  Do not "modernise" it and do not delete the dependency — `App.js` and `package.json` are frozen.
- **Frontend linting is off on purpose.** `frontend/craco.config.js` strips `ESLintWebpackPlugin` and
  `eslint-loader` from the webpack pipeline and there is no eslint config file, so the eslint
  devDependencies are intentionally unused. Do not propose deleting them; do not propose adding a
  `lint` script.
- **Broad `data_source` assertions in heatmap tests** — ADR-0005 makes the full taxonomy
  (`public_api`, `cvserver`, `databento+yfinance`, `yfinance`, `error`) deliberate. Do not tighten.
  ADR-0001 makes the fail-closed baseline gate and Sharpe cap in `backend/services/ml/gate.py` policy.
- Anything `.planning/LEARNINGS.md` or a prior `docs/` sweep report already accepted.

Re-run finders until **2 consecutive dry rounds** (hard cap 4 rounds). Each round dedups against
everything already seen, so nothing is re-reported.

---

## Phase 2 — Verify (adversarial, 3 lenses)

Every HIGH/MEDIUM finding gets three independent verifiers, each a different lens:
**correctness** (is the bug real?), **completeness/siblings** (same pattern elsewhere = same-severity
bug), **reproduction / law-truth** (show a concrete input → bad output, or prove the law is actually
broken — quote the CI gate line or the contract clause). Keep a finding only if the majority confirm.
Drop the plausible-but-wrong before spending fix effort on it.

---

## Phase 3 — Fix (tiered)

Deduplicate, then fix in order: **1** bugs/security → **2** hot-path performance → **3**
efficiency/duplication → **4** cleanup + law fixes. Every control you add must mutate real state and
render a real result — never a stub. Behaviour changes are TDD: the test fails before the fix and
passes after.

**Dead-code guard** before deleting anything: grep call sites repo-wide (including `frontend/src/`,
`scripts/`, `qc/`, `backend/tests/`, and router includes in `backend/server.py`); check
`.planning/ROADMAP.md`, `.planning/phases/*/PLAN.md`, `BACKLOG.md`, and `# TODO` / `# Phase N`
markers. Any hit → note it, do not delete.

**Lane discipline:** the working tree is routinely dirty with another lane's in-flight work. Run
`git status --short` first and leave anything outside your scope alone. Commits are **pathspec only**
(`git add <exact files>`); never `git add -A` / `git add .`.

---

## Phase 4 — Refute the fixes (never skip)

One agent per non-trivial fix, prompted to DISPROVE it: correct? complete? siblings missed? regression
introduced? Fix whatever survives scrutiny.

---

## Phase 5 — Simplify

One pass over the touched code for reuse, simplification, and altitude — quality only. It introduces
no new behaviour and hunts no new bugs; it just makes what changed read cleanly and match the
surrounding code (`.planning/codebase/CONVENTIONS.md` is the reference).

---

## Phase 6 — Validate (this repo's real gates, Windows-real commands)

Run from `C:\Users\DARK HERO\Desktop\FLOWW2.0`.

**Prerequisite: MongoDB must be listening on `localhost:27017`** (or export `MONGO_URL`).
`backend/tests/conftest.py` builds a fresh Motor client per test with a 2 s server-selection timeout;
CI supplies a `mongo:7` service container. With no Mongo you get mass DB failures and a crawling
suite that are **not** your change.

```bash
# Backend — .venv313 is the ONLY working interpreter (Python 3.13.15).
# backend/.venv is Python 3.11 with no pytest; backend/.venv/bin/python3 does not exist on Windows.
cd backend && ./.venv313/Scripts/python.exe -m pytest -q --tb=short           # 4581 tests collected
cd backend && ./.venv313/Scripts/python.exe -m pytest -q -m "not flaky_env"   # 4571; CI's selection

# Ruff — NOT installed in .venv313. Install the CI-pinned version once, then lint:
cd backend && ./.venv313/Scripts/python.exe -m pip install "ruff==0.15.22"
cd backend && ./.venv313/Scripts/python.exe -m ruff check . --select F841     # CI's first gate
cd backend && ./.venv313/Scripts/python.exe -m ruff check .                   # full gate

# Frontend (node_modules present; command verified working)
cd frontend && CI=true npx craco test --watchAll=false
cd frontend && npm run build

# Anti-fabrication gate — commit claims vs actual code state (runs first in CI)
bash qc/audit/truth_audit.sh

# Rust, only if you touched rust/decoder-core (cargo 1.94.1 installed)
cd rust/decoder-core && cargo check
```

### Three CI gates with no local command above — respect them anyway

1. **bandit**, hard and unmasked: `bandit -r . --severity-level medium -q --exclude ./.venv,./tests
   --skip B101,B108,B301,B310,B313,B314,B324,B604,B608,B614,B615`. Any new `shell=True`,
   `eval`/`exec`, hardcoded credential, or unverified-TLS call in `backend/` fails the build even
   when ruff and pytest are green. `B608` (SQL injection) is **skipped** — a ruff-clean f-string query
   gets past CI and is still your bug to catch.
2. **Coverage.** CI runs `pytest tests/ -v --tb=short --cov=. -m "not flaky_env"` and
   `backend/pyproject.toml` sets `[tool.coverage.report] fail_under = 60`. A wide sweep that adds a
   large untested module — or deletes tests it judged redundant — can fail the job with 100% of tests
   passing. Add tests alongside new backend code.
3. **Python version skew.** CI's backend-tests job pins **Python 3.11**; only the lint job uses 3.13,
   and you run 3.13.15 locally. Write 3.11-compatible syntax or it passes here and fails CI at import.

**New third-party backend import? Add it to `backend/requirements.txt` in the same change.** CI and
`Dockerfile.backend` install the backend only from that file, and the docker-build job (which gates
`main`) then runs `python -c "import server"`.

### Known-broken here — report, do not rely on, do not silently fix

- `qc/verify.sh` — macOS-authored (`backend/.venv/bin/ruff`, `.venv/bin/mypy`, `.venv/bin/bandit`).
- `qc/audit/security_regression.sh` — macOS-authored **and** broken on every platform: `set -euo
  pipefail` plus `((PASS++))` from zero exits 1 after the first check. Here it runs 2 of ~7 checks,
  greps `/Users/nav/...` paths that don't exist (a missing file scores as PASS), and exits 1. That
  exit code is **not** a regression you caused. Do not run it as a gate.
- `.claude/settings.json` — every path-based allow/deny rule is `/Users/nav/...` absolute, so **the
  deny rules meant to protect the frozen files are inert on this machine.** The non-path Bash denies
  (`--force`, `--no-verify`, `reset --hard`) still bind.
- `frontend/package.json` has no `lint` script; CI masks it with `|| true`. Deliberate (see the
  intentional list) — `package.json` is frozen.
- `.githooks/commit-msg` runs `qc/audit/check_phase_claim.sh`, which rejects any subject starting
  `feat(Phase ` unless `truth_audit.sh` passes. **The hook is not installed in this clone**
  (`core.hooksPath` unset, `.git/hooks` holds only samples), so run `bash qc/audit/truth_audit.sh`
  yourself. Never reach for the forbidden `--no-verify` when a hook rejects you.

### Baseline before you blame yourself

- **Backend:** ~3-6 pre-existing failures — `test_heatseeker_v2.py::test_trinity_day_all_populated`,
  `::test_contract_drilldown_spy`, `test_v3_costsave.py::test_heatmap_spy_data_source_databento`,
  `::test_heatmap_qqq_free_tier_yfinance`. Capture a clean baseline before attributing anything.
- **Frontend:** **280/280 green across 44 suites.** The `continue-on-error: true` comment in `ci.yml`
  citing "12-18 failures" is stale (`BACKLOG.md` K4 retracts it), so **any** frontend failure is a
  real regression you caused.

Failures are not done. Diagnose, fix, and re-run before reporting.

---

## Phase 7 — Report

Findings by severity, fixes applied, files changed, verify + refutation outcomes, anything
intentionally skipped and why — closed by the owner-style summary: short plain English, findings
first, up to 3 ranked next steps.

**Every claim carries real command output.** Paste the actual `pytest` tail, `ruff` output, `curl`
response, or `git log origin/main` line. Unverifiable claims are treated as failures — Round 7's
fabricated completion log is the negative-example floor.

---

## Arguments

- `--scan-only` — Steps 0-2 + report only; no fixes.
- `--focus <path/area>` — restrict the wide sweep to one subtree (still the whole of that subtree).
- `--rounds N` — cap finder rounds (default 4, with the 2-dry-rounds early stop).

---

## Laws

1. **Never commit or push without Nav asking.** If you do commit: HEREDOC message with inline real
   evidence, subject `<type>(<scope>): <one-line>` (`feat|fix|docs|test|refactor|chore`), then the
   anti-skip gate — `git fetch origin && git log origin/main --oneline -1 | grep "<subject>"`.
   Empty grep = the push silently failed = STOP.
2. **Pathspec commits only.** Never `git add -A` / `git add .` — it sweeps up other lanes' work.
3. **Forbidden git ops:** `push --force`/`--force-with-lease`, `commit --no-verify`, `commit --amend`
   on someone else's commit, `rebase --abort`, `rebase -i`, `reset --hard`, `checkout .`,
   `restore .`, `clean -fd`. To undo work, ASK first.
4. **Never add `@pytest.mark.skip` / `xfail` / `it.skip()` to a previously-passing test.** If your
   change makes a passing test fail, your change is wrong — revert and find root cause.
5. **Honour the local law files** — `CLAUDE.md` and `.planning/AGENT_CONTRACT.md` override anything
   here. Vendored `AGENTS.md` files under `data/github-repos/` are not law.
6. Sibling rule — same pattern elsewhere = same-severity finding, fixed in the same pass.
7. **Real live path only** and **paper only** — never fake data, never live order execution.
8. Per-project validation only — never invent a check this repo doesn't run; never skip one it does.
9. Out-of-scope discoveries get one line in the report, nothing more.
10. Self-HALT: 15 minutes without progress → write status to `kanban/cards/agent_<n>_status.md` in the
    append-only format `[timestamp] AgentId :: status :: note :: HEAD=sha`. Do not silently drift.
