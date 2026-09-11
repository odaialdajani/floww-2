# FLOWW reconciliation, AI and UI delivery

User objective confirmed 2026-09-11: preserve and commit local work, review colleague changes and backlog, bring current main into the working branch, implement the two specified plans, validate and commit delivery.

## Authoritative scope
- AI: .planning/unknowns/lodestar-plan-v4-review-draft.md
- UI: .planning/mockups/tidehunter-pro-2026-09-05/PLAN.md
- Preserve explicit later live-trading authorization and forward-observation gates; do not count unavailable external evidence as completed implementation.

## Evidence and progress
- [x] Identify and preserve both exact plans.
- [x] Copy all 102 dirty/untracked files to external safety copy FLOWW2-safety-20260911-1531.
- [x] Commit 77 source/test/design files at 3b98ada0 on work/reconcile-ai-ui-20260911.
- [x] Fetch colleague main (7685a44b initially; 424 commits ahead of original local main).
- [x] Review 18 merge conflicts independently for backend and main dashboard; resolve preserving local single-page design and incoming backend/Skylit fixes.
- [x] Commit integration at 9d5e500a; focused merge checks passed (full release checks remain open).
- [x] Review open PRs 3, 4, 5. Do not merge obsolete regressions; retain useful fixes already present and preserve unknown source times.
- [ ] Review remaining merged changes and record actionable backlog with evidence.
- [x] Bounded research contracts and reproduced failures for grounding, spending, request identity and cancellation.
- [ ] Complete durable evidence-backed research and shared screen context.
- [ ] UI v3 full controls, four answers and dealer drill-down.
- [ ] Research acceptance/recovery/ownership/cost proof.
- [ ] Remaining meaningful capabilities, proposals, paper book, watch/briefs per AI gates.
- [ ] Full required checks, real UI comparison and read-only research handoff.
- [ ] Final commits, refresh remote and publish reviewable delivery.

## Merge decisions
- Preserve local dashboard JSX/CSS as base: incoming version restores obsolete scanner/flow/gamma tabs. Port useful incoming factual metadata separately.
- Incoming Skylit ticker universe and cycling supersede local no-op arrows; retain other auto-merged local behavior.
- Keep local fetch coordinator optional budget handling and calibration correctness; incoming quota module/tests and outcomes extend capabilities.
- Incoming alert defaults align with incoming scan rules; preserve local spread-leg demotion.
- Preserve local alert-persistence decision naming actual floww database.

## Open findings
- Incoming invalid/nonfinite return counting fixed and regression-tested in the integration commit.
- Latest full frontend run: 75 suites, 609 tests passed. Production build and both narrow/wide browser views checked with explicitly synthetic offline data. More focused controls and two-address checks are in progress.
- Latest focused research run: 77 tests passed on Python 3.11. Coverage includes real calculators, native DuckDB read seam, owner isolation, bounded work, cancellation, restart, model format validation, spending/reconciliation and import/order boundaries.
- Full backend attempt stopped with 867 passed and 29 failed after roughly 17 percent. A missing local MongoDB makes every root fixture wait; failures also include existing model files, ticker routes and other services. This is not a full pass or total-coverage proof.
- Automatic approval review rejected downloading/starting the local MongoDB with reason "blocked by policy". No database was installed. Real durable restart and authorized provider benchmarking remain blocked; the browser fixture is explicitly not that proof.
- Paper accounting correction is proposed in ADR 0010; user decision is pending. Paper, remote identity, account bindings, live enabling and forward promotion remain gated.
- Remaining research release work includes outcome-path/minimal resolver completion, full fault/functional evaluation, provider comparison, and deployed storage-driver proof. Later catalog/proposal/watch/paper/live stages are not being marked complete by the core implementation.
- Unrelated changes to .planning/config.json and kanban/BOTTLENECK_ALERTS.md are preserved and excluded from this delivery staging.
- Scratch transcripts/research remain local and backed up; they are not implementation artifacts.

## Checked checkpoint - 2026-09-11 17:38 UTC

