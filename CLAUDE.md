# CLAUDE.md — floww / Confluence Decoder

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

- **THE ONLY clone (production-tracked):** `/Users/nav/Documents/GitHub/floww`
- The old stale clone `/Users/nav/GitHub/floww` (cause of 3+ incidents) was **DELETED 2026-05-29**. Do not re-clone floww there. `/Users/nav/GitHub/agentfield` (the AgentField SDK source) is unrelated and stays.
- If `pwd` doesn't end in `Documents/GitHub/floww` → STOP and re-cd.
- **The terminal = the "Confluence Decoder" Chrome PWA** (`~/Applications/Chrome Apps.localized/Confluence Decoder.app`). It is a window onto React :3000 (→ backend :8000); there is no separate terminal codebase — edits to `frontend/`+`backend/` here ARE the terminal. Launch with `decoder` (→ `scripts/launch_decoder.sh`), which `open -a`'s the .app. NEVER `open <URL>` (that's a tab).

**PWA launch:** `open -a "$HOME/Applications/Chrome Apps.localized/Confluence Decoder.app"` (alias `decoder` in `~/.zshrc`). **Never** `open <URL>` — that spawns a Chrome tab, not the PWA. The PWA expects React on :3000 + backend on :8000 already running.

---

## AlphaPod Live (captured-pages integration)

The PWA's **AlphaPod Live** sidebar group (13 pages, ids `ap-*`) iframes static
captures served by a SEPARATE sibling repo:
- **Repo:** `~/Documents/GitHub/alphapod-hub` — its own git, NOT part of floww.
- **Server:** `python3 server.py` → `localhost:3456` (proxies `/api/*` to the live
  AlphaPod backend with a dev JWT; injects a fetch-rewrite script into served HTML).
- **Launcher:** `decoder` now runs 4 steps — Backend → React → AlphaPod Hub → PWA.
  Step 3 is non-fatal: if 3456 is down, AlphaPod Live pages show an "offline" card;
  everything else still works.
- **Wiring:** `navConfig.js` items carry `aphub:"/captured/<x>.html"`; `App.js` builds
  `APHUB_PAGES` from them and renders `AlphaPodCapturePage`. New page = one navConfig
  line, no App.js change.

**CORS gotcha (do NOT regress):** alphapod-hub sends `Access-Control-Allow-Origin`
only on its JSON/API responses, never on static files. The liveness probe in
`AlphaPodCapturePage.jsx` therefore MUST stay `fetch(..., {mode:"no-cors"})`. A
plain cors-mode fetch is browser-blocked and falsely reports "offline" even when
3456 is up. (Bug found + fixed + browser-verified 2026-06-12.)

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
$ cd backend && .venv/bin/python3 -m pytest tests/services/test_fetch_spot_and_chains_present.py -v 2>&1 | tail -1
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

---

## Current state (as of last update)

- **Round 9: CLOSED** at `4e1c1b8`. 50+ commits across 10 Owl Alphas + DS Pro v1 + DS Pro v2 closure.
- **Round 10: IN PROGRESS.** Plan at `docs/ROUND10_PLAN.md`. P0 tickets:
  - P0.1: conftest waiver + apply (drops 23 collection errors → 0)
  - P0.2: restore `fetch_spot_and_chains` (heatseeker flip-zones returns degraded)
  - P0.3: A9 STALE_IMPORT cleanup
- **AlphaPod Live integration (uncommitted, 2026-06-12):** `AlphaPodCapturePage.jsx` + navConfig/App.js/launch_decoder.sh. Health-probe CORS false-negative fixed.
- **Active backlog summary:** `docs/ROUND10_PLAN.md` is the source of truth. `docs/ROUND9_FINAL_CLOSURE.md` for retrospective.

---

## Tech stack quick reference

