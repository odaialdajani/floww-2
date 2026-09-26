# R8 visual receipts (R8-06) — live-data layout evidence, not fixtures

Branch `solstice/r7`, head `36872db7` + uncommitted R8 deltas (see RUN_STATE).
Backend `server:app` :18081 (Public vendor data, no mocks), frontend dev
:3007, Chromium 1243 headless (`PW_CHROMIUM_EXE`), viewports 1600×900 and
390×844. Rerun: `PW_CHROMIUM_EXE=... FRONTEND_URL=... node
docs/solstice/capture-solstice.mjs`. Tooling: playwright-core only (no repo
dependency changes); screenshots via CDP (page.screenshot hangs on font
load — documented in the script).

| File | Viewport | State |
|---|---|---|
| solstice-desktop.png | 1600×900 | Solstice single grid, live SPY chain, status strip + sidebar mounted |
| inspector-desktop.png | 1600×900 | Grid cell selected → SELECTED WALL inspector, Follow control |
| compare-desktop.png | 1600×900 | GEX+VEX compare desk, independent panes/scales |
| single-narrow.png | 390×844 | Single grid stacked, readable, no overlap |
| movers-populated.png | 1600×900 | Top Movers populated live (MSFT +3.66%, AAPL +1.53%, session dates, 2/75 partial + last-good badge), Data usable · OI |

Data is live vendor chain (spot ~771, session 2026-09-25), so cell values
are layout receipts, not reproducible fixtures. Mounted jsdom tests pin
values; these pins layout/density/preservation.
