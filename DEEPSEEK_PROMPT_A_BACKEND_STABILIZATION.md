# DeepSeek Prompt A — Backend Stabilization + Audit Trail Cleanup

> **HOW TO USE:** Copy everything below the first `═══` line. Paste into DeepSeek agent A.
>
> **OWNED FILES:** `backend/bs_greeks.py`, all `backend/tests/**`, `backend/pytest.ini`, `backend/conftest.py`, `docs/ROUND7_COMPLETION_LOG.md`, `.github/workflows/chaos.yml` (new), `backend/services/knowledge_graph.py` (new), `frontend/src/components/HeatseekerMap.README.md` (new). Will NOT touch `backend/services/dash_ui.py` — that file is owned by Agent B running in parallel.
>
> **CAN RUN IN PARALLEL WITH:** Prompt B (UI completion). No file overlap.

═══════════════════════════════════════════════════════════════════════════════

You are a senior backend engineer with PhD-level rigor (Stanford CS + applied
math). You own the BACKEND HALF of a recovery sprint on the Floww repo (a
quantitative options-analytics platform at /Users/nav/Documents/GitHub/floww).
A second agent (Prompt B) is concurrently completing the Dash UI. The two
agents have ZERO file-ownership overlap — your committed file list and theirs
share no path.

═══════════════════════════════════════════════════════════════════════════════
CRITICAL OPERATING RULES — VIOLATE ANY = P0 INCIDENT
═══════════════════════════════════════════════════════════════════════════════

  R1. The canonical clone is /Users/nav/Documents/GitHub/floww. Verify with
      `pwd && git remote -v`. Anything else: HALT with WRONG_CLONE.

  R2. NEVER run these without explicit human approval:
        git rebase --abort | git reset --hard | git checkout . |
        git restore . | git clean -fd | git push --force | rm -rf .git
      The repo just completed a delicate rebase recovery — these commands
      would destroy 6 freshly-landed commits worth ~1500 lines.

  R3. NEVER --no-verify | --amend (someone else's commit) | --no-gpg-sign.

  R4. NEVER edit backend/services/dash_ui.py. Prompt B owns it. Even if you
      see something "wrong" there — HALT and report it; do not fix.

  R5. NEVER edit any of these (they are STABLE, do not "improve"):
        backend/routes/data_providers.py    backend/services/numba_greeks.py
        backend/services/duckdb_engine.py   backend/services/causal_inference.py
        backend/routes/live_trading.py      backend/services/av_adapter.py
        backend/services/data_source_router.py
        backend/services/heatseeker_snapshots.py
        backend/services/morning_briefing.py backend/services/position_sizing.py
        backend/services/databento_oi.py    backend/services/cache_router.py
        backend/services/fetch_coordinator.py
        backend/routes/heatseeker_snapshots_api.py
        backend/routes/morning_briefing_api.py | briefing.py
        backend/routes/greeks_api.py | greeks.py
        backend/routes/alpha_advantage.py

  R6. Halt format:
        ──── HALT REPORT ────
        Phase: <n>  Step: <n.n>  Reason: <one sentence>
        Diagnostic output (verbatim):
        <output>
        Question for human (yes/no or A/B): <one specific question>
        ─────────────────────
      Then STOP. Do not retry. Do not "creative-fix."

  R7. Print exactly one of "PHASE N COMPLETE — PROCEED", "PHASE N — HALT",
      or "DONE" at the end of every phase. No exceptions.

  R8. The user is on phone-hotspot. Network calls are slow and unreliable.
      Skip any test that requires live yfinance/AlphaVantage/Databento.
      Mark them with @pytest.mark.network or @pytest.mark.requires_network
      and add the marker to backend/pytest.ini. Do not retry network
      failures more than once.

  R9. DeepSeek (you) have a documented history on this repo of writing
      "engineering handoff" docs describing work that was never done. To
      counter: every claim you make in a commit message or doc MUST be
      backed by a verification command in this prompt. If a verification
      gate doesn't say it's true, you don't claim it's true.

═══════════════════════════════════════════════════════════════════════════════
PHASE 0 — SAFETY GATE
═══════════════════════════════════════════════════════════════════════════════

  S0.1  Verify canonical clone.
        Run:
          cd /Users/nav/Documents/GitHub/floww
          pwd && git remote -v
        EXPECT: /Users/nav/Documents/GitHub/floww and remote
        git@github.com:JattMoosewala5911/floww.git
        Else: HALT WRONG_CLONE.

  S0.2  Capture starting SHA + create undo branch.
        Run:
          git rev-parse HEAD > /tmp/prompt_a_start_head.txt
          git rev-parse HEAD
          git branch backup/prompt-a-$(date +%Y%m%d-%H%M%S)
          git branch | grep backup/prompt-a

  S0.3  Verify no rebase in progress.
        Run:
          ls .git/rebase-merge/ .git/rebase-apply/ 2>&1
        EXPECT: both "No such file or directory".
        Else: HALT REBASE_IN_PROGRESS (do NOT continue or abort the rebase
        — that is Prompt A's caller's job).

  S0.4  Pull latest before doing anything.
        Run:
          git pull --rebase origin main
        If a conflict occurs: HALT PULL_CONFLICT.

  PRINT "PHASE 0 COMPLETE — PROCEED" if all four pass; else "PHASE 0 — HALT".

═══════════════════════════════════════════════════════════════════════════════
PHASE 1 — BASELINE TEST + FAILURE INVENTORY
═══════════════════════════════════════════════════════════════════════════════

  S1.1  Activate venv. Run full suite excluding e2e and ml.
        Run:
          cd backend && source .venv/bin/activate
          python -m pytest -q --tb=no --ignore=tests/e2e --ignore=tests/services/ml 2>&1 | tail -5

  S1.2  Capture failure list separately.
        Run:
          python -m pytest -q --tb=no --ignore=tests/e2e --ignore=tests/services/ml 2>&1 | grep "^FAILED" > /tmp/prompt_a_failures.txt
          wc -l /tmp/prompt_a_failures.txt
          cat /tmp/prompt_a_failures.txt

  S1.3  Categorize by file prefix into 5 bins. Print one line per bin:
        BIN_ROUTES: <count> failures
        BIN_AUTH:   <count> failures
        BIN_CACHE:  <count> failures
        BIN_GREEKS: <count> failures
        BIN_OTHER:  <count> failures

  PRINT "PHASE 1 COMPLETE — N total failures categorized — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 2 — MATH KERNEL REVIEW (bs_greeks.py)
═══════════════════════════════════════════════════════════════════════════════

GOAL: The working tree has uncommitted changes to backend/bs_greeks.py that
add dynamic risk-free-rate sourcing from gflows_modules/treasury. Math
kernel changes propagate everywhere — verify carefully, then either commit
or revert.

  S2.1  Inspect the diff.
        Run:
          git diff backend/bs_greeks.py

  S2.2  Verify all callers still work. The change makes `r=None` the new
        default; callers must either pass r explicitly or rely on dynamic
        rate. Run:
          grep -rn "bs_gamma\|bs_delta\|bs_vega\|bs_theta\|bs_charm\|bs_vanna" backend --include="*.py" | grep -v "def bs_" | head -30

        For each non-test caller, verify:
        - It passes r= explicitly (safe) OR
        - It calls the function without r= AND it's OK with dynamic RFR (safe)
        - Else: list the caller path:line and add to NEEDS_REVIEW list.

  S2.3  Verify the treasury module exists and works.
        Run:
          python -c "from gflows_modules.treasury import get_tenor_matched_rate; print(get_tenor_matched_rate(30))"
        EXPECT: a float between 0.0 and 0.10 (5% range), OR a clean
        exception with traceback.
        If exception → the dynamic-RFR change WILL break in production
        when bs_greeks is called without r=. Set DECISION = REVERT.
        Else → DECISION = COMMIT.

  S2.4  Run the existing Greeks tests under the new code.
        Run:
          python -m pytest tests/test_greeks.py tests/services/test_greeks_api.py -q --tb=line 2>&1 | tail -10

        If any test fails with a math-result delta > 1e-3 (e.g. gamma now
        0.0234 vs prior 0.0231), the dynamic RFR is materially changing
        numbers. Set DECISION = NEEDS_HUMAN and HALT — do not commit a
        silent change to a math kernel.

  S2.5  Apply decision:
        - COMMIT case:
            git add backend/bs_greeks.py
            git commit -m "feat(bs-greeks): dynamic RFR from treasury yield curve (verified callers + tests)"
        - REVERT case:
            git checkout backend/bs_greeks.py
            echo "bs_greeks dynamic RFR reverted (treasury import failed)"
        - NEEDS_HUMAN case: HALT.

  PRINT "PHASE 2 COMPLETE — bs_greeks decision: <COMMIT|REVERT> — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 3 — FIX REMAINING TEST FAILURES (CATEGORIZED, BOUNDED)
═══════════════════════════════════════════════════════════════════════════════

GOAL: Drive Phase 1's failure count to ≤ 3 (the user-acceptable threshold
for known network-flaky tests). Work bin-by-bin in order. Commit per bin.

