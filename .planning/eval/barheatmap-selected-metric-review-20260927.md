# Independent selected-metric bar review - 2026-09-27

Final verdict: PASS after selected-metric expiry union correction. Initial review required changes. Read-only production review; temporary mounted checks only.

The correction properly prevents VEX/Charm from falling back to raw GEX, represents true zero without a directional bar, and keeps null/sparse selected coverage unavailable. However its selected sum originally reused `grid.expiries`, whose current server meaning is vendor-GEX expiry coverage. Canonical VEX can legitimately have more expiries because vendor gamma is not needed for local vanna.

## Concrete numerical/sign reproduction

At spot/strike 100, IV .4, T .1, multiplier 100:
- January call OI100, supplied gamma .01.
- February put OI1000, supplied gamma absent.

Actual compute_gex_grid_vendor produces January-only axes and raw GEX +10000. Actual compute_vex_grid_local produces January +337.160062409988 and February -3371.6006240998795, complete VEX coverage with zero missing inputs. Server `_with_vex` attaches that selected matrix to the GEX grid. Correct selected full VEX net is -3034.4405616898916.

The initial revised BarHeatmap mounted a positive +337.160062409988 right-hand bar, because it silently omitted the February VEX expiry. This is a material sign reversal, not a formatting issue.

Evidence: `output/barheatmap-expiry-axis-repro-20260927.json` contains exact synthetic inputs, actual producer outputs and the data shape used by the mounted component. `output/barheatmap-independent-red-20260927.json` records two failures and two passes: real-producer opposite-sign case and empty raw expiry axes fail; explicit null matrix and sparse missing coverage/true cancellation pass.

Real consumer: App.js Bars view renders BarHeatmap with current displayData and viewMode. Minimal correction: include both declared raw expiry axes and actual selected-matrix expiry keys, deduplicated; keep finite-cell completeness and no fallback. An empty raw expiry list must not erase real selected matrix axes.


## Final independent verification - 02:24 UTC

Root applied the union of declared grid expiry axes and actual selected-matrix keys. Independent mounted rerun passed all 11 tests across the four fresh reviewer cases and seven authored regressions: `output/barheatmap-independent-green-20260927.json`.

The actual producer-shaped case now mounts the correct negative VEX net -3034.4405616898916 and left-side bar; empty raw expiry axes retain selected-matrix data; explicit null matrices cannot fall back to legacy numbers; sparse missing cells cannot become a surviving subtotal; full cancellation remains numeric zero without a directional bar. GEX-derived king styling is not applied to VEX.

Scratch test source is preserved at `output/barheatmap-independent-20260927.test.jsx`; it was moved out of frontend source after execution. Reviewer made no production changes. No remaining blocker was found in the scoped metric-substitution/expiry-sum correction. Browser visual verification is separate; this review executed local mounted React checks with real producer outputs and no external/model/provider/order calls.

Final BarHeatmap.jsx SHA-256: `9b5c620125ec268625810d9b39af7a559e73a3cb97086657f8faf380b25a209a`.
