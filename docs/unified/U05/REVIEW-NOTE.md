# U05 — Review: chart PNG neutral background

Owner: OpenCode (review of parent implementation). Reviewer: Cline.
Baseline `8194eca4`. No reimplementation.

## Patch under review

`frontend/src/components/heatseeker/RecordedPriceChart.jsx` (`downloadChart`):

- Captures `window.getComputedStyle(surface.current).backgroundColor` BEFORE
  any await (`setExporting`, serialization, image decode), closing the
  navigate-away export race: the background is pinned from the displayed
  surface, not re-read after async work.
- Canvas fill uses the captured value; falls back to `#111111` only when the
  captured value is missing/`transparent`. Old hard-coded `#0c1118`
  (blue-black) removed.
- Everything else unchanged: visible window, held scales, original line
  colors, recorded levels, ticker + New York dates, single download, error
  paths.

## Counterexample verification

Extended download test (parent-authored, executed here): surface background
set to `#111111`; asserts the canvas `fillStyle` actually used was
`'rgb(17, 17, 17)'` — the computed display value, not a constant. Combined
with the pre-existing assertions (60 candles serialized, saved-node line,
resolved candle/label colors, NY dates, window/price bounds unchanged after
export, single PNG download, revoke after 1100ms), this proves the PNG
matches the displayed surface.

Race reasoning: `background` is read synchronously in the click handler
before the first await; a mid-export navigation cannot change the pinned
value. Export-while-navigating still resolves safely (abort paths untouched).

## Receipts

`RecordedPriceChart` suite green within the 238/238 focused run (exit 0).
Real-browser PNG download receipt is U05 acceptance remainder: requires the
sealed snapshot + isolated browser run (browser evidence, not jsdom). The
mocked-canvas test is supporting evidence only — stated, not oversold.

## Verdict (OpenCode → Cline)

REVIEW_ACCEPT_SUBJECT_TO_PEER on code + unit evidence. Remaining for U05
acceptance: your independent verdict + a real isolated-browser PNG receipt on
the frozen snapshot (U17 may cover the browser half).
