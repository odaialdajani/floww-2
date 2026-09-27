# R8 visual receipts (R8-06) — live-data layout evidence, not fixtures

> **The authoritative R8 claim is `docs/solstice/R8-ACCEPTANCE.md`.** This file
> is a capture index. The head below was corrected on 2026-09-27: the previous
> version pinned head `36872db7` and referenced a `RUN_STATE` file that does not
> exist, so its screenshots were 16 commits stale and could not evidence the
> current build.

**Current head:** `main @ 71f83625` (Merge PR #53 `fix/v3-budget-honesty`)

Recaptured 2026-09-27 against the live local stack: frontend `:3000` (production
static build), backend `:8000` (`server:app`, Public vendor data, no mocks),
headless Chromium via `playwright-core` 1.59.1 driving the local Chrome binary
(`--no-sandbox --disable-dev-shm-usage`). Viewports 1600×900 and 390×844.

Rerun:

```
cd docs/solstice
PW_CHROMIUM_EXE='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  FRONTEND_URL=http://127.0.0.1:3000 node capture-solstice.mjs
```

Tooling: `playwright-core` only, symlinked from an existing global install — no
repo dependency changes. The script uses CDP `Page.captureScreenshot` because
`page.screenshot` hangs on font load; that is documented in the script.

| File | Viewport | State | At this head? |
|---|---|---|---|
| r8-01-selected-wall.png | 1600×1100 (element) | SELECTED WALL inspector element, full 1089px height — NOW / CHANGED / CONFIRM / INVALIDATES / DATA all visible, not folded | yes |
| r8-02-review-saved.png | 1600×900 | Review save surface mounted, state pill rendered | yes |
| inspector-desktop.png | 1600×900 | Grid cell selected, full app with sidebar + status strip | yes |
| compare-desktop.png | 1600×900 | GEX+VEX compare desk, independent panes and scales | yes |
| single-narrow.png | 390×844 | Single grid stacked, readable, no overlap | yes |
| older-heads/solstice-desktop.png | 1600×900 | Solstice single grid, live SPY chain | **no — older head** |
| older-heads/prod-gex.png | 1600×900 | Production stack, GEX tab | **no — older head** |
| older-heads/prod-vex.png | 1600×900 | Production stack, VEX tab | **no — older head** |
| older-heads/movers-populated.png | 1600×900 | Top Movers populated live | **no — older head** |
| older-heads/blend-inspector.png | 1600×900 | Inspector blend pass | **no — older head** |

The five `older-heads/` files were moved out of this directory on 2026-09-27 so
they cannot be mistaken for current-head evidence. See their README.

Data is live vendor chain, so cell values are layout receipts, not reproducible
fixtures. Mounted jsdom tests pin values; these pin layout, density and
preservation. Every image at this head was checked for non-blank content by
unique-colour count (2,580–10,678) before being accepted — a reload loop or an
error page produces near-uniform images.

## Preserved appearance

The R8 brief requires the heatmap's appearance stay unchanged. The recaptured
shots confirm the same single grid, dark styling, palette, density, strike rail,
expiry columns, zoom, scrolling and familiar controls as before. R8 changed the
inspector, compare and review surfaces — not the grid.
