# Market repeat-history independent review - 2026-09-26

## Verdict

The reviewed repeat-history and snapshot-truth repairs are present in the production source files. No remaining blocker was found within this bounded review. This is approval of the checked implementation and local evidence, not proof of complete real-time market coverage or a live second full-market rotation after the change.

At 23:56 UTC, all four production service files matched the reviewed isolated copies exactly after decoding and newline conversion; their parsed Python structures also matched. Raw byte hashes differ between production and preparation copies because of file representation, not source changes.

## Original failures and repaired state

- The former global 20,000-contract cache lost every prior observation in an 8,786-name, three-contract-per-name rotation: independent prior-hit counts were 0 then 0. The bounded per-name persistent store retains up to 60 selected contracts per name without another name evicting them; the replacement fixture yielded 0 then 26,358 usable prior records. Per-name limits and unavailable storage are disclosed.
- Invalid volume, same-day downward revisions, day changes, duplicate receipts and bad clocks no longer manufacture fresh volume. Receipt-window changes remain descriptive; source-timed arrival rates require their own supporting source times. Invalid prior intervals remain unknown.
- Old or misordered quotes cannot revive directional signing from stale mids. Current quotes later than the trade are rejected. Conflicting repeated identities and distinct identities colliding under the existing display key are excluded consistently from rows, stored observations and derived context; identical repeats collapse once.
- The desk receives the validated snapshot change and receipt time while retaining its existing campaign and volatility work. Failure and capacity states remain visible.
- Cumulative day volume times a current/model price remains an estimate. Both Public quote input and the alternate raw daily-volume source receive cumulative-snapshot scope. Aggregate direction stays unknown, last-trade classification stays separate, no known-direction score bonus is awarded, and directional price levels are absent. Saved context preserves these facts through the normal alert feed.
- The current UI shows the estimate prefix and its calculation basis, renders no aggregate direction, and excludes these rows from directional trade-now selection. The remaining misleading print labels were changed to daily activity. Useful daily volume and activity rows remain available.
- SQLite startup closes unsuccessful connections, retries only busy/locked initialization failures and leaves no cached partial connection. Scanner storage calls run through worker threads. Retry is bounded but is NOT a strict two-second total timeout.

## Independent evidence

The detailed original reproductions and incremental checks remain in output/market-coverage-check/repeated-scan-review.md and snapshot-premium-review.md. Review checks used isolated synthetic inputs and temporary/in-memory stores, with no provider/model calls.

Independent execution included:
- Reversed duplicate-order and display-key collision cases through scanner rows, normal alert conversion and stored observation selection.
- Snapshot truth tests plus updated alert tests: 41 passed.
- Actual eval_institutional -> persist_alerts -> read_alert_feed for both quote-priced and model-priced daily rows: both survived as FLOW, unknown bias, absent directional levels and saved estimate provenance. A local zero score gate was used only to exercise emission; this was not a production filtering claim.
- Actual frontend helpers on top-level and saved-context scope: estimate retained, NO DIRECTION, no levels and no trade-now candidate.
- Startup recovery/non-lock refusal/concurrency: 3 focused tests passed. An independently held exclusive SQLite lock exhausted safely and later recovered; an asynchronous heartbeat continued with a maximum 16ms gap. Observed startup exhaustion took 3.188 seconds, establishing why the retry must not be called a strict two-second cap.

Final integrated test artifacts checked:
- integrated-services-final.log: 246 passed, 27 warnings.
- integrated-observations-final.log: 24 passed, 6 subtests passed; includes real local storage/rotation checks.
- integrated-consumers-corrected.log: 40 passed, 27 warnings. Synthetic known-direction tests now explicitly supply signed evidence; daily-input negative direction checks remain.
- truth-ui-full.log: earlier full frontend run, 847 passed across 98 suites; retained an open-handle warning after the assertions.
- truth-ui-mounted-final.log: final touched component/helper group, 100 passed across 3 suites.
- truth-ui-build-wrap-final.log and exit record: final build succeeded.

These are separate, potentially overlapping groups and are not presented as one unique combined test count. Earlier failures are preserved: the initial integrated invocation had test-import collection errors; an earlier consumer run exposed old tests that had treated cumulative daily volume as signed trades. The subsequent correctly scoped and corrected runs above passed.

The actual-component browser record at output/market-repeat-preparation/premium-ui/verification.json reports a synthetic ~$200k estimate with the explanatory tooltip, unknown direction, no obsolete Fresh print label, no page errors and no horizontal overflow at checked widths. It identifies the final production stylesheet and source hashes. This reviewer independently verified the helper behavior and inspected that browser artifact; the browser check itself was performed by the parent agent.

## Live pass and integration boundary

The saved .planning/eval/market-full-pass-20260926.json ended at 23:51:51 UTC with completed_with_gaps: all 8,786 provider-listed option-enabled names were attempted, 4,350 returned usable results and 4,436 were unavailable. This is a complete attempt, not complete usable coverage. Only two expiries per name were requested, the feed applies its disclosed row bounds, and the provider directory is not proven to be the entire exchange-listed universe.

Independent comparison of before-integration-proof.json against the live record confirmed all seven frozen source hashes were unchanged from the start of that pass until the pre-patch check at 23:52:21 UTC. Production integration therefore followed completion of the preserved old-source pass. That pass cannot be claimed as live validation of the later repeat-history repair.

## Remaining limits

No post-integration live second full-market rotation, restarted application behavior or new source-time provenance was claimed. Current-price repricing is not actual executed money; snapshot change does not prove when individual trades occurred. The store intentionally retains only its bounded subset. Startup worker waits can exceed two seconds although retry terminates and does not block the asynchronous loop. This review did not reopen unrelated project, paper-trading or model-evaluation scope.

## Production source receipt

Production raw SHA-256 values checked at 23:56 UTC:

- backend/services/scan_observations.py: c781b69902f962a699a2cf67403f70fc1154ebeae53c60566436328f465ab8a6
- backend/services/public_scanner.py: efab105e0145ba302c2f4811ccb239ee7157e035f52dceb0ace767b180d6e6db
- backend/services/flow_alerts.py: b29cd5e12c5c576186c95c8b01ca3943f9938413808f240517160aabd85346ab
- backend/services/flow_desk.py: 9f6d5fabaca0477f57a642e226eadace06ca87e5a7c4d2b80382c62c7f00bd38
