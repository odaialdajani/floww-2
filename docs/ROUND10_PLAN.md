# Round 10 Plan

**Synthesized from:** Round 9 carry-forward tickets (T2, T3, T5, T7, T8, T9, T10 outputs)  
**Generated:** 2026-05-27 by DS Pro  
**Status:** Draft — ready for architect review

---

## ✅ Status update — 2026-06-13 (verified against current tree)

The Draft below is stale. Verified completion status (commands re-run live):

| Ticket | Status | Evidence |
|---|---|---|
| **P0.1** conftest collection | ✅ done | `pytest --collect-only` → 2703 collected, **0 errors** (was ~23) |
| **P0.2** `fetch_spot_and_chains` | ✅ done | defined at `server.py:720`; no `not defined` error |
| **P0.3** F401 cleanup | ✅ done | PR floww#2 — `ruff --select F401` = 0; 33 service tests pass |
| **P1.2** Schwab chaos coverage | ✅ done | 13 mocked chaos tests pass incl `test_token_refresh_when_expired` + `test_resubscribe_after_reconnect` (acceptance was ≥5) |
| **P1.3a** `/api/ml/calibration` | ✅ done | live `200` (`routes/ml_api.py::get_calibration_default`) |
| **P1.3b** `/api/ml/compare` | ✅ done | live `200` (`routes/ml_api.py::ml_compare`) |
| **P1.3c** `/chain` route | ✅ resolved (documented) | Canonical route is **`/api/chain`** (live `200`, `routes/chain.py`). The T7 smoke test used the wrong path `/chain` (404). **No bare alias added** — the whole API uses `APIRouter(prefix="/api")`, so an unprefixed `/chain` would be an inconsistent outlier with zero callers. Smoke tests should target `/api/chain`. |

**Still open:** P1.1 (AlphaVantageProvider), P1.4 (frontend jest config — likely moot; `craco test` is 133/133 green), P1.5 (type hints), P2.x.

---

## Top Priorities (P0 — Week 1)

### P0.1 — Conftest.py Freeze Waiver + Apply (30 min)
- **Scope:** `backend/tests/conftest.py`
- **Source:** T3 triage (`docs/ROUND10_CONFTEST_WAIVER_TRIAGE.md`)
- **Problem:** 23 test files fail collection because `conftest.py` forces `from server import app` before pytest's pythonpath is set. Root cause is `services-not-package` import order.
- **Action:** Defer `from server import app` until pytest pythonpath is loaded
- **Acceptance:** Pytest collection errors drop from ~23 to 0
- **Note:** conftest.py was FROZEN in Round 9. This waiver is RECOMMENDED for R10.

### P0.2 — Restore `fetch_spot_and_chains` (Heatseeker Degraded) (30 min)
- **Scope:** `backend/routes/heatseeker.py` or `backend/services/`
- **Source:** T7 smoke test — `/api/heatseeker/flip-zones?ticker=SPY` returns 200 but degraded with `name 'fetch_spot_and_chains' is not defined`
- **Problem:** A9 deletion miss — function was deleted but still called
- **Action:** Find original definition in git history (`git show 7ec433f^`), restore it
- **Acceptance:** `/api/heatseeker/flip-zones?ticker=SPY` returns non-degraded response

### P0.3 — A9 STALE_IMPORT Cleanup (20 min)
- **Scope:** Files identified in `docs/ROUND10_A9_DELETION_VERIFICATION.md`
- **Action:** Remove dead import lines for A9-deleted names classified as STALE_IMPORT
- **Acceptance:** `ruff check --select F401 backend/` shows 0 new unused imports

---

## Medium Priorities (P1 — Week 2-3)

### P1.1 — AlphaVantageProvider Restoration (45 min)
- **Scope:** `backend/data_providers.py`
- **Source:** T2 — deferred during DS Pro session (depends on circuit breaker module)
- **Action:** Restore AlphaVantageProvider from `7ec433f^`, resolve circuit breaker import
- **Acceptance:** `from data_providers import AlphaVantageProvider` succeeds