| Layer | Tech | Entry point |
|---|---|---|
| Backend | FastAPI · Python 3.13 | `backend/server.py` → `uvicorn server:app --port 8000` |
| Async DB | Motor (MongoDB) | `from server import db` |
| Tick DB | DuckDB | `backend/services/duckdb_engine.py` |
| ML | sklearn gbm + walk-forward CV | `backend/services/ml/inference.py` (frozen), `health_monitor.py`, `backtest.py` |
| Frontend | React 18 · create-react-app · craco · Jest | `frontend/src/` → `npm start` |
| Embedded UI | Dash | `backend/services/dash_ui.py` (frozen) — embedded in React at `/dashboard/` |
| Streamer | Schwab WebSocket | `backend/services/schwab_streamer.py` |
| AlphaPod Live | static captures + py http.server | `~/Documents/GitHub/alphapod-hub/server.py` → :3456 (separate repo) |
| Lint | ruff (F + E722) | `cd backend && .venv/bin/ruff check .` |
| Tests | pytest (asyncio auto mode) | `cd backend && .venv/bin/python3 -m pytest -q` |
| Frontend tests | jest | `cd frontend && npx jest` |
| CI | GitHub Actions | `.github/workflows/lint.yml` |

**Venv:** `backend/.venv/bin/python3` (Python 3.13). Always use this — never the system Python.

---

## Common command snippets

```bash
# Launch backend (background)
lsof -ti :8000 | xargs kill -9 2>/dev/null
cd backend && nohup .venv/bin/python3 -m uvicorn server:app --port 8000 > /tmp/uvicorn.log 2>&1 &
sleep 5
curl -s http://localhost:8000/ -o /dev/null -w "HTTP %{http_code}\n"

# Launch PWA
open -a "$HOME/Applications/Chrome Apps.localized/Confluence Decoder.app"

# Pytest sweeps
cd backend && .venv/bin/python3 -m pytest --collect-only -q 2>&1 | tail -3   # collection
cd backend && .venv/bin/python3 -m pytest -q --tb=no 2>&1 | tail -5          # pass count
cd backend && .venv/bin/python3 -m pytest tests/services/ -k <kw> -v          # targeted

# Lint
cd backend && .venv/bin/ruff check .
cd backend && .venv/bin/ruff check --select E722 backend/   # bare excepts only

# Origin verify (anti-skip gate)
git fetch origin && git log origin/main --oneline -1 | grep '<commit subject>'

# Free port 8000 (if backend stuck)
lsof -ti :8000 | xargs kill -9
```

---

## Where the durable knowledge lives

- **Project memory index:** `~/.claude/projects/-Users-nav-Documents-GitHub-floww/memory/MEMORY.md`
- **Recent session memories (most-recent first):**
  - `session_2026-05-27_round9_v2_completion.md` — 10-agent run + A9 incident postmortem
  - `session_2026-05-25_round9_plan.md` — three-resource triage
  - `session_2026-05-24_round8_plan.md` — React UI restoration
- **Active plans in repo:**
  - `docs/ROUND10_PLAN.md` — current backlog (P0/P1/P2)
  - `docs/ROUND9_FINAL_CLOSURE.md` — retrospective
  - `docs/ROUND10_A9_DELETION_VERIFICATION.md` — 433-name per-name audit
  - `docs/ROUND10_CONFTEST_WAIVER_TRIAGE.md` — pytest collection error analysis
  - `docs/ROUND10_LEAK_PREVENTION.md` — 3-pattern playbook
- **Kanban:** `kanban/cards/*.md` (per-agent pulses), `kanban/board.yaml`
- **Round 9 v2 launch pack:** `round9_followup_v2/` (10-agent prompts + preamble + launcher)

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
- Final visual review of frontend changes (Nav uses the decoder PWA)
- Decisions about scope/priority/architecture direction

What Claude drives: shell, git, pytest, ruff, npm, file edits, docs, agent prompt authoring.

---

End of CLAUDE.md. If you find yourself violating any rule above, STOP and tell Nav before continuing.