- Final frontend: 75 suites / 609 tests pass; final production build succeeds. Viewed final 1280px board and dealer chart with explicit synthetic offline source. Prior 390px fit and same/separate-origin saved-answer flows were exercised. No production data or restart proof is inferred from this fixture.
- Research: 77 focused tests pass, including corrected-bar ambiguity, receipt-time lookahead, immutable claim identity, owner-only collected history, browser recovery preflight, and nonblocking tracked maintenance. Prediction resolver remains a tested primitive: no predictive claims are issued, no real bar-range source/projection is enabled, no performance claims are made.
- Backend full Ruff passes. Required medium Bandit scan passes with the CI exclusions plus the second local virtual environment. Existing truth audit: 24 pass / 0 fail. Full backend remains incomplete; prior run stopped at 867 pass / 29 fail. Changed agent endpoint tests now pass; data-route invariant still fails because separately mounted brokerage paths share the prefix.
- Newly found merged live-order exposure: public_brokerage submission had no environment gate and falsely claimed paper default. Added explicit off-by-default FLOWW_ENABLE_LIVE_PUBLIC gate before broker access and explicit private-key dependencies for submission/cancellation. Six refusal tests failed before and pass after; seven existing mocked validation tests pass. No real orders were sent, no enablement setting changed. This is a safety repair, not approval or readiness for live use.
- Full test_public_api_only isolated attempt had four additional failures beyond the now-passing six authenticated validation cases: unavailable removed route expectation, history response shape, quote source mismatch, indicator error status. Preserve these in the review backlog; do not label the full backend green.
- Remote fetched at 17:35: branch contains current origin/main (3 ahead / 0 behind before this checkpoint commit). New colleague appshell typo branch duplicates the compile fix already integrated. No main merge, deployment or live service restart performed.

## Release blockers and next accepted work

1. User starts a real local database. Original automated installation/start was rejected by automatic approval review, reason: blocked by policy. No retry or workaround performed. Real driver compatibility, durable restart, restore, recovery/concurrency tests remain mandatory.
2. Freeze and evaluate >=30 held-out functional prompts, then compare the authorized models against deterministic answers with actual cost accounting. No paid benchmark or provider quality improvement is claimed.
3. Complete and validate claim projection and actual historical path availability, freshness/product policy and full research acceptance before expanding later catalogs/proposals/watch features. Current answers remain descriptive/non-gradeable.
4. Resolve broader merged-test failures with reproductions and scope evidence. Do not silence the data-only routing invariant merely because a gated brokerage route exists.
5. User accounting decision remains pending; paper book and later live stages are gated by the exact plan. Remote public access still requires verified identity. Do not enable later features merely to call the whole plan complete.

## Recovery and frozen baseline checkpoint - 2026-09-11 17:52 UTC

- Added replayable projection from the atomically saved answer into owner-scoped claims. Projection failure retains the canonical pending seed; startup and maintenance recover it. Finalization verifies the claim's evidence against the actual saved answer ledger and reissues the prediction at server time, refusing an already-elapsed event.
- Added immutable raw-path/resolution records with canonical timestamp strings, source-availability identity, owner checks and bounded per-tick work. Old repeated paths cannot replace newer corrections; revision order is separate from polling time. Save/reload BSON and the delayed-correction/interleaved-poll regression pass.
- The existing scheduler now records explicit unavailable historical windows for open claims. No recent-bars response is passed off as arbitrary-range backfill. No actual research answer authors predictive claims yet; the new recorder and resolver remain preparation for gated research outcome recording.
- Focused research checks now total 84 passing tests. Independent review found no further critical issue in this change. Real Mongo concurrency/restart remains unproven; same-millisecond conflicting source revisions need a declared tie/revision policy before automated grading is enabled. No real driver compatibility or restoration claim is made.
- Froze 32 new functional prompts, scenarios, exact screen contexts and human rubrics under eval/lodestar-research-v1. Captured deterministic answers with 32/32 request-scope/save/isolation checks passing and zero provider/model calls. The output explicitly states that mock storage and local latency are not production evidence. Human usefulness is reviewed separately; no paid candidate comparison or model advantage is claimed.
- Original local database start/install denial remains unresolved; port 27017 still absent. The accounting decision is also unanswered. Later research release, paper/live and full-plan completion gates remain open.