### P1.2 — A8 Schwab Streamer Chaos Coverage Continuation (90 min)
- **Scope:** `backend/services/schwab_streamer.py`, `backend/tests/services/test_schwab_streamer_reconnect.py`
- **Source:** T5 handoff (`docs/ROUND9_A8_HANDOFF.md`)
- **Action:** Add token refresh chaos test + re-subscribe-on-reconnect state preservation test
- **Acceptance:** ≥5 chaos tests pass (all mocked, no live Schwab connection needed)

### P1.3 — Missing API Endpoints (65 min total)
- **P1.3a:** Add bare `/api/ml/calibration` endpoint with default ticker (15 min)
- **P1.3b:** Add `/api/ml/compare` endpoint (30 min)
- **P1.3c:** Add or document `/chain` route (20 min)
- **Source:** T7 smoke test (3 endpoints returned 404)
- **Acceptance:** All 3 endpoints return 200 with documented response schema

### P1.4 — Frontend Jest/Babel Config Fix (60 min)
- **Scope:** `frontend/jest.config.js`, `frontend/package.json`
- **Source:** T8 — frontend tests fail on JSX parse + ESM import errors
- **Problem:** Pre-existing config issue (not introduced by Round 9)
- **Acceptance:** `npx jest --no-coverage` runs without JSX/ESM errors

### P1.5 — Type Hints Expansion (2 hr)
- **Scope:** `services/greek_aggregator`, `iv_skew_analyzer`, `oi_change_detector`, `rate_limit_tracker`
- **Source:** A10 candidates list
- **Action:** Annotate fully, add to mypy strict per-module
- **Acceptance:** `mypy <files>` exits 0

---

## Lower Priorities (P2 — Week 3+)

### P2.1 — Dead-Code Phase 2 (4 hr spread across PRs)
- **Scope:** "Likely dead" list from A9's audit
- **Action:** Owner sign-off → per-file PR deletion with caller-grep verification
- **Acceptance:** Each PR shows: caller-grep = 0, tests pass, code review OK

### P2.2 — Heatseeker Edge-Case Bugs (TBD)
- **Scope:** From `docs/ROUND9_A4_CLOSEOUT.md`
- **Acceptance:** Each documented edge case has a regression test + fix

### P2.3 — Frontend Med/Low Leak Fixes (30 min)
- **Scope:** Files flagged Med/Low in `docs/ROUND9_FRONTEND_LEAK_AUDIT.md`
- **Action:** Apply same AbortController cleanup pattern A3 used for the High-severity leak

---

## Discovered-During-Round-9-but-Deferred

- **_map_binary_to_3way HOLD-zone fix** accepted in DS Pro T1. Round 10 should grep for any other binary→3way conversion pattern in the codebase that might have the same bug.
- **A9's mass deletion incident** — Round 10 must add a HARD precondition to all READ-ONLY agent missions: **no deletions without per-name caller verification and architect sign-off.**
- **Memory growth of 9.5%** is acceptable but worth monitoring. Re-run T10 procedure in Round 10 midpoint to catch regression.

---

## Resource Allocation Suggestions

| Resource | Session | Tasks |
|---|---|---|
| DS Pro (Architect) | 1 session, 2 hr | P0.1, P0.2, P0.3 — sensitive judgment calls |
| Owl Alpha x3 | 3 sessions, 2 hr each | P1.1, P1.2, P1.3 in parallel |
| DS Flash | 1 session, 2 hr | P2.1 mechanical sweep |

---

## Directly Implied Follow-up Actions

- Commit all DS Pro session docs (`ROUND9_DSPRO_SMOKE_RESULTS.md`, `ROUND9_DSPRO_ML_PIPELINE.md`, `ROUND9_DSPRO_MEMORY_PROFILE.md`, `ROUND9_FINAL_CLOSURE.md`, `ROUND10_PLAN.md`)
- Final pulse to `kanban/cards/agent_DSPRO_status.md`
- Git tag: `round-9-closed` at final closure commit
