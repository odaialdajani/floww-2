# U04 — Review: neutral surfaces and page identity

Owner: OpenCode (review of parent implementation). Reviewer: Cline.
Baseline `8194eca4`. No reimplementation; no friend file edited.

## Patch under review

1. `frontend/src/NeutralTheme.css` (new, 107 lines, SHA256
   `31f400f6e8834a6afae7996c61a75200280dfc96c7a987f59bca605929be008a`,
   identical in `work/host-opencode` and `work/floww-unified`).
2. `frontend/src/index.js`: `import "./NeutralTheme.css";` placed after all
   provider/context imports (last stylesheet in the entry).
3. `frontend/.storybook/preview.jsx`: NeutralTheme imported; story background
   token `solstice` `#080b10` → `#090909`.

## Invariant checks (current source)

- Every theme selector is scoped under `html:not([data-theme="light"])`;
  light-theme users unaffected.
- Zero references to `flowseeker` in the theme file; all 77 friend files
  byte-identical to baseline (`git diff 8194eca4 -- flowseeker/` empty).
- Palette is strictly neutral gray (`#111111 #191919 #282828 #090909 #222222
  #454545 #777777 #666666 #303030 #242424 #1c1c1c #151515 #080808`); no
  cyan/violet/green/red/amber semantic token appears. Heatmap, candle, node,
  signal, co-movement and directional/status colors untouched by construction
  (theme only overrides surface/border/chrome-text selectors).
- Geometry/scale/window/scroll allocation unchanged: theme file contains no
  layout, size or positioning rule outside surface color/border (verified by
  read; 107 lines, all color/border-chrome).
- Portals covered: includes `dialog.floww-stock-directory` (ticker picker),
  `.related-body` (Related panel), `.trin-spot-rail-label`, saved-activity
  hover chrome, scrollbars. Saved-activity overlay styles chrome only; friend
  `SavedStockActivity.css/jsx` unedited.
- Route identity: 8 NAV_ITEMS, labels (`Screener`, `Stock chart`,
  `Market view`, `Options map`, …), route IDs and default entry unchanged
  (`frontend/src/shell/navConfig.js` unmodified).

## Receipts

No behavior rewrite, so no new unit tests required (visual acceptance is
U17 on the frozen snapshot). Structural proof: selector/palette/friend-diff
reads above + file hashes in `EVIDENCE.json`. Focused frontend suites touching
adjacent surfaces green in the 238/238 run.

## Verdict (OpenCode → Cline)

REVIEW_ACCEPT_SUBJECT_TO_PEER: overlay is narrow, last-imported, neutral-only,
portal-inclusive, friend-clean. Cline: confirm on the sealed snapshot; visual
sign-off remains U17 on the frozen candidate.
