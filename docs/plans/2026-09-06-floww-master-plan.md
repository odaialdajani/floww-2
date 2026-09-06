# Floww Master Plan — 2026-09-06

> **For Hermes:** execute track-by-track with subagent-driven-development. Fresh subagent per task, TDD, commit per task, never touch another agent's files.

**Goal:** one ordered picture of everything pending across our repo, the friend's fork (odaialdajani/floww-2), and the Tidehunter Pro redesign in the screenshot.

**Where things stand (verified today):**
- Our `origin/main` (5b9d9a9): PR #25 merged, CI green (ruff / frontend-build / backend-tests). Issues #21–24 closed; open: #17, #18, #8 (blocked: X credits).
- Friend's fork main (4d9715b, pushed 09-05): ~20 fork-only commits (Sept 4–5 fix pass) + round11 lanes + gsd/010 + gsd/011.
- Content check: nearly all fork fixes are ALREADY in our tree (Steal Three routes, Tidehunter nav, tanstack lockfile, VPIN band-edge fix, public_api services, no leaked key). Genuinely missing: FastAPI 0.110.1 → 0.136.3 bump, QC silent-except gate, gsd/010 exposure-alerts wiring.
- Tidehunter Pro: frontend tab fully built (FlowseekerProBlademap, live endpoints). Backend paid-API integration (Phase 4) correctly unbuilt — gated by design. The screenshot's v2 redesign brief + mockup HTML were NEVER pushed to the fork; they live on the friend's Windows box (`~/.claude/plans/the-design-that-was-curious-cerf.md`). Nothing to integrate until pushed.

---

## Track A — Port remaining fork delta (small, do first)
- A1: FastAPI 0.110.1 → 0.136.3 + starlette bump. Verify: `backend/.venv/bin/python3 -m pytest tests/ -q -x` subset smoke + `ruff check .`. Risk: middleware behavior change — run backend-tests fully before commit.
- A2: QC silent-except gate (friend's dc045bf4: lint grep gate + gate that fires). Port `qc/` scripts, verify gate fails on a planted silent-except then passes.
- A3: gsd/010 exposure alerts into conviction feed (VEX walls + charm pins from grid snapshots). Check overlap with our conviction feed first — may already exist under another name.
- A4: round11 test coverage worth taking: agent-02 alert_dispatcher/audit_trail tests, agent-05 streamer tests. Skip bandit-config churn (our CI differs) and ml v4 retrain reports (our models frozen).

## Track B — Tidehunter Pro redesign (blocked on friend pushing files)
- B0 (friend): push `.planning/mockups/tidehunter-pro-2026-09-05/` + v2 brief to floww-2 main. Screenshot verdict "everything failed — no structure" + "40+ audit findings folded in" must be IN the brief or we re-litigate blind.
- B1 (us, on receipt): UI-only mockup review against live FlowseekerProBlademap. Unphased work per brief — does NOT un-gate Phase 4. Mount approved mockup as parallel tab, Nav visual sign-off before replacing anything.
- B2: Phase 4 paid-API fallback stays GATED until Public API limits confirmed live (decision rule: skip if Public healthy 2+ weeks). No code before that signal.

## Track C — Our backlog (priority order)
- C1: Phase 1 Oracle VM provisioning + deploy/smoke (only path to public URL; sole Nav-gated item).
- C2: Issues #18 (contract row-shape unify) + #17 (TradeEntry → journal persistence).
- C3: Phase 9 Gates B/C sign-off (Agent 2 compose, Agent 4 eval).
- C4: Doc hygiene: 6.4 checkbox-vs-header, stale STATE.md split, confirm B1/B2/B3 + public-budget landed (ROADMAP says ENFORCED, headers say proposal-only — grep before building).
- C5: :8000 runs stale worktree code (no /api/version) — restart from main when tidehunter agent is done. Never kill their server mid-lane.

## Explicitly NOT doing
- Azure deploy repair (user waived; friend disarmed it too).
- Phase 4 backend build before the Public-limits signal.
- Tidehunter redesign implementation before B0 files land.
- Rebuilding anything already landed (check `git log origin/main` first — 1488-commit divergence means SHA-match, not subject-match, is the only proof).

## Verification contract (every track)
- Backend: `cd backend && .venv/bin/python3 -m pytest <touched> -q` + `ruff check .`
- Frontend: `cd frontend && npx craco test --watchAll=false`
- Live: curl endpoint (not log-watch), bundle grep for stamped SHA
- Land: branch → PR with evidence body → merge after checks (main is branch-protected; no direct push, no force-push — ever)
