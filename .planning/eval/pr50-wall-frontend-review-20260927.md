# PR50 wall frontend independent review - 2026-09-27

## Current verdict

PASS for the bounded data-truth frontend recheck at 2026-09-27 01:10 UTC. All three grouped findings below are CLOSED; historical reproduction evidence is preserved. Product source is read-only for this reviewer. Owned only this report and output/pr50-wall-review-20260927 independent proofs. No paid/model/provider calls, no browser attempt, no paper changes and no commit.

Hard-tasks proof target: current selected-wall readings preserve measured-zero versus missing distinctions, count each member once, disclose incomplete VEX coverage, and never show malformed or non-finite amounts as valid dollars. Parent owns physical product-layout inspection.

## Reproduced findings

1. Duplicate members double-count net/per-expiry (medium). With wall.members=[100,100] and one finite VEX cell 25 plus contract gross 100, row displays $100 / $50. Gross uses a set while net loops the original list. The same member loop appears in per-expiry contributions and displays $50 instead of $25. Deduplicate valid member identities once and use consistently.

2. Partial VEX coverage silently appears complete (medium). Members [100,101], one covered zero-net member with gross100, and canonical VEX metadata reporting missing_vanna_inputs=2/quarantined=1/invalid_type=1 displays $100 / $0 with only 1 cells. There is no member denominator, partial flag or missing-input explanation. Show covered/total member coverage; report metadata counts as scope-level counts because the current metadata cannot localize missing contracts to this wall. Existing backend populates these metadata counters even when status is ok, so status alone cannot establish complete coverage.

3. Non-finite or non-numeric amounts become invalid dollar readings (medium). Two individually finite Number.MAX_VALUE VEX cells overflow their sum and gross sum to $InfinityB. Direct Infinity wall/activity amounts also format as dollars. Common fmtUsd coerces empty string and false to $0, and a nonnumeric string to $NaN. Require strict finite numeric formatting, finite aggregate results and finite per-expiry inputs. Missing/malformed values must not become measured zero.

## Initial proof

- First independent run: 4 FAIL / 3 PASS, exit1; independent.log.
- Expanded sibling checks: 8 FAIL / 3 PASS, exit1; independent-expanded.log.
- Scratch mounted suite: output/pr50-wall-review-20260927/independent.test.jsx, with local jest.config.json. All subprocesses explicitly windowsHide:true.
- Passing positive protections: duplicate gross rows are rejected, explicit new zero usable count overrides a positive legacy count, and changing current wall members/current grid cannot retain prior gross. No source edits performed by reviewer.

## Reviewed integration

SkylitDashboard SelectedWallBlock passes current data.grid to the inspector. Existing refresh test changes both net/gross and then removes the gross field to check old-snapshot unavailable behavior. The existing mounted dashboard, inspector truth and selection suites were rerun after corrections: 59/59 tests pass. Comparison basis text is visible in a small element, not only hover text. Existing end-of-App.css status/replay rules remain present. This is source inspection, not browser layout acceptance.

## Initial source identities

- frontend/src/components/heatseeker/WallInspector.jsx = 89012905a8bac39d70be62222c7ef8a5eb537e2cff22bb7a01edd736bf7c0a5e
- frontend/src/components/heatseeker/SkylitDashboard.jsx = b5c50ff5f6b05105f73b39313cc13d56f96d3c08b855a9b5e5b0f40f54fcd207
- frontend/src/App.css = d3071106856a3d1153c4e89365591e55996229580ddcbde0282c03e4596671f2

Manifest: output/pr50-wall-review-20260927/source-hashes-red.json. No claim of backend economic correctness, browser paint, complete comparison acceptance, trading setup eligibility or trading authorization.


## Closure recheck

- Independent original probes: 11/11 PASS, independent-recheck.log. Expanded final probes: 18/18 PASS, independent-final.log, exit0. Added strict explicit-new-count tests for true/string/negative/fraction/infinity/null and mixed numeric/string/invalid member identities.
- Existing dashboard, inspector truth and Solstice selection suites: 3 suites / 59 tests PASS, exit0; existing-recheck.log. Three React act warnings remain from dashboard review-journal state setters, not assertion failures.
- CLOSED duplicate members: shared memberStrikes retains only finite positive numeric identities and deduplicates numeric strings/numbers before both VEX and per-expiry aggregation. Single net25/gross100 remains $100/$25 with one member.
- CLOSED partial VEX disclosure: the visible basis reports covered/total member strikes and explicitly labels missing/quarantined/invalid-contract counts as scope counts. It does not falsely claim those global counts are wall-local.
- CLOSED false numeric amounts: common money formatting accepts only finite numbers; invalid primitive values and overflowing aggregate results display unavailable. Per-expiry inputs also require finite numbers. New usable counts are strict nonnegative safe integers; an explicitly invalid new count cannot borrow legacy positive coverage.
- Current-member refresh, duplicate gross identity rejection, old-snapshot missing gross, measured-zero coverage and explicit missing-input warnings remain verified. Reviewer source remained read-only.

