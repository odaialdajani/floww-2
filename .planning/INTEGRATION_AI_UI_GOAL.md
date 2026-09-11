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
- [ ] Pass combined baseline checks and commit integration.
- [ ] Review open PRs 3, 4, 5; integrate sound missing fixes. PRs 4/5 have failed ruff checks at initial inspection.
- [ ] Review remaining merged changes and record actionable backlog with evidence.
- [ ] AI contracts and failing examples.
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
- Incoming rule-value statistics admit invalid/nonfinite returns into sample counts; reproduce and fix.
- Frontend merge validation running; backend first invocation failed because pytest-cov is absent (--no-cov unsupported), rerun without it.
- Scratch transcripts/research remain local and backed up; they are not implementation artifacts.
