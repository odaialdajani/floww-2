# DISCORD RESTART PLAN v2 — two-way bot, gated (supersedes the 24h clock plan)

Status: G1 gateway truth landed (`8f948e7` on `origin/phase9/agent2-flowseeker`:
107 passed incl. 36 new gateway tests, ruff clean). Everything below is
measured, not claimed. Live trading/paper-loop gates stay RED.

## 0. Why you can read but not command (root causes, all measured 2026-09-06)

1. **Webhook and bot live in different Discord servers.** Webhook `Spidey Bot`
   posts into guild `1064310508947255387` / channel `1108293620873822308`
   (your `#trading` screenshot). Bot `skykt` (`1545889540995158176`) belongs
   ONLY to guild `1180641806459879545`; its GET on the webhook channel returns
   **403 code 50001 Missing Access**. The bot never sees `#trading`, so no `!`
   command there can ever reply. No code change fixes this — it is an invite /
   webhook placement issue. (Fix = Nav checklist item N1 below.)
2. **Wrong API key in the old runbook.** `GET /api/discord/status` requires
   `API_SECRET_KEY` (`backend/auth.py:68-90`), not `PUBLIC_API_KEY` → 401 is
   AUTH, not a bug. With the right key → 200, booleans only.
3. **Two backend launch groups + stale bot.** PIDs `21964` (`*:8000`) and
   `27873` (`127.0.0.1:8000`); bot PID `75453` since Sep-5 22:43. Process
   existence ≠ current code. Every live claim must name PID + git SHA.
4. **Mock-proof ≠ live proof.** Old catalog marked commands WORKING on pytest
   pins. New standard (§1) forbids that.

## 1. Proof standard (three levels, every claim labeled)

- **OFFLINE** — pytest/jest pin, command + count quoted. Proves logic, nothing live.
- **CONFIG** — key/flag presence or read-only GET (bot identity, webhook
  metadata, Alpaca clock/account reads). Proves prerequisites, not transport.
- **WITNESSED** — real human message ID + real bot reply ID + timestamp in the
  designated test channel, pasted into LEDGER. ONLY this closes a gate.
- Paper reads already WITNESSED-at-CONFIG: `/v2/clock` 200
  (`is_open=false`, next `2026-09-08T09:30-04:00`), `/v2/account` 200 ACTIVE
  unblocked, options level 3, 0 open orders. No POST/DELETE was made.

## 2. Gate pipeline (gates, not hours — sync when a gate completes, not at 6/12/18h)

- **GATE-0 Transport (G4 + Nav).** Exit: bot + webhook in ONE guild/channel;
  bot GET channel 200; `!help` from a non-admin human → bot reply, both IDs in
  LEDGER. Nothing else starts before this.
- **GATE-1 Reads (G1).** Exit: `!heatmap/!vanna/!walls/!status/!clock/!alerts`
  each WITNESSED once in the test channel; cooldowns observed; NL variants
  mapped to the same callbacks. G1 gateway work (`8f948e7`) is the OFFLINE
  base — needs WITNESSED confirmation, not more code.
- **GATE-2 Paper loop (G3 + genuine user).** Exit: ONE full loop on paper —
  `!approve <real-key>` → fill → journal seed → `!journal` shows it →
  `!close` → `!pnl` — every step with IDs/logs in LEDGER. U3 options verdict
  (1-contract paper option attempt; 403 → equity-only posture documented).
- **GATE-3 Harden (G2/G4).** Exit: 429-retry + missed-post replay proven by
  chaos tests; DROPPED_EMPTY monitor; digest ≤3 msgs/sweep confirmed live.
- **FINAL (G4).** Full suites, secret scan, HANDOFF with measured-vs-proxy
  table. Tidehunter split + any Meridian UI work start ONLY after FINAL.

## 3. Process fixes (adopt at restart)

- **Branching:** agents work on `phase9/agentX-<topic>` branches, push there,
  verify with `git log origin/<branch>`. Main merges ONLY by G4 after gate
  review. Never rebase the shared dirty checkout to satisfy an origin grep.
- **Ownership map bug (G4 owns the fix, needs unanimous):** catch-all `*`
  precedes the Discord B rows, so `loop_guard.sh` labels them UNOWNED.
  Proposed: move `* | UNOWNED` to the END of the table. Until amended, follow
  the written G-briefs, not the guard output, for Discord paths.
- **Commit hygiene:** explicit paths only, `git diff --cached --name-only`
  before every commit, `git show --stat HEAD` after. Ledger rows are
  append-only (all agents may append; D owns structure).

