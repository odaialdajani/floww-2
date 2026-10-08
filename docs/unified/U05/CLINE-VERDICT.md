# U05 — Cline independent verdict: ACCEPT (code + unit evidence). Browser PNG remainder stays open under U17.

Reviewer: Cline. Baseline `8194eca43a580121901516b291c1b2435da7ce2c`. `RecordedPriceChart.jsx` verified at sha256 `e4f794c02390e1...`.

## Independent read of `downloadChart` (exact diff)

- `window.getComputedStyle(surface.current).backgroundColor` is captured on the FIRST line of the click handler, before `setExporting` and before any await — the navigate-away race (background re-read after async serialization/decode) is closed by ordering, confirmed in source.
- Canvas fill: `background && background !== 'transparent' && background !== 'rgba(0, 0, 0, 0)' ? background : '#111111'`. The old hard-coded `#0c1118` (blue-black) is fully removed. jsdom `getComputedStyle` returns `rgb(r, g, b)` form; the `rgba(0, 0, 0, 0)` guard covers the transparent case. Fallback value `#111111` equals the theme surface token (U04) — consistent.
- Everything else in the diff hunk unchanged: visible window, held scales, original line colors, recorded level nodes, NY dates, single download + revoke after 1100ms, error paths.

## Independent test execution

- Combined run: the extended download test hit the jest 5000ms timeout under parallel load (disclosed in U02 verdict).
- Isolated `--runInBand` re-run: **20/20 pass**, exit 0, includes the pin asserting actual canvas `fillStyle === 'rgb(17, 17, 17)'` (the displayed computed value, not a constant). Log: `../evidence/cline-verify-rpc.log` sha256 `45648d53e3cc0140...`.

## Honest remainder

The unit receipt uses a mocked canvas. A real isolated-browser PNG download on the frozen snapshot is **not yet executed**; per the dossier that remainder belongs to U17's visual/interaction gate. This verdict covers code + unit evidence only, exactly the scope the dossier requested.

**Verdict: ACCEPT** — bound to baseline `8194eca4` + file hash above. Task U05's full acceptance additionally waits on the U17 browser receipt.
