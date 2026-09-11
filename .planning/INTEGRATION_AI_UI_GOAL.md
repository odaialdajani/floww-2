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
- Latest focused research run: 60 tests passed on Python 3.11. Coverage includes real calculators, native DuckDB read seam, owner isolation, bounded work, cancellation, restart, model format validation, spending/reconciliation and import/order boundaries.
- Full backend attempt stopped with 867 passed and 29 failed after roughly 17 percent. A missing local MongoDB makes every root fixture wait; failures also include existing model files, ticker routes and other services. This is not a full pass or total-coverage proof.
- Automatic approval review rejected downloading/starting the local MongoDB with reason "blocked by policy". No database was installed. Real durable restart and authorized provider benchmarking remain blocked; the browser fixture is explicitly not that proof.
- Paper accounting correction is proposed in ADR 0010; user decision is pending. Paper, remote identity, account bindings, live enabling and forward promotion remain gated.
- Remaining research release work includes outcome-path/minimal resolver completion, full fault/functional evaluation, provider comparison, and deployed storage-driver proof. Later catalog/proposal/watch/paper/live stages are not being marked complete by the core implementation.
- Unrelated changes to .planning/config.json and kanban/BOTTLENECK_ALERTS.md are preserved and excluded from this delivery staging.
- Scratch transcripts/research remain local and backed up; they are not implementation artifacts.
