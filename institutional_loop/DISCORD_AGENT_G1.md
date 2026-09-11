# G1 — BOT COMMANDS (Discord surface). You own the user experience.
Read `institutional_loop/DISCORD_MASTER_PLAN.md` (§2 catalog is your backlog),
`CONTRACTS.md`, then post ready + first 2 claims to LEDGER and start.

OWN: `backend/discord_bot.py`, `HELP_TEXT`/topics in `services/discord_ops.py`.
READ-ONLY elsewhere. Skills: TDD, systematic-debugging, verification-before-completion.

## Tasks (each: failing test → patch → suite + ruff → commit + push → ledger)
- **G1.1 Live-confirm the NEEDS-CONFIRM rows.** Against the REAL test channel
  + paper account: !buy/!sell/!bracket/!approve/!close/!cancel/!holdings/!orders/
  !pnl/!risk. Record each in the §2 proof table (reply text or it didn't happen).
  Do NOT invent results — a red row with a reason beats a claimed green.
- **G1.2 U6 intent proof.** `!help` round-trip from a non-admin test user;
  document intent state. If deaf, write the exact Portal fix, don't code around it.
- **G1.3 NL-read expansion (reads only).** Add `spy gex`, `qqq flip`-style
  patterns + `!`less `status`/`clock`. Trading stays prefix-only (test pins it).
- **G1.4 Cooldown/alias polish.** Per-command usage counters in audit; tune
  20s/5s from measured build costs; add missing aliases users actually type
  (log-driven, not guessed).
- **G1.5 Tidehunter-bot split prep.** Extract shared command scaffolding
  (cooldown/audit/fuzzy/parse) into `services/discord_harness.py` PURE module
  with tests, so the second bot imports it instead of forking discord_bot.py.
  Bot keeps thin shims. No behavior change (all 27+ discord tests stay green).

Constraints: never touch trading semantics (G3), alert formatting (G2), or
infra (G4). discord.py API only; no new deps without LEDGER note.
