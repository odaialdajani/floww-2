# G4 — RELIABILITY & DOCS (Discord program gate). You own the truth.
Read `institutional_loop/DISCORD_MASTER_PLAN.md` (esp. §9 unknowns — U1/U8
are yours first), `CONTRACTS.md`, then post ready + LEDGER machinery check.

OWN: launchd/ops docs, `/api/discord/*`, rate-limit accounting, `docs/`,
`DISCORD_SETUP.md`, HANDOFF, merges. NOTHING else without owner sign-off.
Skills: TDD, systematic-debugging, verification-before-completion,
executing-plans (you run every sync gate).

## Tasks
- **G4.1 U1 root-cause closeout.** Audit every process that could have posted
  (launchd list, crons, agent-launched backends, :8000 vs :8001): add
  process-identity (pid + git sha) to sweep log lines so the next mystery
  takes minutes, not hours. Report verdict in LEDGER either way.
- **G4.2 U8 relaunch runbook.** `launch_decoder --restart` cadence, freshness
  check, :8000-vs-tree drift detector (route presence probe). Nav owns the
  click; you own the checklist.
- **G4.3 Missed-post replay ops.** Schema + retention for the G2 post-attempt
  table; replay runbook; monitor the DROPPED_EMPTY counter (page Nav if it
  moves — it means the producer regressed).
- **G4.4 MCP guardrails + prompt pack** (from main program P1-8, Discord
  scope): 10 example prompts against the bot's surface, tested.
- **G4.5 P2-10 enforcement + HANDOFF.** No claimed verified sweeps/HIRO/dark
  pool anywhere in bot/help/docs. Final HANDOFF: measured-vs-proxy table,
  proof table (§2 all green or named reds), secrets handling attestation.
- **Syncs 6/12/18h + final gate** (same discipline as main program).

Powers/limits: may revert red commits (log + notify). May NOT change
signal/feed/money logic to make tests pass. Escalate: secrets in code,
frozen-file needs, vendor outage >2h, agent dark >90 min.
