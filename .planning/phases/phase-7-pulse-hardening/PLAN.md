# Phase 7 — Pulse Hardening (BladeMap parity + false-positive kill)

**Status:** PLANNED 2026-09-03 (single-agent lane: Tidehunter Pro frontend + scanLogic)
**Parent:** ROADMAP.md §Phase 6 (parallel track; does not block 6.3/6.4/6.5 or Phase 1)
**Source:** recon batch deleg_02cefcd8 (`/tmp/wf_pulse_4iNXsa/out_frontend.md`,
`out_scoring.md`), UI spec (`/tmp/wf_pulse_4iNXsa/ui_spec.md`),
commits 6948ffe/bf00d48. Backend recon agent produced no file; backend
verified inline (retuner display-only, dispatcher 15-min dedup exists,
scan 429-backoff exists).

**Goal:** Pulse tape matches the BladeMap reference pixel-contract, stops
flooding, and stops lying. Every silent catch gets a visible state; every
threshold lineage agrees; dead code goes.

## Locked decisions
- Reference screenshot is the SIGNAL spec: ASK→BULLISH / BID→BEARISH for CALLs
  AND PUTs alike. Put-ASK hedge ambiguity is ANNOTATED (HEDGE? tag), never
  flipped — flipping would diverge from the reference Nav approved.
- Tape WHALE ($1M size badge, reference-visual) vs alert WHALE ($25M rule)
  are different tiers with different names after 7.7; tooltips say so.
- Calibration loop stays open by design (desk's dials); 7.8 proposes a
  read-only recommender for the backend lane owner. No auto-tuning in Phase 7.
- Backend engine edits (flow_alerts/flow_quality/flow_calibration) are
  PROPOSALS for the lane owner, not this phase's work. This phase touches
  frontend + scanLogic defaults only.

## Tickets (wave order = tracer-first)

| ID | Ticket | Files | Verify |
|---|---|---|---|
| 7.1 | Threshold parity: alertScore 85→92; evalAlerts defaults minScore 85→92, whale $10M→$25M, sigma 4→6; Jest parity assert vs DEFAULT_RULES | FlowseekerProBlademap.jsx:297, scanLogic.js:146-161, test | new test: engine defaults == DEFAULT_RULES; suite green |
| 7.2 | Close 0DTE loophole (frontend): zeroDteScore 70→85 + require volOI≥2 | scanLogic.js:150,229-232 | Jest: 0DTE lotto row (score 70-84, low mult) no longer fires |
| 7.3 | Put-ASK honesty tag: keep BULLISH per reference, add HEDGE? marker on put-ASK rows + tooltip | Blademap.jsx render, test | Jest: put-ASK row carries hedge flag; call-ASK does not |
| 7.4 | Retoken Pulse → Solstice index.css (bg/panels/borders/text/green/red/radius/mono); rename --fsb-blue (renders gold); thread PL const through vars | FlowseekerProBlademap.css:73-95, Blademap.jsx:30-34 | visual diff tape+scanner vs SkylitDashboard; suite green |
| 7.5 | Reference chrome gaps: refresh/pause buttons, HOW TO READ popover, info-dot tooltips, PREM 90s subline always (reference shows it on every row) | Blademap.jsx, css | mount test: buttons+popover render; suite green |
| 7.6 | Formatter/DTE unification: delete local fmtMoney/fmtTime/dteOf/dteDays, re-export fmtUSD/fmtK/bizDTE/fmtClock from scanLogic | Blademap.jsx:37-44, scanLogic.js:3-53 | grep: zero local const fmt/dteOf; suite green |
| 7.7 | Whale naming: pulseBadges WHALE→tape-tier w/ tooltip (alert WHALE stays $25M); delete vestigial alertScore gate split (max(alertScore,90) vs 92) | Blademap.jsx:121-140,947,1005 | Jest badge tests updated; suite green |
| 7.8 | Delete dead views: VOL view+drawVol, Academy view (~60 lines); header comment corrected | Blademap.jsx:1100,1397,1986 | grep setTab: no vol/academy targets; suite green |
| 7.9 | Visible states: split fetch-error vs filter-empty; conviction "unavailable + retry" (not perpetual loading); VPIN/λ inline "needs trade-level feed"; stale heartbeat single semantics | Blademap.jsx:313,317,722-727,745,763-767,1896 | block endpoints in dev proxy, screenshot each state; suite green |
| 7.10 | DECISION (Nav): mount-or-delete InstitutionalAlertsPanel cluster (836 lines + useAlertStream/convictionAlert/autoTrade) | — | checkpoint:decision before acting |

**Waves:** A = 7.1+7.2+7.3 [DONE f55bd4a] → B = 7.4 [DONE 0f7fbb2] + 7.5/7.6/7.7/7.8
[DONE bdd57c0] → D = 7.9 [DONE 6a0a366] → Wave2 universe opening [DONE c5cba5a].
Phase 7 COMPLETE except 7.10 (Nav decision: mount-or-delete
InstitutionalAlertsPanel cluster).
**7.10 EXECUTED 2026-09-03 as DELETE** (Nav: "delete whatever we dont need"):
23 dead files (~5000 lines) removed — unmounted panel + panel-only cluster
+ legacy FlowseekerTab chain + synthetic FlowEngine + orphan hook/CSS/HTML.
Full suite 40/40, 291/291 green. **Phase 7 CLOSED.**

## Verification loop (every wave)
1. `npx craco test --watchAll=false` full suite green (baseline 45/300).
2. `git status -sb`: only own files staged (reset-then-add, never `-A`).
3. Live: `:8000` + `:3000` 200; screenshot Pulse vs ui_spec.md checklist.
4. Commit subject `fix(tidehunter): …` with inline Jest evidence.

## Backend proposals (lane owner, NOT this phase)
- P1 spread-demotion port to Pulse path (flow_quality detect_spreads → mapPublicChainToRows).
- P2 infer_side_bias 1.5→2.0; P3 zero_dte_score 70→85 server-side.
- P4 threshold_recommendations() read-only endpoint (stage≥1) for manual approval.
- P5 decay-AMBER rules auto-cap at BRONZE until P4 lands.

## What's NOT in scope
- Replacing Public API as primary; Phase 4 stays gated.
- Backend engine edits; ROADMAP.md edits (in-flight by another agent).
- Auto-tuning thresholds; touching other agents' files.
