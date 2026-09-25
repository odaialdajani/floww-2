# CLAUDE.md — floww / Confluence Decoder

> **Environment note (2026-09-25):** the Canonical-paths / launch-machinery
> sections below were written for the Windows checkout
> (`C:/Users/DARK HERO/Desktop/FLOWW2.0`). R6 work also ships from the macOS
> checkout (`/Users/nav/Documents/GitHub/floww-2`, same `origin`). The
> "STOP / DEAD path" rules are machine-specific: on any checkout, verify with
> `git rev-parse --show-toplevel` and `git log origin/main` instead of halting
> solely because `pwd` names a different machine's canonical path.

> Auto-loaded by Claude Code on every session in this directory. Keep TIGHT — short × frequent = cost. Update only when something durably changes the way work should be done.

---

## Who I'm talking to

**Nav (Navdeep Kumar)** — PhD math/physics from Stanford, ex-Jane Street HFT, drives the project. Voice-to-text shorthand is common; understand "agent 3" / "Hermes" / "DS Pro" / "Owl Alpha" / "freebuff" / "Skylit" / "Heatseeker" without re-explaining.

**Operate as:** master architect. Terse. No preamble. No "I'll now…" / "Let me…". No platitudes. State what you found, what you'll do, and do it. Honest when wrong — Nav explicitly prefers "I broke this, here's how" over face-saving. Round 7's fake-completion incident is the negative-example floor.

**Output style:** plain code blocks, tables, real grep/git output. Do not invent SHAs. Do not claim something landed without verifying with `git log origin/main`. Never mark a test xfail/skip without architect approval.

---

## Project identity (1 paragraph)

**floww = Confluence Decoder** — free options-intel platform. **FastAPI** backend (port 8000) + **React** SPA (port 3000 — the REAL UI) + **Mongo** (Motor async) + **DuckDB** (ingestion engine) + **ML** (5 production gbm models per ticker: SPY/QQQ/DIA/IWM/TLT, walk-forward CV, 3-class predictions). A **Dash** app at `/dashboard/` is an embedded tab in the React UI — do not confuse them.

---

## Canonical paths (BURN THESE IN)

- **THE ONLY clone (production-tracked):** `C:/Users/DARK HERO/Desktop/FLOWW2.0` — Windows 11.
  Remote is `origin` → `https://github.com/odaialdajani/floww-2.git`.
- If `pwd` doesn't end in `Desktop/FLOWW2.0` → STOP and re-cd. Never work out of a copy or a second
  clone — stale-clone confusion is what caused 3+ historical incidents.
- **The macOS-era paths are DEAD on this machine** and must never be `cd`'d into or re-created:
  `/Users/nav/Documents/GitHub/floww`, `/Users/nav/GitHub/floww`, `/Users/nav/floww`. Any doc,
  script, or agent prompt still naming them is stale — correct it or ignore it, do not obey it.
- **The UI is React on :3000** (→ backend :8000). There is no separate terminal codebase — edits to
  `frontend/` + `backend/` here ARE the terminal. Open `http://localhost:3000` after starting both
  servers (see "Common command snippets").

**macOS launch machinery does NOT work here.** `scripts/launch_decoder.sh` and
`scripts/stop_decoder.sh` still exist in the repo but hardcode `$HOME/Documents/GitHub/floww` and
`open -a`; the `decoder` zsh alias, the `Chrome Apps.localized/Confluence Decoder.app` PWA, and the
`~/Library/LaunchAgents/com.confluence-decoder.plist` auto-start are all macOS-only leftovers.
There is no auto-startup on this box — start MongoDB, backend, and frontend yourself.

---

## Forbidden files (architect-frozen)

