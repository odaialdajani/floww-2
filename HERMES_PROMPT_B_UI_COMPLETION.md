# Hermes Prompt B — Heatseeker UI Completion (Single-Agent Run)

> **HOW TO USE:** Copy everything below the first `═══` line. Paste into one Owl Alpha Hermes agent. Runs in parallel with DeepSeek Prompt A (zero file overlap).
>
> **OWNED FILE:** `backend/services/dash_ui.py` + ONE new test file. DeepSeek Prompt A owns everything else.

═══════════════════════════════════════════════════════════════════════════════
ROUND 7 STANDING PREAMBLE — PROJECT ORACLE (FLOWW)
═══════════════════════════════════════════════════════════════════════════════

You are a Round-7 Hermes autonomous execution agent (single-agent run, no
swarm coordination needed this round). Architect: Nav (PhD math + physics,
ex-Jane Street HFT). Project: /Users/nav/Documents/GitHub/floww (Project
Oracle — institutional options-analytics terminal with live data integration).

Concurrent context: DeepSeek Prompt A is running in parallel on backend
test stabilization. You and DeepSeek share ZERO files. If you find yourself
about to edit anything other than `backend/services/dash_ui.py` or your
single new test file, halt — that means file ownership has been violated.

■ VERIFY CANONICAL REPO BEFORE WRITING ANY CODE:
    pwd && git remote -v
  Expected working directory: /Users/nav/Documents/GitHub/floww
  Expected remote: git@github.com:JattMoosewala5911/floww.git
  If you are in /Users/nav/GitHub/floww or any other path → HALT IMMEDIATELY.
  Round 5 and the early Round 6/7 work failed because agents worked in stale
  clones. This check is mandatory.

