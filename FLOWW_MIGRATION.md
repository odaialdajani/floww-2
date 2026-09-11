# Migration: floww → floww-2 (2026-09-11)

**floww-2 is the live project. `mrbeast1179-sketch/floww` is frozen and must
receive no commits, merges, or pushes ever again.**

## What moved

- `floww/main@a9a54b2` merged into `floww-2/main` (PR #1, merge `8748cf4`),
  preserving all 23 destination-only commits (Lodestar layer intact).
- All 160 local branches mirrored to floww-2 (same names), except local `main`
  (stale `ef360ef`, superseded — never push it).
- All 94 `origin/*` tips verified reachable in floww-2. Divergent tips kept on
  both sides: existing floww-2 tips left untouched (no force-push); local-only
  tips preserved under `archive/floww-local/*`; origin-only tips under
  `archive/origin/*`. Nothing overwritten, nothing lost.
- Tag `a3/t1-scroller-fix-v2-2026-09-08-recovered` mirrored.
- No stashes existed. All worktrees were clean at migration.

## PR mapping (floww PRs closed, continued here)

| floww (closed) | floww-2 (open) | head |
|---|---|---|
| #69 Skylit panel bugs | #3 | `ca25557` |
| #71 fetched_at pipeline | #4 | `008e31b` |
| #72 X4 stale-data indicator | #5 | `7d3d75c` |

## Freeze enforcement (local floww checkout, `/Users/nav/Documents/GitHub/floww`)

- `core.hooksPath=/Users/nav/.hermes/floww-freeze-hooks` — `pre-commit`,
  `pre-merge-commit` always fail; `pre-push` fails for
  `mrbeast1179-sketch/floww`. Verified live 2026-09-11.
- `origin` push URL set to `DISABLED-floww-frozen-use-odaialdajani-floww-2`
  (fetch still works). Second layer if hooks are bypassed.
- Preservation snapshot (pre-migration dirty worktrees + refs bundle):
  `/private/tmp/floww-preserve-nIHI36` (`dirty-files.tgz a6604efc…`,
  `refs.bundle b225d477…`, `inventory.json c8cc421a…`).

## Pointer updates (same day)

`~/.zshrc` decoder alias, hermes gsd-loop build/review shims,
confluence-decoder-start.sh, 4 LaunchAgent WorkingDirectories, hermes cron
jobs.json, skill-bundle canonical repo, `.claude` trust + allowlist — all now
point at `/Users/nav/Documents/GitHub/floww-2`.

## Parked: ex-floww issue #8 (reopen as a floww-2 issue once Issues are enabled)

floww-2 currently has GitHub Issues disabled (needs the `odaialdajani`
owner). Until then, this spec lives here. Original:
`mrbeast1179-sketch/floww#8` (labels were `gsd:ready`, `gsd:blocked`;
both labels pre-created in floww-2).

Title: heatseeker X chatter card via xurl search (needs X API credits)

Why: the heatseeker tab has no social-signal surface; show X chatter about
the watched ticker alongside the quantitative panels. xurl CLI installed and
authed; only X API credits block it (402 credits-depleted as of 2026-08-25).

Outcomes:
- O-1 — backend route GET /api/heatseeker/x-chatter/{ticker} via xurl search,
  normalized posts {author, text, url, posted_at, engagement}
- O-2 — 10-minute server-cache so polls don't burn credits
- O-3 — HeatseekerDashboard lazy "X Chatter" card, silently hidden on
  credits/402 errors

Exclusions: no X writes; no sentiment/LLM scoring (deferred); briefing strip,
charm panel, signal cards untouched.

Pointers: BriefingStrip.jsx (card pattern), server.py SWR cache-key
convention, useHeatseeker.js (fetch hook). Tests: normalizer incl. malformed
frames; cache single-upstream assertion.
