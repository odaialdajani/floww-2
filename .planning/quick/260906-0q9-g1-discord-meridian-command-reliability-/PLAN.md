---
status: in-progress
lane: G1
mode: quick-validate
---
# G1 Discord → Meridian command reliability

Scope: G1 owned backend/discord_bot.py and new gateway tests; LEDGER append-only. No frontend, broker transport, journal semantics, alert formatter, frozen contracts or ownership-map edits. Meridian is the existing React PWA (frontend/public/manifest.json), not a new application.

## Claims
1. G1.1/G1.2: inspect real backend/bot and existing human-command/reply evidence. Never emulate a human using a bot token. Missing witnessed approval/fill/journal/close remains NEEDS-LIVE-CONFIRM.
2. G1.3/G1.4: close NL cooldown bypass and misleading portfolio/status replies. Reuse command dispatch rather than duplicating render paths. Keep trading prefix-only.

## Tasks and gates
1. Read-only live discovery and command-boundary review. Capture sanitized identifiers and timestamped responses; never env values or tokens. Gate: measured-vs-proxy distinction.
2. Write failing gateway tests for NL routing/cooldowns, bot-author ignore, flip/status/clock reads, canceled-order truth and cancelable IDs, unknown clock and configured-only status. Run red before implementation. Patch bot surface only; run new suite plus related discord/heatmap/paper tests and required ruff rules.
3. Independently review diff and test boundary semantics. Check forbidden paths unchanged by this task and don't stage concurrent analytics/server work. Gate: real tests, not synthetic Discord proof.
4. Commit explicit owned source/test paths with command evidence; append LEDGER; push current branch only. Origin/main diverges (56 main-only/67 current-only at preflight), so G4 merger approval is required to land on main. Never rebase shared dirty clone or claim origin/main success for a feature-branch push.

## Program gates kept red until witnessed
- Solstice Sync-2: real human approve key → paper fill → journal seed → lifecycle → close → P&L.
- U6: non-admin human !help → matching bot reply, not application flags alone.
- Tidehunter process split and new app UI integration remain gated by Sync-2 and respective owner approval.
- Syncs 6/12/18h and final 23–24h are program requirements, not elapsed or completed in this short task.

## Ownership machinery finding
OWNERSHIP.md catch-all '*' precedes Discord B rows, so loop_guard first-match logic labels them UNOWNED. Do not alter frozen map without unanimous sign-off. Follow explicit G1 brief even if machine guard permits broader writes.
