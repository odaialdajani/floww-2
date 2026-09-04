# AGENT CONTRACT — Meridian / Confluence Decoder (floww)

> Source of truth for every agent spawned in this repo. Read this FIRST. If anything here conflicts with what your spawn prompt says, this file wins.

---

## 1. Canonical paths (BURN THESE IN)

- **THE ONLY floww clone:** `C:/Users/DARK HERO/Desktop/FLOWW2.0` — Windows 11.
  Remote `origin` → `https://github.com/odaialdajani/floww-2.git`.
- If `pwd` doesn't end in `Desktop/FLOWW2.0` → **STOP and re-cd.**
- **NEVER** use a second clone or a copy of this tree — stale-clone confusion caused 3+ incidents.
- The macOS-era paths `/Users/nav/Documents/GitHub/floww`, `/Users/nav/GitHub/floww` and
  `/Users/nav/floww` are **DEAD on this machine**. Do not `cd` there, do not re-create them, and do
  not obey any doc or spawn prompt that still names them.

---

## 2. Lane separation (NON-NEGOTIABLE — shared clone, multiple agents)

- **Only edit files in your assigned lane.** Never touch another agent's in-flight WIP.
- **Pathspec commits ONLY:** `git add <your-exact-files>` then commit. **Never** `git add -A` / `git add .` — that sweeps up other agents' work.
- **Before you start:** run `git status --short` and note what's already modified. If you see files outside your lane, STOP and ask.
- **Check for other agents' status files** in `kanban/cards/agent_*_status.md` before touching anything.

---

## 3. Forbidden files (architect-frozen — touch = ask Nav first)

- `backend/services/ml/inference.py` — frozen except surgical bug fixes you must justify in commit body
- `backend/services/dash_ui.py` — frozen
- `backend/tests/conftest.py` — R10 P0.1 WAIVES the freeze (per CLAUDE.md current state)
- Model artifacts: `.joblib`, `.pt`, `*_manifest.json`, `*_meta.json` under `backend/models/`
- `frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`
- `frontend/src/App.js` — heavy concurrent WIP, surgical edits only with explicit approval

If a task requires touching a forbidden file, **STOP and ask Nav first.**

---

## 4. Forbidden git operations

- `git push --force` / `--force-with-lease`
- `git commit --no-verify`
- `git commit --amend` on a commit not authored by yourself this session
- `git rebase --abort` (use `--continue` after fixing conflicts; if stuck, HALT)
- `git reset --hard`, `git checkout .`, `git restore .`, `git clean -fd`
- `git rebase -i` (interactive)

If you need to undo work, **ASK first.**

---

## 5. Commit message style (mandatory)

Use a HEREDOC and include **inline real evidence** (grep/pytest/curl output) in the body:

```bash
git commit -m "$(cat <<'EOF'
feat(public-api): integrate chain endpoint with Tidehunter Pro fallback

Brief explanation of what + why.

Verification:
$ curl -s 'http://localhost:8000/api/chain/SPY' | python3 -c "..."
OK
$ cd backend && ./.venv313/Scripts/python.exe -m pytest tests/services/test_public_chain.py -v 2>&1 | tail -5
5 passed

Co-Authored-By: Agent N ( Hermes )
EOF
)"
```