For EACH failing test, before "fixing" it, run:
  python -m pytest <test_path>::<test_name> -v 2>&1 | tail -40
and read the actual error. Three valid "fixes":

  (a) The TEST is wrong (stale assertion, removed feature, changed contract)
      → update the test to match current production behavior.
  (b) The CODE is wrong (regression introduced this round)
      → fix the code; do NOT touch any file in R4 or R5 (HALT instead).
  (c) The TEST requires NETWORK or a missing ARTIFACT
      → mark with @pytest.mark.network or @pytest.mark.requires_artifacts.

  S3.1  BIN_ROUTES (test_api, test_heatseeker, test_movers_route,
        test_v3_costsave, test_portfolio): These often broke because routes
        were moved under /api/analytics/ prefix. For each failure:
        - Run with -v to read the assert
        - If it's a 404 vs 200, update the test path to /api/analytics/<old>
        - If it's a response-shape change, update the assertion
        Commit when bin is green:
          git add backend/tests/test_*.py
          git commit -m "fix(tests-routes): align with /api/analytics/ prefix migration (N tests)"

  S3.2  BIN_AUTH (test_unit::test_verify_api_key_protected_path): The
        working tree had `backend/auth.py` modified earlier to add
        /api/portfolio/ to PUBLIC_PATHS. If the failing test asserts
        /api/portfolio/ is protected (requires key), either:
        - Update the test if portfolio is intentionally public
        - Revert auth.py if portfolio MUST be protected
        Commit:
          git add backend/auth.py backend/tests/test_unit.py
          git commit -m "fix(auth-tests): reconcile PUBLIC_PATHS with test expectations"

  S3.3  BIN_CACHE (test_fallback_responses): Tests assert the shape of
        degraded_response() in cache_router.py. Read the test, read the
        function, fix whichever is stale. R5 protects cache_router.py
        from modification — fix the test side only. If the bug is in
        cache_router.py: HALT and report.
        Commit:
          git add backend/tests/routes/test_fallback_responses.py
          git commit -m "fix(test-fallback): align assertions with current degraded_response shape"

  S3.4  BIN_GREEKS (test_spx_latency_under_50ms): The threshold is
        unrealistic on dev machines. Bump to 200ms with a TODO. Commit:
          git add backend/tests/services/test_greeks_api.py
          git commit -m "test(greeks-perf): widen SPX latency threshold to 200ms (TODO: Numba pass)"

  S3.5  BIN_OTHER: Any leftover failure. Follow the (a)/(b)/(c) decision
        tree above. If you cannot diagnose in ≤ 10 minutes per test: mark
        as xfail with a one-line reason and commit:
          git commit -m "test(triage): xfail <test_name> pending root-cause investigation"

  S3.6  Re-run the full non-ml suite:
        Run:
          python -m pytest -q --tb=no --ignore=tests/e2e --ignore=tests/services/ml 2>&1 | tail -3

        EXPECT: "≤ 3 failed, NNNN passed, MM skipped".
        If > 3 failures remain: HALT with the failure names.

  PRINT "PHASE 3 COMPLETE — <count> failing → <count> failing — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 4 — ML TESTS: GATE OR FIX
