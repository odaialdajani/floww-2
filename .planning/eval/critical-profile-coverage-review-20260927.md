# Critical profile coverage review - 2026-09-27

## Verdict

CONFIRMED and fixed in owned component. Missing/null expiry cells were rendered as measured zero and could mark the strike AIR, falsely describing unavailable coverage as a low-pressure pocket. Root must review/commit; browser reviewer is separately capturing final source.

## Actual application and source connection

App.js passes displayData directly to VolumeProfileGrid when Profile is selected (line 980 in inspected source). displayData only decimates the outer flat strike list above 2000 rows; nested grid is preserved. Profile always represents gamma here, not another metric selector.

Backend services/gex_core.py compute_gex_grid_vendor builds a sparse grid, skipping contracts with missing supplied gamma. Its expiry/strike axes are unions of accepted cells. A missing cell therefore cannot establish measured zero; absent listed contracts and skipped unavailable contracts are not distinguished in this shape.

Called that actual pure producer with spot 100 and four synthetic call contracts. Strike 103 has gamma 0.1, OI 100 at each of two expiries. Strike 99 has gamma 0.0001 at the first expiry and missing gamma at the second, both OI 100. Actual output cells are 100000/100000 for strike 103 and 100/absent for strike 99.

Mounted that exact output in both original committed component and corrected component. Original strike 99 printed [100,0], received is-air styling, and header advertised Air: 1 strikes. Corrected strike 99 prints [100,unavailable dash], has no AIR styling or header claim, and reports incomplete readings. At spot 100 this strike is also the nearest spot row, so the separate AIR tag is intentionally suppressed by existing SPOT behavior; false AIR styling and header count were still visible before the fix. Original/null-cell regression separately verifies false AIR tag on non-spot rows.

## Correction

- Accept only finite numeric readings. Missing/null/nonfinite/string values stay unavailable; strings no longer crash number formatting.
- Keep explicit numeric zero as zero. Fully covered zero rows retain AIR when appropriate.
- A strike total is available only if every displayed expiry has a known reading. Low-pressure interpretation requires that complete coverage and uses summed absolute expiry pressure, preserving existing protection against cancellation being mistaken for AIR.
- Flat legacy total_gex still works when gex is absent. Explicit missing gex is authoritative and does not silently fall back to a different field.
- Missing expiry axes no longer manufacture an empty sum of zero.
- Visible notice explains that incomplete rows are not marked AIR. Existing externally supplied node strip is unchanged.

## Verification

Before fix: 7 failed, 5 passed across 12 mounted tests. Failures cover explicit null, absent cell, partial expiry coverage, missing flat gamma, nonfinite/string readings and missing expiry list. After final source edit: all 12 passed. Additional actual-producer before/after comparison: 2 passed, explicitly asserting the old false reading and new unavailable reading. git diff --check passed, with ordinary Git line-ending notices only.

Final source edit: 2026-09-27 02:23:41 UTC. Proof includes red/green outcomes, exact synthetic producer input/output, rendered before/after values, and source SHA-256 hashes: .planning/eval/critical-profile-coverage-proof-20260927.json. Temporary scripts/output/configuration remain in C:/Users/DARK HERO/AppData/Local/Temp/floww-chain-review-e25801c5. No source files outside VolumeProfileGrid.jsx and its existing test were edited; no commit performed.

## Limits and unsupported meaning

No real provider call, full App mount, or app restart. Browser painting is separately owned. A finite upstream cell may itself omit another unavailable contract at the same strike/expiry; frontend receives no per-cell completeness data to discover that. This correction prevents frontend invention from visibly absent cells, not certification of underlying producer completeness. Sparse missing cells cannot prove either no listed contract or unavailable inputs, so both display unavailable. Node-strip Air levels supplied by backend are upstream-owned and unchanged. No new data-shape guessing or broad node-methodology edits.
