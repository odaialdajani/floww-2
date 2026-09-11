# RFC-3 (Agent 2): overview-bar consolidation — SIDE-matrix vs C/P-only lean

Two implementations of the same bar exist; only one renders today.
`pulse/overviewBar.js:computeOverview` has zero imports outside `pulse/`
(verified 2026-09-03) — this RFC is timing, not emergency.

## The fork (exact)
- LIVE (`scanLogic.js:overviewStats`, rendered Blademap ovbar):
  lean from the SIDE×C/P matrix — call-ASK + put-BID legs = bull,
  call-BID + put-ASK = bear; FIR = |bull−bear|/(bull+bear), gate 0.3
  (H1). Empty tape → fir 0, Neutral. Uses `_aggPrem ?? premium`.
- UNWIRED (`pulse/overviewBar.js:computeOverview` + `OverviewBar.jsx`):
  lean from call−put premium only; FIR null (not 0) on empty;
  field names differ (netPremium/pcRatio/sessionLabel/total).

## Why it matters
On a put-ASK-heavy tape the two leans DISAGREE (mine: Bullish per the
reference ASK→BULLISH contract; theirs: Bearish from put premium).
Whichever bar survives must keep one definition — the desk reads lean
as aggression direction, not contract-type bias.

## Proposal (no edits made — surface is yours)
Option A: `OverviewBar.jsx` consumes `overviewStats` (SIDE-matrix) and
`computeOverview` is deleted — one definition, H1 intact.
Option B: keep C/P-only lean but rename it (e.g. `cpBias`) and never
render it as Bullish/Bearish — direction words stay with SIDE.
Either way, delete the other implementation in the same commit.
Fixtures already exist on both sides (`pulse/overviewPayloads.json`,
my CostCaption tape test).