- `backend/services/ml/inference.py` — frozen except surgical bug fixes you must justify in commit body (A2's HOLD-zone fix is the canonical example, accepted at `888abd4`)
- `backend/services/dash_ui.py` — Round 7 frozen
- `backend/tests/conftest.py` — was frozen R9; R10 P0.1 (`docs/ROUND10_PLAN.md`) WAIVES the freeze with architect approval
- Model artifacts: `.joblib`, `.pt`, `*_manifest.json`, `*_meta.json` under `backend/models/`
- `frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`
- `frontend/src/App.js` — heavy concurrent WIP, surgical edits only with explicit approval

If a task requires touching a forbidden file, STOP and ask Nav first.

---

## Money path (the live-execution gate)

There are **three** code paths that can place a broker order. Know all three before touching anything
near execution — an earlier version of this section claimed there was only one, and that was wrong.

**1. Alpaca — MOUNTED and REACHABLE, and it is the safe one.**
`backend/routes/alpaca.py` `POST /order` → `AlpacaClient.place_stock_order`. The router IS included in
`server.py`. It is safe *by construction*, not by a gate: `backend/alpaca_client.py` hardcodes
`ALPACA_BASE_URL = "https://paper-api.alpaca.markets"` — Alpaca's paper endpoint. No live money can
leave through it. **Changing that constant to a live host is forbidden without Nav's approval.**

**2. `OrderRouter` — GATED, fail-closed, but currently guards nothing reachable.**
`backend/services/order_router.py` → `OrderRouter.submit_order()` runs
`if os.getenv("FLOWW_ENABLE_LIVE_SCHWAB") != "1":` before any outbound Schwab order POST and returns
`{"status": "error", "reason": "live order submission requires FLOWW_ENABLE_LIVE_SCHWAB=1 ..."}`.
Env unset = **refuse**. Pinned by `backend/tests/services/test_order_router_gate.py` — **13 collected
tests** (6 test functions, one parametrized over 6 env values).
**`OrderRouter` has no callers outside its own module and its tests**, so today this gate protects a
path nothing can reach. Do not read "the gate exists" as "the app is gated".
Note: `backend/routes/live_trading.py` is **not** this route surface — its handlers call
`get_live_policy` / `update_live_policy` / `stop_live_tape` in `server.py` and never touch
`OrderRouter`.

**3. `PublicBroker.place_order` — UNGATED, points at a LIVE gateway, currently unreachable.**
`backend/services/public_api.py` → `PublicBroker.place_order` POSTs to
`BASE_URL = "https://api.public.com"` — the real Public.com trading gateway, no sandbox host, **no
gate of any kind**. It is referenced by nothing outside `public_api.py`'s own
`place_limit_order` / `place_stop_order` helpers, so it is dead code right now. That is the only thing
keeping it safe.
**Wiring it — or any of its helpers — to a route, service, or agent without first putting a
fail-closed gate in front of it is FORBIDDEN without Nav's explicit approval.** The Public.com data
adapter (`services/public_api_adapter.py`) is deliberately data-only and must stay that way; two tests
enforce that it never references an order method.

**FORBIDDEN without Nav's explicit approval, on all three paths:** removing a check, inverting it,
defaulting it on, short-circuiting around it, repointing a paper host at a live one, or adding any new
code path that reaches a real broker order. This is not a refactor you get to make on your own
judgment — STOP and ask.

---

## Forbidden git operations

- `git push --force` / `--force-with-lease`
- `git commit --no-verify`
- `git commit --amend` on a commit not authored by yourself in the current session
- `git rebase --abort` (use `--continue` after fixing conflicts; if stuck, HALT)
- `git reset --hard`, `git checkout .`, `git restore .`, `git clean -fd`
- `git rebase -i` (interactive — not supported)

If you need to undo work, ASK first.

---

## Commit message style (mandatory)

Use a HEREDOC and include grep/test/curl evidence INLINE in the body:

```bash
git commit -m "$(cat <<'EOF'
fix(round-10-P0.2): restore fetch_spot_and_chains (A9 deletion miss)

Brief explanation of what + why.

Verification:
$ curl -s 'http://localhost:8000/api/heatseeker/flip-zones?ticker=SPY' | python3 -c "..."
OK
$ cd backend && ./.venv313/Scripts/python.exe -m pytest tests/services/test_fetch_spot_and_chains_present.py -v 2>&1 | tail -1
2 passed
EOF
)"
```

Subject line: `<type>(<scope>): <one-line>`. Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`. Scopes follow round naming (`round-9-h26`, `round-10-P0.1`, `round-10-architect`, etc.).

---

## Test discipline (non-negotiable)

- NEVER add `@pytest.mark.skip`, `@pytest.mark.xfail`, `it.skip()` to a previously-passing test
- If your change makes a passing test fail, your change is WRONG — revert and find root cause
- A test you write yourself MUST fail before your fix and pass after
- Round 7's fabricated completion log is the negative-example floor — never do that

**The CI gate set (`.github/workflows/ci.yml`) — green locally ≠ green in CI.**
These steps are HARD (no `|| true`, no `continue-on-error`) and will fail the build:

1. `bash qc/audit/truth_audit.sh` — runs first, before Python is even installed.
2. `ruff check . --output-format=github` with `pip install "ruff==0.15.22"`.
3. `bandit -r . --severity-level medium -q --exclude ./.venv,./tests --skip B101,B108,B301,B310,B313,B314,B324,B604,B608,B614,B615` — a single medium+ finding fails the build.
4. `python -m pytest tests/ -v --tb=short --cov=. -m "not flaky_env"` — `--cov=.` makes
   `[tool.coverage.report] fail_under = 60` in `backend/pyproject.toml` binding. Drop total coverage
   under 60% and CI fails even with every test passing.
5. `npm test -- --watchAll=false` in `frontend-build`, plus `npm run build`.

Only the mypy step is masked (`|| true`) — it is advisory.

**Version skew trap:** CI installs its own Python; local is 3.13.15. Never assume they match —
read the live pin before using new syntax:
`grep -n "python-version" .github/workflows/ci.yml`

---

## Current state (as of 2026-09-04)

- **Phase tracking is NOT duplicated here — on purpose.** `.planning/STATE.md` (current phase +
  log) and `.planning/ROADMAP.md` (phase and ticket list) are authoritative. Read both at session
  start. Copying phase details into this file is exactly what made it go stale before.
- **Deploy-ready:** full Oracle Always Free runbook at `deploy/free/README.md`. Bootstrap via
  `deploy/free/oracle-setup.sh` + read-only deploy key `oracle-vm-deploy`.
  Awaiting Nav's VM provisioning. (The old Obsidian cross-link is dropped — no Obsidian vault
  exists on this machine.)
- **Test suite — reproduce, don't trust a remembered number:**
  - Backend: **4640 tests collect, 0 collection errors** —
    `cd backend && ./.venv313/Scripts/python.exe -m pytest --collect-only -q`
    A *pass* count is deliberately not asserted here — see the MongoDB note below.
  - Frontend: **280 passed / 280 total across 44 suites** —
    `cd frontend && CI=true npx craco test --watchAll=false`
  - pytest config: **`backend/pytest.ini` is the single source of truth** (`asyncio_mode = auto`,
    `flaky_env` marker registered). pytest reports `configfile: pytest.ini`. A duplicate
    `[tool.pytest.ini_options]` block used to sit in `backend/pyproject.toml`; pytest **ignored it**
    and warned about it, so it was deleted. Do not re-add pytest settings to `pyproject.toml` —
    they will silently do nothing.
- **MongoDB is a prerequisite for a real pass count, not for the suite to start.**
  `backend/tests/conftest.py` builds a Motor client against `MONGO_URL`
  (default `mongodb://localhost:27017`) per test. Client construction is **lazy and does not raise**,
  so with Mongo down the suite still collects and most tests still pass — what you actually get is a
  ~2 s server-selection timeout on each DB-touching test (a slow run) plus failures confined to the
  DB-dependent tests. It does **not** error out at startup. Start `mongod`, then:
  `cd backend && ./.venv313/Scripts/python.exe -m pytest -q --tb=no`
- **The backend SHIPS ON PYTHON 3.11 — local dev is 3.13. All backend code must compile on 3.11.**
  `Dockerfile.backend` is `python:3.11-slim`; `.github/workflows/ci.yml` and `deploy.yml` pin 3.11.
  A 3.12-only nested-quote f-string in `routes/quant.py` once made the shipped image fail at
  `import server`. Syntax oracle before you commit new backend code:
  `cd backend && ./.venv/Scripts/python.exe -c "import py_compile;py_compile.compile('<file>',doraise=True)"`
  (`backend/.venv` is a bare Python 3.11.15 kept for exactly this check — it has no pytest.)
- **Architecture decisions are binding:** `docs/adr/` holds 6 **Accepted** ADRs (model promotion
  policy, data-source policy, backtest equity, deploy CORS, test discipline, coupling). Read the
  relevant one before touching ML promotion, data-source routing, or test assertions — ADR-0005 in
  particular makes the broad `data_source` taxonomy assertion in the heatmap tests deliberate.
- **Codebase intel:** `.planning/codebase/` — 7 GSD map documents
  (STACK/INTEGRATIONS/ARCHITECTURE/STRUCTURE/CONVENTIONS/TESTING/CONCERNS).
- **Learnings:** `.planning/LEARNINGS.md` — decisions/lessons/patterns/surprises
  extracted from the 2026-08-23/24 deploy-prep + test-infra session.
- Historical round notes (9/10) preserved below and in docs/.

<details>
<summary>Historical: Round 9/10 state</summary>

- **Round 9: CLOSED** at `4e1c1b8`. 50+ commits across 10 Owl Alphas + DS Pro v1 + DS Pro v2 closure.
- **Round 10 plan:** `docs/ROUND10_PLAN.md`. P0 tickets:
  - P0.1: conftest waiver + apply (drops 23 collection errors → 0)
  - P0.2: restore `fetch_spot_and_chains` (heatseeker flip-zones returns degraded)
  - P0.3: A9 STALE_IMPORT cleanup</details>
- **Phase 6 Task 10 (silent-failure audit): CLOSED** at `654a377`. Audit doc: `docs/superpowers/research/2026-06-20-decoder-endpoint-silent-failure-audit.md` (initial `ebd5f77`). All 4 Decision Queue fixes shipped on `origin/main`:
  - DQ #1 `routes/ml_api.py` 5× silent excepts → `5f0dec5` (observability contract; partial-data preserved over audit's `HTTPException(500)` recommendation)
  - DQ #2 `routes/gemini.py` 9× silent error returns → `23baf34` (`JSONResponse(503)` shim)
  - DQ #3 `routes/alerts.py` 2× silent error returns → `2b3af45` (`JSONResponse(503)` shim)
  - DQ #4 `routes/admin.py` 2× silent excepts → `72b00c8` (observability contract)
- **Active backlog summary:** `docs/ROUND10_PLAN.md` is the source of truth. `docs/ROUND9_FINAL_CLOSURE.md` for retrospective.

---

## Tech stack quick reference

| Layer | Tech | Entry point |
|---|---|---|
| Backend | FastAPI · Python 3.13.15 local (CI pin: see `ci.yml`) | `backend/server.py` → `./.venv313/Scripts/python.exe -m uvicorn server:app --port 8000` |
| Async DB | Motor (MongoDB) | `from server import db` |
| Tick DB | DuckDB | `backend/services/duckdb_engine.py` |
| ML | sklearn gbm + walk-forward CV | `backend/services/ml/inference.py` (frozen), `health_monitor.py`, `backtest.py` |
| Frontend | React 18 · create-react-app · craco · Jest | `frontend/src/` → `npm start` |
| Embedded UI | Dash | `backend/services/dash_ui.py` (frozen) — embedded in React at `/dashboard/` |
| Streamer | Schwab WebSocket | `backend/services/schwab_streamer.py` |
| Lint | ruff — config in `backend/pyproject.toml` | `cd backend && ./.venv313/Scripts/python.exe -m ruff check .` |
| Tests | pytest (asyncio auto mode) | `cd backend && ./.venv313/Scripts/python.exe -m pytest -q` |
| Frontend tests | jest via craco | `cd frontend && npx craco test --watchAll=false` |
| Deploy | Caddy + docker-compose (free-tier ARM) | `deploy/free/README.md` |
| CI | GitHub Actions | `.github/workflows/ci.yml` (also `lint.yml`, `deploy.yml`) |

**Venv:** `backend/.venv313/Scripts/python.exe` (Python 3.13.15). Always use this — never the system
Python, and **never `backend/.venv`**: that is a bare Python 3.11.15 with no pytest and no ruff, and
it fails with `No module named pytest`. There is no `backend/.venv/bin/python3` on this machine —
that is a POSIX path on a Windows box.

**Ruff rules (real config, `backend/pyproject.toml`):** `select = ["E","F","W","I","B","UP","SIM"]`,
`ignore = ["E501","SIM102","SIM108","SIM117"]`, `line-length = 120`, `target-version = "py313"`,
`extend-exclude = [".venv","services/ml/inference.py","services/dash_ui.py","tests/conftest.py"]`,
plus per-file-ignores. Note `E722` is NOT in `select` — it comes in via the `E` family.
**ruff is not installed locally.** Install it at CI's exact pin before you lint:
`cd backend && ./.venv313/Scripts/python.exe -m pip install "ruff==0.15.22"`.

---

## Common command snippets

Windows 11. PowerShell is the primary shell; Git Bash is available for POSIX scripts. These are
verified to run on this machine — the macOS forms (`lsof`, `nohup`, `open -a`) are not.

```powershell
# Launch backend (background, detached) — verified: HTTP 200 on /api/health ~6s after start
Start-Process -FilePath "C:\Users\DARK HERO\Desktop\FLOWW2.0\backend\.venv313\Scripts\python.exe" `
  -ArgumentList "-m","uvicorn","server:app","--port","8000" `
  -WorkingDirectory "C:\Users\DARK HERO\Desktop\FLOWW2.0\backend" `
  -WindowStyle Hidden -RedirectStandardError "$env:TEMP\floww-uvicorn.err"
Start-Sleep -Seconds 8
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/health" -UseBasicParsing | Select-Object StatusCode

# Free port 8000 (if backend stuck) — the lsof/xargs equivalent
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object { taskkill /PID $_.OwningProcess /F }

# See what's holding a port
netstat -ano | Select-String ":8000\s.*LISTENING"
```

```bash
# Launch frontend (Git Bash) — verified: "Compiled successfully!" + HTTP 200 on :3000
cd frontend && BROWSER=none npm start
# then open http://localhost:3000 in a browser (no PWA on this machine)
# stop it: Get-NetTCPConnection -LocalPort 3000 -State Listen | ForEach-Object { taskkill /PID $_.OwningProcess /F /T }

# Pytest sweeps  (a PASS run needs MongoDB on localhost:27017; collection does not)
cd backend && ./.venv313/Scripts/python.exe -m pytest --collect-only -q 2>&1 | tail -3   # collection
cd backend && ./.venv313/Scripts/python.exe -m pytest -q --tb=no 2>&1 | tail -5          # pass count
cd backend && ./.venv313/Scripts/python.exe -m pytest tests/services/ -k <kw> -v         # targeted

# Frontend tests
cd frontend && CI=true npx craco test --watchAll=false

# Lint — ruff is NOT installed locally; install CI's exact pin first
cd backend && ./.venv313/Scripts/python.exe -m pip install "ruff==0.15.22"
cd backend && ./.venv313/Scripts/python.exe -m ruff check .                  # rules from pyproject.toml
cd backend && ./.venv313/Scripts/python.exe -m ruff check --select E722 .    # bare excepts only
cd backend && ./.venv313/Scripts/python.exe -m ruff check --fix .            # auto-fix safe issues

# Origin verify (anti-skip gate)
git fetch origin && git log origin/main --oneline -1 | grep '<commit subject>'
```

**MongoDB prerequisite:** `mongod` is not on PATH and no MongoDB service is registered on this box.
Confirm it's up before a full backend run — `netstat -ano | Select-String ":27017\s.*LISTENING"`.
Empty output means the pytest suite will error out on the Motor fixture in `tests/conftest.py`.

---

## Where the durable knowledge lives

- **Project memory:** `~/.claude/projects/C--Users-DARK-HERO-Desktop-FLOWW2-0/memory/` — the
  Windows-side memory directory for this repo. It is currently **empty**; there is no `MEMORY.md`
  and none of the `session_2026-05-*_round9/round8` notes exist here. The macOS index
  `~/.claude/projects/-Users-nav-Documents-GitHub-floww/` does **not** exist on this machine — treat
  the repo's own `docs/` + `.planning/` as the durable record instead.
- **Architecture decisions:** `docs/adr/` — 6 ADRs, all **Accepted**, index at `docs/adr/README.md`.
  They bind future work: 0001 model promotion policy (4 gates), 0002 data-source policy & priority
  chain, 0003 backtest equity model, 0004 deploy CORS headers, 0005 test discipline &
  data-source assertion policy, 0006 Black Friday / Ferrari coupling boundary. Read the relevant
  one BEFORE changing anything in its area; supersede, never rewrite.
- **GSD phase tracking:** `.planning/STATE.md` (current phase) + `.planning/ROADMAP.md` (tickets) —
  authoritative, checked in, and the only place phase status should be read from.
- **Active plans in repo:**
  - `docs/ROUND10_PLAN.md` — current backlog (P0/P1/P2)
  - `docs/ROUND9_FINAL_CLOSURE.md` — retrospective
  - `docs/ROUND10_A9_DELETION_VERIFICATION.md` — 433-name per-name audit
  - `docs/ROUND10_CONFTEST_WAIVER_TRIAGE.md` — pytest collection error analysis
  - `docs/ROUND10_LEAK_PREVENTION.md` — 3-pattern playbook
- **Kanban:** `kanban/cards/*.md` (per-agent pulses), `kanban/board.yaml`
- **Round 9 v2 launch pack:** `round9_followup_v2/` (10-agent prompts + preamble + launcher)

---

## Dual GEX scale convention (DO NOT "FIX" — intentional)

Two GEX scales coexist by design. They share the name `gex_total` but differ by a factor of `spot`. **They are NOT interchangeable.**

| Engine | Scale | Formula | Purpose |
|---|---|---|---|
| `services/gex_aggregator.py` | S² (dollar-GEX) | `sign * γ * OI * 100 * spot² * 0.01` | Display (Heatseeker, UI heatmaps) |
| `services/gex_history.py` | S¹ (feature-GEX) | `sign * γ * OI * 100 * spot * 0.01` | ML features → frozen GBM models |

**Relationship:** `display_net_gex == spot * feature_net_gex` — pinned by golden oracle tests in `tests/services/test_gex_aggregator_oracle.py`.

**Model-locked constants in gex_history.py:** `_RISK_FREE = 0.045`, `_IV_FALLBACK = 0.20`. Changing these shifts every trained model's `gex_total` feature. Requires retrain. Lock tests exist.

**If you need to unify:** that's a retraining migration (re-backfill gex_history collection + retrain all production GBM models). Out of scope for correctness audits.

**Audit docs:** `docs/superpowers/specs/2026-06-13-gex-gamma-correctness-audit-*`

---

## Skill usage (`/using-superpowers`)

This project uses the **superpowers** skill suite. Invoke `/using-superpowers` if you don't already see it loaded, then follow the rule: **invoke any 1%-relevant skill BEFORE responding**.

Core skills you'll use often on this project:
- `superpowers:writing-plans` — for any multi-step task or multi-agent prompt
- `superpowers:executing-plans` — when given a plan file to run task-by-task
- `superpowers:test-driven-development` — for every feature/bugfix (failing test → patch → passing test)
- `superpowers:verification-before-completion` — before claiming work done
- `superpowers:systematic-debugging` — for any bug, before proposing fixes
- `superpowers:brainstorming` — before any creative work

Anti-pattern: never call a skill "overkill" and skip it. Round 7's fabricated completion log is what happens when you do.

---

## How to start a task (the loop)

1. **State the goal in one sentence.** Confirm with Nav if the requirement is ambiguous.
2. **Pre-flight:** `pwd` + `git fetch origin && git status --short` + capture pytest baseline if relevant.
3. **Write a failing test** (TDD) when adding behavior or fixing a bug — test pins the contract.
4. **Apply the smallest patch** that makes the test pass.
5. **Run the test + the wider module sweep** — must not regress.
6. **Commit** with HEREDOC + inline evidence.
7. **Push + verify on origin** — `git fetch origin && git log origin/main --oneline -1 | grep <subject>`.
8. If the grep fails, the push silently failed — STOP and investigate.

For multi-step tasks (3+ steps), use `TaskCreate` to track progress.

---

## When to ask Nav vs decide

**Decide yourself:**
- TDD test design (use judgment)
- Patch implementation when scope is clear
- Commit message wording (follow the style above)
- Whether to use a skill (default: yes)
- Whether to run pytest after a change (default: always)

**Ask first:**
- Touching a forbidden file
- Reverting another agent's commit
- Force-pushing or any destructive git op
- Changing the architecture of an existing module
- Scope creep beyond the stated task
- Marking a test xfail/skip (default: never; ask if you think you need to)

---

## Anti-skip gate (per task)

Every commit MUST be followed by:
1. `git pull --rebase origin main && git push origin main`
2. `git fetch origin && git log origin/main --oneline -1 | grep <subject substring>`
3. The grep MUST find your subject. Empty → push silently failed → STOP.

This is what catches Round 7's fake-completion pattern in real time.

---

## What Nav drives (not Claude)

- PyCharm, DataGrip, WebStorm — Nav's IDE work
- Anything that involves clicking a button in an IDE
- Final visual review of frontend changes (Nav looks at React on `http://localhost:3000`)
- Decisions about scope/priority/architecture direction

What Claude drives: shell, git, pytest, ruff, npm, file edits, docs, agent prompt authoring.

---

## Dev Environment

**This machine (Windows 11, verified 2026-09-04):**
- Python **3.13.15** at `backend/.venv313/Scripts/python.exe` (pytest 9.1.1, uvicorn 0.52.4)
- Node **v24.11.1** / npm **11.12.1**; `frontend/node_modules` installed
- cargo **1.94.1** (`rust/decoder-core` is a real crate)
- git **2.49.0.windows.1**; shells: PowerShell 7 (primary) + Git Bash
- **NOT present / NOT on PATH:** `ruff`, `mongod`, `docker`, `brew`, `lsof`. MongoDB is not
  listening on 27017 by default — start it before any backend pytest run.

<details>
<summary>Historical: retired macOS box (2026-07-28) — none of this applies on Windows</summary>

**Homebrew:** 296 formulae, 13 casks. Key tools available globally:
- **Runtimes:** Python 3.12+3.14, Node 26, Go 1.26.4, Rust 1.96
- **Editors:** neovim 0.12.3, helix 25.01
- **Terminal:** tmux 3.6b, zellij 0.44.3, starship, atuin, fzf, zoxide
- **Git:** delta, difftastic, lazygit, tig, gitui, diff-so-fancy
- **Databases:** MongoDB 8.2.9, PostgreSQL 16.14, Redis 8.8.0 (all running)
- **Containers:** Docker 29.5.3 via colima, lazydocker, dive
- **K8S:** kubectl, helm, minikube, kind, k9s
- **Python tools:** ruff, mypy, isort, pre-commit, poetry, pyenv, pipx
- **Rust tools:** cargo-watch, cargo-edit, cargo-expand, cargo-audit, cargo-generate
- **Go tools:** golangci-lint, gofumpt, staticcheck, goreleaser
- **Linting:** shellcheck, shfmt, yamllint, prettier, eslint, clang-format
- **Data:** dasel, jq, yq, fx, jc, xsv, csvkit, miller
- **Network:** doggo, mitmproxy, socat, netcat, nmap

**Services running:** redis, postgresql@16 (via brew services). Start with `brew services start redis postgresql@16` if needed.
</details>

---

## Known vendor-side issues (DO NOT chase as code bugs)

The floww backend depends on a small number of external services. Most are polite and surface clear errors. **A few return errors that LOOK like code bugs but are actually vendor-side account state** — chasing these as code problems wastes time and ships unnecessary defensive code. The canonical example is below; future agents SHOULD NOT reopen it.

### Databento Historical API — `auth_account_locked`

**Symptom in the backend log** (wherever you redirected uvicorn's output): repeated WARN lines of the form

```
WARNING databento: databento OI fetch fail <PARENT> <DAY>:
{"auth_account_locked":"Your account has been locked for security reasons. (auth_account_locked)"}
```

where `<PARENT>` ∈ `{SPY.OPT, QQQ.OPT, IWM.OPT, DIA.OPT, TLT.OPT, SPXW.OPT, AAPL.OPT, ...}` (any OPRA.PILLAR parent).

**Root cause:** databento's API gateway locks the account at the vendor's discretion — payment failure, burst-pattern detection, security incident flag, or manual support action. The lock is **not** recoverable by rotating the API key. `DATABENTO_API_KEY` being SET in `backend/.env` is irrelevant.

**What this is NOT:**

- NOT an application error — the SDK layer received a valid 403 with a clear vendor-side reason.
- NOT recoverable by changing the code — no code path can bypass databento's account-level lock.
- NOT a missing-key scenario — that returns a different error string (`Databento client not initialized — missing DATABENTO_API_KEY`) and is local-config-only.

**Correct action (in order):**

1. File a vendor support ticket asking databento for cause + recovery ETA + time-of-incident alignment. (A paste-ready draft used to live at `/tmp/databento-support-ticket.md` on the old macOS box; that file does not exist here — re-draft it.)
2. Leave `DISABLE_DATABENTO` UNSET in `backend/.env` while waiting. The conviction tier strip is **cvserver-driven** — databento OI is non-critical and the per-parent circuit breaker absorbs the WARN log noise in the meantime.
3. Wait for vendor unlock. **Do NOT rotate the API key** — won't help, the lock is account-level not key-level.

**Defense-in-depth is already deployed:** `backend/databento_provider.py` (v2.6+) carries a per-parent circuit breaker (15 pytest tests in `backend/tests/services/test_databento_circuit.py`) that caps the WARN spam to one per parent per 10-min window. This is NOT the fix — it's the noise floor. The fix is the vendor unlock.

**Cross-references:**

- Defense-in-depth code: `backend/databento_provider.py` (per-parent `_circuit` + `is_circuit_open`) — verified present in this repo.
- The macOS-era pointers for this incident (`Documents/Obsidian Vault/2026-07-07.md`,
  `/tmp/databento-support-ticket.md`, `/tmp/floww-backend.log`) do **not** exist on this machine.
  Re-derive the log path from however you launched uvicorn; re-draft the ticket if you need it.

**Resolution status:** `_unresolved_ — vendor support ticket filed; awaiting cause + ETA`. Update this line once databento replies, with the cause + unlock timestamp. (There is no Obsidian vault on this machine — this line is the record.)

---

End of CLAUDE.md. If you find yourself violating any rule above, STOP and tell Nav before continuing.
