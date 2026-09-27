# Main reconciliation - 2026-09-27

Status: IN PROGRESS. Do not treat this checkpoint as a completed merge or deployment.

## Authorized scope

User requested our branch, latest main and remaining colleague work be reconciled, tested and pushed to main, with the measurement upgrade plan saved. Priority is actual market-data legitimacy, math, reading precision and backend/frontend consistency. New paper/demo trading improvements are deferred. Existing work is preserved; merging existing code does not claim deferred product features are complete. User explicitly chose that authenticated cancellations remain available when new live submissions are stopped. No live trading is enabled.

## Starting references

| Reference | Starting commit | Disposition |
| --- | --- | --- |
| origin/main | 5d92ae012d07903bf1d503e7bada42e7a6940ec1 | Base for isolated integration; 18 commits absent from work branch |
| work/reconcile-ai-ui-20260911 | d4d724a38cbc93d438afd658d2dec1b796486219 | 50 commits absent from main; primary merge being resolved |
| origin/fix/audit-2026-09 | 577345c4a7d6cd7e6bea6e330c417b07c90c8a77 | Pending reviewed integration |
| origin/docs/model-audit-2026-09 | 206de221019cf7f9712ef8c7302d55dd452c2302 | Pending documentation integration |
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
- Full combined validation and final independent review: PENDING.
- Push, remote ancestry verification and canonical main checkout: PENDING.
