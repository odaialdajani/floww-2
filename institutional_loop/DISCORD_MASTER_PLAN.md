# DISCORD MASTER PLAN — the whole bot + alerts program, rebuilt properly
**Trigger:** Sep-2026 incident — gutted WHALE embeds (`SPY ? ?`, every field
`—`) reached Discord. Formatter + pipeline proven correct on live data the
same night; the incident response below makes that failure class
STRUCTURALLY IMPOSSIBLE and observable, then rebuilds the surface area.

## 1. What broke, honestly
- Symptom: 2× `GOLD WHALE — SPY ? ?` embeds, all fields blank, 8:30/8:50 PM.
- Proven: current `_mk_alert` always emits full dicts; live Saturday sweep
  (191 rows → 112 alerts) produced ZERO gutted alerts; the :8000 backend log
  shows NO discord posts and last fired alerts 4:24 AM (stale pre-discord
  code). Verdict: the posts came from an intermediate/parallel process state,
  not from any defect reproducible in the current tree.
- Response (already landed): `validate_alert_for_post` gate in BOTH post
  paths (singles + digest) — gutted alerts are dropped, counted in
  `DROPPED_EMPTY`, and logged with key + missing list (the log line is the
  dead letter). Exposed on `/api/discord/status`. Zero-value fields are
  measurements, not missing. No "— / —" embed can ever ship again.

## 2. Command catalog — verified status (test = jest/pytest pin or live proof)
| Command | Status | Data source | Notes |
|---|---|---|---|
| !heatmap / hm | WORKING (live SPY proof) | build_heatmap (Public-first) | 20s/user cooldown |
| !vanna / v | WORKING (live 196-strike proof) | chain + BS vomma | 20s/user cooldown |
| !walls / w | WORKING | heatmap payload | 5s cooldown |
| !buy / !sell | WORKING (mock-proof; needs live confirm) | Alpaca paper | allowlist only |
| !bracket | CODE-COMPLETE, NEEDS LIVE CONFIRM | Alpaca paper + Public quote | allowlist only |
| !approve | CODE-COMPLETE, NEEDS LIVE CONFIRM | ledger + Alpaca paper + journal | allowlist only |
| !close / !cancel | CODE-COMPLETE, NEEDS LIVE CONFIRM | Alpaca paper | allowlist only |
| !holdings / !orders / !pnl / !risk | CODE-COMPLETE, NEEDS LIVE CONFIRM | Alpaca paper | read-only |
| !alerts / !journal | WORKING (mock-proof) | DuckDB ledger/journal | read-only |
| !status / !clock / !audit | WORKING (mock-proof) | budget/Alpaca/journal | audit allowlisted |
| !help [+topic] / fuzzy / NL reads | WORKING (tests) | — | — |
| `spy walls` (no prefix) | WORKING (tests) | same as commands | reads only, never trades |

## 3. Alert pipeline (post-incident shape)
```
sweep → norm → quote-truth → eval → desk → dedup → persist
                                                    ↓
                              VALIDATE (drop+count+log gutted) → gate (tier/rule)
                                                    ↓
                              ≤3 singles (approve keys) / >3 digests (≤3 msgs)
```
- Webhook limits honored: ≤3 POSTs/sweep (Discord: ~30/min). Rate-limit
  (429) handling: log + counter (retry-after respect = Phase-2 D4).
- Missed-alert replay: every persisted alert is re-readable from
  flow_alerts_daily; `!alerts` is the manual replay. Auto-replay of failed
  posts = Phase-2 D4.
- Calibration/tier changes flow through automatically (gates read live alerts).

## 4. Paper-trading loop ( Solstice bot scope )
`!approve key [qty]` → bias→side → Alpaca paper market order → journal
equity seed (type=equity, ref-px convention, per-second date) → lifecycle
tracker follows to exit → `!journal`/`!pnl` review. `!bracket` adds TP/SL
legs from live-quote-derived absolutes. `!close`/`!cancel` unwind.
UI/API path (`POST /api/alpaca/order[/option]`) journals identically.
Options need paper-account approval (403 surfaces honestly).

## 5. Bot split (per Nav)
- **This bot = Solstice** (gamma/vanna/walls + paper trading of anything).
- **Tidehunter bot (later, separate process/token)** = flow alerts, scanner
  digests, sweep commands, OI boards. Shares discord_ops library, never this
  process. Its plan is out of scope here.

## 6. Four agents — workstreams + ownership (no overlap)
- **G1 Bot Commands** — owns `discord_bot.py`, `HELP_TEXT`/topics. Verify every
  NEEDS-LIVE-CONFIRM row above against REAL paper + REAL Discord test channel;
  per-command proof table in LEDGER. May read all, write only bot + its tests.
- **G2 Alert Quality** — owns `format_alert_message`, digest builder, validator
  thresholds, `should_notify` gates. Kill the last `—`-capable path; add
  429-retry + missed-post replay; per-rule tier tuning from the outcome ledger.
  Writes: `services/discord_ops.py` (format/gate/digest only), its tests.
- **G3 Paper Loop** — owns approve→fill→journal→track→review + bracket/close/
  cancel hardening (partial fills, rejects, 403-no-approval, duplicate
  protection). Writes: `execute_approve`, journal hooks, `alpaca_client.py`,
  `routes/alpaca.py`, their tests. Live-proves one full loop on paper.
- **G4 Reliability & Docs** — owns launchd/ops, `/api/discord/*`, rate-limit
  accounting, `DISCORD_SETUP.md`, HANDOFF. Runs all gates, owns merges,
  keeps the catalog (§2) truthful. Writes: docs, health/ops, tests for those.

## 7. 24h runbook
H0–1 read + post ready + claim 2 tasks each · H1–6 build block 1 ·
H6 SYNC-1 (rebase, contract deltas, red triage, D chairs) · H6–12 block 2
(live-confirm rows) · H12 SYNC-2 (integration: alert→approve→fill→journal
on paper, END-TO-END witnessed) · H12–18 hardening (retry/replay/chaos) ·
H18 SYNC-3 (kill/keep per command from proof table) · H18–23 polish/docs ·
H23–24 FINAL GATE (D): full suites, replay determinism, secret scan,
HANDOFF. Same loop discipline as the main program (plan→failing test→
patch→suite+ruff→commit+push→ledger).

## 8. Verification gates
- Task: failing test first; module suite + ruff green.
- Sync: backend scope + jest flowseeker/discord suites green; LEDGER current;
  proof table updated (no command stays NEEDS-CONFIRM without a named run).
- Final: full suites green; one witnessed end-to-end paper loop; no forbidden
  files; HANDOFF with measured-vs-proxy table.

## 9. Unknowns, each with an owner (no orphan unknowns)
- U1 Which process posted the gutted 8:30/8:50 embeds? → G4: audit launchd/
  cron/agent-launched backends; add process-identity to sweep log lines.
- U2 Do `!buy/!bracket/!approve` succeed against REAL paper? → G1+G3 live run.
- U3 Does the paper account have options approval? → G3: attempt tiny paper
  option order, record verdict (approval applied for if missing).
- U4 Webhook 429 behavior under a 100+ burst? → G2 chaos test (mock 429s).
- U5 Missed-post replay path? → G4 design, G2 implements.
- U6 Message-content-intent actually on? → G1: `!help` live round-trip proves it.
- U7 Per-user cooldown abuse vectors (alt accounts)? → accepted risk, logged.
- U8 Who restarts :8000 on new code? → G4 runbook (launch_decoder --restart
  cadence + freshness check), Nav owns the click.