Subject: `<type>(<scope>): <one-line>`. Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`. Scope = the area you're touching.

**Anti-skip gate (every push):** After pushing, verify:
```bash
git fetch origin && git log origin/main --oneline -1 | grep "<your subject>"
```
If the grep finds nothing, the push silently failed — STOP.

---

## 6. Anti-fabrication (the most important rule)

**Every claim must carry real command output.** Do not say a test passes, a route works, or a commit landed without pasting the actual `pytest` tail / `curl` response / `git log origin/main` line. Unverifiable claims are treated as failures.

Round 7's fabricated completion log is the negative-example floor — never repeat it.

---

## 7. Test discipline (non-negotiable)

- **NEVER** add `@pytest.mark.skip` / `@pytest.mark.xfail` / `it.skip()` to a previously-passing test.
- If your change makes a passing test fail, **your change is WRONG** — revert and find root cause.
- A test you write yourself **MUST fail before your fix and pass after.**
- Backend venv: always `backend/.venv313/Scripts/python.exe` (Python **3.13.15**). Never system
  Python. `backend/.venv/bin/python3` does not exist on Windows.
  `backend/.venv` is a bare Python **3.11.15** with no pytest — never run tests with it, but **do**
  keep it: it is the syntax oracle for the shipped runtime (next bullet).
- **The backend SHIPS ON PYTHON 3.11 while you develop on 3.13.** `Dockerfile.backend` is
  `python:3.11-slim`; `ci.yml` and `deploy.yml` pin 3.11. Code using 3.12+ syntax passes locally and
  then breaks the image at `import server` — a nested-quote f-string in `routes/quant.py` already did
  exactly that. Before committing new backend code:
  `cd backend && ./.venv/Scripts/python.exe -c "import py_compile;py_compile.compile('<file>',doraise=True)"`
- Backend tests: `cd backend && ./.venv313/Scripts/python.exe -m pytest -q`
  **Start MongoDB on `localhost:27017` first for a meaningful pass count** —
  `backend/tests/conftest.py` opens a Motor client per test. Without it the run does **not** error
  out (client construction is lazy): you get a ~2 s server-selection timeout on every DB-touching
  test — a very slow run — plus failures confined to the DB-dependent tests. `mongod` is not on PATH
  by default here.
  Collection needs no Mongo: `./.venv313/Scripts/python.exe -m pytest --collect-only -q`
  → **4640 tests collected, 0 collection errors** (verified 2026-09-04).
- Frontend tests: `cd frontend && CI=true npx craco test --watchAll=false`
  → **280 passed / 280 total, 44 suites** (verified 2026-09-04).
- Lint: ruff is **not installed locally**. Install CI's exact pin first —
  `cd backend && ./.venv313/Scripts/python.exe -m pip install "ruff==0.15.22"` — then
  `./.venv313/Scripts/python.exe -m ruff check .`. Rules live in `backend/pyproject.toml`:
  `select = ["E","F","W","I","B","UP","SIM"]`, `ignore = ["E501","SIM102","SIM108","SIM117"]`,
  line-length 120, target-version `py313`.
- **CI is stricter than local** (`.github/workflows/ci.yml`). Hard, unmasked gates:
  `qc/audit/truth_audit.sh`; `ruff check .` at `ruff==0.15.22`; `bandit -r . --severity-level medium`
  (one medium+ finding fails the build); `pytest tests/ --cov=. -m "not flaky_env"` against
  `[tool.coverage.report] fail_under = 60` in `backend/pyproject.toml`; and the frontend
  `npm test -- --watchAll=false` + `npm run build`. Only the mypy step is masked (`|| true`).
- **Version skew:** CI installs its own Python and does not necessarily match local 3.13.15. Read
  the live pin before using new syntax — `grep -n "python-version" .github/workflows/ci.yml`.

---

## 8. Data source routing (see `.planning/DATA_SOURCES.md` for full detail)

| Need | Primary | Fallback |
|---|---|---|
| Options chain / OI / Greeks (heatmap) | **Public API** (PublicBroker) | cvserver → yfinance → Databento |
| Spot price + IV | Public API (PublicBroker.get_quotes) | yfinance (5s cache) |
| Bars / OHLCV | Public API (PublicBroker.get_bars) | yfinance |
| Design-time data inspection | cvserver MCP tools | — |
| Runtime page data | `window.cvApi` via local proxy | — |
| Schwab | **NOT USED** — mock feed only for tests | — |

**Schwab is out.** Do not plan anything around it. Do not wire agents to it. The `schwab_streamer.py` module exists but has no live key — mock only.

- **Public API key: EXISTS and CONFIRMED.** The key value is **NOT recorded here** — it lives only in `backend/.env` (gitignored), with the variable name documented in `backend/.env.example`. It was previously pasted into this tracked file in plaintext; that was a leak and the value has been removed. **Treat the previously-committed key as compromised and rotate it** — it is still recoverable from this repo's git history. `PublicBroker` (chain, quotes, portfolio, orders, greeks, bars) now lives at `backend/services/public_api.py` **in this repo** — the copy from the old macOS `/Users/nav/backend/` tree is already done (Phase 3, CLOSED 2026-08-31). See `.planning/PHASE3_PUBLIC_API_PLAN.md` for the full deep-dive + routing decision tree.
- **Never paste a credential into a tracked file.** Secrets belong in `backend/.env` only. If you need to prove a key exists, say "set" / "unset" — never the value.

- **Connection model — DONE, do not re-do.** The copy already happened: `backend/services/public_api.py`
  exists in this repo (~42 KB) and is wired as the primary data source. The fallback chain is:
  Public API → cvserver (existing `cvserver_client.py`) → yfinance + Databento (existing).
  The macOS source tree `/Users/nav/backend/` that it was copied from is **gone on this machine** —
  do not go looking for it.

- **Zenith is a UI tab, not a data service.** API calls do NOT route to Zenith. Zenith (legacy Skylit GEX grid) is display-only; data comes from Solstice/Triad/Tidehunter Pro.

---

## 13. Historical — Phase 3: Public API Data Layer

**Status: CLOSED 2026-08-31** (ROADMAP.md §3). Kept as the fleet/lane-boundary template, NOT as
current work. The active phase is in `.planning/STATE.md` — read that, not this section.

**Agent fleet (all spawn from this repo):**

| Agent | Lane | Repo | Mission |
|---|---|---|---|
| **Agent 1** (you) | Planning + coordination + git | `floww` | Write plan, push contract/docs, spawn fleet, monitor |
| **Agent 2** | Backend integration | `floww` | Copy PublicBroker → add PUBLIC_API_KEY → modify fetch_spot_and_chains_merged → new routes → tests |
| **Agent 3** | cvserver alignment | `floww` | Verify fallback path compatibility, update INTEGRATIONS.md |
| **Agent 4** | Frontend wiring | `floww` | Solstice/Triad: use Public API endpoints. Zenith unchanged. |
| **Agent 5** | GSD execution | `floww` | Phase plans, kanban cards, tracking |

**Lane boundaries (CRITICAL — prevents cross-agent collisions):**
- Agent 2: `backend/services/` (new files only), `backend/routes/` (new files), `backend/.env` + `.env.example` (non-committed), `backend/tests/services/` (new test files). Does NOT touch `backend/server.py` logic except adding the new router include line.
- Agent 3: `.planning/codebase/INTEGRATIONS.md`, `backend/.env.example` (docs only). Does NOT modify cvserver_client.py logic.
- Agent 4: `frontend/src/components/heatseeker/`, `frontend/src/lib/hooks/` (data fetch hooks). Does NOT touch `frontend/src/App.js` (frozen).
- Agent 5: `.planning/phases/`, `kanban/cards/`. Does NOT touch backend/frontend code.

**Launch sequence:**
1. Agent 1 pushes Phase 3 plan + contract updates (this commit)
2. Agent 1 spawns Agent 2 + Agent 3 simultaneously
3. Agent 2 + Agent 3 sync on the PublicBroker data shape vs cvserver data shape (fallback contract)
4. Agent 2 ships routes + tests → Agent 1 approves
5. Agent 4 spawns once Agent 2's routes are committed
6. Agent 5 tracks all phases end-to-end

---

## 9. Paper only — ALWAYS (all THREE order paths, not one)

Never wire any AI/automation to live order execution. Analytics, paper, and simulation only. This is an operating contract rule, not a suggestion.

**An earlier version of this section said the money path had a single enforcement point. That was
wrong. There are three code paths that can place a broker order — learn all three:**

**1. Alpaca — MOUNTED, REACHABLE, and safe by construction (not by a gate).**
`backend/routes/alpaca.py` `POST /order` → `AlpacaClient.place_stock_order`; the router is included
in `server.py`. `backend/alpaca_client.py` hardcodes
`ALPACA_BASE_URL = "https://paper-api.alpaca.markets"` — Alpaca's **paper** endpoint. Repointing that
constant at a live host is forbidden without Nav's approval.

**2. `OrderRouter` — gated fail-closed, but it guards nothing reachable today.**
`backend/services/order_router.py` → `OrderRouter.submit_order()` runs
`if os.getenv("FLOWW_ENABLE_LIVE_SCHWAB") != "1":` **before** any outbound Schwab order POST and
returns `{"status": "error", "reason": "live order submission requires FLOWW_ENABLE_LIVE_SCHWAB=1 ..."}`.
Env unset = **refuse**; it must stay fail-closed.
Pinned by `backend/tests/services/test_order_router_gate.py` — **13 collected tests** (6 functions,
one parametrized over 6 env values).
`OrderRouter` has **no callers outside its own module and tests**, so "the gate exists" does not mean
"the app is gated". `backend/routes/live_trading.py` is **not** its route surface — those handlers
call `get_live_policy` / `update_live_policy` / `stop_live_tape` in `server.py`.

**3. `PublicBroker.place_order` — UNGATED, LIVE endpoint, currently unreachable.**
`backend/services/public_api.py` → `PublicBroker.place_order` POSTs to
`BASE_URL = "https://api.public.com"` — the real Public.com trading gateway, no sandbox host, **no
gate at all**. Nothing outside `public_api.py`'s own `place_limit_order` / `place_stop_order` helpers
references it, which is the only reason it is currently harmless.
The Public.com **data** adapter (`services/public_api_adapter.py` — chain, quotes, bars) is
deliberately data-only and two tests enforce that it never references an order method. Keep it that
way.

- **FORBIDDEN without Nav's explicit approval, on all three paths:** removing a check, inverting it,
  defaulting it on, bypassing it, repointing a paper host at a live one, or adding any code path that
  reaches a real broker order without a fail-closed gate in front of it.
  If your task appears to require this — **STOP and ask Nav.**

---

## 10. Self-HALT rule

If you go **15 minutes without progress**, stop and write your status to `kanban/cards/agent_<n>_status.md` using the append-only format. Do not silently drift.

---

## 11. Status reporting

Each agent writes append-only status lines to `kanban/cards/agent_<n>_status.md`:

```
[2026-08-30T12:00:00Z] AgentN :: in-progress :: <what you're doing> :: HEAD=<git sha>
[2026-08-30T12:15:00Z] AgentN :: DONE :: <what shipped> :: HEAD=<git sha>
```

Format: `[timestamp] AgentId :: status :: note :: HEAD=sha`

---

## 12. GSD integration state (as of 2026-08-31)

- GSD scaffolded at `.planning/` (ROADMAP.md, PROJECT.md, STATE.md, REQUIREMENTS.md, config.json, 7 codebase maps)
- Current phase: **Phase 6 — Backlog Promotion [ACTIVE]** per `.planning/STATE.md`. Phase 5 —
  Frontend Public API Wiring [COMPLETE 2026-08-31]. If this line and STATE.md ever disagree,
  **STATE.md wins** — check it rather than trusting this snapshot.
- **Phase 6 — Backlog Promotion** — see ROADMAP.md §6. Phase 4 (Tidehunter Pro) is gating-only scaffolding; no live build until Public API limits confirmed. Phase 6 items being promoted: 6.2 backtest [DONE], 6.4 quant [DONE], 6.6 ADRs [DONE]; remaining: 6.1 Prometheus, 6.3 alert persistence, 6.5 portfolio.

Kanban: 5 agent status cards (agent_1 through agent_5) refreshed post-Phase-5. Phase 3 + Phase 5 kanban closed.

- Phase 2 — Round 10 P0 Closure: COMPLETE (P0.1-0.3 done)
- Phase 3 — Public API Data Layer: COMPLETE [CLOSED 2026-08-31] (94c3c89 + downstream)
- Phase 5 — Frontend Public API Wiring: COMPLETE [2026-08-31] (c5e3b18, a1e69bc, dd14e32)
- Phase 6.2 — Backtest hardening: COMPLETE [be3b7f8]
- Phase 6.4 — Quant signal exposure: COMPLETE [ecb6715 + e6e5d9c]
- Phase 6.6 — ADR expansion: COMPLETE [3c4019f, 5 ADRs shipped]

**Where the durable knowledge lives:**
- `.planning/STATE.md` — current phase + log. **Authoritative.** Read it at session start; do not
  trust a phase status quoted anywhere else, including this file.
- `.planning/ROADMAP.md` — phase and ticket list.
- `docs/adr/` — 6 architecture decision records, **all Accepted**, index at `docs/adr/README.md`.
  They bind future work: 0001 model promotion policy (4 gates), 0002 data-source policy & priority
  chain, 0003 backtest equity model, 0004 deploy CORS headers, 0005 test discipline &
  data-source assertion policy, 0006 Black Friday / Ferrari coupling boundary. Read the one that
  covers your area BEFORE you change it; supersede an ADR, never rewrite it.
- `.planning/LEARNINGS.md`, `.planning/codebase/` (7 GSD map docs), `docs/ROUND10_PLAN.md`.
- There is **no** Claude project-memory index for this repo on this machine —
  `~/.claude/projects/C--Users-DARK-HERO-Desktop-FLOWW2-0/memory/` is empty, and the macOS path
  `~/.claude/projects/-Users-nav-Documents-GitHub-floww/` does not exist. The repo is the record.

Test state — **reproduce it, do not quote a remembered number.** The counts below were verified
2026-09-04 on this machine:
- Backend: **4640 tests collect, 0 collection errors** —
  `cd backend && ./.venv313/Scripts/python.exe -m pytest --collect-only -q`.
  No pass count is asserted here: a meaningful one needs MongoDB on `localhost:27017` (see §7). Get it
  yourself with `./.venv313/Scripts/python.exe -m pytest -q --tb=no` once Mongo is up.
- Frontend: **280 passed / 280 total across 44 suites** —
  `cd frontend && CI=true npx craco test --watchAll=false`.