## Rechecked source identities

- frontend/src/components/heatseeker/WallInspector.jsx = 7da4fc48bfb3346172241d64b4950865e7c8dd4d3b89ace121eebf87e83b29d7
- frontend/src/components/heatseeker/SkylitDashboard.jsx = b5c50ff5f6b05105f73b39313cc13d56f96d3c08b855a9b5e5b0f40f54fcd207
- frontend/src/App.css = d3071106856a3d1153c4e89365591e55996229580ddcbde0282c03e4596671f2

Manifest: output/pr50-wall-review-20260927/source-hashes-recheck.json. CSS identity is only the state read at this recheck; parent may adjust styling after physical layout inspection, so later CSS must receive its own final hash/visual check. No browser was opened by this reviewer. No remaining blocker found within the tested data-reading scope; physical layout and backend acceptance remain separate.


## Narrow sidebar layout recheck - 2026-09-27 01:26 UTC

Parent actual-product inspection found a strongest-wall price wrapping to two lines (reported 34.8px width / 33px height) and a five-column candidate row clipping in the 200px sidebar. Reviewer opened output/playwright/pr50/desktop-before.png and inspector-before.png: the candidate details visibly split into narrow fragments and extend beyond the inspector. These are before captures, not proof that the correction paints correctly.

Source changes reviewed read-only: summary rows inside .skylit-metrics-sidebar use a two-column grid, keep the value on one line, and place the supporting aggregate on a separate line under the value. The selector is scoped to the summary component; the separate selected-wall inspector is its sibling and does not inherit the no-wrap rule. The candidate table now has its own .skylit-shortlist-table class: each row uses a 12px membership column plus a flexible detail column, with four detail cells stacked beside the marker. All five existing cells and values remain in the component; no data is discarded. Comparison-table basis remains visible, and existing end-of-file status/replay CSS remains intact.

Focused current checks: four existing suites (sidebar, dashboard, inspector truth, selection) 71/71 PASS; layout-focused.log. Independent wall data probes 18/18 PASS; layout-independent.log. Both commands exit0, hidden processes completed. The same three dashboard review-journal act warnings are retained in the log; assertions pass. These DOM tests do not calculate actual CSS geometry. No new product/source tests or source edits were added by reviewer.

Current reviewed source identities:

- frontend/src/App.css = b5ef5296f12562de81a06cf86eded88182d07f1f18779ff1962965ce53bb666e
- frontend/src/components/heatseeker/WallInspector.jsx = b4c4195957bd0068cc76fd44946493c0a9c8a6233889997ac62bce2aca80d583
- frontend/src/components/heatseeker/SkylitMetricsSidebar.jsx = cabc16c722631061e5a0f165aec4b8fae2de343d412f82547297158bc1d21cf8
- frontend/src/components/heatseeker/SkylitDashboard.jsx = b5c50ff5f6b05105f73b39313cc13d56f96d3c08b855a9b5e5b0f40f54fcd207

Manifest: output/pr50-wall-review-20260927/source-hashes-layout.json. No source-level blocker found in the two layout corrections. Actual final compiled paint, clipping checks and browser geometry remain with parent and are not claimed complete in this recheck. Reviewer opened only supplied local images, not a browser, and did not restart any app or call providers/models.

## Final supplied production-build paint - 2026-09-27 01:28 UTC

Bounded visual PASS for the two corrected areas in the supplied final captures. Reviewer independently opened output/playwright/pr50/shortlist-final-1280-centered.png and summary-final-1280.png. Candidate membership marker, complete contract identity, expiry/delta, bid/ask/spread, quote times and tick-unknown label are readable within the narrow area. The strongest-wall price $650.0 is intact on one line and its aggregate is on a separate line below it. No clipped text is visible in these final cropped areas.

Reviewer also read measure-final-1600.json and measure-final-1280.json. Both record a 199px candidate table with scrollWidth 199; the membership cell is 12px and all detail cells are 183px, each with matching scrollWidth. Document width/scrollWidth match their 1600px and 1280px viewports. Price height is 16.5px, compared with the parent's earlier 33px wrapped observation. These inspectable measurements support absence of horizontal clipping for these rendered examples.

Parent identifies the final compiled assets as main.8c1a4ff0.js and main.0166caf6.css, served in an isolated local preview using clearly labeled synthetic inputs through the actual data/heatmap polling and selection path, with no injected styles on final navigation. Reviewer inspected the supplied output rather than independently navigating that preview. The existing floating Ask button covered an earlier crop; ordinary centering scroll produced the unobstructed final candidate capture. This does not claim the floating control can never overlap content at other scroll positions.

The supplied browser log includes unavailable synthetic-preview endpoints (503) and a failed external font request. The visual result is therefore accepted for the font actually painted in these captures, not as proof of clean network operation, every installed/downloaded font, all viewport sizes, screen-reader behavior or live-market correctness. No additional tests, source changes, browser control, app restarts or provider/model calls were performed for this final image review. The previously reported functional checks and current source identities remain separate evidence.
