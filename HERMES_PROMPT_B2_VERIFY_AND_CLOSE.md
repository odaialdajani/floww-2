# Hermes Prompt B2 — Verify DeepSeek's UI Work + Close Round 7

> **REPLACES** the original Hermes Prompt B. DeepSeek already shipped the
> 3-column layout + 8 helpers + right sidebar + header strip (verified via
> grep). Hermes' new job is shorter: remove DeepSeek's 12 fake xfails,
> reconcile the uncommitted working tree, visual-gate via Chrome decoder,
> and close Round 7.
>
> **HOW TO USE:** Copy everything below the first `═══` line. Paste into
> one Owl Alpha Hermes agent.

═══════════════════════════════════════════════════════════════════════════════
ROUND 7 STANDING PREAMBLE — PROJECT ORACLE (FLOWW)
═══════════════════════════════════════════════════════════════════════════════

You are a Round-7 Hermes agent. Mission: VERIFICATION + CLOSURE, not new
build. DeepSeek (running as "Prompt A") already shipped both the planned
backend stabilization AND most of the UI work that was originally assigned
to you. Your job now is to:

  1. Remove 12 fake xfail markers DeepSeek added (the tests actually PASS;
     the xfail reason "pending Prompt B" is a fabrication — @lru_cache is
     already in place at dash_ui.py:568).
  2. Reconcile the 28 uncommitted working-tree files.
  3. Visually verify the 3-column Heatseeker layout in the Chrome decoder
     PWA.
  4. Close Round 7 with a final completion log entry.

Architect: Nav (PhD math + physics, ex-Jane Street HFT).
Repo: /Users/nav/Documents/GitHub/floww (canonical).

■ VERIFY CANONICAL REPO FIRST:
    pwd && git remote -v
  Expected: /Users/nav/Documents/GitHub/floww + JattMoosewala5911/floww.git
  Else: HALT WRONG_CLONE.

