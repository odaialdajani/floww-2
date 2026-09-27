# Integration verification - 2026-09-26

Full AI/UI objective remains open; this report records the current-main integration and bounded corrections. Mobile work remains paused. No deployment, merge into remote main, broker order, production migration, or AI quality acceptance is implied.

## Source scope

Pre-merge branch: dba50893403922a2f82e2be7c5a2671ea8d37780. Incoming main: 79b28ec25d4f9c3cedd983ecd14a27e88b2f8948 (fetched again at 20:18 UTC). Conflict resolutions retain Public-only market access, the desktop redesign, durable saved research, exact selected-map context, incoming recorded replay/compare/wall review, and conservative missing-data states.

Bounded independent reviews: backend-integration-review-20260926.md, frontend-integration-review-20260926.md, pr-backlog-review-20260926.md. These are not a claim that every incoming line was audited. Useful sidebar-label changes from PR49 and ticker paging from PR12 were ported; a reproduced shrinking-universe paging defect was corrected. Older PR3/4/5 decisions remain unchanged. Remote PRs were not modified.

## Confirmed repairs

- Replay now removes current spot, percent change, live refresh and movers from all surrounding dashboard and application summaries. Recorded missing spot remains unknown; replay cannot initiate trade actions. Live exit restores current information. Unsupported replay/overlay AI research is explicitly refused rather than silently answering a different live map.
- Map selection uses the actual displayed grid/overlay axes and preserves valid selection across same-scope refresh. Manual refresh and polling cannot overwrite newer responses.
- Snapshot selection and retention sort mixed legacy string/new datetime timestamps by their actual instant before applying limits. Historical route filters use the same ordering.
- Checklist exposes truthful levels, ATM volatility, expected move and model-based hedge shares. Historical IV rank, missing skew wings, absent signed walls and unsupported strategy recommendations remain unavailable. Corrected hedge-share calculation removes a factor-of-100 error and states its call-positive/put-negative inventory assumption; it does not establish real dealer positioning.
- Per-connection storage locks prevent a failing snapshot transaction from rolling back another thread's acknowledged write. Saved reviews validate decision/ticker ownership and return failure when persistence is unconfirmed.
- Bound query parameters prevent a stored policy string from deleting another decision's outcome. Low-level decision listing validates and binds its limit. Other static query warnings are retained, with literal-escaping probes; no broad security certification is claimed.
- Source provenance, empty chart eligibility, observed open-interest changes, accepted expiry coverage and actual contract series clock were corrected. Expired test fixtures now use controlled trading dates or future expiries. A malformed continuous-check configuration was repaired.

## Controlled desktop evidence

Headless browser, locally built production assets, controlled route responses, outside requests blocked. Live fixture spot999 versus recorded unknown spot and a stored1.1K cell made contamination visible. Final replay view contained no live999, showed stored1.1K, disabled Trade, and live exit restored999. Screenshots merge-replay-hidden-fixed.png and merge-replay-layout-final.png were inspected locally. This proves the controlled interaction, not live-provider availability or historical causality.

Frontend full run:95 suites/815 tests passed (includes two tests from concurrent uncommitted history work). Production build passed after final replay spacing changes. Rust unit tests:29 passed;23 existing compiler warnings remain. Whole backend Ruff passed. Whitespace check passed. Focused independent final checklist/query checks:8 passed. The final backend suite result is recorded below when complete.

## Remaining evidence and ownership limits

The fresh AI comparison remains unrun. Its September11 execution seal no longer matches merged code; preserve the old seal and input/rubric history, create a new versioned freeze, check authoritative shared usage and keep the daily40-call limit. A reset/empty temporary database is not quota evidence. Broader research, proposals, durable paper trading, watches, forward learning and later-fill reconciliation remain unfinished under the full plan. Paper slippage accounting is awaiting explicit user choice. No live-trading authorization exists.

Historical chart lookback belongs to the existing goal. Another ongoing local session owns stock catalog and price/node history files and their mounting work. Those untracked files are preserved and excluded from this integration commit; they are not declared delivered here. A chart can compare saved readings with subsequent price, not establish causality. Current replay does not create missing historical observations.

Legacy missing model/reference/backtest inputs and absent Python browser dependency remain unverified. Production backup/restore, forced crash recovery, complete worker startup and remote authenticated ownership still need their own evidence. Earlier incident/audit notes and September11 failed results remain preserved. This run used isolated test stores and an offline network guard. All new checks launch hidden; existing user windows and jobs remain untouched.

## Final full result

Backend: **5902 passed,39 skipped,0 failures,0 errors**,140 warnings,381.92seconds. The full result and all skipped identities/reasons are in [backend-suite-20260926.json](backend-suite-20260926.json). The collection-time skip is tests.test_dvt_backtest_byte_compat. These39 remain unverified, not passes. Warnings include old serialized-model library versions and existing numerical/deprecation notices; passing tests do not establish trained-model validity. Source hashes captured before this final run matched afterward. No production source changed after collection.

Raw logs, source-hash inventory, screenshots and isolated-store evidence remain local under output; the sanitized result and reviews are committed.

Post-run cosmetic change: removed redundant trailing blank lines in heatmap_history.py and test_r7_7_red.py after the staged whitespace check identified them. No executable statements changed.
