# Browser receipt — live candidate (2026-10-08, prep evidence, not acceptance)

Harness: `work/verify_unified.cjs` (headless Chromium, NY timezone, dark
scheme, isolated browser profile) against the RUNNING preview pair —
frontend `work/floww-unified:3000`, backend `:8002`. No service was
started, restarted, or modified; screenshots/JSON written to `outputs/`
per architect pattern (existing files refreshed).

## Result: 11/11 checks

Latest labels, chart+options coexistence, neutral chart surface
`rgb(17, 17, 17)`, zero stray-`}` text nodes, real PNG download
(`SPY-price-chart.png`, saved to `outputs/FLOWW-Chart-Export.png`),
options-desk focus, Related pane, assistant dock, portal palette
(`rgb(17, 17, 17)`), Triad Market view, Tidehunter + saved activity,
8 sidebar destinations, phone viewport containment, zero page errors,
zero broker-order POSTs.

## completes U05's open remainder (prep)

The mocked-canvas caveat in the U05 dossier is now covered by a real
isolated-browser download receipt: `outputs/FLOWW-Chart-Export.png` +
`outputs/FLOWW-Browser-Verification.json` (`checkedAt`
2026-10-08T00:47:17Z). U05 acceptance still needs Cline's independent
verdict on the sealed snapshot.

## Interaction checks (2026-10-08, `work/verify_u17prep.cjs`)

6/6 green, zero-fetch by design (no route navigation; one same-page reload
to revert client zoom): keyboard focus + Enter opens Chart tools, focus
lands on 14 labelled controls in sequence, all sidebar destinations named,
200% zoom contains scrolling with both studies mounted
(`outputs/FLOWW-Zoom200.png`), post-zoom reload restores, zero errors and
zero order POSTs. Receipt: `outputs/FLOWW-Interaction-Verification.json`.

## Finding for Cline/U13 (not repaired by OpenCode)

The run's `failedReads` lists HTTP 429 on ORDINARY GETs, including
`/api/version` and `/api/preferences/theme` — the running preview backend
still spends the per-IP mutation burst budget on admitted reads. Backend is
Cline-owned; the running service was not touched. If the read-budget
reclassification already landed in another lane, it is not deployed on
`:8002`; re-verify there after deploy. No provider/broker call was made by
this check (reads only, existing preview data).