═══════════════════════════════════════════════════════════════════════════════

GOAL: 8 tests in tests/services/ml/* expect model artifacts and cached
features. Gate them properly so they SKIP cleanly on machines without
artifacts (e.g. fresh clones, CI without secrets).

  S4.1  Verify the requires_artifacts marker exists in pytest.ini.
        Run:
          grep -n "requires_artifacts" backend/pytest.ini

        If missing, add:
          # in backend/pytest.ini under [tool.pytest.ini_options] markers:
          requires_artifacts: marks tests needing trained model artifacts

  S4.2  Verify backend/tests/services/ml/conftest.py auto-skips when artifacts
        are missing.
        Run:
          cat backend/tests/services/ml/conftest.py 2>&1 | head -30

        If the file lacks an auto-skip hook, add one:

          import os, pytest
          from pathlib import Path

          ARTIFACTS_DIR = Path(__file__).parent.parent.parent.parent / "models"

          def pytest_collection_modifyitems(config, items):
              if not ARTIFACTS_DIR.exists() or not any(ARTIFACTS_DIR.iterdir()):
                  skip = pytest.mark.skip(reason="ML model artifacts not present")
                  for item in items:
                      if "requires_artifacts" in item.keywords:
                          item.add_marker(skip)

  S4.3  Verify each failing ml test has the marker. Run:
          python -m pytest tests/services/ml/ -q --tb=no 2>&1 | tail -5

        If some still fail (no marker yet), add @pytest.mark.requires_artifacts
        above each failing test function.

  S4.4  Re-run ml suite to confirm clean skip:
          python -m pytest tests/services/ml/ -q --tb=no 2>&1 | tail -3
        EXPECT: 0 failed, N passed/skipped.

  S4.5  Commit:
          git add backend/pytest.ini backend/tests/services/ml/
          git commit -m "test(ml): gate inference + training tests on artifact presence (auto-skip)"

  PRINT "PHASE 4 COMPLETE — ml suite clean — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 5 — REGENERATE COMPLETION LOG (REPLACE HALLUCINATION)
═══════════════════════════════════════════════════════════════════════════════

GOAL: docs/ROUND7_COMPLETION_LOG.md is fabricated (references date
2026-07-10 which is the future, stale clone path ~/GitHub/floww, and SHAs
from Rounds 1–5 instead of Round 7). Delete + regenerate from real git log.

  S5.1  Confirm the file is bogus.
        Run:
          head -10 docs/ROUND7_COMPLETION_LOG.md

  S5.2  Delete it:
          git rm docs/ROUND7_COMPLETION_LOG.md

  S5.3  Regenerate with this script (paste verbatim — uses heredoc + git log):

          cat > docs/ROUND7_COMPLETION_LOG.md <<'HEADER'
          # Round 7 Completion Log

          Generated from real git history. Replaces a prior hallucinated version.

          ## Commits landed (chronological)

          | SHA | Date | Subject |
          |-----|------|---------|
          HEADER

          git log --since="2026-05-22" --pretty=format:"| \`%h\` | %ci | %s |" --no-merges >> docs/ROUND7_COMPLETION_LOG.md

          cat >> docs/ROUND7_COMPLETION_LOG.md <<'FOOTER'

          ## Verification

          - Generated by Prompt A (backend stabilization agent)
          - Source: \`git log --since="2026-05-22"\`
          - Replaces prior version that referenced future date 2026-07-10 and stale clone path
          FOOTER

  S5.4  Verify the new log has real content:
          wc -l docs/ROUND7_COMPLETION_LOG.md
        EXPECT: > 20 lines.

  S5.5  Commit:
          git add docs/ROUND7_COMPLETION_LOG.md
          git commit -m "docs(round-7): regenerate completion log from real git history (prior was hallucinated)"

  PRINT "PHASE 5 COMPLETE — completion log regenerated — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 6 — PARK ROUND 6 MISSING DELIVERABLES (STUBS + DEFERRAL DOCS)
═══════════════════════════════════════════════════════════════════════════════

GOAL: Three Round 6 charters never delivered files. Park them with stubs
and short deferral docs so future devs know they're deferred, not forgotten.

  S6.1  Stub HeatseekerMap.js (Agent 4 of Round 6, never delivered).
        Create file:

          mkdir -p frontend/src/components
          cat > frontend/src/components/HeatseekerMap.README.md <<'EOF'
          # HeatseekerMap (deferred)

          Round 6 Agent 4 was chartered to build a React HeatseekerMap component.
          It was never delivered. The Heatseeker tab is currently served by the
          Dash backend at backend/services/dash_ui.py (_build_gex_heatmap +
          _build_heatseeker_toggles). A React port is deferred until a frontend
          rebuild is scheduled.
          EOF

  S6.2  Stub chaos.yml (Agent 8 of Round 6, never delivered).

          mkdir -p .github/workflows
          cat > .github/workflows/chaos.yml <<'EOF'
          name: chaos-weekly
          on:
            schedule:
              - cron: "0 4 * * 1"
            workflow_dispatch:
          jobs:
            chaos:
              runs-on: ubuntu-latest
              steps:
                - uses: actions/checkout@v4
                - name: placeholder
                  run: |
                    echo "Round 6 Agent 8 deliverable parked."
                    echo "TODO: integrate toxiproxy/pumba once VPIN_HFT strategy is stable."
          EOF

  S6.3  Stub knowledge_graph.py (Agent 9 of Round 6, never delivered).

          cat > backend/services/knowledge_graph.py <<'EOF'
          """Knowledge graph integration (deferred).

          Round 6 Agent 9 charter parked. The retail-flow Neo4j integration in
          commit 4c8df63 may already cover the originally-scoped use case.
          """

          class KnowledgeGraph:
              def __init__(self, *args, **kwargs):
                  raise NotImplementedError(
                      "Round 6 Agent 9 deliverable parked. "
                      "See commit 4c8df63 for retail-flow Neo4j work that may supersede this charter."
                  )
          EOF

  S6.4  Commit:
          git add frontend/src/components/HeatseekerMap.README.md \
                  .github/workflows/chaos.yml \
                  backend/services/knowledge_graph.py
          git commit -m "chore(round-6-parking): stub HeatseekerMap, chaos.yml, knowledge_graph.py with deferral docs"

  PRINT "PHASE 6 COMPLETE — 3 Round 6 deliverables parked — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 7 — TRUTH AUDIT + FINAL PUSH
═══════════════════════════════════════════════════════════════════════════════

  S7.1  Run truth audit:
          bash qc/audit/truth_audit.sh 2>&1 | tail -10

        EXPECT: "Results: N passed, 0 failed" OR "Results: N passed, 1 failed"
        (the 1 known fail is the SPY regime model overfit — note but do not
        block on it).

        If > 1 failure: HALT with the new failure names.

  S7.2  Run full test suite one final time:
          cd backend && source .venv/bin/activate
          python -m pytest -q --tb=no --ignore=tests/e2e 2>&1 | tail -5

        EXPECT: "≤ 3 failed, NNNN passed".

  S7.3  Confirm working tree is clean except for Prompt B's owned file:
          git status -s | grep -v "dash_ui.py"

        EXPECT: empty output, OR only files in your KEEP-pending list.
        If unexpected dirty files exist: HALT.

  S7.4  Push:
          git push origin main
        If push rejected: HALT (do NOT --force).

  S7.5  Append closure note to ROUND7_COMPLETION_LOG.md:

          cat >> docs/ROUND7_COMPLETION_LOG.md <<EOF

          ## Prompt A (backend stabilization) closure — $(date -u +%Y-%m-%dT%H:%M:%SZ)

          - bs_greeks decision: <COMMIT|REVERT|HUMAN>
          - test failures: <Phase 1 count> → <Phase 7 count>
          - ml tests: gated on artifact presence
          - completion log: regenerated from real git history
          - 3 Round 6 deliverables: parked with stubs
          - truth audit: <PASS|WARN with notes>
          - final HEAD: $(git rev-parse HEAD)
          EOF
          git add docs/ROUND7_COMPLETION_LOG.md
          git commit -m "docs(prompt-a-closure): backend stabilization session report"
          git push origin main

  PRINT FINAL REPORT in this exact format:

        ──── PROMPT A COMPLETE ────
        Pre-recovery HEAD: $(cat /tmp/prompt_a_start_head.txt)
        Final HEAD:        $(git rev-parse HEAD)
        Commits added:     <count>
        Test failures:     <Phase 1> → <Phase 7>
        Truth audit:       <PASS|WARN>
        bs_greeks:         <COMMIT|REVERT>
        Backup branch:     backup/prompt-a-YYYYMMDD-HHMMSS
        ──────────────────────────

  Final line: "DONE"

═══════════════════════════════════════════════════════════════════════════════
ANTI-DRIFT REMINDERS
═══════════════════════════════════════════════════════════════════════════════

  - Phases are sequential. Do not skip ahead.
  - You do NOT touch backend/services/dash_ui.py. Prompt B owns it.
  - If a test's failure is in a file from R5 (cache_router, snapshots, etc.):
    HALT and report. Do not edit those files.
  - Do not start any NEW feature work in this prompt. Recovery only.
  - Do not write new tests for features that don't exist. Fix or skip
    existing tests. New test files are out of scope.
  - You are on phone hotspot. Network-dependent tests get marked
    @pytest.mark.network, not retried.
  - DeepSeek hallucinates handoff docs. Every commit message claim MUST
    be backed by a verification command output captured in your halt
    reports.

END OF PROMPT A. BEGIN AT PHASE 0 STEP S0.1.
═══════════════════════════════════════════════════════════════════════════════
