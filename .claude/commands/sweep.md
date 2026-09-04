# /sweep — Scoped Quality Sweep (floww / Confluence Decoder)

Anti-pattern scan of ONE chosen scope, then fix everything found, then try to disprove the fixes.
For the whole repo in one run, use `/sweep-wide`. For a preventative line-by-line audit (no style/perf
hunting), use `/verify`.

Read `CLAUDE.md` and `.planning/AGENT_CONTRACT.md` before Phase 1. **The contract wins over this file
and over your spawn prompt** — with two carve-outs, because both law files were written on a macOS
machine and two clauses are false here:

- Contract §1 ("the only clone is `/Users/nav/Documents/GitHub/floww`; if `pwd` doesn't end in
  `Documents/GitHub/floww` → STOP and re-cd") is **superseded**. `C:\Users\DARK HERO\Desktop\FLOWW2.0`
  is the working tree. Do not stop.
- Contract §7 / CLAUDE.md ("always `backend/.venv/bin/python3`") is **superseded**. Use
  `backend/.venv313/Scripts/python.exe` (see Phase 4).

Everything else in the contract still wins.
Also read `docs/adr/` (6 Accepted ADRs) before touching ML promotion, data-source routing, backtest
equity, CORS, or test assertions — those decisions are already litigated.

---

## Scope rule — what this repo lets you touch

**IN SCOPE (project source):**

| Area | What's there |
|---|---|
| `backend/` | 592 `.py` — `routes/` 55, `services/` 167 (12 sub-packages), `tests/` 293, `scripts/` 37, `domain/` 8 |
| `frontend/src/` | 150 `.js`/`.jsx` — `components/` 48 + `heatseeker/` 48 + `flowseeker/` 23, `hooks/` 9, `lib/` 8, `shell/` 5. **React 19** (19.2.8 installed). **No `pages/`, no TypeScript, no React Router in use.** |
| `qc/`, `scripts/`, `deploy/`, `.github/workflows/` | shell + CI gates |
| `rust/decoder-core/` | 14 `.rs`. In scope, but gate it with `cargo check` (cargo 1.94.1 is installed). |

**PERMANENTLY OUT OF SWEEP SCOPE — never scan, never fix, never spawn an agent into:**

- `data/github-repos/` — 1987 tracked files of **vendored third-party clones**. Their `AGENTS.md` /
  `CLAUDE.md` files carry **zero authority** over this project. Their bugs are not our bugs.
- `app/` — a **stale parallel mini-app** (`app/backend/greeks.py`, `app/frontend/src/components/
  GEXHeatmap.jsx`, `VEXHeatmap.jsx`) that duplicates real Greek/GEX logic. Never report it as
  duplication of `backend/services/` — it is the repo's single biggest false-duplication trap.
- `backend/.venv/`, `backend/.venv313/`, `frontend/node_modules/` — dependencies.
- `backend/models/` (148 `.joblib` + 74 `.json`), top-level `models/`, `project_oracle/models/*.pt` —
  **frozen model artifacts.** Touching them invalidates every trained model.
- `cache/`, `reports/`, `test_reports/`, `data/` (ex-repos), `.playwright-mcp/`, `*.png`, lockfiles.
- `kanban/`, `round9_agents/`, `round9_followup*/`, `round11_test_coverage/`, root `*_ROUND*.md` /
  `DEEPSEEK_*.md` / `LAUNCH_PROMPTS*.md` — historical agent prompt packs, not code.
- `docs/` — documentation. Fix docs only when a code fix makes them wrong, and say so.

**ARCHITECT-FROZEN — flag, never edit (STOP and ask Nav first):**

- `backend/services/ml/inference.py` — surgical bug fixes only, justified in the commit body
- `backend/services/dash_ui.py`
- `frontend/src/App.js` — 1128 lines, heavy concurrent WIP, surgical only with explicit approval
- `frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`
- Model artifacts under `backend/models/`
- (`backend/tests/conftest.py` — freeze **WAIVED** per Round 10 P0.1)

---

## Step 0 — Lock the target (always ask when no args)

- **With args:** `/sweep <files or area>` — that is the scope. No survey.
- **No args:** AskUserQuestion — "What should I sweep?"
  1. **Uncommitted work (Recommended)** — changed + staged + untracked, filtered to `.py`/`.jsx`/`.js`
     under `backend/` and `frontend/src/`.
     `git status --short` then `git diff --name-only HEAD`.
  2. **Files or an area I name** — free-text follow-up; resolve to concrete files before spawning.
  3. **A recent commit** — `git log --oneline -8`, ask which, scope = that commit's diff.

Final scope = target files **plus their direct callers and pattern-siblings**, nothing wider.
Empty scope → say so and stop.

> **Working-tree note:** this repo routinely sits dirty with another lane's in-flight work.
> Run `git status --short` first. If you see modified files outside your scope, leave them alone —
> lane separation is non-negotiable, and commits are **pathspec only** (`git add <exact files>`,
> never `git add -A` / `git add .`).

---

## Phase 1 — Scan (parallel read-only agents)

Split the scope into 2-6 logical areas. One `Explore` agent per area, **all spawned in a SINGLE
message**. Each agent hunts, with file+line+snippet for every hit:

**HIGH (bugs & hot-path waste):**

*Python / FastAPI / async:*
- Blocking I/O inside an `async def` route or service (`requests`, `time.sleep`, sync `pymongo`,
  sync file reads, sync `duckdb.execute` in a request path)
- A coroutine created but never awaited; `await` inside a loop where `asyncio.gather` belongs
- Unbounded Mongo reads — `find()` with no `limit`/projection; a full-collection scan per request
- N+1: one DB/HTTP round trip per contract/strike/ticker inside a loop
- Per-request model or artifact reload (`joblib.load` / DataFrame rebuild on the hot path)
- `O(n²)` over option chains where a dict/index gives `O(n)`
- Query strings built by f-string / `%` / `.format()` interpolation (DuckDB **and** Mongo `$where`)
- **Silent failure** — `except Exception: pass` with no justification comment. `.github/workflows/
  lint.yml` has a "GSD #11" step for this, but **its grep is broken and the gate never fires** (it
  matches `file:LINENO-` while grep emits `file-LINENO-`): `backend/server.py` already carries 11
  unjustified silent excepts and CI stays green. Treat this as a manual rule you enforce, not an
  automated one. Convention when the swallow is deliberate: `# silent by design: <reason>` on the
  next line. Also flag bare `except:` and `except: return {}` shims that swallow a real error into an
  empty payload the UI renders as "no data".
- Unhandled `None` from a data-source fallback (Public API → cvserver → yfinance → Databento) that
  propagates into a Greek/GEX calculation as `NaN` or `0`

*React (JS/JSX, no TypeScript in this repo):*
- Expensive work in render — chain/heatmap math not behind `useMemo`
- `useEffect` with a missing or over-broad dependency array causing a fetch loop
- `axios` calls with no cleanup/abort on unmount (this repo has already shipped one fix for this class)
- Whole-context subscription causing cascade re-renders across `heatseeker/` or `flowseeker/`
- `console.error`/`console.log` shipped to the browser instead of a user-facing error state
  (removed once already in `b24fa7a` — treat any new one as a regression)

**MEDIUM (efficiency & quality):**
- Duplicate logic copy-pasted across `routes/` or `services/`
- Swallowed error context (`except Exception as e: return {"error": str(e)}` with no log/status)
- Oversized files (>1000 LOC) and dead code (unused functions, unreachable branches)
- `ruff` rules the repo actually enforces but the file violates: `E, F, W, I, B, UP, SIM`
  (ignoring `E501, SIM102, SIM108, SIM117`) — see `backend/pyproject.toml`
- Unused variables (`F841`) — CI runs this as its own gate before the full ruff pass

  **Check ruff's own exemptions before filing lint debt.** `backend/pyproject.toml` `extend-exclude`s
  `services/ml/inference.py`, `services/dash_ui.py`, and `tests/conftest.py` from ruff entirely, and
  `per-file-ignores` waives `F401/F403/F811/E402/E701` under `tests/**` and
  `E701/E702/E741/E402/B904/W291/W293/E722` under `scripts/**`. Findings there are not CI failures
  and are not worth a fix — two of those files are frozen anyway.

**LOW (cleanup):**
- Magic numbers without named constants, commented-out code, unused imports

**LAWS (project-specific — severity = whatever the broken rule implies):**
- **Fake / synthetic / demo data on a real surface.** `qc/audit/truth_audit.sh` runs first in CI and
  is keyed to your **commit message**, not just to code: 12 rules. The `np.random.` rule only greps
  `backend/ml*.py` (4 files) — that glob is its entire reach. A subject containing "refactor" fails if
  `backend/server.py` grows past 3532 lines (2971 today); "vex"/"dex"/"vega" require the matching
  `calc_*` function to exist; rules 9-12 fail any model meta JSON with empty baselines, Sharpe > 5,
  < 50 samples, feature/sample ratio > 0.2, or accuracy > 0.95. Real live path only regardless.
- **MONEY PATH — paper only, and it has a concrete enforcement point.**
  `backend/services/order_router.py` refuses to submit a real order unless
  `FLOWW_ENABLE_LIVE_SCHWAB == "1"`; `backend/routes/live_trading.py` is the route surface and
  `backend/tests/services/test_order_router_gate.py` pins the behaviour (`backend/tests/conftest.py`
  sets the flag to `"1"` for the suite). **Any change that removes, inverts, defaults-on, or bypasses
  that check is a HIGH finding.** Never delete it as "dead Schwab code".
- **Schwab as a data feed is out.** `backend/services/schwab_streamer.py` has no live key — mock-only.
  Do not "fix" it toward a live feed. This does **not** mean the live-execution path is dead code —
  see MONEY PATH above.
- A control that renders but mutates nothing; a tab or button with no reachable route.

### Do NOT flag these — they are intentional

- **Dual GEX scale.** `services/gex_aggregator.py` is dollar-GEX (`spot²`, for display);
  `services/gex_history.py` is feature-GEX (`spot¹`, for the frozen GBM models). They share the name
  `gex_total` on purpose and are pinned by oracle tests in
  `tests/services/test_gex_aggregator_oracle.py`. Unifying them is a retraining migration, not a bug.
  `_RISK_FREE = 0.045` and `_IV_FALLBACK = 0.20` in `gex_history.py` are **model-locked constants**.
- **Databento `auth_account_locked` warnings.** Vendor-side account lock, not a code bug, not fixable
  by rotating the key. The per-parent circuit breaker in `backend/databento_provider.py` is the noise
  floor, not the fix. See CLAUDE.md → "Known vendor-side issues".
- **Frontend linting is off on purpose.** `frontend/craco.config.js` strips `ESLintWebpackPlugin` and
  `eslint-loader` from the webpack pipeline and there is no eslint config file, so the eslint
  devDependencies are intentionally unused. Do not propose deleting them, and do not propose adding a
  `lint` script — `package.json` and `craco.config.js` are both frozen.
- **Broad `data_source` assertions in heatmap tests.** ADR-0005 (`docs/adr/0005-test-discipline.md`,
  Accepted) makes tests assert the full taxonomy (`public_api`, `cvserver`, `databento+yfinance`,
  `yfinance`, `error`) deliberately. Do not "tighten" them. ADR-0001 likewise makes the fail-closed
  baseline gate and Sharpe cap in `backend/services/ml/gate.py` policy, not magic numbers.
- Anything a prior sweep already examined and accepted — check `docs/` sweep/audit reports and
  `.planning/LEARNINGS.md` before re-flagging.

---

## Phase 2 — Fix (autonomous)

Deduplicate and tier: **1** bugs/security → **2** hot-path performance → **3** efficiency/duplication
→ **4** cleanup + law fixes. Fix with `general-purpose` agents (one per tier or area, spawned together
when independent and touching disjoint files).

**Dead code guard — before deleting ANY "dead" function/module:**
1. Grep call sites across the ENTIRE repo, not just the file — include `frontend/src/`, `scripts/`,
   `qc/`, and `backend/tests/`
2. Check `.planning/ROADMAP.md`, `.planning/phases/*/PLAN.md`, `BACKLOG.md`, and TODO comments for
   planned use
3. Check for `# TODO`, `# Phase N`, `# noqa`, `@pytest.mark.*`, or a route registered in `server.py`
4. Any of the above true → do **NOT** delete; note it instead
5. Delete only genuinely orphaned code with zero references and no future-phase marker

**TDD is required for behaviour changes:** the test must fail before your fix and pass after.

---

## Phase 3 — Refute the fixes (never skip)

One `Explore` agent per non-trivial fix, prompted to DISPROVE it: correct? complete? siblings missed?
regression introduced? Fix what survives.

---

## Phase 4 — Validate (this repo's real gates, Windows-real commands)

Run from the repo root at `C:\Users\DARK HERO\Desktop\FLOWW2.0`.

**Prerequisite: MongoDB must be listening on `localhost:27017`** (or export `MONGO_URL`).
`backend/tests/conftest.py` builds a fresh Motor client per test with a 2 s server-selection timeout,
and CI supplies a `mongo:7` service container for exactly this reason. With no Mongo you get a wall
of DB failures and a crawling suite that are **not** your change.

```bash
# Backend tests — .venv313 is the ONLY working interpreter (Python 3.13.15).
# backend/.venv is Python 3.11 with no pytest installed; .venv/bin/python3 does not exist on Windows.
cd backend && ./.venv313/Scripts/python.exe -m pytest -q --tb=short          # 4581 tests collected
cd backend && ./.venv313/Scripts/python.exe -m pytest -q -m "not flaky_env"  # 4571; CI's selection
cd backend && ./.venv313/Scripts/python.exe -m pytest tests/services/ -k <kw> -v   # targeted

# Ruff — NOT installed in .venv313. Install the CI-pinned version once, then lint:
cd backend && ./.venv313/Scripts/python.exe -m pip install "ruff==0.15.22"
cd backend && ./.venv313/Scripts/python.exe -m ruff check . --select F841    # CI's first gate
cd backend && ./.venv313/Scripts/python.exe -m ruff check .                  # full gate

# Frontend tests (node_modules is installed; verified working)
cd frontend && CI=true npx craco test --watchAll=false
cd frontend && CI=true npx craco test --watchAll=false --testPathPattern="<name>"   # targeted
cd frontend && npm run build                                                  # craco build

# Truth audit — the repo's own anti-fabrication gate (runs first in CI)
bash qc/audit/truth_audit.sh

# Rust, only if you touched rust/decoder-core
cd rust/decoder-core && cargo check
```

### Three CI gates that have no local equivalent in the list above — respect them anyway

1. **bandit** runs as a hard, unmasked gate: `bandit -r . --severity-level medium -q --exclude
   ./.venv,./tests --skip B101,B108,B301,B310,B313,B314,B324,B604,B608,B614,B615`. Any new
   `shell=True`, `eval`/`exec`, hardcoded credential, or unverified-TLS call in `backend/` (tests
   excluded) fails the build even when ruff and pytest are green. Note `B608` (SQL injection) is
   skipped — so a ruff-clean f-string query still gets past CI and is still your bug to catch.
2. **Coverage.** CI runs `pytest tests/ -v --tb=short --cov=. -m "not flaky_env"` and
   `backend/pyproject.toml` sets `[tool.coverage.report] fail_under = 60`. Adding a large untested
   module — or deleting tests you judged redundant — can fail the job with every test passing.
3. **Python version skew.** CI's backend-tests job pins **Python 3.11**; only the lint job uses 3.13.
   You run 3.13.15 locally. Write 3.11-compatible syntax, or it passes here and fails CI at import.

**New third-party backend import? Add it to `backend/requirements.txt` in the same change.** CI and
`Dockerfile.backend` install the backend only from that file, and the docker-build job then runs
`python -c "import server"`. A package that merely happens to sit in your local `.venv313` breaks both.

### Known-broken here — report, do not rely on, do not silently fix

- `qc/verify.sh` — macOS-authored (`backend/.venv/bin/ruff`, `.venv/bin/mypy`, `.venv/bin/bandit`).
- `qc/audit/security_regression.sh` — macOS-authored **and** broken on every platform: `set -euo
  pipefail` plus `((PASS++))` from zero exits 1 after the first check. Here it runs 2 of ~7 checks,
  greps `/Users/nav/...` paths that don't exist (a missing file scores as PASS), and exits 1. That
  exit code is **not** a regression you caused.
- `.claude/settings.json` — every path-based allow/deny rule is `/Users/nav/...` absolute, so **the
  deny rules meant to protect the frozen files are inert on this machine.** The non-path Bash denies
  (`--force`, `--no-verify`, `reset --hard`) still bind.
- `frontend/package.json` has **no `lint` script**; CI masks the failure with `|| true`. This is
  deliberate (see the intentional list above) — `package.json` is frozen.
- `.githooks/commit-msg` runs `qc/audit/check_phase_claim.sh`, which rejects any subject starting
  `feat(Phase ` unless `truth_audit.sh` passes. **The hook is not installed in this clone**
  (`core.hooksPath` unset, `.git/hooks` holds only samples), so run `bash qc/audit/truth_audit.sh`
  yourself. Never reach for the forbidden `--no-verify` when a hook rejects you.

### Baseline before you blame yourself

- **Backend:** ~3-6 pre-existing failures — `test_heatseeker_v2.py::test_trinity_day_all_populated`,
  `::test_contract_drilldown_spy`, `test_v3_costsave.py::test_heatmap_spy_data_source_databento`,
  `::test_heatmap_qqq_free_tier_yfinance`. Confirm against a clean baseline before attributing.
- **Frontend:** **280/280 green across 44 suites.** The `continue-on-error: true` comment in
  `ci.yml` citing "12-18 failures" is stale (`BACKLOG.md` K4 retracts it), so **any** frontend
  failure is a real regression you caused.

Failures are not done. Diagnose, fix, and re-run before reporting.

---

## Phase 5 — Report

Findings by severity, fixes applied, files changed, refutation outcomes, anything intentionally
skipped (with reason) — closed by the owner-style summary: short plain English, findings first,
up to 3 ranked next steps.

**Every claim carries real command output.** Paste the actual `pytest` tail, `ruff` output, or `curl`
response. An unverifiable claim is treated as a failure — Round 7's fabricated completion log is the
negative-example floor.

---

## Arguments

- `--scan-only` — Steps 0-1 + report only, no fixes.

---

## Laws

1. **Never commit or push without Nav asking.** If you do commit: HEREDOC message with inline real
   evidence, `<type>(<scope>): <one-line>` subject, then the anti-skip gate —
   `git fetch origin && git log origin/main --oneline -1 | grep "<subject>"`. Empty grep = the push
   silently failed = STOP.
2. **Pathspec commits only.** `git add <your exact files>`. Never `git add -A` / `git add .`.
3. **Forbidden git ops:** `push --force`/`--force-with-lease`, `commit --no-verify`, `commit --amend`
   on someone else's commit, `rebase --abort`, `rebase -i`, `reset --hard`, `checkout .`,
   `restore .`, `clean -fd`. To undo work, ASK first.
4. **Never add `@pytest.mark.skip` / `xfail` / `it.skip()` to a previously-passing test.** If your
   change makes a passing test fail, your change is wrong — revert and find root cause.
5. Same pattern elsewhere = same-severity finding, fixed in the same pass.
6. **Real live path only** — never build, keep, or "fix" demo/fake/simulated features.
7. Out-of-scope discoveries get one line in the report, nothing more.
8. Self-HALT: 15 minutes without progress → stop and write status to
   `kanban/cards/agent_<n>_status.md` in the append-only format. Do not silently drift.
