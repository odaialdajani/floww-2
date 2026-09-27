# Main reconciliation - 2026-09-27

Status: RECONCILED AND VALIDATED locally; main publication and checkout equality are verified at delivery. This is a source merge, not an application deployment.

## Authorized scope

User requested our branch, latest main and remaining colleague work be reconciled, tested and pushed to main, with the measurement upgrade plan saved. Priority is actual market-data legitimacy, math, reading precision and backend/frontend consistency. New paper/demo trading improvements are deferred. Existing work is preserved; merging existing code does not claim deferred product features are complete. User explicitly chose that authenticated cancellations remain available when new live submissions are stopped. No live trading is enabled.

## Starting references

| Reference | Starting commit | Disposition |
| --- | --- | --- |
| origin/main | 5d92ae012d07903bf1d503e7bada42e7a6940ec1 | Base for isolated integration; 18 commits absent from work branch |
| work/reconcile-ai-ui-20260911 | d4d724a38cbc93d438afd658d2dec1b796486219 | 50 commits absent from main; primary merge being resolved |
| origin/fix/audit-2026-09 | 577345c4a7d6cd7e6bea6e330c417b07c90c8a77 | Merged with reviewed corrections |
| origin/docs/model-audit-2026-09 | 206de221019cf7f9712ef8c7302d55dd452c2302 | Merged; exact history preserved |
| origin/fix/skylit-panel-bugs | ca255571c3e2dae059567fba3f74d180750b1e38 | Superseded/imported behavior; independent review below |
| origin/agent2/fetched-at-pipeline-v2 | 008e31b95f7076e1fe1da143055918ecc854b658 | Valid timestamps already preserved; do not invent a missing timestamp |

All 280 original Git refs are in a verified complete local recovery bundle; current local-only model files and the plan are separately copied and hashed. Original working tree was clean. Integration occurs in a linked worktree, not in the running app directory. No historical branch or user file is deleted.

## Primary conflict decisions

- Market-data responses retain main's dollar-GEX units and the work branch's source/event/receipt/staleness metadata.
- Main's durable node/wall state functions are retained with the work branch's shared-connection guard, including its existing guards on history operations.
- Both live movers and the universe leaderboard remain hidden in replay.
- The newer Tidehunter design retains main's 60-second scan-age warning, based on the supplied age rather than a refresh click. Unknown age remains unknown.
- The race-safe WebSocket hook keeps main's authentication token on initial connection and reconnection.
- Wall inspection retains true gross/net and coverage distinctions plus main's durable/memory-only label.
- Paging retains main's wide ticker universe and the bounded-page correction after the universe shrinks.
- Tests preserve fixed-clock and future-session fixtures, typed quote objects and independent calls rather than manufacturing missing data.
- One duplicate clean-merged frontend integrity check was removed; the same blocking check remains.
- Order submission validates input and refuses before broker acquisition when disarmed; cancellation still requires authentication and is allowed when submissions are disarmed (user decision). This is reconciliation of existing safeguards, not new trading work.

## Older open branches

Independent read-only review found PR 3's named panel fix 280c44cf byte-identical to imported 24690400, already an ancestor of main and work. Current panel behavior, clamps, navigation accessibility, type/import fixes and gamma scale tests preserve useful intent. SwarmFrame/AlphaPod additions were explicitly retired; restoring them would revive dead features. The three old model binaries were excluded during import and are documented in docs/salvage/README.md. Current ignored copies are backed up; meta_anomaly_v1.pt is newer than the old branch binary and must not be overwritten.

PR 4's live fetch timestamp is already recorded and preserved through cached responses and research reads. Its fallback from missing fetched_at to now would manufacture freshness and is intentionally rejected. The opt-in historical-filtering warning from its eval helper will be retained in documentation. No production caller was found for that scoring helper. Historical preservation branches are not a queue of new feature work.

## Plan preservation

The reviewed plan is now .planning/MEASUREMENT_UPGRADE_PLAN.md (tracked entry point), replacing reliance on an ignored local scratch file. It is still a proposed upgrade plan. This merge does not implement all its formula/settings work.

## Validation so far

- Focused frontend tests: 88 passed in two suites, including authenticated reconnect and scan age after refresh. The new 60-second warning test first failed against the unported design, then passed after the visible warning was restored.
- Focused backend tests: 134 passed, covering data routing, quote truth, history, exposure units, payload shape and the resolved order gate.
- Full combined backend: 6333 passed, 36 skipped, 150 warnings in 415.09 seconds on Python 3.11. Outside-network connections blocked, isolated test storage. No coverage or Python 3.12 result is claimed.
- Final frontend: 103 suites / 910 passed; final production build passed.
- Final independent backend/frontend review: no remaining material findings within declared scopes.
- Delivery requires ordinary non-force main push, ancestor checks for original work/main and current colleague tips, and canonical checkout equality. A local delivery receipt records those results.

## Combined integration corrections and validation

Reconciled the colleague audit branch with the newer production screens and accepted source-quality contracts. Corrected: Charm dollar scaling, declared time units, weighting and missing-cell coverage; restoration choosing an older full wall record over a newer event; duplicate alert broadcast functions; and node readings treating call/put activity as directional evidence or saved alerts as executions. Node rows now match contract strike and actual stored expiry/context fields, preserve negative gamma and distinguish missing direction.

- Full frontend: 103 suites, 910 tests passed after the corrections. Final production build passed.
- Focused merge regression set: 70 passed; final persisted-field checks additionally passed in independent review. Full backend result is recorded below.
- Full backend Ruff and configured medium Bandit checks passed.
- Independent backend and frontend reviews report no remaining material finding in their stated scope.
- Browser inspected the actual merged NodeConfluencePanel with current production CSS and synthetic data generated by the actual node service. At strike 500, call-heavy activity stayed grey, negative GEX retained its sign, one saved alert was labelled as an alert, and direction displayed not enough evidence. This is bounded component display proof, not live-provider or whole-app acceptance.
- Latest remote main advanced to b46e9af0 with model-manifest audit discovery; its related self-test branch is also merged.

## Final current-branch reconciliation

Merged current main b46e9af0, original work d4d724a3, colleague audit577345c4, model-audit documentation206de221, manifest discovery f9275c57 and audit self-tests e9db2910. Documentation and manifest branches have equivalent content already on main; their merges preserve actual history without restoring older files. Archived salvage branches retain the earlier documented disposition.

The incoming audit tests initially failed20 checks on Windows. Corrected tool selection, Git executable-mode verification, shell line endings, hidden child launches and explicit test interpreter. Discovery checks now execute the real gate block; all four filename conventions receive actual metric verdicts. No gate rule was disabled. Independent source review found no blocker.

The6333-test full run preceded the newly fetched audit self-tests, so final evidence is that completed full run plus the separate incoming audit test run. All1433 existing backend/frontend tracked source hashes remained unchanged through completion; the additional work is audit tests and shell line-ending policy. Browser proof remains synthetic and bounded. The measurement plan is saved and remains proposed, not fully implemented by this merge.

Final incoming audit check: 27 passed, 1 existing warning; no skips. Final focused Ruff passed.
