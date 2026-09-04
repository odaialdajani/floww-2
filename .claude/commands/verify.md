# /verify — Nuclear Audit (Scoped) — floww / Confluence Decoder

Exhaustive preventative audit of ONE chosen scope. Flags what COULD go wrong, not just what IS wrong.
No corners cut. For a quality sweep that also fixes style/perf debt, use `/sweep`; for the whole repo,
use `/sweep-wide`.

Read `CLAUDE.md`, `.planning/AGENT_CONTRACT.md`, and `docs/adr/` (6 Accepted ADRs) before spawning
anything. **The contract wins over this file and over your spawn prompt** — with two carve-outs,
because both law files were written on a macOS machine:

- Contract §1 ("the only clone is `/Users/nav/Documents/GitHub/floww`; if `pwd` doesn't end in
  `Documents/GitHub/floww` → STOP and re-cd") is **superseded**. `C:\Users\DARK HERO\Desktop\FLOWW2.0`
  is the working tree. Do not stop.
- Contract §7 / CLAUDE.md ("always `backend/.venv/bin/python3`") is **superseded**. Use
  `backend/.venv313/Scripts/python.exe`.

Everything else in the contract still wins.

---

## Scope rule

**AUDITABLE:** `backend/**/*.py` · `frontend/src/**/*.{js,jsx}` · `scripts/*.py` · `qc/*.sh` ·
`deploy/**` · `.github/workflows/*.yml` · `rust/decoder-core/src/*.rs`.

**NEVER AUDITED — drop from the target list and say so:**
`data/github-repos/**` (1987 files of vendored third-party clones — their `AGENTS.md` carries zero
authority here) · `app/**` (a stale parallel mini-app whose `greeks.py` / `GEXHeatmap.jsx` /
`VEXHeatmap.jsx` duplicate real logic — never report it as duplication of `backend/services/`) ·
`backend/.venv*/` · `frontend/node_modules/` · `backend/models/**` and top-level `models/` and
`project_oracle/models/*.pt` (frozen artifacts) · `cache/` · `reports/` · `test_reports/` ·
`kanban/` · `round9*/`, `round11*/` and root `*_ROUND*.md` / `DEEPSEEK_*.md` / `LAUNCH_PROMPTS*.md`
prompt packs · `.playwright-mcp/` · `*.png` · lockfiles · `.env*`.

**ARCHITECT-FROZEN — audit and flag, but NEVER edit (STOP and ask Nav first):**
`backend/services/ml/inference.py` · `backend/services/dash_ui.py` · `frontend/src/App.js` (1128 lines,
concurrent WIP) · `frontend/.env` · `frontend/package.json` · `frontend/craco.config.js` ·
model artifacts under `backend/models/`. (`backend/tests/conftest.py` — freeze **WAIVED**, R10 P0.1.)

There is **no TypeScript** in `frontend/src` (109 `.jsx` + 41 `.js`) and **no `frontend/src/pages/`**
directory. There is **no C#** anywhere. Don't audit for what isn't here.

---

## Step 0 — Lock the target (always ask when no args)

- **With args:** `/verify backend/routes/ml_predict_api.py heatseeker` — those files / that area are
  the scope. No survey.
- **No args:** AskUserQuestion — "What should I audit?"
  1. **Uncommitted work (Recommended)** — `git diff --name-only HEAD` + `git diff --cached
     --name-only` + untracked code files from `git status --porcelain`, filtered to `.py`/`.js`/`.jsx`.
  2. **Files or an area I name** — free-text follow-up; resolve the name to concrete files before
     spawning anything.
  3. **A recent commit** — run `git log --oneline -8`, ask which one, scope = that commit's diff.

Empty scope → report that and stop. Never widen the scope on your own; out-of-scope discoveries get
one line in the report, nothing more.

> **Lane check first.** `git status --short` — this repo routinely sits dirty with another lane's
> in-flight work. Anything outside your scope is someone else's; do not touch it, do not "clean" it.

---

## How to run

You (the orchestrator) do the logistics. Agents do the auditing. Don't waste agent tokens on process.

**Step 1 — Gather the diff.** `git diff HEAD -- <file>` per target (whole file if untracked). Agents
who don't know what changed audit aimlessly.

**Step 2 — Split by area, not dimension.** Group files into logical units (e.g. "`ml_predict_api.py`
route + the `services/ml/` functions it calls + its tests"). Each agent gets ONE area and audits it
across ALL dimensions, so no two agents read the same files.

**Step 3 — Spawn the audit wave.** Parallel `Agent` calls in a SINGLE message, `subagent_type:
Explore` (read-only). Minimum 3, maximum 8.

**Step 4 — Every agent prompt MUST include:**
1. The actual git diff for their files
2. The mandatory audit rules below (copy verbatim)
3. A concrete description of their area and what to focus on

**Step 5 — Collect results.** Deduplicate, rank, present to the user. AskUserQuestion: fix all /
fix HIGH+MEDIUM / review first. Apply approved fixes with `general-purpose` agents or directly.
Behaviour changes are TDD — the test fails before the fix and passes after.

**Step 6 — Refutation pass (never skip).** Spawn a SECOND wave — one `Explore` agent per fix —
prompted to DISPROVE it: is it correct, complete, and did the fixer miss siblings? Round 2 always
catches something. Fix what survives scrutiny.

**Step 7 — Validate.** Run this repo's real gates (below) and report results honestly. Failing tests
mean not done.

---

## MANDATORY AUDIT RULES (copy into every agent prompt)

```
=== AUDIT RULES — THESE OVERRIDE YOUR DEFAULTS ===

PROJECT: floww / Confluence Decoder — FastAPI + React 19 (CRA/craco, JavaScript only)
+ MongoDB (Motor async) + DuckDB + 5 production GBM models (SPY/QQQ/DIA/IWM/TLT).
Repo root: C:\Users\DARK HERO\Desktop\FLOWW2.0 (Windows).

VERSIONS THAT CHANGE YOUR JUDGEMENT:
  - React 19.2.8 (package.json pins ^19.0.0) — NOT 18. Legacy ReactDOM.render and
    unmountComponentAtNode are gone; ref-as-prop and forwardRef guidance changed; act()
    and StrictMode double-invoke semantics differ. Judge effects and refs by React 19 rules.
  - You run backend code on Python 3.13.15 locally, but CI's backend-tests job pins Python
    3.11 (only the lint job uses 3.13). Flag any 3.12+ only syntax or stdlib call as a
    CI-breaking finding even though it runs fine here.

MINDSET: This audit is PREVENTATIVE. You are not checking "does it work today."
You are checking "what could possibly go wrong." Flag everything. The user wants
20 findings where 15 turn out safe rather than missing 1 real bug.

SIBLING RULE: For EVERY bug or weakness you find, grep the codebase for the same
pattern in other files. Every instance is a BUG with the SAME severity. Never
write "pre-existing", "acceptable", "low severity", or "known design choice."
Broken code that hasn't bitten yet is still broken code. This is non-negotiable.

ANTI-FABRICATION: Every claim carries real evidence — file path, line number, and
the literal snippet, or the actual command output. Never state that a test passes,
a route works, or a value is correct without pasting the proof. Unverifiable claims
are treated as failures.

SEVERITY DEFINITIONS (use these, not your gut):
- HIGH: Wrong number shown to a trader, data corruption, silent data loss, crash,
        unbounded memory/query growth, a security hole, or anything that could put
        automation near live order execution.
- MEDIUM: Degraded behavior under specific conditions (fallback path, empty chain,
          market closed, reconnect, missing API key). Accumulates or surfaces under load.
- LOW: Code smell, suboptimal pattern, missing guard that has backup protection.

WHAT TO CHECK for every changed function/block:

Logic & correctness:
  [ ] Every conditional: true? false? unexpected value (None, NaN, 0, -1, "", empty dict)?
  [ ] Every loop: empty input, single element, first/last iteration, full option chain
  [ ] Every list/dict op: empty, key missing, index bounds, sort invariant held
  [ ] Every arithmetic: division by zero, NaN propagation, float precision on Greeks,
      overflow on OI * 100 * spot^2
  [ ] Every cast/parse: can the upstream payload actually be that type at runtime?

Data flow (this product's real path):
  [ ] Trace data from entry — Public API (PublicBroker) -> cvserver -> yfinance -> Databento
      fallback chain, or DuckDB / Mongo — through every transform to exit (JSON route
      response -> React render).
  [ ] At each fallback hop: does a None/partial payload get detected, or does it become
      a 0 / NaN / empty chain that renders as a confident-looking wrong number?
  [ ] Every Mongo write: who reads it? Does the reader handle all possible states?
  [ ] Every field: always present? What happens downstream if it's missing?
  [ ] Databento may return auth_account_locked (vendor-side account lock, NOT a code bug).
      Check the code HANDLES it; do not file it as a bug to fix.

Async & concurrency (FastAPI + Motor):
  [ ] Any blocking call inside `async def`? (requests, time.sleep, sync pymongo,
      sync duckdb.execute, sync file/joblib read on a request path)
  [ ] Any coroutine created but never awaited? Any `await` in a loop that should be
      asyncio.gather?
  [ ] Two requests firing simultaneously: shared module-level state, cache, or client
      mutated without protection? Trace the interleaving.
  [ ] Background tasks / streamers: what happens on reconnect — state preserved or reset?

Error handling (enforce this MANUALLY — the CI gate is broken):
  [ ] `except Exception: pass` in services/, routes/, or server.py should carry
      `# silent by design: <reason>` or an explanatory comment on the next line.
      .github/workflows/lint.yml has a "GSD #11" step for this, but its grep matches
      `file:LINENO-` while grep emits `file-LINENO-`, so the gate NEVER FIRES —
      backend/server.py already holds 11 unjustified silent excepts and CI is green.
      Every one of them is a live finding, not accepted debt.
  [ ] Any bare `except:`? Any `except ...: return {}` that turns a real error into an
      empty payload the UI renders as "no data"?
  [ ] Does the route surface a real status (503/500 + reason) or fake success?

Security (CI runs bandit as a HARD, unmasked gate):
  [ ] Any new subprocess(shell=True), eval/exec, hardcoded credential, or requests call
      without verify in backend/ (tests excluded)? bandit runs
      `-r . --severity-level medium -q --exclude ./.venv,./tests --skip B101,B108,B301,
      B310,B313,B314,B324,B604,B608,B614,B615` and fails the build.
  [ ] B608 (SQL injection) is SKIPPED by that config — so an f-string-built query passes
      both ruff and bandit. It is still a HIGH finding. Catch it yourself.

Dependency & coverage (silent CI breakers):
  [ ] Any new third-party backend import that is NOT in backend/requirements.txt? CI and
      Dockerfile.backend install only from that file, then run `python -c "import server"`.
      A package that merely exists in the local .venv313 breaks CI and the Docker gate.
  [ ] CI runs pytest with `--cov=.` and backend/pyproject.toml sets
      `[tool.coverage.report] fail_under = 60`. A large untested addition can fail the job
      with every test passing.

ML-specific:
  [ ] Feature vector order and dtype must match the trained model's manifest. A silently
      reordered or renamed feature is a HIGH finding.
  [ ] Model artifacts under backend/models/ are FROZEN — flag any code path that writes,
      regenerates, or version-bumps them.
  [ ] No synthetic data. qc/audit/truth_audit.sh (12 rules, keyed to the COMMIT MESSAGE)
      fails an ML-titled commit that puts np.random. data generation into backend/ml*.py —
      that glob is the rule's entire reach, so np.random. elsewhere is still your finding.
      Rules 9-12 also fail model meta JSON with empty baselines, Sharpe > 5, < 50 samples,
      feature/sample ratio > 0.2, or accuracy > 0.95.
  [ ] backend/services/ml/inference.py is architect-frozen — audit it, never edit it.
  [ ] ADR-0001 (docs/adr/0001-model-promotion-policy.md, Accepted) defines the fail-closed
      baseline-beat gate and MAX_PLAUSIBLE_DAILY_SHARPE in backend/services/ml/gate.py.
      Those are policy, not magic numbers — flag any weakening as HIGH.

MONEY PATH (the paper-only law's concrete enforcement point):
  [ ] backend/services/order_router.py refuses to submit a real order unless
      FLOWW_ENABLE_LIVE_SCHWAB == "1". backend/routes/live_trading.py is the route surface;
      backend/tests/services/test_order_router_gate.py pins the behaviour; and
      backend/tests/conftest.py sets the flag to "1" for the whole suite.
  [ ] Treat ANY change that removes, inverts, defaults-on, or bypasses that check as HIGH.
      Never dismiss this path as dead Schwab code — the data feed is mock-only, the
      execution gate is live and load-bearing.

DO NOT FLAG THESE — intentional by design:
  [ ] Dual GEX scale. services/gex_aggregator.py is dollar-GEX (spot^2, for display);
      services/gex_history.py is feature-GEX (spot^1, for the frozen GBM models). They
      share the field name gex_total on purpose; display_net_gex == spot * feature_net_gex
      is pinned by tests/services/test_gex_aggregator_oracle.py. Unifying them is a
      retraining migration, not a bug. _RISK_FREE = 0.045 and _IV_FALLBACK = 0.20 in
      gex_history.py are MODEL-LOCKED constants — changing them invalidates every model.
  [ ] No React Router in use. Routing is deliberately a `page` string in App.js with a
      hard-coded ?page= whitelist. react-router-dom sits in package.json but is imported
      nowhere in src/. App.js and package.json are frozen — do not modernise, do not prune.
  [ ] schwab_streamer.py has no live key and is mock-only — Schwab as a DATA FEED is out.
      This says nothing about the execution gate; see MONEY PATH above, which is live.
  [ ] Frontend linting is disabled on purpose: craco.config.js strips ESLintWebpackPlugin
      and eslint-loader and there is no eslint config file, so the eslint devDependencies
      are intentionally unused. Do not flag them, and do not propose a `lint` script.
  [ ] Broad data_source assertions in the heatmap tests are deliberate per ADR-0005 —
      tests accept the full taxonomy (public_api, cvserver, databento+yfinance, yfinance,
      error). Do not report them as sloppy assertions to tighten.
  [ ] ruff's own exemptions: backend/pyproject.toml extend-excludes services/ml/inference.py,
      services/dash_ui.py and tests/conftest.py entirely, and per-file-ignores waives
      F401/F403/F811/E402/E701 under tests/** and E701/E702/E741/E402/B904/W291/W293/E722
      under scripts/**. Lint findings there are not CI failures.

Downstream impact:
  [ ] Every function/route/response-field changed: grep for all callers and readers,
      including frontend/src/ (components/heatseeker/, components/flowseeker/, hooks/, lib/)
  [ ] Does the change break a consumer's assumption about shape, order, units, or presence?
  [ ] Which of the 6 surfaces is affected — Solstice (page id "heatseeker"), Triad
      ("trinity"), Zenith ("skylit", display-only), Tidehunter Pro ("flowseeker-pro"),
      Portfolio, Journal? Check each one that reads the touched data.

React specifics:
  [ ] Expensive chain/heatmap math in render without useMemo
  [ ] useEffect dependency array wrong -> fetch loop
  [ ] axios call with no abort/cleanup on unmount
  [ ] context over-subscription cascading re-renders
  [ ] console.* shipped to the browser instead of a user-facing error state (a regression
      of the fix in b24fa7a)

Efficiency:
  [ ] Simpler way? Fewer round trips? Better time complexity? N+1 per strike/contract?
  [ ] Is every changed line justified by the diff? Any dead code introduced?
  [ ] Does it match ruff's enforced rules (E, F, W, I, B, UP, SIM; ignoring E501, SIM102,
      SIM108, SIM117 per backend/pyproject.toml)?

REPORTING: For each finding, provide ALL of these:
  File:        backend/routes/example.py
  Line(s):     123-145
  Code:        `exact snippet`
  Verdict:     CORRECT | BUG | FRAGILE | MISSING
               (CORRECT = verified safe with proof.
                BUG = broken, needs fix.
                FRAGILE = works today, breaks if assumptions change.
                MISSING = guard/check that should exist but doesn't.)
  Severity:    HIGH | MEDIUM | LOW (skip for CORRECT)
  Confidence:  CERTAIN | LIKELY | UNCERTAIN
  Symptom:     What the trader sees on which surface if this fails
  Fix:         What to change
  Siblings:    Other files with same pattern (grep results, or "none found")

Report CORRECT findings too — they prove you actually checked. An audit that only
reports bugs didn't look hard enough at the safe code.

=== END AUDIT RULES ===
```

---

## Step 7 — Validate (this repo's real gates, Windows-real commands)

Run from `C:\Users\DARK HERO\Desktop\FLOWW2.0`.

**Prerequisite: MongoDB must be listening on `localhost:27017`** (or export `MONGO_URL`).
`backend/tests/conftest.py` builds a fresh Motor client per test with a 2 s server-selection timeout;
CI supplies a `mongo:7` service container. With no Mongo you get mass DB failures that are **not**
your change.

```bash
# Backend — .venv313 is the ONLY working interpreter (Python 3.13.15).
# backend/.venv is Python 3.11 with no pytest; backend/.venv/bin/python3 does not exist on Windows.
cd backend && ./.venv313/Scripts/python.exe -m pytest -q --tb=short           # 4581 tests collected
cd backend && ./.venv313/Scripts/python.exe -m pytest tests/routes/ -v        # targeted
cd backend && ./.venv313/Scripts/python.exe -m pytest -q -m "not flaky_env"   # 4571; CI's selection

# Ruff — NOT installed in .venv313. Install the CI-pinned version once, then lint:
cd backend && ./.venv313/Scripts/python.exe -m pip install "ruff==0.15.22"
cd backend && ./.venv313/Scripts/python.exe -m ruff check . --select F841
cd backend && ./.venv313/Scripts/python.exe -m ruff check .

# Frontend (node_modules present; command verified working)
cd frontend && CI=true npx craco test --watchAll=false
cd frontend && CI=true npx craco test --watchAll=false --testPathPattern="<name>"
cd frontend && npm run build

# Live endpoint check. There is NO project `uvicorn` on PATH — a bare `uvicorn` resolves to an
# unrelated venv without this backend's dependencies. Always go through the project interpreter:
cd backend && ./.venv313/Scripts/python.exe -m uvicorn server:app --port 8000
curl -s "http://localhost:8000/api/heatseeker/flip-zones?ticker=SPY"

# Anti-fabrication gate — commit claims vs actual code state (runs first in CI)
bash qc/audit/truth_audit.sh

# Rust, only if you touched rust/decoder-core (cargo 1.94.1 installed)
cd rust/decoder-core && cargo check
```

### Known-broken here — report, do not rely on, do not silently fix

- `qc/verify.sh` — macOS-authored (`backend/.venv/bin/ruff`, `.venv/bin/mypy`, `.venv/bin/bandit`).
- `qc/audit/security_regression.sh` — macOS-authored **and** broken on every platform: `set -euo
  pipefail` plus `((PASS++))` from zero exits 1 after the first check. Here it runs 2 of ~7 checks,
  greps `/Users/nav/...` paths that don't exist (a missing file scores as PASS), and exits 1. That
  exit code is **not** a regression. Do not run it as a gate.
- `.claude/settings.json` — every path-based allow/deny rule is `/Users/nav/...` absolute.
  **State this in any audit report: the deny rules meant to protect the frozen files are inert on
  this machine.** The non-path Bash denies (`--force`, `--no-verify`, `reset --hard`) still bind.
- `frontend/package.json` has no `lint` script; CI masks it with `|| true`. Deliberate — frozen file.
- `.githooks/commit-msg` runs `qc/audit/check_phase_claim.sh`, which rejects any subject starting
  `feat(Phase ` unless `truth_audit.sh` passes. **The hook is not installed in this clone**
  (`core.hooksPath` unset, `.git/hooks` holds only samples), so run the audit yourself. Never reach
  for the forbidden `--no-verify` when a hook rejects you.

### Baseline before attributing a failure to your change

- **Backend:** ~3-6 pre-existing failures — `test_heatseeker_v2.py::test_trinity_day_all_populated`,
  `::test_contract_drilldown_spy`, `test_v3_costsave.py::test_heatmap_spy_data_source_databento`,
  `::test_heatmap_qqq_free_tier_yfinance`.
- **Frontend:** **280/280 green across 44 suites.** The `continue-on-error: true` comment in `ci.yml`
  citing "12-18 failures" is stale (`BACKLOG.md` K4 retracts it), so **any** frontend failure is a
  real regression.

---

## Iron laws

1. **No corners cut.** Every line, every branch, every edge case inside the scope.
2. **No assumptions.** Prove it with traces or flag as uncertain. If unclear, AskUserQuestion.
3. **No footnotes.** Same pattern elsewhere = same-severity bug. Fix in the same pass.
4. **No "acceptable" downgrades.** Broken is broken regardless of current caller behavior.
5. **No hand-waving.** File path + line number + code snippet. Always.
6. **No skipping the refutation pass.** Fixes always get independently attacked.
7. **Never add `@pytest.mark.skip` / `xfail` / `it.skip()` to a previously-passing test.** If a fix
   makes a passing test fail, the fix is wrong — revert and find root cause.
8. **Never commit or push without Nav asking.** If you do commit: HEREDOC message with inline real
   evidence, subject `<type>(<scope>): <one-line>`, **pathspec `git add` only** (never `-A`/`.`), then
   the anti-skip gate — `git fetch origin && git log origin/main --oneline -1 | grep "<subject>"`.
   Empty grep = the push silently failed = STOP.
9. **Forbidden git ops:** `push --force`/`--force-with-lease`, `commit --no-verify`, `commit --amend`
   on someone else's commit, `rebase --abort`, `rebase -i`, `reset --hard`, `checkout .`,
   `restore .`, `clean -fd`. To undo work, ASK first.
10. **Paper only.** Never wire AI or automation to live order execution — analytics, paper, and
    simulation only.
11. Self-HALT: 15 minutes without progress → write status to `kanban/cards/agent_<n>_status.md` in the
    append-only format `[timestamp] AgentId :: status :: note :: HEAD=sha`.
12. **Owner-facing summary at the end** follows the global output style: short plain English, findings
    first, up to 3 ranked next steps.