The independent baseline review found 14 met / 10 partly / 8 failed, not a useful-answer release pass. A four-versus-five exchange-session bug was reproduced and fixed using the installed calendar implementation. The original baseline capture stays immutable. These now-exposed cases are retired from unseen evaluation; a separate unseen set is required before candidate-improvement claims. Research checks now total 85 passing tests.

Further offline fixes: deterministic fallback now includes price versus a healthy same-time computed flip, gamma-regime explanation, actual expiry-date facts and explicit limits for unsupported events/product terms/probabilities/orders. Owner history is read without requiring a paid model; closing requests require the exact completed exchange close and matching price evidence, never an older closing substitute. Question expiry aliases preserve original chart context; ambiguous bare observation words do not change expiry, and naming the selected ticker retains its visible expiry filter. Research checks: 96 pass. Saved/rendered the richer answer in the offline browser; the test fixture was restarted by verified own process identity only.

New next-slice gap found during actual browser inspection: cached dealer map currently contributes to snapshot identity but is not converted to displayed-map evidence. The existing single default map cache key also cannot establish every Solstice scope. This must be completed or honestly unavailable before the shared chart-context release gate closes; do not mark the UI/AI plans completed.

## Exact displayed-map evidence checkpoint - 2026-09-11 18:23 UTC

- Added bounded read-only display evidence from the exact server cache key and build version. The heatmap response now carries its original request scope; both screen publishers freeze that scope instead of inferring it from controls that can outrun a pending response. This also fixes the previous 200-strike assumption: ordinary heatmap requests use the route's actual 80-strike default.
- Verified selected strikes/expiries and cell values against the server matrix. Dealer net/cumulative values preserve missing cells; incomplete totals are unavailable. Display gamma units remain separate from the raw-chain dollar exposure model. Cached map price is explicitly distinct from a separately updated quote.
- Tidehunter draws the flip from the same heatmap response. Solstice research follows its sidebar flip precedence. The map-level flip retains a separate scope from the visible-row sum and is not described as a recalculation for the user's expiry filter. Unknown source times remain unknown; the map's 120-second stale boundary and future-time guard apply to research too.
- Expanded Solstice drops an old ticker's map, freezes the actual visible response, and clears selected cell readings when the view or version changes. A shared row-selection function keeps the displayed table and research selection aligned. Saved answer headings now use the actual requested expiry window.
- Added display scope to snapshot identity after reproducing a collision between two different row selections. This prevents two different displayed-evidence sets from sharing the same saved anchor key.
- Validation: 105 focused research tests pass; 76 frontend suites / 612 tests pass; production build succeeds; full backend Ruff and scoped required-medium Bandit checks pass. Independent reviews found and drove the cache-key, flip-source, scope and stale-age corrections; the final bounded re-review found no additional critical issue.
- Viewed the real frontend with the explicitly synthetic local fixture and actual research service: saved SPY answer for expiry 2026-09-18 contains 13 facts, cached map price 500 versus flip 498, displayed gamma total zero, separate chain exposure, and scope limitations. Screenshot: output/playwright/research-displayed-map.png. This uses mock storage and no paid model; it does not establish deployed persistence, real market accuracy or model quality.
- Fetched origin again: current branch contains origin/main with no missing commits. No main merge, production deployment, paid request, paper order or live order was performed.
- The full plans remain incomplete. Local MongoDB still was not listening on 27017 at 18:22 UTC. Original automatic approval review rejected downloading/starting it with reason "blocked by policy"; no workaround was attempted. Real storage/restart/driver/restore checks, useful-answer acceptance and authorized model comparison remain required before later gated features. The paper-accounting decision is still unanswered. Broader backend failures and the exposed baseline's 14 met / 10 partly / 8 failed review remain recorded above.

## Session access checkpoint - 2026-09-11 18:33 UTC

