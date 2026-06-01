# Round-12 Dispatch v3 — Worktree-Isolated Agents (2026-05-31)

> **What changed vs v1/v2:** same disjoint-file lane idea, but each agent now works in its
> **own git worktree** (separate working directory). That is what actually prevents collisions
> — in one shared clone, "a branch each" is a lie because a single working tree can only have
> one branch checked out. Worktrees give each lane its own tree + branch → they physically
> cannot touch each other's files. Consolidated 10 → **5 lanes** because the bottleneck is
> verification, not agent count.
>
> **Prereqs (do first):** `main` clean @ `d7aeb55` and collecting (2655 tests, verified
> 2026-05-31). Qdrant key rotated + in `backend/.env`. WIP from prior rounds is preserved on
> `backup/r12-wip-20260531-070635` (`2bff176`) — cherry-pick from there if a lane needs it.

---

## 0. Operator (Nav) — set up the worktrees, then launch

```bash
R=/Users/nav/Documents/GitHub/floww
for N in 1 2 3 4 5; do
  git -C "$R" worktree add "$R/../floww-l$N" -b "agent/l$N" main
  cp "$R/backend/.env" "$R/../floww-l$N/backend/.env"            # env is NOT copied by worktree
  ln -s "$R/backend/.venv" "$R/../floww-l$N/backend/.venv"       # share the py3.13 venv
done
git -C "$R" worktree list        # verify 5 trees, each on agent/lN
```
Launch 5 agents. Give **each** agent the **Preamble (A)** + its **one Lane (B)**. One agent per
worktree. Cleanup after merge: `git -C "$R" worktree remove ../floww-lN`.

---

## A. SHARED PREAMBLE — paste above EVERY lane

You are one of 5 parallel agents on **floww (Confluence Decoder)**. Obey exactly:

**Your sandbox**
- You work **ONLY** inside your worktree: `/Users/nav/Documents/GitHub/floww-l<N>`. `cd` there.
- You are on branch `agent/l<N>`. Never `git switch`/`checkout` to another branch. Never push.
- Touch **ONLY the files listed in your lane.** Editing any file outside your list = STOP and
  report. Other lanes own other files; you cannot see or fix their work.
- Python is `backend/.venv/bin/python3` (3.13). Never system python.

**Frozen — never edit (architect-locked):** `backend/services/ml/inference.py`,
`backend/services/dash_ui.py`, `backend/tests/conftest.py`, anything under `backend/models/`,
`frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`, `frontend/src/App.js`.
If your task seems to need one of these → STOP and report; do not touch it.

**The loop (TDD — mandatory):**
1. Write a failing test that pins the behavior. Run it; confirm it FAILS for the right reason.
2. Smallest patch to make it pass. 3. Run your test + the module's wider sweep — must not regress.
4. `cd backend && .venv/bin/python3 -m pytest <your tests> -q` and paste the real tail.

**Verification gate (anti-fabrication — this is the floor):**
- NEVER mark a previously-passing test `skip`/`xfail`. If your change breaks a passing test,
  your change is wrong — revert and find root cause.
- NEVER claim a result you didn't run. Paste real pytest/ruff/curl output in the commit body.
  Round-7's fabricated completion log is the negative example — do not repeat it.
- Lint clean before commit: `cd backend && .venv/bin/ruff check <your files>`.

**Commit (HEREDOC + inline evidence):**
```bash
git commit -m "$(cat <<'EOF'
<type>(round-12-l<N>): <one line>

What + why.

Verification:
$ cd backend && .venv/bin/python3 -m pytest <your test path> -q 2>&1 | tail -2
<paste real output>
EOF
)"
```
Commit to your branch only. Do **not** push — the architect merges and pushes. When done,
write a 5-line status to `kanban/cards/agent_l<N>_status.md` (files changed, tests added,
pass count, anything you had to leave).

---

## B. THE 5 LANES (disjoint — every file appears in exactly one lane)

**L1 — server core + auth/admin.** Owns: `backend/server.py`, `backend/auth.py`,
`backend/routes/__init__.py`, `backend/routes/admin.py`, `backend/routes/health.py`.
Focus: lifespan/startup correctness, admin-route auth, health contract; tests for each.

**L2 — analytics + cache.** Owns: `backend/advanced_analytics.py`, `backend/cache.py`,
`backend/routes/analytics.py`, `backend/routes/anomaly.py`.
Focus: degraded-response contract on cache miss; analytics coverage.

**L3 — ML training/pipeline (NOT inference).** Owns: `backend/ml_training.py`,
`backend/ml_pipeline.py`, `backend/ml_advanced.py`, `backend/ml_price_prediction.py`.
Focus: no train/test leakage; kill any fabricated Sharpe; coverage. `inference.py` is FROZEN —
do not touch; if inference behavior matters, write a test against the public API only.

**L4 — data providers + clients.** Owns: `backend/data_providers.py`,
`backend/databento_provider.py`, `backend/data_collector.py`, `backend/alpaca_client.py`,
`backend/flashalpha_client.py`, `backend/data/repositories.py`, `backend/routes/data_providers.py`,
`backend/routes/alpaca.py`, `backend/routes/flashalpha.py`, `backend/routes/alpha_advantage.py`.
Focus: resilience/timeouts/retries; provider coverage + lint.

**L5 — alerts + execution + portfolio.** Owns: `backend/alert_engine.py`,
`backend/routes/alerts.py`, `backend/paper_trading.py`, `backend/portfolio.py`,
`backend/bs_greeks.py`, `backend/morning_briefing.py`, `backend/error_tracking.py`.
Focus: alert correctness, paper-trading fills, greeks numerics; coverage.
(Risk-gate / live execution is off-limits — paper only.)

> Unowned this round (assign later if needed): `gemini_analyzer.py`, `routes/gemini.py`,
> `routes/hawkes.py`, `routes/heatseeker*.py`, `routes/market_data.py`, `cron_*.py`,
> `memory_integration.py`, `routes/agentfield_api.py`. Reddit/Qdrant work plugs into L4 once keys land.

---

## C. Integration (architect, after agents report)
1. Per lane: `cd ../floww-l<N> && cd backend && .venv/bin/python3 -m pytest -q --tb=no | tail -3`.
   If a lane isn't green, it does NOT merge — bounce it back.
2. Merge order L1→L2→L3→L4→L5 into `main`. Between each merge run the full suite
   (`pytest -q --tb=no | tail -5`) — must stay ≥ baseline, 0 collection errors.
3. Only after all merges + green suite: `git pull --rebase origin main && git push origin main`,
   then verify with `git log origin/main --oneline -1 | grep <subject>` (anti-skip gate).
4. `git worktree remove ../floww-l<N>` for each; delete merged `agent/l<N>` branches.