■ LOAD CONTEXT IN PARALLEL (use Skill tool: Read in parallel):
  - MASTER_ARCHITECT_REPORT_2026-05-24.md          (current state assessment)
  - docs/ROUND7_COMPLETION_LOG.md                  (what's already landed)
  - backend/services/dash_ui.py                    (the file you'll modify)
  - backend/routes/morning_briefing_api.py         (or briefing.py — endpoint contract)
  - backend/routes/position_sizing_api.py          (Kelly endpoint contract — may not exist yet)
  - backend/routes/heatseeker_snapshots_api.py     (TOP MOVERS / HISTORY contract)

■ OPERATING LAWS (Project Oracle invariants — non-negotiable):
  - I-1: No synthetic data in production paths (placeholders OK; raise
         DegenerateModelError where applicable)
  - I-2: TDD — failing test first, see it fail, implement, see it pass
  - I-3: OLAP-first — no Pandas in hot paths; PyArrow only
  - I-5: NaN safety — every numeric comparison guarded with math.isfinite()
  - I-6: git pull --rebase origin main before every push
  - I-7: NO double /api/ prefixes on FastAPI routes
  - I-8: Explicit math.isnan() / math.isfinite() guards before float ops
  - I-9: No look-ahead bias in feature engineering
  - I-10: Conventional commits; Co-Authored-By: Hermes <hermes@floww.dev>
  - NEVER --no-verify, --amend (someone else's commit), or force-push main
  - Commit per logical deliverable, push after each commit

■ FILE OWNERSHIP — CRITICAL EXCLUSION ZONE:
  You may ONLY modify:
    backend/services/dash_ui.py
    backend/tests/services/test_dash_ui_three_column.py  (new file you create)

  DO NOT TOUCH any of these (other agents own them, or they're stable):
    backend/routes/data_providers.py        backend/services/numba_greeks.py
    backend/services/duckdb_engine.py       backend/services/causal_inference.py
    backend/routes/live_trading.py          backend/services/av_adapter.py
    backend/services/data_source_router.py  backend/services/heatseeker_snapshots.py
    backend/services/morning_briefing.py    backend/services/position_sizing.py
    backend/services/databento_oi.py        backend/services/cache_router.py
    backend/services/fetch_coordinator.py   backend/routes/heatseeker_snapshots_api.py
    backend/routes/morning_briefing_api.py  backend/routes/greeks_api.py
    backend/services/gflows_integration.py  backend/gflows_modules/
    backend/bs_greeks.py                    backend/server.py
    backend/auth.py                         backend/pytest.ini
    Any other test file                     Any frontend/src/ file
    Any docs/                               Any .github/

  You MAY read these to consume their public interfaces; you MUST NOT
  import their internals or refactor them.

■ EXECUTION MODE: AUTONOMOUS + KANBAN-TRACKED
  - Work continuously without waiting for human approval between tasks,
    EXCEPT at the Phase 3 visual gate (user must confirm Chrome decoder
    shows the layout correctly).
  - After each phase commit, append one line to docs/ROUND7_COMPLETION_LOG.md:
      <SHA> | hermes-prompt-b | <acceptance criterion satisfied> | <one-line insight>
  - If blocked: write kanban/cards/hermes_prompt_b_blocked_$(date +%Y-%m-%d).md
    with the issue, then HALT — do not silently proceed past blocked work.
  - Run pytest after every implementation step; current baseline is
    2522 passing / 1 failed / 69 skipped (the 1 known fail is in
    tests/services/ml/test_inference.py and is being handled by Prompt A).

■ STOP CONDITIONS (any of these = HALT immediately):
  - Truth audit red → halt, do not commit (qc/audit/truth_audit.sh)
  - Test count drops below 2522 passing → halt, revert your last change
  - File-ownership violation (you about to edit a forbidden file) → halt
  - WRONG_CLONE detected → halt
  - User has not confirmed Phase 3 visual gate → halt, wait for "LOOKS GOOD"
  - 3 consecutive push failures → exit clean, write blocker to kanban

═══════════════════════════════════════════════════════════════════════════════
SKILLS YOU SHOULD INVOKE
═══════════════════════════════════════════════════════════════════════════════

Use the Skill tool (no leading slash):

  superpowers:test-driven-development    — for every Phase 1, 2, 4 test loop
  superpowers:using-superpowers          — if you forget the skill protocol
  superpowers:debugging                  — if a test fails and cause isn't obvious
  superpowers:requesting-code-review     — invoke at end of Phase 4 to
                                            self-review before push

Do NOT invoke:
  subagent-driven-development            — you ARE the agent
  dispatching-parallel-agents            — single-agent run this round
  writing-plans                          — plan already exists

═══════════════════════════════════════════════════════════════════════════════
CONTEXT — VERIFIED CURRENT STATE (do not trust handoff docs, only this)
═══════════════════════════════════════════════════════════════════════════════

The Confluence Decoder Terminal at http://localhost:8000/dashboard/ is a
Dash + Plotly + dash-bootstrap-components app served via FastAPI WSGI
middleware. It has 10 tabs (Heatseeker, Flowseeker, Toxicity, Vol Surface,
Trinity, Atlas, Replay, Agent Hub, Nexus, Greeks Exposure). Leave 9 of
those tabs untouched. Only the Heatseeker tab gets modified this round.

CURRENT Heatseeker tab structure (verified by `grep`, NOT by any handoff
document — the prior "three-column layout upgrade" handoff was fabricated):

  html.Div([
      html.Div([
          sidebar,                  # _build_heatseeker_toggles() — EXISTS
          html.Div(graph, style={"flex": 1}),
      ], style={"display": "flex", "flexDirection": "row"}),
  ])

This is a TWO-column layout: left sidebar (5 toggle groups) + center
heatmap. There is NO right sidebar, NO header strip, NO cell tags (KING/
FLOOR/CEIL/GATE/AIR badges).

YOUR MISSION: add the missing third column (9 right-sidebar panels), the
header strip (POSITIVE/NEGATIVE Γ badge), and cell-tag computation.

Theme constants (in dash_ui.py, do not redefine):
    BG_DARK   = "#0a0a1a"
    BG_CARD   = "#1a1a2e"
    BG_PLOT   = "#16213e"
    ACCENT    = "#00ff88"   (positive gamma / live)
    WARN      = "#ffaa00"   (caution / KING)
    DANGER    = "#ff4444"   (negative gamma / CEIL)
    TEXT      = "#e0e0e0"

Backend endpoints already operational (call from callbacks if needed; OK
to handle 404/503 with a "—" placeholder — the user is on phone hotspot):
    GET /api/chain/{ticker}                       — main data (already wired)
    GET /api/briefing/{ticker}                    — Morning Briefing
    GET /api/heatseeker/top-movers/{ticker}       — TOP MOVERS delta
    GET /api/heatseeker/history/{ticker}          — HISTORY snapshots

═══════════════════════════════════════════════════════════════════════════════
HALT FORMAT (use this exact structure when stopping)
═══════════════════════════════════════════════════════════════════════════════

    ──── HALT REPORT ────
    Agent:     Hermes Prompt B
    Phase:     <n>
    Step:      <n.n>
    Reason:    <one sentence>
    Diagnostic output (verbatim):
    <output>
    Question for human (yes/no or A/B): <one specific question>
    ─────────────────────

Then STOP. Do not retry. Do not "creative-fix." Wait for human reply.

Hermes-specific note: also write the halt to
kanban/cards/hermes_prompt_b_blocked_$(date +%Y-%m-%d).md so the
orchestrator can pick it up.

═══════════════════════════════════════════════════════════════════════════════
GREP-VERIFICATION RULE (counters DeepSeek-style handoff hallucinations)
═══════════════════════════════════════════════════════════════════════════════

Every commit message claim MUST be backed by a `grep` output. Examples:

  Bad commit message:
    "feat(heatseeker): add right sidebar with 9 panels"
  Good commit message:
    "feat(heatseeker): add right sidebar with 9 panels

    Verification:
      $ grep -c '_build_heatseeker_right_sidebar' backend/services/dash_ui.py
      2
      $ grep -E 'KEY LEVELS|MORNING BRIEFING|TUG-OF-WAR' backend/services/dash_ui.py | wc -l
      3"

If you can't grep-verify a claim, don't make it.

═══════════════════════════════════════════════════════════════════════════════
PHASE 0 — SAFETY GATE
═══════════════════════════════════════════════════════════════════════════════

  S0.1  Verify canonical clone + capture starting state:
          cd /Users/nav/Documents/GitHub/floww
          pwd && git remote -v
          git rev-parse HEAD > /tmp/hermes_b_start.txt
          cat /tmp/hermes_b_start.txt

  S0.2  Confirm no rebase in progress:
          ls .git/rebase-merge/ .git/rebase-apply/ 2>&1
        EXPECT: both "No such file or directory". Else HALT.

  S0.3  Pull latest, create backup branch:
          git pull --rebase origin main
          git branch backup/hermes-b-$(date +%Y%m%d-%H%M%S)

  S0.4  Verify dash_ui.py has the expected baseline shape:
          wc -l backend/services/dash_ui.py
          grep -n "_build_heatseeker_toggles\|def _build_gex_heatmap\|tab == \"heatseeker\"" \
              backend/services/dash_ui.py | head -10

        EXPECT:
          - file > 1500 lines
          - `_build_heatseeker_toggles` function exists
          - `_build_gex_heatmap` function exists
          - render_tab has a `tab == "heatseeker"` branch
        Else: HALT — baseline is wrong, prompt assumptions invalid.

  PRINT "PHASE 0 COMPLETE — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 1 — TDD: WRITE FAILING TESTS FOR THE 8 COMPUTE HELPERS
═══════════════════════════════════════════════════════════════════════════════

INVOKE: superpowers:test-driven-development before this phase.

  S1.1  Create backend/tests/services/test_dash_ui_three_column.py with
        these 8 tests (write FIRST, before any implementation):

        ```python
        """TDD test for Heatseeker three-column layout compute helpers.

        These tests are RED at the start of Phase 1.
        They go GREEN after Phase 2 implements the helpers.
        """
        import math
        import pytest

        SAMPLE_CONTRACTS = [
            {"strike": 740, "gex":  3e8, "oi": 5000, "type": "call", "expiry": "2026-06-20"},
            {"strike": 745, "gex":  5e8, "oi": 8000, "type": "call", "expiry": "2026-06-20"},
            {"strike": 750, "gex":  1e8, "oi": 9000, "type": "call", "expiry": "2026-06-20"},
            {"strike": 755, "gex": -2e8, "oi": 4000, "type": "put",  "expiry": "2026-06-20"},
            {"strike": 760, "gex": -4e8, "oi": 6000, "type": "put",  "expiry": "2026-06-20"},
        ]
        SPOT = 748.0


        def test_gamma_regime_returns_valid_label():
            from services.dash_ui import _compute_gamma_regime
            regime, color, ratio = _compute_gamma_regime(SAMPLE_CONTRACTS)
            assert regime in ("BULLISH", "NEUTRAL", "BEARISH", "UNKNOWN")
            assert color in ("#00ff88", "#ff4444", "#ffaa00", "#666666")
            assert isinstance(ratio, (int, float)) and math.isfinite(ratio)


        def test_key_levels_returns_all_keys():
            from services.dash_ui import _compute_key_levels
            klv = _compute_key_levels(SPOT, SAMPLE_CONTRACTS)
            assert set(klv.keys()) == {"gamma_flip", "call_wall", "put_wall", "max_pain", "spot"}
            assert klv["spot"] == SPOT


        def test_risk_levels_returns_4_levels():
            from services.dash_ui import _compute_risk_levels
            risk = _compute_risk_levels(SPOT, SAMPLE_CONTRACTS)
            assert set(risk.keys()) == {"R1", "R2", "S1", "S2"}


        def test_stacked_nodes_top_n_limit():
            from services.dash_ui import _compute_stacked_nodes
            nodes = _compute_stacked_nodes(SAMPLE_CONTRACTS, top_n=3)
            assert len(nodes) <= 3
            for n in nodes:
                assert {"strike", "call_pct", "put_pct", "total_oi"} == set(n.keys())


        def test_cell_tags_assigns_king():
            from services.dash_ui import _compute_cell_tags
            tags = _compute_cell_tags(SPOT, SAMPLE_CONTRACTS)
            assert any("KING" in t for t in tags.values()), "KING tag missing"


        def test_handles_empty_contracts():
            from services.dash_ui import (_compute_gamma_regime, _compute_key_levels,
                                          _compute_stacked_nodes, _compute_cell_tags)
            assert _compute_gamma_regime([])[0] == "UNKNOWN"
            assert _compute_key_levels(SPOT, [])["spot"] == SPOT
            assert _compute_stacked_nodes([]) == []
            assert _compute_cell_tags(SPOT, []) == {}


        def test_handles_nan_gex_safely():
            from services.dash_ui import _compute_gamma_regime
            contracts = [{"strike": 745, "gex": float("nan"), "oi": 1000, "type": "call"}]
            regime, _, _ = _compute_gamma_regime(contracts)
            assert regime == "UNKNOWN"   # NaN must be filtered


        def test_fmt_money_handles_edge_cases():
            from services.dash_ui import _fmt_money
            assert _fmt_money(1_500_000_000) == "$1.50B"
            assert _fmt_money(473_200_000) == "$473.2M"
            assert _fmt_money(float("nan")) == "—"
            assert _fmt_money(None) == "—"
        ```

  S1.2  Verify all 8 tests FAIL with import errors (expected):
          cd backend && source .venv/bin/activate
          python -m pytest tests/services/test_dash_ui_three_column.py -v 2>&1 | tail -15

        EXPECT: 8 errors/failures, all complaining about missing
        `_compute_*` or `_fmt_money` imports.
        If anything passes here: HALT — the implementation already exists
        and something is wrong with our reading of state.

  S1.3  Commit the failing tests:
          git add backend/tests/services/test_dash_ui_three_column.py
          git commit -m "test(heatseeker-ui): failing TDD tests for 8 compute helpers (RED)

          Verification:
            $ python -m pytest tests/services/test_dash_ui_three_column.py 2>&1 | tail -3
            === 8 failed in 0.0Ns ===

          Co-Authored-By: Hermes <hermes@floww.dev>"

  PRINT "PHASE 1 COMPLETE — 8 RED tests committed — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 2 — IMPLEMENT 8 COMPUTE HELPERS (GREEN)
═══════════════════════════════════════════════════════════════════════════════

  S2.1  Locate the insertion point in dash_ui.py. Find the line just
        after `_build_heatseeker_toggles` ends:
          grep -n "^def " backend/services/dash_ui.py | head -20

  S2.2  Insert these 8 NaN-safe helpers (use Edit tool) just before the
        next function definition:

        ```python
        # ── Right-sidebar compute helpers (I-5/I-8 NaN-safe) ─────────────

        def _compute_gamma_regime(contracts):
            """Return (label, dot_color, signed_ratio)."""
            if not contracts:
                return ("UNKNOWN", "#666666", 0.0)
            valid = [c.get("gex", 0) for c in contracts
                     if isinstance(c.get("gex"), (int, float)) and math.isfinite(c.get("gex"))]
            net = sum(valid)
            total_abs = sum(abs(v) for v in valid)
            if total_abs <= 0:
                return ("UNKNOWN", "#666666", 0.0)
            ratio = net / total_abs
            if ratio > 0.10:
                return ("BULLISH", "#00ff88", ratio)
            if ratio < -0.10:
                return ("BEARISH", "#ff4444", ratio)
            return ("NEUTRAL", "#ffaa00", ratio)


        def _compute_key_levels(spot, contracts):
            """Return {gamma_flip, call_wall, put_wall, max_pain, spot}."""
            out = {"gamma_flip": None, "call_wall": None, "put_wall": None,
                   "max_pain": None, "spot": spot}
            if not contracts:
                return out
            by_strike = {}
            for c in contracts:
                s = c.get("strike")
                if not isinstance(s, (int, float)) or not math.isfinite(s):
                    continue
                d = by_strike.setdefault(s, {"gex": 0.0, "call_oi": 0, "put_oi": 0})
                g = c.get("gex", 0)
                if isinstance(g, (int, float)) and math.isfinite(g):
                    d["gex"] += g
                oi = c.get("oi", 0) or 0
                if c.get("type") == "call":
                    d["call_oi"] += oi
                else:
                    d["put_oi"] += oi
            strikes_sorted = sorted(by_strike.keys())
            # Gamma flip: where cumulative GEX crosses zero
            cum, prev_s = 0.0, None
            for s in strikes_sorted:
                cum_new = cum + by_strike[s]["gex"]
                if prev_s is not None and cum * cum_new < 0:
                    out["gamma_flip"] = round((prev_s + s) / 2, 2)
                    break
                cum, prev_s = cum_new, s
            # Walls
            calls_above = [(s, by_strike[s]["call_oi"]) for s in strikes_sorted if s > spot]
            if calls_above:
                out["call_wall"] = max(calls_above, key=lambda x: x[1])[0]
            puts_below = [(s, by_strike[s]["put_oi"]) for s in strikes_sorted if s < spot]
            if puts_below:
                out["put_wall"] = max(puts_below, key=lambda x: x[1])[0]
            # Max pain
            def pain_at(K):
                p = 0.0
                for s in strikes_sorted:
                    if s >= K:
                        p += by_strike[s]["call_oi"] * (s - K) * 100
                    if s <= K:
                        p += by_strike[s]["put_oi"] * (K - s) * 100
                return p
            if strikes_sorted:
                out["max_pain"] = min(strikes_sorted, key=pain_at)
            return out


        def _compute_risk_levels(spot, contracts):
            """Return {R1, R2, S1, S2}. TODO: derive from ATR or IV instead of ±0.5%/1.0%."""
            if not spot or not math.isfinite(spot):
                return {"R1": None, "R2": None, "S1": None, "S2": None}
            return {
                "R1": round(spot * 1.005, 2),
                "R2": round(spot * 1.010, 2),
                "S1": round(spot * 0.995, 2),
                "S2": round(spot * 0.990, 2),
            }


        def _compute_flip_zones(spot, contracts):
            """Return [(label, strike, pct_distance), ...]."""
            if not contracts or not spot:
                return []
            klv = _compute_key_levels(spot, contracts)
            zones = []
            for label, val in [("GEX Flip", klv["gamma_flip"]),
                               ("Max Pain", klv["max_pain"])]:
                if val is not None and math.isfinite(val):
                    zones.append((label, val, (val - spot) / spot * 100))
            return zones


        def _compute_stacked_nodes(contracts, top_n=4):
            """Return top N strikes by combined OI with call/put share."""
            if not contracts:
                return []
            by_strike = {}
            for c in contracts:
                s = c.get("strike")
                if not isinstance(s, (int, float)) or not math.isfinite(s):
                    continue
                d = by_strike.setdefault(s, {"call_oi": 0, "put_oi": 0})
                oi = c.get("oi", 0) or 0
                if c.get("type") == "call":
                    d["call_oi"] += oi
                else:
                    d["put_oi"] += oi
            nodes = []
            for s, d in by_strike.items():
                total = d["call_oi"] + d["put_oi"]
                if total > 0:
                    nodes.append({
                        "strike": s,
                        "call_pct": d["call_oi"] / total * 100,
                        "put_pct":  d["put_oi"]  / total * 100,
                        "total_oi": total,
                    })
            nodes.sort(key=lambda n: n["total_oi"], reverse=True)
            return nodes[:top_n]


        def _compute_tug_of_war(contracts):
            """Return (positive_gex_total, negative_gex_total) in dollars."""
            if not contracts:
                return (0.0, 0.0)
            valid = [c.get("gex", 0) for c in contracts
                     if isinstance(c.get("gex"), (int, float)) and math.isfinite(c.get("gex"))]
            return (sum(v for v in valid if v > 0), sum(v for v in valid if v < 0))


        def _compute_cell_tags(spot, contracts):
            """Return {strike: [tag_labels]} for KING/FLOOR/CEIL/GATE/AIR."""
            if not contracts:
                return {}
            by_strike = {}
            for c in contracts:
                s = c.get("strike")
                if not isinstance(s, (int, float)) or not math.isfinite(s):
                    continue
                g = c.get("gex", 0)
                if isinstance(g, (int, float)) and math.isfinite(g):
                    by_strike.setdefault(s, 0.0)
                    by_strike[s] += g
            if not by_strike:
                return {}
            total_abs = sum(abs(g) for g in by_strike.values())
            if total_abs <= 0:
                return {}
            tags = {s: [] for s in by_strike}
            king = max(by_strike, key=lambda s: abs(by_strike[s]))
            tags[king].append("KING")
            for s in sorted([k for k in by_strike if by_strike[k] > 0 and k <= spot],
                            key=lambda s: by_strike[s], reverse=True)[:3]:
                tags[s].append("FLOOR")
            for s in sorted([k for k in by_strike if by_strike[k] < 0 and k >= spot],
                            key=lambda s: by_strike[s])[:3]:
                tags[s].append("CEIL")
            for s, g in by_strike.items():
                if abs(g) / total_abs > 0.10 and "KING" not in tags[s]:
                    tags[s].append("GATE")
            for s, g in by_strike.items():
                if abs(g) / total_abs < 0.01:
                    tags[s].append("AIR")
            return {s: t for s, t in tags.items() if t}


        def _fmt_money(n):
            """Format dollar amounts: $1.50B, $473.2M, $52.3K, or '—'."""
            if not isinstance(n, (int, float)) or not math.isfinite(n):
                return "—"
            if abs(n) >= 1e9:
                return f"${n/1e9:.2f}B"
            if abs(n) >= 1e6:
                return f"${n/1e6:.1f}M"
            if abs(n) >= 1e3:
                return f"${n/1e3:.1f}K"
            return f"${n:.0f}"
        ```

  S2.3  Run the 8 tests — they MUST now pass (TDD GREEN):
          python -m pytest tests/services/test_dash_ui_three_column.py -v 2>&1 | tail -15
        EXPECT: 8 passed. If any fail: read the failure and fix
        implementation (do NOT relax the tests).

  S2.4  Run full suite to confirm no regression:
          python -m pytest -q --tb=no --ignore=tests/e2e --ignore=tests/services/ml 2>&1 | tail -3
        EXPECT: failed count NOT higher than baseline (~0–1). If it rose,
        you introduced a regression — fix before committing.

  S2.5  Commit:
          git add backend/services/dash_ui.py
          git commit -m "feat(heatseeker-ui): implement 8 NaN-safe right-sidebar compute helpers (GREEN)

          Verification:
            \$ python -m pytest tests/services/test_dash_ui_three_column.py 2>&1 | tail -1
            === 8 passed in 0.Ns ===
            \$ grep -c '_compute_gamma_regime\\|_compute_key_levels\\|_compute_cell_tags' backend/services/dash_ui.py
            <expect ≥ 6>

          Co-Authored-By: Hermes <hermes@floww.dev>"
          git push origin main

  PRINT "PHASE 2 COMPLETE — 8/8 tests GREEN, helpers pushed — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 3 — UI ASSEMBLY (RIGHT SIDEBAR + HEADER + 3-COLUMN LAYOUT)
═══════════════════════════════════════════════════════════════════════════════

  S3.1  Add `_build_heatseeker_right_sidebar(spot, contracts)` immediately
        after `_build_heatseeker_toggles`:

        ```python
        def _build_heatseeker_right_sidebar(spot, contracts):
            """Right sidebar: 9 analytics panels for the Heatseeker tab."""
            regime, dot_color, ratio = _compute_gamma_regime(contracts)
            klv = _compute_key_levels(spot, contracts)
            risk = _compute_risk_levels(spot, contracts)
            zones = _compute_flip_zones(spot, contracts)
            stacked = _compute_stacked_nodes(contracts)
            pos_gex, neg_gex = _compute_tug_of_war(contracts)

            def panel(title, children):
                return html.Div([
                    html.Div(title, style={"color": ACCENT, "fontSize": "10px",
                                            "fontWeight": "bold", "letterSpacing": "1px",
                                            "marginBottom": "4px"}),
                    html.Div(children, style={"fontSize": "11px", "color": TEXT}),
                ], style={"background": BG_CARD, "padding": "8px 10px",
                         "marginBottom": "6px", "borderRadius": "4px",
                         "border": f"1px solid {BG_PLOT}"})

            def kv(label, value):
                return html.Div([
                    html.Span(label, style={"color": "#888", "fontSize": "10px"}),
                    html.Span(str(value) if value is not None else "—",
                             style={"color": TEXT, "float": "right",
                                    "fontFamily": "monospace"}),
                ], style={"marginBottom": "2px"})

            briefing = panel("MORNING BRIEFING", html.Div([
                html.Span("●", style={"color": dot_color, "marginRight": "6px",
                                       "fontSize": "14px"}),
                html.Span(regime, style={"fontWeight": "bold"}),
                html.Div(f"Net/|Σ| GEX: {ratio:+.1%}" if ratio else "",
                         style={"color": "#888", "fontSize": "9px", "marginTop": "2px"}),
            ]))

            key_levels = panel("KEY LEVELS", html.Div([
                kv("Gamma Flip", klv["gamma_flip"]),
                kv("Call Wall",  klv["call_wall"]),
                kv("Put Wall",   klv["put_wall"]),
                kv("Max Pain",   klv["max_pain"]),
                kv("Spot",       spot),
            ]))

            strategy = panel("STRATEGY", html.Div("—", style={"color": "#666"}))
            sizing   = panel("POSITION SIZING", html.Div([
                html.Div("Kelly: —", style={"color": "#888", "fontSize": "10px"}),
            ]))

            risk_panel = panel("RISK LEVELS", html.Table([
                html.Tr([
                    html.Td(f"R1 {risk['R1'] or '—'}", style={"padding": "2px 6px",
                                                              "color": DANGER}),
                    html.Td(f"R2 {risk['R2'] or '—'}", style={"padding": "2px 6px",
                                                              "color": DANGER}),
                ]),
                html.Tr([
                    html.Td(f"S1 {risk['S1'] or '—'}", style={"padding": "2px 6px",
                                                              "color": ACCENT}),
                    html.Td(f"S2 {risk['S2'] or '—'}", style={"padding": "2px 6px",
                                                              "color": ACCENT}),
                ]),
            ], style={"width": "100%", "fontFamily": "monospace", "fontSize": "10px"}))

            checklist = panel("PRE-MARKET CHECKLIST", dcc.Checklist(
                id="heatseeker-checklist",
                options=[
                    {"label": " GEX regime identified",     "value": "regime"},
                    {"label": " Gamma flip noted",          "value": "flip"},
                    {"label": " Call/Put walls confirmed",  "value": "walls"},
                    {"label": " Max pain identified",       "value": "pain"},
                    {"label": " Strategy selected",         "value": "strategy"},
                    {"label": " Position size calculated",  "value": "size"},
                    {"label": " Stop loss set",             "value": "stop"},
                    {"label": " Risk/reward ≥ 1:2",         "value": "rr"},
                ],
                value=[], persistence=True, persistence_type="local",
                style={"color": TEXT, "fontSize": "10px"},
            ))

            flip_panel = panel("FLIP ZONES",
                html.Div([
                    html.Div([
                        html.Span("● ", style={"color": ACCENT if pct < 0 else DANGER}),
                        html.Span(f"{label}: ", style={"color": "#888"}),
                        html.Span(f"{val:.1f} ({pct:+.2f}%)",
                                 style={"color": TEXT, "fontFamily": "monospace"}),
                    ], style={"marginBottom": "2px", "fontSize": "10px"})
                    for label, val, pct in zones
                ]) if zones else html.Div("—", style={"color": "#666"}))

            def node_row(n):
                return html.Div([
                    html.Span(f"{int(n['strike'])} ", style={"color": TEXT,
                              "fontFamily": "monospace", "fontSize": "10px"}),
                    html.Div([
                        html.Div(style={"width": f"{n['call_pct']:.0f}%",
                                       "background": ACCENT, "height": "6px",
                                       "display": "inline-block"}),
                        html.Div(style={"width": f"{n['put_pct']:.0f}%",
                                       "background": "#9933ff", "height": "6px",
                                       "display": "inline-block"}),
                    ], style={"width": "60%", "display": "inline-block",
                             "marginLeft": "4px"}),
                    html.Span(f" {n['call_pct']:.0f}/{n['put_pct']:.0f}",
                             style={"color": "#888", "fontSize": "9px",
                                    "marginLeft": "4px"}),
                ], style={"marginBottom": "3px"})

            stacked_panel = panel("STACKED NODES",
                html.Div([node_row(n) for n in stacked])
                if stacked else html.Div("—", style={"color": "#666"}))

            total_for_bar = abs(pos_gex) + abs(neg_gex)
            pos_pct = (pos_gex / total_for_bar * 100) if total_for_bar > 0 else 50
            tug_panel = panel("TUG-OF-WAR", html.Div([
                html.Div([
                    html.Div(style={"width": f"{pos_pct:.0f}%", "background": ACCENT,
                                   "height": "10px", "display": "inline-block"}),
                    html.Div(style={"width": f"{100-pos_pct:.0f}%", "background": DANGER,
                                   "height": "10px", "display": "inline-block"}),
                ], style={"width": "100%"}),
                html.Div([
                    html.Span(f"+{_fmt_money(pos_gex)}",
                             style={"color": ACCENT, "fontSize": "10px"}),
                    html.Span(f" {_fmt_money(neg_gex)}",
                             style={"color": DANGER, "fontSize": "10px", "float": "right"}),
                ], style={"marginTop": "2px"}),
            ]))

            return html.Div([briefing, key_levels, strategy, sizing, risk_panel,
                            checklist, flip_panel, stacked_panel, tug_panel],
                           style={"width": "280px", "padding": "8px",
                                  "overflowY": "auto",
                                  "maxHeight": "calc(100vh - 100px)"})
        ```

  S3.2  Add the header strip helper right after the right sidebar:

        ```python
        def _build_heatseeker_header(spot, contracts, ticker):
            """Header strip: ticker | price | regime badge | LIVE indicator."""
            regime, _, _ = _compute_gamma_regime(contracts)
            badge_text = {"BULLISH": "POSITIVE Γ", "BEARISH": "NEGATIVE Γ",
                         "NEUTRAL": "NEUTRAL Γ"}.get(regime, "UNKNOWN Γ")
            badge_bg = {"BULLISH": ACCENT, "BEARISH": DANGER,
                       "NEUTRAL": WARN}.get(regime, "#666")
            return html.Div([
                html.Span(ticker.upper(), style={"fontSize": "20px",
                          "fontWeight": "bold", "color": TEXT, "marginRight": "12px"}),
                html.Span(f"${spot:.2f}" if spot else "—", style={"fontSize": "16px",
                          "color": TEXT, "fontFamily": "monospace", "marginRight": "12px"}),
                html.Span(badge_text, style={"background": badge_bg, "color": BG_DARK,
                          "padding": "2px 8px", "borderRadius": "10px",
                          "fontSize": "10px", "fontWeight": "bold",
                          "marginRight": "12px"}),
                html.Span("● LIVE", style={"color": ACCENT, "fontSize": "10px",
                          "float": "right"}),
            ], style={"padding": "8px 12px", "background": BG_CARD,
                     "borderBottom": f"1px solid {BG_PLOT}", "marginBottom": "8px"})
        ```

  S3.3  Modify the `tab == "heatseeker"` branch in render_tab. Find the
        existing branch (around line 1297-1325) and replace its return
        statement with:

        ```python
            if tab == "heatseeker":
                spot = chain_data.get("spot", 0) if isinstance(chain_data, dict) else 0
                contracts = chain_data.get("contracts", []) if isinstance(chain_data, dict) else []
                ticker = chain_data.get("ticker", "SPY") if isinstance(chain_data, dict) else "SPY"

                expiry_dates = []
                if isinstance(chain_data, dict):
                    seen = set()
                    for c in chain_data.get("contracts", []):
                        exp = c.get("expiry", c.get("expiration", ""))
                        if exp and exp not in seen:
                            seen.add(exp)
                            expiry_dates.append(exp)
                    expiry_dates.sort()

                left_sidebar  = _build_heatseeker_toggles(expiry_dates=expiry_dates)
                right_sidebar = _build_heatseeker_right_sidebar(spot, contracts)
                header        = _build_heatseeker_header(spot, contracts, ticker)
                fig = _build_gex_heatmap(spot=spot, contracts=contracts, dark=dark)
                graph = dcc.Graph(id="heatseeker-graph", figure=fig,
                                  style={"height": "650px"}, config={"responsive": True})

                return html.Div([
                    header,
                    html.Div([
                        left_sidebar,
                        html.Div(graph, style={"flex": 1, "minWidth": "0"}),
                        right_sidebar,
                    ], style={"display": "flex", "flexDirection": "row",
                             "alignItems": "flex-start"}),
                ])
        ```

  S3.4  Smoke-test the import chain:
          python -c "from services.dash_ui import (_build_heatseeker_right_sidebar, _build_heatseeker_header); print('imports OK')"
        EXPECT: "imports OK".

  S3.5  Run full suite — no regressions:
          python -m pytest -q --tb=no --ignore=tests/e2e --ignore=tests/services/ml 2>&1 | tail -3

  S3.6  Commit + push:
          git add backend/services/dash_ui.py
          git commit -m "feat(heatseeker-ui): assemble 3-column layout (header + L sidebar + graph + R sidebar)

          Verification:
            \$ grep -c '_build_heatseeker_right_sidebar\\|_build_heatseeker_header' backend/services/dash_ui.py
            <expect ≥ 3>
            \$ grep 'minHeight\\|maxHeight\\|overflowY' backend/services/dash_ui.py | wc -l
            <expect ≥ 1>

          Co-Authored-By: Hermes <hermes@floww.dev>"
          git pull --rebase origin main
          git push origin main

  PRINT "PHASE 3 COMPLETE — 3-column layout assembled and pushed — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 4 — HUMAN VISUAL GATE (BLOCKS — DO NOT PROCEED WITHOUT APPROVAL)
═══════════════════════════════════════════════════════════════════════════════

  S4.1  Start uvicorn:
          cd /Users/nav/Documents/GitHub/floww/backend
          source .venv/bin/activate
          nohup uvicorn server:app --port 8000 > /tmp/uvicorn_hermes_b.log 2>&1 &
          sleep 8

  S4.2  Smoke-test:
          curl -s -o /dev/null -w "dashboard: %{http_code}\n" http://localhost:8000/dashboard/
          curl -s -o /dev/null -w "chain SPY:  %{http_code}\n" http://localhost:8000/api/chain/SPY
        EXPECT both 200 (chain may be 429 if rate-limited — that's OK).

  S4.3  Post the visual verification request to the user:

          ══════════════════════════════════════════════════════════════════
          HUMAN VISUAL VERIFICATION REQUIRED — open your Chrome decoder app

          1. Open the Confluence Decoder PWA (or http://localhost:8000/dashboard/)
          2. Click the Heatseeker tab (or press "1")
          3. Confirm you see ALL of:
             ✓ HEADER strip: SPY | \$<price> | POSITIVE/NEGATIVE/NEUTRAL Γ badge | ● LIVE
             ✓ LEFT sidebar (existing): 5 toggle groups
                                         (VIEW / MODE / INDICATOR / DTE / EXPIRIES)
             ✓ CENTER: heatmap (strikes × expiries, teal/purple/yellow-green)
             ✓ RIGHT sidebar (new — 9 panels stacked vertically):
                MORNING BRIEFING — colored dot + label + ratio
                KEY LEVELS — 5 rows (Gamma Flip / Call Wall / Put Wall / Max Pain / Spot)
                STRATEGY — em-dash placeholder
                POSITION SIZING — Kelly placeholder
                RISK LEVELS — 2×2 grid (R1/R2 red, S1/S2 green)
                PRE-MARKET CHECKLIST — 8 checkboxes (persists across reload)
                FLIP ZONES — colored bullets with %distance from spot
                STACKED NODES — top 4 strikes with call/put split bars
                TUG-OF-WAR — single horizontal bar + dollar totals
          4. Confirm NO horizontal scrollbar at 1440px viewport width
          5. Reply with one of:
                "LOOKS GOOD"   → I'll proceed to Phase 5 (close server, push final report)
                "PANEL X IS WRONG: <what's wrong>"  → I'll halt and ask for guidance
          ══════════════════════════════════════════════════════════════════

  S4.4  BLOCK. Wait for human reply. Do not invent visual changes.

        - On "LOOKS GOOD": kill %1 ; sleep 1 ; PROCEED.
        - On any other reply: HALT with the user's complaint verbatim.
          Write a kanban blocker card. Wait for guidance.

  PRINT "PHASE 4 COMPLETE — human approved layout — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 5 — CLOSURE: COMPLETION LOG + KANBAN UPDATE + FINAL PUSH
═══════════════════════════════════════════════════════════════════════════════

  S5.1  Append closure note to docs/ROUND7_COMPLETION_LOG.md:

          cat >> docs/ROUND7_COMPLETION_LOG.md <<EOF

          ## Hermes Prompt B closure — $(date -u +%Y-%m-%dT%H:%M:%SZ)

          | Phase | Acceptance | Commit |
          |-------|------------|--------|
          | 1 | 8 TDD tests RED | $(git log --pretty=%h --grep="failing TDD" -1) |
          | 2 | 8 compute helpers GREEN | $(git log --pretty=%h --grep="8 NaN-safe right-sidebar" -1) |
          | 3 | 3-column layout assembled | $(git log --pretty=%h --grep="assemble 3-column" -1) |
          | 4 | Human visual gate: LOOKS GOOD | — |

          Net change: dash_ui.py +~400 lines, +1 test file (8 tests), 0 regressions.
          Final HEAD: $(git rev-parse HEAD)

          Co-Authored-By: Hermes <hermes@floww.dev>
          EOF

  S5.2  Wait — DO NOT commit ROUND7_COMPLETION_LOG.md here. DeepSeek Prompt A
        owns that file. Instead, write your closure to a dedicated card:

          cat > kanban/cards/hermes_prompt_b_$(date +%Y-%m-%d).md <<EOF
          ---
          id: hermes-prompt-b-$(date +%Y-%m-%d)
          title: "Hermes Prompt B — Heatseeker UI completion"
          status: done
          assignee: hermes-prompt-b
          acceptance: |
            8 TDD tests RED → GREEN; 3-column layout assembled; human visual gate passed.
          files_owned:
            - backend/services/dash_ui.py
            - backend/tests/services/test_dash_ui_three_column.py
          ---

          ## Commits

          $(git log --pretty="- %h %s" --grep="heatseeker-ui" --since="2 hours ago")

          ## Verification

          \`\`\`
          $ python -m pytest tests/services/test_dash_ui_three_column.py 2>&1 | tail -1
          === 8 passed in 0.Ns ===
          $ grep -c '_build_heatseeker_right_sidebar\\|_build_heatseeker_header\\|_compute_gamma_regime' backend/services/dash_ui.py
          <expect ≥ 5>
          \`\`\`
          EOF

          git add kanban/cards/hermes_prompt_b_*.md
          git commit -m "chore(round-7): hermes prompt B closure card

          Co-Authored-By: Hermes <hermes@floww.dev>"
          git pull --rebase origin main
          git push origin main

  S5.3  Print final report:

          ──── HERMES PROMPT B COMPLETE ────
          Start HEAD:        $(cat /tmp/hermes_b_start.txt)
          Final HEAD:        $(git rev-parse HEAD)
          Commits added:     <count>
          Files modified:    backend/services/dash_ui.py (+~400 lines)
          New tests:         8 unit tests in test_dash_ui_three_column.py
          Layout:            3-column (left sidebar + center graph + right sidebar)
          New panels:        9 right-sidebar panels + header strip
          Cell tags:         KING/FLOOR/CEIL/GATE/AIR computed (rendering deferred)
          Test delta:        0 regressions (baseline maintained)
          Visual gate:       human-approved
          Kanban card:       kanban/cards/hermes_prompt_b_$(date +%Y-%m-%d).md
          Backup branch:     backup/hermes-b-YYYYMMDD-HHMMSS
          ─────────────────────────────────

  Final line: "DONE"

═══════════════════════════════════════════════════════════════════════════════
KNOWN-DEFERRED ITEMS (DO NOT IMPLEMENT)
═══════════════════════════════════════════════════════════════════════════════

  - Wiring STRATEGY panel to a recommendation engine: deferred to Round 8.
  - Wiring POSITION SIZING live equity input: needs account integration.
  - Wiring MORNING BRIEFING to live /api/briefing (async callback):
    client-side derivation from chain payload is sufficient for now.
  - Cell-tag rendering as Plotly annotations: helpers exist; rendering
    on heatmap is a separate Plotly challenge for Round 8.
  - TOP MOVERS panel in LEFT sidebar: depends on snapshot_chain.py
    running ≥ 2 times; UI hookup deferred.
  - VIEW toggle Bars / Chain modes: still "Coming Soon" — deferred.

If you find yourself starting any of these: HALT. Out of scope.

═══════════════════════════════════════════════════════════════════════════════
ANTI-DRIFT REMINDERS
═══════════════════════════════════════════════════════════════════════════════

  - You touch ONE file (dash_ui.py) + ONE new test file. Nothing else.
  - 9 other tabs are SACRED — do not change them.
  - Theme constants are immutable.
  - Every commit message claim is grep-verifiable.
  - Phone-hotspot tolerance: API failures render "—", never crash.
  - Phase 4 BLOCKS on human confirmation. Do not invent visual changes
    while waiting for the user to look at the Chrome PWA.
  - Round 7 is recovery + finishing, not a new feature round.

END OF PROMPT. INVOKE superpowers:test-driven-development, THEN BEGIN AT PHASE 0.
═══════════════════════════════════════════════════════════════════════════════