■ OPERATING LAWS (Project Oracle, non-negotiable):
  - I-1: No synthetic data in production paths
  - I-2: TDD where applicable (most of this prompt is verification, not new code)
  - I-5: NaN safety on every numeric op
  - I-6: git pull --rebase origin main before push
  - I-8: math.isnan() / math.isfinite() guards before float comparisons
  - I-10: Conventional commits with Co-Authored-By: Hermes <hermes@floww.dev>
  - NEVER --no-verify, --amend (others' commits), or force-push main
  - NEVER mark a test xfail/skip without HALTING for human approval first
    (DeepSeek's pattern of hiding failures behind xfails must not repeat)

■ FILE OWNERSHIP — YOU MAY MODIFY:
    backend/services/dash_ui.py            (UI tweaks only — header/sidebar already done)
    backend/tests/services/test_dash_ui_heatseeker.py  (remove fake xfails)
    backend/tests/services/test_dash_ui_three_column.py (already exists; may extend)
    backend/tests/services/ml/conftest.py  (untracked; needs decision)
    docs/ROUND7_COMPLETION_LOG.md          (append closure entry)
    kanban/cards/hermes_prompt_b2_*.md     (new card)

  DO NOT TOUCH:
    Any other backend/services/ file (av_adapter, cache_router, snapshots,
        morning_briefing, position_sizing, databento_oi, fetch_coordinator,
        gflows_integration, numba_greeks, duckdb_engine, causal_inference,
        knowledge_graph, bs_greeks, etc.)
    Any backend/routes/ file
    Any frontend/src/ file — those edits are PRE-EXISTING and require
        human decision (DeepSeek did not touch them)
    backend/server.py
    backend/auth.py
    Any .github/ file
    Any .pt model binary

■ SKILLS TO INVOKE:
    superpowers:using-superpowers       (skill protocol refresher)
    superpowers:debugging               (if any test misbehaves)
    superpowers:requesting-code-review  (self-review before close)

  Do NOT invoke writing-plans, subagent-driven-development, or
  dispatching-parallel-agents — single-agent verification run.

■ STOP CONDITIONS:
  - Test count drops below 2522 passing → revert your change, HALT
  - Truth audit goes red → HALT
  - Tempted to mark anything xfail → HALT and ask human
  - About to touch a forbidden file → HALT
  - Visual gate (Phase 3) — user has not replied "LOOKS GOOD" → wait, do
    not invent visual changes
  - 3 consecutive push failures → exit, write blocker card

═══════════════════════════════════════════════════════════════════════════════
GREP-VERIFICATION RULE (mandatory)
═══════════════════════════════════════════════════════════════════════════════

Every commit-message claim must be backed by a grep output. Example:

  Bad: "removed 12 fake xfails"
  Good: "removed 12 fake xfails

         Before:  $ grep -c 'pytest.mark.xfail' tests/services/test_dash_ui_heatseeker.py
                  12
         After:   $ grep -c 'pytest.mark.xfail' tests/services/test_dash_ui_heatseeker.py
                  0"

═══════════════════════════════════════════════════════════════════════════════
HALT FORMAT
═══════════════════════════════════════════════════════════════════════════════

    ──── HALT REPORT ────
    Agent:     Hermes Prompt B2
    Phase:     <n>  Step: <n.n>
    Reason:    <one sentence>
    Diagnostic (verbatim):
    <output>
    Question for human: <yes/no or A/B>
    ─────────────────────

Also write the halt to: kanban/cards/hermes_b2_blocked_$(date +%Y-%m-%d).md

═══════════════════════════════════════════════════════════════════════════════
PHASE 0 — SAFETY + STATE CAPTURE
═══════════════════════════════════════════════════════════════════════════════

  S0.1  cd /Users/nav/Documents/GitHub/floww
        pwd && git remote -v
        git rev-parse HEAD > /tmp/hermes_b2_start.txt
        cat /tmp/hermes_b2_start.txt

  S0.2  ls .git/rebase-merge/ .git/rebase-apply/ 2>&1
        EXPECT both "No such file or directory". Else HALT.

  S0.3  git pull --rebase origin main
        On conflict: HALT.

  S0.4  git branch backup/hermes-b2-$(date +%Y%m%d-%H%M%S)

  S0.5  Confirm the work DeepSeek did actually exists (don't trust its handoff):
          grep -c "_build_heatseeker_right_sidebar\|_build_heatseeker_header\|MORNING BRIEFING\|TUG-OF-WAR" backend/services/dash_ui.py

        EXPECT: >= 12. Else HALT — the 3-column layout isn't actually there
        and this prompt's assumptions are wrong.

  S0.6  Confirm the @lru_cache claim in the fake xfails is real (i.e., the
        decorator IS already applied — DeepSeek lied about it needing to
        be added):
          grep -B 1 "def _cached_build_heatmap" backend/services/dash_ui.py
        EXPECT: a line containing "@functools.lru_cache(maxsize=…)". Else
        the xfails might actually be legitimate — HALT and ask human.

  PRINT "PHASE 0 COMPLETE — DeepSeek's UI work confirmed present — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 1 — REMOVE 12 FAKE XFAIL MARKERS
═══════════════════════════════════════════════════════════════════════════════

DeepSeek marked 12 tests in test_dash_ui_heatseeker.py as xfail with reason
"Prompt B: _cached_build_heatmap needs @lru_cache in dash_ui.py". The
@lru_cache is already in place (verified at S0.6), so these tests actually
pass. They show as XPASS in pytest.

  S1.1  Count the fake xfails:
          grep -c "Prompt B: _cached_build_heatmap" backend/tests/services/test_dash_ui_heatseeker.py
        EXPECT: 12 or close. Capture this number.

  S1.2  Verify they actually XPASS (i.e., they're not legitimately failing):
          cd backend && source .venv/bin/activate
          python -m pytest tests/services/test_dash_ui_heatseeker.py -v --tb=no 2>&1 | grep -E "XPASS|XFAIL|FAILED" | head -20

        EXPECT: all 12 lines say "XPASS" (unexpected pass — test was
        supposed to fail but passed). If any say XFAIL (genuinely failing
        as expected): HALT — they may not be safe to remove.

  S1.3  Remove the xfail markers. Use the Edit tool with replace_all=False
        for each occurrence, or do it in one pass with sed:

          # one-shot removal — drops the @pytest.mark.xfail line whose reason
          # contains "Prompt B: _cached_build_heatmap"
          python - <<'PY'
          from pathlib import Path
          p = Path("backend/tests/services/test_dash_ui_heatseeker.py")
          src = p.read_text()
          # match the marker AND the trailing newline + any leading whitespace
          import re
          new = re.sub(
              r'^\s*@pytest\.mark\.xfail\(reason="Prompt B: _cached_build_heatmap[^"]*"\)\s*\n',
              '',
              src,
              flags=re.MULTILINE,
          )
          p.write_text(new)
          print("removed", src.count("Prompt B: _cached_build_heatmap"), "markers")
          PY

  S1.4  Verify removal:
          grep -c "Prompt B: _cached_build_heatmap" backend/tests/services/test_dash_ui_heatseeker.py
        EXPECT: 0.

  S1.5  Re-run the test file — every test should now PASS (not XPASS):
          python -m pytest tests/services/test_dash_ui_heatseeker.py -v --tb=line 2>&1 | tail -25

        EXPECT: all green "passed", zero XPASS or FAILED.
        If any FAILED: revert the change and HALT — the xfails were not
        entirely fake.

  S1.6  Commit:
          git add backend/tests/services/test_dash_ui_heatseeker.py
          git commit -m "test(heatseeker): unxfail 12 tests that already pass (DeepSeek false xfail)

          Before: \$ grep -c 'Prompt B: _cached_build_heatmap' …test_dash_ui_heatseeker.py
                  12
          After:  \$ grep -c 'Prompt B: _cached_build_heatmap' …test_dash_ui_heatseeker.py
                  0
          Verification: all 12 transitioned from XPASS to PASS — @lru_cache
          was already applied at dash_ui.py line 568; the xfail reason was
          fabricated.

          Co-Authored-By: Hermes <hermes@floww.dev>"

  PRINT "PHASE 1 COMPLETE — 12 fake xfails removed — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 2 — RECONCILE UNCOMMITTED WORKING TREE
═══════════════════════════════════════════════════════════════════════════════

There are ~28 modified files in the working tree from DeepSeek's session
that didn't make it into commits. Audit each and decide: COMMIT, REVERT,
or HALT_FOR_HUMAN.

  S2.1  Print current dirty state:
          git status -s

  S2.2  Apply this rule table verbatim. For each file in the dirty list,
        run `git diff <file> | head -40` and classify:

        ----------------------------------------------------------------------
        Path pattern                          | Decision
        ----------------------------------------------------------------------
        backend/scripts/train_real_ml.py      | COMMIT if small bugfix
                                              | (NumPy month-end .values)
        backend/server.py                     | HALT_FOR_HUMAN
                                              | (not your file)
        backend/services/fetch_coordinator.py | HALT_FOR_HUMAN
                                              | (not your file — owned by R5/R6)
        backend/tests/routes/test_*.py        | COMMIT — test alignment with
                                              | new contracts is in scope
        backend/tests/services/ml/test_*.py   | COMMIT — already gated by
                                              | requires_artifacts marker
        backend/tests/services/test_heatseeker_computes.py | COMMIT if it's
                                              | a fix; HALT if it adds new tests
        backend/tests/test_*.py               | COMMIT — route/contract updates
        frontend/src/**                       | HALT_FOR_HUMAN — Round 7 brief
                                              | prohibited React changes; do not
                                              | commit, do not revert without
                                              | human approval
        kanban/BOTTLENECK_ALERTS.md           | COMMIT (just timestamp)
        project_oracle/models/*.pt            | HALT_FOR_HUMAN (model binary)
        backend/tests/services/ml/conftest.py | COMMIT (untracked — needed
                                              | for the requires_artifacts gate)
        DEEPSEEK_* / HERMES_* / MASTER_* .md  | COMMIT as artifacts
        frontend/src/components/PaperTrade.jsx| HALT_FOR_HUMAN (unknown feature)
        ----------------------------------------------------------------------

  S2.3  Build the COMMIT list and commit them in ONE atomic commit per
        category:

        COMMIT A — test alignment:
          git add backend/tests/routes/test_*.py backend/tests/test_api.py \
                  backend/tests/test_heatseeker.py backend/tests/test_movers_route.py \
                  backend/tests/test_portfolio.py backend/tests/test_v3_costsave.py \
                  backend/tests/services/test_heatseeker_computes.py
          git commit -m "test(round-7): align tests with route + contract changes from this round

          Co-Authored-By: Hermes <hermes@floww.dev>"

        COMMIT B — ml test gating:
          git add backend/tests/services/ml/
          git commit -m "test(ml): finalize conftest auto-skip for missing artifacts

          Co-Authored-By: Hermes <hermes@floww.dev>"

        COMMIT C — train_real_ml.py bugfix (if small + clear):
          git add backend/scripts/train_real_ml.py
          git commit -m "fix(ml-training): handle Series .values for is_month_end calendar features

          Co-Authored-By: Hermes <hermes@floww.dev>"

        COMMIT D — prompt artifacts:
          git add DEEPSEEK_*.md HERMES_*.md MASTER_*.md 2>/dev/null
          git commit -m "docs(round-7): archive recovery + prompt artifacts

          Co-Authored-By: Hermes <hermes@floww.dev>" || echo "no artifacts to commit"

        COMMIT E — kanban timestamp:
          git add kanban/BOTTLENECK_ALERTS.md
          git commit -m "chore(kanban): refresh bottleneck alerts timestamp

          Co-Authored-By: Hermes <hermes@floww.dev>" || echo "no kanban change"

  S2.4  Print the remaining HALT_FOR_HUMAN list — these stay uncommitted:
          git status -s

  S2.5  Run full suite to confirm no regression from the commits you made:
          python -m pytest -q --tb=no --ignore=tests/e2e --ignore=tests/services/ml 2>&1 | tail -3

        EXPECT: 0 failed, ≥ 2522 passed.

  S2.6  Push committed work:
          git pull --rebase origin main
          git push origin main

  PRINT "PHASE 2 COMPLETE — N commits pushed, M files held for human — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 3 — HUMAN VISUAL GATE (BLOCKS — do not skip)
═══════════════════════════════════════════════════════════════════════════════

  S3.1  Start uvicorn in background:
          cd /Users/nav/Documents/GitHub/floww/backend
          source .venv/bin/activate
          nohup uvicorn server:app --port 8000 > /tmp/uvicorn_hermes_b2.log 2>&1 &
          sleep 8

  S3.2  Smoke endpoints:
          curl -s -o /dev/null -w "dashboard:    %{http_code}\n" http://localhost:8000/dashboard/
          curl -s -o /dev/null -w "chain SPY:    %{http_code}\n" http://localhost:8000/api/chain/SPY
          curl -s -o /dev/null -w "briefing SPY: %{http_code}\n" http://localhost:8000/api/briefing/SPY

        EXPECT: dashboard 200, chain 200 or 429, briefing 200 or 404.
        Else: tail /tmp/uvicorn_hermes_b2.log and HALT.

  S3.3  Post the visual-verification block to the user (exact text):

          ══════════════════════════════════════════════════════════════════
          HUMAN VISUAL VERIFICATION REQUIRED — open Chrome decoder PWA

          1. Open http://localhost:8000/dashboard/ in your Chrome app
          2. Click the Heatseeker tab (or press "1")
          3. Confirm ALL of these are visible:
             [a] HEADER strip: SPY | \$<price> | POSITIVE/NEGATIVE/NEUTRAL Γ
                 chip | ● LIVE
             [b] LEFT sidebar: 5 toggle groups (VIEW / MODE / INDICATOR /
                 DTE / EXPIRIES)
             [c] CENTER: heatmap (strikes × expiries, teal/purple cells)
             [d] RIGHT sidebar — 9 panels stacked vertically:
                   • MORNING BRIEFING (colored dot + regime + ratio)
                   • KEY LEVELS (5 rows)
                   • STRATEGY (em-dash placeholder OK)
                   • POSITION SIZING (placeholder OK)
                   • RISK LEVELS (2×2 R1/R2/S1/S2)
                   • PRE-MARKET CHECKLIST (8 checkboxes, persistent)
                   • FLIP ZONES (bullets + %distance)
                   • STACKED NODES (top 4 strikes with call/put bars)
                   • TUG-OF-WAR (single bar + dollar totals)
          4. Confirm: no horizontal scrollbar at 1440px viewport width
          5. Confirm: no other tab (Flowseeker, Toxicity, Vol, Trinity,
             Atlas, Replay, Agent Hub, Nexus, Greeks) looks BROKEN —
             they should look exactly as they did before
          6. Reply with one of:
                "LOOKS GOOD"           → I'll close Round 7
                "MISSING: <list>"      → I'll halt and add the missing pieces
                "BROKEN: <tab>: <how>" → I'll halt and investigate
          ══════════════════════════════════════════════════════════════════

  S3.4  BLOCK. Wait for user reply. Do NOT proceed without it. Do NOT
        invent visual changes.

        - "LOOKS GOOD" → kill %1 ; sleep 1 ; PROCEED.
        - Any other reply → HALT with the reply verbatim.

  PRINT "PHASE 3 COMPLETE — visual gate approved — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 4 — CLOSE ROUND 7
═══════════════════════════════════════════════════════════════════════════════

  S4.1  Append closure entry to docs/ROUND7_COMPLETION_LOG.md:

          cat >> docs/ROUND7_COMPLETION_LOG.md <<EOF

          ## Hermes Prompt B2 closure — $(date -u +%Y-%m-%dT%H:%M:%SZ)

          Mission: verify DeepSeek Prompt A's UI work + remove 12 fake xfails
          + reconcile working tree + visual-gate the 3-column Heatseeker layout.

          Outcome:
          - 12 fake xfails removed (all tests now PASS, not XPASS)
          - N working-tree files committed in categorized commits
          - M files held for human decision (frontend/, server.py,
            auth.py, fetch_coordinator.py, PaperTrade.jsx)
          - 3-column Heatseeker layout visually approved by Nav via Chrome PWA
          - test count: 2522 → <new> passing, 0 failed

          Round 7 closed at HEAD: $(git rev-parse HEAD)

          Co-Authored-By: Hermes <hermes@floww.dev>
          EOF

          git add docs/ROUND7_COMPLETION_LOG.md
          git commit -m "docs(round-7-closure): Hermes Prompt B2 verification + visual gate complete

          Co-Authored-By: Hermes <hermes@floww.dev>"

  S4.2  Write the closure kanban card:

          cat > kanban/cards/hermes_b2_closure_$(date +%Y-%m-%d).md <<EOF
          ---
          id: hermes-b2-closure-$(date +%Y-%m-%d)
          title: "Hermes Prompt B2 — verify + close Round 7"
          status: done
          assignee: hermes-prompt-b2
          acceptance: |
            12 fake xfails removed (XPASS → PASS); working tree reconciled;
            3-column Heatseeker visually approved; test count maintained.
          ---

          ## Commits

          $(git log --pretty="- %h %s" --since="2 hours ago" --grep="Hermes\\|hermes")

          ## Files held for human decision (not committed)

          $(git status -s | head -10)
          EOF

          git add kanban/cards/hermes_b2_closure_*.md
          git commit -m "chore(kanban): hermes b2 closure card

          Co-Authored-By: Hermes <hermes@floww.dev>"

  S4.3  Push:
          git pull --rebase origin main
          git push origin main

  S4.4  Print final report:

          ──── HERMES PROMPT B2 COMPLETE ────
          Start HEAD:        $(cat /tmp/hermes_b2_start.txt)
          Final HEAD:        $(git rev-parse HEAD)
          Fake xfails:       12 → 0
          Commits added:     <count>
          Working tree:      <N> committed, <M> held for human
          Visual gate:       PASSED (Chrome PWA approved)
          Tests:             2522+ passing, 0 failed
          Round 7 status:    CLOSED
          ──────────────────────────────────

  Final line: "DONE"

═══════════════════════════════════════════════════════════════════════════════
ANTI-DRIFT REMINDERS
═══════════════════════════════════════════════════════════════════════════════

  - You did NOT come to build new features. You came to verify + close.
  - Forbidden file lists must be honored even if you spot "improvements."
  - If tempted to xfail/skip a test: HALT instead.
  - Every commit-message claim must be grep-verifiable.
  - Phase 3 BLOCKS on human; do not invent visual changes while waiting.
  - The 9 non-Heatseeker tabs are sacred.

END OF PROMPT. BEGIN AT PHASE 0 STEP S0.1.
═══════════════════════════════════════════════════════════════════════════════