## 4. Meridian scope (no new app)

Meridian IS the existing React PWA (`frontend/public/manifest.json`). No
Discord code exists in `frontend/src`, and `App.js` is frozen/surgical-only.
Integration = the already-shared backend (Alpaca paper routes, journal store).
No agent builds Discord UI in the frontend in this program.

## 5. Nav checklist (the only human-click items — agents cannot do these)

- N1: Invite `skykt` to the server holding `#trading`, OR move the alert
  webhook into the bot's server channel. Confirm bot can GET the channel.
- N2: Designate ONE test channel (recommend a new `#bot-test`, not `#trading`).
- N3: From a NON-admin account, send `!help`; paste both message IDs.
- N4: Send one `!approve` + `!close` pair on paper when G3 is ready.
- N5: Decide Tidehunter token/server after FINAL.

## 6. Agent launch prompts (paste one per agent, fresh session each)

--- PASTE G1 ---
You are G1 in /Users/nav/Documents/GitHub/floww on a NEW branch
`phase9/g1-<topic>`. Read institutional_loop/DISCORD_RESTART_PLAN.md (§1-2),
DISCORD_MASTER_PLAN.md (§2), DISCORD_AGENT_G1.md, CONTRACTS.md (C6/C10-C12).
Status: your gateway truth patch `8f948e7` is OFFLINE-green (107 passed, ruff
clean) — do NOT rewrite it without a failing test. Post ready + 2 claims to
LEDGER, then drive GATE-1: get each read command WITNESSED in the Nav-
designated test channel (human msg ID + bot reply ID per command). Do not
impersonate a human with the bot token. Write only backend/discord_bot.py +
your tests. Loop: failing test → patch → suite + ruff → commit own paths →
push branch → verify on origin/<branch> → ledger. Never touch trading
semantics (G3), formatter (G2), infra (G4), forbidden files, or another
agent's hunks.
--- END ---

--- PASTE G2 ---
You are G2 in /Users/nav/Documents/GitHub/floww on a NEW branch
`phase9/g2-<topic>`. Read institutional_loop/DISCORD_RESTART_PLAN.md (§1-2),
DISCORD_MASTER_PLAN.md (§3), CONTRACTS.md (C6), DISCORD_AGENT_G2.md. Post
ready + 2 claims to LEDGER, then own GATE-3 alert half: validator fuzz
(None/NaN/""/missing/zero per render field), 429+Retry-After backoff with
per-sweep POST budget, missed-post replay table + runbook. Never weaken the
validator to make traffic flow. Write only services/discord_ops.py
format/gate/digest + your tests; engine/route needs go in LEDGER as diffs.
Same loop discipline as G1. Sync on gate completion, not on hours.
--- END ---

--- PASTE G3 ---
You are G3 in /Users/nav/Documents/GitHub/floww on a NEW branch
`phase9/g3-<topic>`. Read institutional_loop/DISCORD_RESTART_PLAN.md (§1-2),
DISCORD_MASTER_PLAN.md (§4), CONTRACTS.md (C10), DISCORD_AGENT_G3.md. Post
ready + 2 claims to LEDGER, then own GATE-2: ONE witnessed paper loop
(`!approve` real key → fill → journal seed → lifecycle → `!journal` →
`!close` → `!pnl`), every step with IDs/logs in LEDGER. PAPER ONLY — any diff
touching a non-paper URL fails review. U3: attempt one 1-contract paper
option order; 403 → record verdict + equity-only posture, no silent fallback.
Write only execute_approve/journal hooks/alpaca_client.py/routes/alpaca.py/
order_router Alpaca transport + tests. No human impersonation: the approve
tap must be Nav's genuine command.
--- END ---

--- PASTE G4 ---
You are G4 in /Users/nav/Documents/GitHub/floww, stay on
`phase9/agent2-flowseeker` (or a `phase9/g4-<topic>` branch). Read
institutional_loop/DISCORD_RESTART_PLAN.md (all, esp. §0/§3), CONTRACTS.md,
DISCORD_AGENT_G4.md. Post LEDGER machinery check + own GATE-0 with Nav:
unify bot+webhook into one guild/channel, designate `#bot-test`, resolve the
duplicate :8000 groups, publish the process-identity rule (pid+SHA on sweep
lines). Own the ownership-map reorder proposal (unanimous + LEDGER line),
all merges to main, all sync gates, secret scan, and FINAL HANDOFF with the
measured-vs-proxy table. Write docs/health/ops + your tests only. May revert
red commits (log + notify); may never change signal/feed/money logic to make
tests pass.
--- END ---