- Previous goal turn classified as progress: committed exact displayed-map evidence and verified the rendered saved answer. The local database is still absent; the same external block remains, but review found useful local work rather than an impasse.
- Reproduced an already-open research stream continuing after its session was revoked. Streams now recheck ownership before each event/heartbeat and stop on revoked access or unavailable session storage.
- Added End research session to the shared conversation. It waits for explicit server confirmation, clears displayed/history state on success, invalidates pending history replies and notifies other same-origin tabs through storage events. It stays unavailable while an ask is active, avoiding overlapping session creation. Failed revocation is reported as unconfirmed and preserves the answer. Ending access does not delete stored history.
- Validation: 106 focused research tests; 76 frontend suites / 615 tests; production build, full backend Ruff and scoped medium Bandit pass. Reviewed the single-tab races independently, fixed the identified cross-view late-history gap, and tested two providers plus the browser storage event. Browser opened a saved answer and ended the session; the viewed screenshot output/playwright/research-session-ended.png confirms the answer/history disappear and the saved-history recovery notice is visible. This uses the same explicit offline fixture, not production persistence proof.
- A fresh UI requirement review found actionable gaps to fix next: acknowledged history reviving Trade now; percent-rule units; non-removable filter chips; stale-by-age labels; tape clear/oldest-first behavior. These prevent declaring UI acceptance complete even while database-dependent research checks are blocked.

## Feed and saved-control checkpoint - 2026-09-11 18:55 UTC

- Fixed acknowledged history reviving Trade now: visible history and eligible unacknowledged alerts now have separate paths. Cleared-feed observation identities persist without deleting acknowledgements or redispatching the same old alert; a genuinely newer observation can return. Added oldest-first order while retaining one pinned eligible row.
- Restored removable filter chips and slash-to-open/focus ticker search. Preserved each unrelated filter when removing a chip. Added elapsed cache-age handling, explicit unknown-age wording, limited scan coverage on answer cells, and a fifteen-minute source-age guard for money-card SIGMA readings.
- OI rules now accept displayed percent points consistently. Legacy fractional saved rules migrate once on read and persist through the guarded settings save; versioned rules do not convert twice. Negative/scientific numeric ranges and blank numeric values are tested.
- Browser inspection caught the cleared view still claiming an empty server feed and retaining old rule counts. Reproduced the misleading label in a failing check; changed it to No unacknowledged signals in this screen and count only the visible feed.
- Validation: 77 frontend suites / 627 tests pass; final production build succeeds. The broader public-advantage group now passes all 43 checks. Its older spread-propagation test failed because the fixed expiry's estimated premium fell below alert eligibility; a fixed price and future expiry isolate the original propagation assertions without changing production rules. Backend reviewer confirmed the fixture repair is appropriately scoped.
- Viewed the real built frontend against the explicitly synthetic offline fixture: slash opens and focuses search, QQQ filter removes the SPY rows, removable chip restores them, feed clear removes Trade now, oldest-first order works, and reload preserves the cleared feed and layout. Narrow 390px controls wrap without whole-page overflow; viewed output/playwright/feed-controls-narrow.png. The underlying model/data/store are still offline fixtures, not real persistence proof.
- Real storage and restart/restore testing remain blocked by the original automatic approval rejection of downloading/starting MongoDB (reason: blocked by policy). No retry or workaround performed. Paper-accounting decision remains unanswered. Full backend and unseen real-provider usefulness gates remain open; later dependent paper/live work remains disabled. No real model, paid provider or broker request was made.

## Offline route-check repair - 2026-09-11 18:58 UTC

- Reproduced the five previously recorded Public route failures with a fail-closed external-network guard: missing test auth configuration; old bars count field; two outdated indicator mock targets; and a data-router assertion incorrectly enumerating all app routes including the separately mounted brokerage router.
- Corrected the tests to their current documented contract, asserted the actual timeframe/session forwarding, retained numeric SMA and unknown-indicator assertions, and kept brokerage refusal checks separate. No production trading rule or endpoint permission was weakened.
- Added a shared test guard against external socket connections and real HTTP transports. Windows asyncio loopback socketpairs remain allowed. Attempted requests also fail teardown, so an exception swallowed into a 502 cannot make an accidental outbound attempt pass.
- Before this guard was installed, the independent reviewer ran two outdated supposedly offline tests that unexpectedly read Public account metadata and SPY history. The reviewer stopped and reported the leak. No order was sent. This corrects any earlier blanket statement that no provider request occurred during the entire integration session; the synthetic browser/research evaluations still made no paid model calls and are not live-data proof.
- Final isolated Python 3.11 route and brokerage checks: 65 passed, with no attempted external connection; scoped Ruff passed. Full backend remains unverified: the earlier incomplete full run and its unrelated failures are not superseded by this narrower result.
