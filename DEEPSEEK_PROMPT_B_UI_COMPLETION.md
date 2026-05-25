# DeepSeek Prompt B — Dash UI Completion (Right Sidebar + Cell Tags + Header)

> **HOW TO USE:** Copy everything below the first `═══` line. Paste into DeepSeek agent B.
>
> **OWNED FILE:** `backend/services/dash_ui.py` — and ONLY this file. Will NOT touch any test file, route file, or other service. Prompt A (running in parallel) handles those.
>
> **CAN RUN IN PARALLEL WITH:** Prompt A (backend stabilization). No file overlap.

═══════════════════════════════════════════════════════════════════════════════

You are a senior Dash/Plotly UI engineer with PhD-level rigor (Stanford CS,
strong information-design background). You own ONE file:
`/Users/nav/Documents/GitHub/floww/backend/services/dash_ui.py`. That is your
universe for this session. A second agent (Prompt A) is concurrently doing
backend test stabilization in different files — DO NOT touch their files
even if you see something "wrong."

═══════════════════════════════════════════════════════════════════════════════
CONTEXT — WHAT EXISTS, WHAT'S MISSING
═══════════════════════════════════════════════════════════════════════════════

The Confluence Decoder Terminal at http://localhost:8000/dashboard/ is a
Dash + Plotly + dash-bootstrap-components app served via FastAPI WSGI
middleware. It has 10 tabs (Heatseeker, Flowseeker, Toxicity, Vol Surface,
Trinity, Atlas, Replay, Agent Hub, Nexus, Greeks Exposure). LEAVE ALL 10
TABS AS THEY ARE EXCEPT THE HEATSEEKER TAB.

CURRENT Heatseeker tab structure (verified by grep, NOT trusting any
handoff document — DeepSeek has a history of fabricating "completed" docs):

  html.Div([
      html.Div([
          sidebar,                  # _build_heatseeker_toggles() — EXISTS
          html.Div(graph, style={"flex": 1}),
      ], style={"display": "flex", "flexDirection": "row"}),
  ])

That is a TWO-COLUMN layout: left sidebar (5 toggle groups) + center
heatmap graph. There is NO RIGHT SIDEBAR. There is NO HEADER STRIP. There
are NO CELL TAGS (KING/FLOOR/CEIL/GATE/AIR badges next to strike rows).

Your job: add those three things. Convert to a 3-column layout. Do not
touch anything else.

The user already has DASH/Plotly + dash-bootstrap-components installed.
Imports at the top of dash_ui.py already include `html`, `dcc`, `dbc`,
`go`. Use them. Do NOT import React, htmx, Vue, or anything else.

Backend endpoints you may call from within Dash callbacks (use
`httpx.AsyncClient(base_url="http://localhost:8000")` or `requests`):

  GET /api/chain/{ticker}                       — full chain (already used)
  GET /api/briefing/{ticker}                    — Morning Briefing engine
  GET /api/position-sizing?equity=N&win_prob=…  — Kelly calculator
  GET /api/heatseeker/top-movers/{ticker}       — TOP MOVERS delta
  GET /api/heatseeker/history/{ticker}          — HISTORY snapshots

If any of these returns 404 during your work, the corresponding panel
should render a "—" placeholder, NOT crash.

═══════════════════════════════════════════════════════════════════════════════
CRITICAL OPERATING RULES — VIOLATE ANY = P0 INCIDENT
═══════════════════════════════════════════════════════════════════════════════

  R1. Verify canonical clone: `pwd && git remote -v` must show
      /Users/nav/Documents/GitHub/floww and JattMoosewala5911/floww.
      Else HALT WRONG_CLONE.

  R2. NEVER --abort | --reset --hard | --checkout . | --restore . |
      --clean -fd | --push --force | --no-verify | --no-gpg-sign.

  R3. THE ONLY FILE YOU MAY MODIFY is
      backend/services/dash_ui.py
      Plus you may create ONE test file:
      backend/tests/services/test_dash_ui_three_column.py
      Touching ANY other file: HALT.

  R4. Touch only the Heatseeker tab section of dash_ui.py. The render_tab
      function has branches for `tab == "heatseeker"`, `tab == "flowseeker"`,
      etc. You may modify ONLY the heatseeker branch and add new helper
      functions. Do NOT change flowseeker, toxicity, vol, trinity, atlas,
      replay, agent-hub, nexus, or greeks branches.

  R5. Theme constants are IMMUTABLE. Use these exact strings from existing
      dash_ui.py constants (do not redefine):
        BG_DARK   = "#0a0a1a"
        BG_CARD   = "#1a1a2e"
        BG_PLOT   = "#16213e"
        ACCENT    = "#00ff88"   (positive gamma, live indicator)
        WARN      = "#ffaa00"   (caution, KING tag)
        DANGER    = "#ff4444"   (negative gamma, CEIL tag)
        TEXT      = "#e0e0e0"

  R6. Halt format:
        ──── HALT REPORT ────
        Phase: <n>  Step: <n.n>  Reason: <one sentence>
        Diagnostic (verbatim):
        <output>
        Question for human: <yes/no or A/B>
        ─────────────────────

  R7. Every numeric computation: NaN-safe. Use `math.isfinite()` on every
      float before comparison or aggregation. Round 5 had silent failures
      because NaN comparisons return False.

  R8. The user is on phone hotspot; live API calls may fail. Every panel
      that fetches from /api/* must handle 404/500/timeout by rendering
      a "—" placeholder, never crashing the whole layout.

  R9. DeepSeek (you) tend to fabricate "completed handoff" docs. Defense:
      every commit message claim MUST be verifiable with `grep` against
      the actual file. Before claiming "added X", run
      `grep "X" backend/services/dash_ui.py` and include the output in
      your commit message or halt report.

  R10. The user has Chrome with the dashboard installed as a standalone
       app (PWA). After your changes land, the user will reload Chrome
       and visually verify. Make sure the layout doesn't horizontally
       overflow at 1440px viewport width.

═══════════════════════════════════════════════════════════════════════════════
PHASE 0 — SAFETY GATE
═══════════════════════════════════════════════════════════════════════════════

  S0.1  pwd && git remote -v && git rev-parse HEAD > /tmp/prompt_b_start.txt
        cat /tmp/prompt_b_start.txt

  S0.2  ls .git/rebase-merge/ 2>&1
        EXPECT: "No such file or directory". Else HALT REBASE_IN_PROGRESS.

  S0.3  git pull --rebase origin main
        If conflict: HALT PULL_CONFLICT.

  S0.4  git branch backup/prompt-b-$(date +%Y%m%d-%H%M%S)
        git branch | grep backup/prompt-b

  S0.5  Verify the file you'll modify exists and has the expected shape:
          wc -l backend/services/dash_ui.py
          grep -n "_build_heatseeker_toggles\|def _build_gex_heatmap\|tab == \"heatseeker\"" backend/services/dash_ui.py | head -10

        EXPECT:
          - file > 1500 lines
          - _build_heatseeker_toggles function exists
          - _build_gex_heatmap function exists
          - render_tab has a `tab == "heatseeker"` branch

        Else: HALT — the assumptions in this prompt are wrong.

  PRINT "PHASE 0 COMPLETE — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 1 — ADD HELPER COMPUTATIONS (NaN-safe)
═══════════════════════════════════════════════════════════════════════════════

GOAL: Add 6 new compute helpers near the existing _build_heatseeker_toggles
function. Each takes (spot, contracts) and returns a JSON-serializable
value used by the right sidebar.

  S1.1  Locate insertion point — find the line number after the
        _build_heatseeker_toggles function ends (use the `def ` of the
        NEXT function as a marker):
          grep -n "^def " backend/services/dash_ui.py | head -15

  S1.2  Insert these 6 helpers just before the "render_tab" function (or
        wherever fits the existing pattern). Use Edit tool.

        ```python
        # ── Right-sidebar compute helpers (NaN-safe) ─────────────────────

        def _compute_gamma_regime(contracts):
            """Return ('BULLISH'|'BEARISH'|'NEUTRAL'|'UNKNOWN', dot_color, ratio)."""
            if not contracts:
                return ("UNKNOWN", "#666666", 0.0)
            net = sum(c.get("gex", 0) for c in contracts
                      if isinstance(c.get("gex"), (int, float)) and math.isfinite(c.get("gex")))
            total_abs = sum(abs(c.get("gex", 0)) for c in contracts
                            if isinstance(c.get("gex"), (int, float)) and math.isfinite(c.get("gex")))
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
            # Group by strike
            by_strike = {}
            for c in contracts:
                s = c.get("strike")
                if not isinstance(s, (int, float)) or not math.isfinite(s):
                    continue
                by_strike.setdefault(s, {"gex": 0.0, "call_oi": 0, "put_oi": 0})
                g = c.get("gex", 0)
                if isinstance(g, (int, float)) and math.isfinite(g):
                    by_strike[s]["gex"] += g
                oi = c.get("oi", 0) or 0
                if c.get("type") == "call":
                    by_strike[s]["call_oi"] += oi
                else:
                    by_strike[s]["put_oi"] += oi
            # Gamma flip = strike closest to where cum GEX crosses zero
            strikes_sorted = sorted(by_strike.keys())
            cum = 0.0
            prev_s = None
            for s in strikes_sorted:
                cum_new = cum + by_strike[s]["gex"]
                if prev_s is not None and cum * cum_new < 0:
                    out["gamma_flip"] = (prev_s + s) / 2
                    break
                cum = cum_new
                prev_s = s
            # Call wall = max call OI strike above spot
            calls_above = [(s, by_strike[s]["call_oi"]) for s in strikes_sorted if s > spot]
            if calls_above:
                out["call_wall"] = max(calls_above, key=lambda x: x[1])[0]
            # Put wall = max put OI strike below spot
            puts_below = [(s, by_strike[s]["put_oi"]) for s in strikes_sorted if s < spot]
            if puts_below:
                out["put_wall"] = max(puts_below, key=lambda x: x[1])[0]
            # Max pain = strike minimizing total option payoff
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
            """Return {R1, R2, S1, S2} as price levels.
            Uses ±0.5% and ±1.0% from spot. TODO: derive from ATR or IV."""
            if not spot or not math.isfinite(spot):
                return {"R1": None, "R2": None, "S1": None, "S2": None}
            return {
                "R1": round(spot * 1.005, 2),
                "R2": round(spot * 1.010, 2),
                "S1": round(spot * 0.995, 2),
                "S2": round(spot * 0.990, 2),
            }

        def _compute_flip_zones(spot, contracts):
            """Return list of (label, strike, pct_distance) for each flip type."""
            if not contracts or not spot:
                return []
            zones = []
            klv = _compute_key_levels(spot, contracts)
            for label, val in [("GEX Flip", klv["gamma_flip"]),
                               ("Max Pain", klv["max_pain"])]:
                if val is not None and math.isfinite(val):
                    pct = (val - spot) / spot * 100
                    zones.append((label, val, pct))
            return zones

        def _compute_stacked_nodes(contracts, top_n=4):
            """Return top N strikes by combined OI, with call/put share."""
            if not contracts:
                return []
            by_strike = {}
            for c in contracts:
                s = c.get("strike")
                if not isinstance(s, (int, float)) or not math.isfinite(s):
                    continue
                by_strike.setdefault(s, {"call_oi": 0, "put_oi": 0})
                oi = c.get("oi", 0) or 0
                if c.get("type") == "call":
                    by_strike[s]["call_oi"] += oi
                else:
                    by_strike[s]["put_oi"] += oi
            nodes = []
            for s, d in by_strike.items():
                total = d["call_oi"] + d["put_oi"]
                if total > 0:
                    nodes.append({
                        "strike": s,
                        "call_pct": d["call_oi"] / total * 100,
                        "put_pct": d["put_oi"] / total * 100,
                        "total_oi": total,
                    })
            nodes.sort(key=lambda n: n["total_oi"], reverse=True)
            return nodes[:top_n]

        def _compute_tug_of_war(contracts):
            """Return (pos_gex_total, neg_gex_total) in dollars."""
            if not contracts:
                return (0.0, 0.0)
            pos = sum(c.get("gex", 0) for c in contracts
                      if isinstance(c.get("gex"), (int, float))
                      and math.isfinite(c.get("gex")) and c.get("gex") > 0)
            neg = sum(c.get("gex", 0) for c in contracts
                      if isinstance(c.get("gex"), (int, float))
                      and math.isfinite(c.get("gex")) and c.get("gex") < 0)
            return (pos, neg)

        def _compute_cell_tags(spot, contracts):
            """Return dict: strike → list of tag labels (KING/FLOOR/CEIL/GATE/AIR)."""
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
            # KING = max |gex|
            king = max(by_strike, key=lambda s: abs(by_strike[s]))
            tags[king].append("KING")
            # FLOOR = top 3 positive below spot
            positives = sorted([s for s in by_strike if by_strike[s] > 0 and s <= spot],
                               key=lambda s: by_strike[s], reverse=True)[:3]
            for s in positives:
                tags[s].append("FLOOR")
            # CEIL = top 3 negative above spot
            negatives = sorted([s for s in by_strike if by_strike[s] < 0 and s >= spot],
                               key=lambda s: by_strike[s])[:3]
            for s in negatives:
                tags[s].append("CEIL")
            # GATE = exceeds 10% threshold (gatekeepers)
            for s, g in by_strike.items():
                if abs(g) / total_abs > 0.10 and "KING" not in tags[s]:
                    tags[s].append("GATE")
            # AIR = below 1% threshold
            for s, g in by_strike.items():
                if abs(g) / total_abs < 0.01:
                    tags[s].append("AIR")
            return {s: t for s, t in tags.items() if t}

        def _fmt_money(n):
            """Format dollar amounts: 1.5B, 473.2M, 52.3K."""
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

  S1.3  Verify the helpers parse correctly:
          python -c "from services.dash_ui import _compute_gamma_regime, _compute_key_levels, _compute_risk_levels, _compute_flip_zones, _compute_stacked_nodes, _compute_tug_of_war, _compute_cell_tags, _fmt_money; print('imports OK')"

        EXPECT: "imports OK". Else HALT.

  S1.4  Commit:
          git add backend/services/dash_ui.py
          git commit -m "feat(heatseeker-ui): add 8 right-sidebar compute helpers (NaN-safe)"

  PRINT "PHASE 1 COMPLETE — 8 helpers added — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 2 — ADD RIGHT SIDEBAR + HEADER STRIP + CELL TAGS
═══════════════════════════════════════════════════════════════════════════════

  S2.1  Add a new function `_build_heatseeker_right_sidebar(spot, contracts)`
        right after the existing `_build_heatseeker_toggles` function.
        Returns an html.Div with the 9 panels stacked vertically.

        Use this exact code (verbatim):

        ```python
        def _build_heatseeker_right_sidebar(spot, contracts):
            """Build the right sidebar with 9 analytics panels."""
            regime, dot_color, ratio = _compute_gamma_regime(contracts)
            klv = _compute_key_levels(spot, contracts)
            risk = _compute_risk_levels(spot, contracts)
            zones = _compute_flip_zones(spot, contracts)
            stacked = _compute_stacked_nodes(contracts)
            pos_gex, neg_gex = _compute_tug_of_war(contracts)

            def panel(title, children):
                return html.Div([
                    html.Div(title, style={
                        "color": ACCENT, "fontSize": "10px", "fontWeight": "bold",
                        "letterSpacing": "1px", "marginBottom": "4px"}),
                    html.Div(children, style={"fontSize": "11px", "color": TEXT}),
                ], style={
                    "background": BG_CARD, "padding": "8px 10px", "marginBottom": "6px",
                    "borderRadius": "4px", "border": f"1px solid {BG_PLOT}"})

            def kv_row(label, value):
                return html.Div([
                    html.Span(label, style={"color": "#888", "fontSize": "10px"}),
                    html.Span(str(value) if value is not None else "—",
                             style={"color": TEXT, "float": "right", "fontFamily": "monospace"}),
                ], style={"marginBottom": "2px"})

            # 1. MORNING BRIEFING
            briefing = panel("MORNING BRIEFING", html.Div([
                html.Span("●", style={"color": dot_color, "marginRight": "6px", "fontSize": "14px"}),
                html.Span(regime, style={"fontWeight": "bold"}),
                html.Div(f"Net/|Total| GEX: {ratio:+.1%}" if ratio else "",
                         style={"color": "#888", "fontSize": "9px", "marginTop": "2px"}),
            ]))

            # 2. KEY LEVELS
            key_levels = panel("KEY LEVELS", html.Div([
                kv_row("Gamma Flip", klv["gamma_flip"]),
                kv_row("Call Wall", klv["call_wall"]),
                kv_row("Put Wall", klv["put_wall"]),
                kv_row("Max Pain", klv["max_pain"]),
                kv_row("Spot", spot),
            ]))

            # 3. STRATEGY (placeholder)
            strategy = panel("STRATEGY", html.Div("—", style={"color": "#666"}))

            # 4. POSITION SIZING (placeholder)
            sizing = panel("POSITION SIZING", html.Div([
                html.Div("Kelly: —", style={"color": "#888", "fontSize": "10px"}),
            ]))

            # 5. RISK LEVELS
            risk_panel = panel("RISK LEVELS", html.Div([
                html.Table([
                    html.Tr([
                        html.Td(f"R1 {risk['R1'] or '—'}", style={"padding": "2px 6px", "color": DANGER}),
                        html.Td(f"R2 {risk['R2'] or '—'}", style={"padding": "2px 6px", "color": DANGER}),
                    ]),
                    html.Tr([
                        html.Td(f"S1 {risk['S1'] or '—'}", style={"padding": "2px 6px", "color": ACCENT}),
                        html.Td(f"S2 {risk['S2'] or '—'}", style={"padding": "2px 6px", "color": ACCENT}),
                    ]),
                ], style={"width": "100%", "fontFamily": "monospace", "fontSize": "10px"}),
            ]))

            # 6. PRE-MARKET CHECKLIST
            checklist = panel("PRE-MARKET CHECKLIST", dcc.Checklist(
                id="heatseeker-checklist",
                options=[
                    {"label": " GEX regime identified", "value": "regime"},
                    {"label": " Gamma flip noted", "value": "flip"},
                    {"label": " Call/Put walls confirmed", "value": "walls"},
                    {"label": " Max pain identified", "value": "pain"},
                    {"label": " Strategy selected", "value": "strategy"},
                    {"label": " Position size calculated", "value": "size"},
                    {"label": " Stop loss set", "value": "stop"},
                    {"label": " Risk/reward ≥ 1:2", "value": "rr"},
                ],
                value=[],
                persistence=True,
                persistence_type="local",
                style={"color": TEXT, "fontSize": "10px"},
            ))

            # 7. FLIP ZONES
            flip_panel = panel("FLIP ZONES", html.Div([
                html.Div([
                    html.Span("● ", style={"color": ACCENT if pct < 0 else DANGER}),
                    html.Span(f"{label}: ", style={"color": "#888"}),
                    html.Span(f"{val:.1f} ({pct:+.2f}%)",
                             style={"color": TEXT, "fontFamily": "monospace"}),
                ], style={"marginBottom": "2px", "fontSize": "10px"})
                for label, val, pct in zones
            ]) if zones else html.Div("—", style={"color": "#666"}))

            # 8. STACKED NODES
            def node_bar(n):
                return html.Div([
                    html.Span(f"{int(n['strike'])} ", style={"color": TEXT,
                                                            "fontFamily": "monospace",
                                                            "fontSize": "10px"}),
                    html.Div([
                        html.Div(style={"width": f"{n['call_pct']:.0f}%",
                                       "background": ACCENT,
                                       "height": "6px", "display": "inline-block"}),
                        html.Div(style={"width": f"{n['put_pct']:.0f}%",
                                       "background": "#9933ff",
                                       "height": "6px", "display": "inline-block"}),
                    ], style={"width": "60%", "display": "inline-block", "marginLeft": "4px"}),
                    html.Span(f" {n['call_pct']:.0f}/{n['put_pct']:.0f}",
                             style={"color": "#888", "fontSize": "9px", "marginLeft": "4px"}),
                ], style={"marginBottom": "3px"})
            stacked_panel = panel("STACKED NODES",
                                  html.Div([node_bar(n) for n in stacked])
                                  if stacked else html.Div("—", style={"color": "#666"}))

            # 9. TUG-OF-WAR
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

            return html.Div([
                briefing, key_levels, strategy, sizing, risk_panel,
                checklist, flip_panel, stacked_panel, tug_panel,
            ], style={"width": "280px", "padding": "8px", "overflowY": "auto",
                     "maxHeight": "calc(100vh - 100px)"})
        ```

  S2.2  Add a new function `_build_heatseeker_header(spot, contracts, ticker)`
        right after the right sidebar function:

        ```python
        def _build_heatseeker_header(spot, contracts, ticker):
            """Build header strip: ticker | price | regime badge | LIVE."""
            regime, dot_color, ratio = _compute_gamma_regime(contracts)
            badge_text = f"POSITIVE Γ" if regime == "BULLISH" else \
                         f"NEGATIVE Γ" if regime == "BEARISH" else \
                         f"NEUTRAL Γ" if regime == "NEUTRAL" else "UNKNOWN Γ"
            badge_bg = ACCENT if regime == "BULLISH" else \
                       DANGER if regime == "BEARISH" else \
                       WARN if regime == "NEUTRAL" else "#666"
            return html.Div([
                html.Span(ticker.upper(), style={
                    "fontSize": "20px", "fontWeight": "bold", "color": TEXT,
                    "marginRight": "12px"}),
                html.Span(f"${spot:.2f}" if spot else "—", style={
                    "fontSize": "16px", "color": TEXT, "fontFamily": "monospace",
                    "marginRight": "12px"}),
                html.Span(badge_text, style={
                    "background": badge_bg, "color": BG_DARK, "padding": "2px 8px",
                    "borderRadius": "10px", "fontSize": "10px", "fontWeight": "bold",
                    "marginRight": "12px"}),
                html.Span("● LIVE", style={
                    "color": ACCENT, "fontSize": "10px", "float": "right"}),
            ], style={"padding": "8px 12px", "background": BG_CARD,
                     "borderBottom": f"1px solid {BG_PLOT}", "marginBottom": "8px"})
        ```

  S2.3  Modify the `tab == "heatseeker"` branch in `render_tab` to assemble
        the three-column layout. Use the Edit tool to find the existing
        branch (approximately around line 1297-1325) and replace its
        return statement with:

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

                left_sidebar = _build_heatseeker_toggles(expiry_dates=expiry_dates)
                right_sidebar = _build_heatseeker_right_sidebar(spot, contracts)
                header = _build_heatseeker_header(spot, contracts, ticker)
                fig = _build_gex_heatmap(spot=spot, contracts=contracts, dark=dark)
                graph = dcc.Graph(
                    id="heatseeker-graph",
                    figure=fig,
                    style={"height": "650px"},
                    config={"responsive": True},
                )

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

  S2.4  Verify the layout assembles:
          python -c "from services.dash_ui import _build_heatseeker_right_sidebar, _build_heatseeker_header; print('layout OK')"

        EXPECT: "layout OK". Else HALT.

  S2.5  Commit:
          git add backend/services/dash_ui.py
          git commit -m "feat(heatseeker-ui): add right sidebar (9 panels) + header strip + 3-column layout"

  PRINT "PHASE 2 COMPLETE — 3-column layout assembled — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 3 — VISUAL VERIFICATION (USER HAS CHROME PWA INSTALLED)
═══════════════════════════════════════════════════════════════════════════════

  S3.1  Start uvicorn in background:
          cd /Users/nav/Documents/GitHub/floww/backend
          source .venv/bin/activate
          nohup uvicorn server:app --port 8000 > /tmp/uvicorn_b.log 2>&1 &
          sleep 8

  S3.2  Smoke-test the dashboard route:
          curl -s -o /dev/null -w "dashboard: %{http_code}\n" http://localhost:8000/dashboard/
        EXPECT: 200. Else: tail -50 /tmp/uvicorn_b.log and HALT.

  S3.3  Smoke-test chain endpoint (this proves the heatseeker tab will
        have data to render):
          curl -s -o /dev/null -w "chain: %{http_code}\n" http://localhost:8000/api/chain/SPY
        Acceptable: 200 (live data), 429 (rate-limited), or 503 (network
        unavailable). HALT only on 404 or 500.

  S3.4  Print instructions for the human to visually verify:
          echo ""
          echo "════════════════════════════════════════════════════"
          echo "MANUAL VERIFICATION — open the Chrome decoder app:"
          echo "  1. Navigate to http://localhost:8000/dashboard/"
          echo "  2. Click the Heatseeker tab (or press '1')"
          echo "  3. CONFIRM you see:"
          echo "     - HEADER strip at top: SPY | \$<price> | POSITIVE/NEGATIVE Γ badge | LIVE"
          echo "     - LEFT sidebar with 5 toggle groups (VIEW/MODE/INDICATOR/DTE/EXPIRIES)"
          echo "     - CENTER heatmap (strikes × expiries, teal/purple colors)"
          echo "     - RIGHT sidebar with 9 panels: BRIEFING, KEY LEVELS, STRATEGY,"
          echo "       POSITION SIZING, RISK LEVELS, CHECKLIST (8 items), FLIP ZONES,"
          echo "       STACKED NODES, TUG-OF-WAR"
          echo "  4. CONFIRM no horizontal scrollbar at 1440px viewport width"
          echo "  5. Reply 'LOOKS GOOD' or paste a screenshot if anything's off"
          echo "════════════════════════════════════════════════════"

  S3.5  Wait for the human's confirmation BEFORE Phase 4.

        If human reports issues → HALT with their feedback. Do not "fix"
        layout problems creatively; ask which specific visual element
        is wrong and how it should appear.

        If human approves → kill the server:
          kill %1
          sleep 1

  PRINT "PHASE 3 COMPLETE — human approved visual — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 4 — UNIT TEST FOR LAYOUT
═══════════════════════════════════════════════════════════════════════════════

  S4.1  Create backend/tests/services/test_dash_ui_three_column.py:

        ```python
        """Unit test for the Heatseeker three-column layout."""
        from unittest.mock import patch, MagicMock
        import pytest

        SAMPLE_CONTRACTS = [
            {"strike": 740, "gex":  3e8, "oi": 5000, "type": "call", "expiry": "2026-06-20"},
            {"strike": 745, "gex":  5e8, "oi": 8000, "type": "call", "expiry": "2026-06-20"},
            {"strike": 750, "gex":  1e8, "oi": 9000, "type": "call", "expiry": "2026-06-20"},
            {"strike": 755, "gex": -2e8, "oi": 4000, "type": "put",  "expiry": "2026-06-20"},
            {"strike": 760, "gex": -4e8, "oi": 6000, "type": "put",  "expiry": "2026-06-20"},
        ]
        SPOT = 748.0

        def test_gamma_regime_bullish_when_net_positive():
            from services.dash_ui import _compute_gamma_regime
            regime, color, ratio = _compute_gamma_regime(SAMPLE_CONTRACTS)
            assert regime in ("BULLISH", "NEUTRAL", "BEARISH", "UNKNOWN")
            assert color in ("#00ff88", "#ff4444", "#ffaa00", "#666666")

        def test_key_levels_returns_all_keys():
            from services.dash_ui import _compute_key_levels
            klv = _compute_key_levels(SPOT, SAMPLE_CONTRACTS)
            assert set(klv.keys()) == {"gamma_flip", "call_wall", "put_wall", "max_pain", "spot"}
            assert klv["spot"] == SPOT

        def test_risk_levels_returns_4_levels():
            from services.dash_ui import _compute_risk_levels
            risk = _compute_risk_levels(SPOT, SAMPLE_CONTRACTS)
            assert set(risk.keys()) == {"R1", "R2", "S1", "S2"}

        def test_stacked_nodes_returns_top_n():
            from services.dash_ui import _compute_stacked_nodes
            nodes = _compute_stacked_nodes(SAMPLE_CONTRACTS, top_n=3)
            assert len(nodes) <= 3
            for n in nodes:
                assert {"strike", "call_pct", "put_pct", "total_oi"} == set(n.keys())

        def test_cell_tags_includes_king():
            from services.dash_ui import _compute_cell_tags
            tags = _compute_cell_tags(SPOT, SAMPLE_CONTRACTS)
            assert any("KING" in t for t in tags.values())

        def test_handles_empty_contracts():
            from services.dash_ui import (_compute_gamma_regime, _compute_key_levels,
                                          _compute_stacked_nodes, _compute_cell_tags)
            assert _compute_gamma_regime([])[0] == "UNKNOWN"
            assert _compute_key_levels(SPOT, [])["spot"] == SPOT
            assert _compute_stacked_nodes([]) == []
            assert _compute_cell_tags(SPOT, []) == {}

        def test_handles_nan_gex():
            from services.dash_ui import _compute_gamma_regime
            contracts = [{"strike": 745, "gex": float("nan"), "oi": 1000, "type": "call"}]
            regime, _, _ = _compute_gamma_regime(contracts)
            assert regime == "UNKNOWN"  # NaN filtered out

        def test_fmt_money_handles_edge_cases():
            from services.dash_ui import _fmt_money
            assert _fmt_money(1_500_000_000) == "$1.50B"
            assert _fmt_money(473_200_000) == "$473.2M"
            assert _fmt_money(float("nan")) == "—"
            assert _fmt_money(None) == "—"
        ```

  S4.2  Run the new test:
          cd backend && source .venv/bin/activate
          python -m pytest tests/services/test_dash_ui_three_column.py -v 2>&1 | tail -15

        EXPECT: 8 passed. Else HALT with the failing test name.

  S4.3  Commit:
          git add backend/tests/services/test_dash_ui_three_column.py
          git commit -m "test(heatseeker-ui): unit test for 8 compute helpers + NaN safety"

  PRINT "PHASE 4 COMPLETE — 8/8 tests pass — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 5 — FULL SUITE REGRESSION CHECK + PUSH
═══════════════════════════════════════════════════════════════════════════════

  S5.1  Run full suite (excluding e2e and ml since Prompt A may still be
        gating those):
          python -m pytest -q --tb=no --ignore=tests/e2e --ignore=tests/services/ml 2>&1 | tail -5

        EXPECT failure count to NOT have increased vs the pre-Prompt-B
        count. The user told us pre-Prompt-B count was ~1.

        If new failures appeared: HALT with the failure names. You
        introduced a regression — investigate before pushing.

  S5.2  Push:
          git pull --rebase origin main   # in case Prompt A pushed first
          git push origin main

        If conflict on pull (Prompt A pushed dash_ui.py changes — should
        not happen since Prompt A doesn't own that file): HALT
        FILE_OWNERSHIP_VIOLATION.

  S5.3  Print final report:
          ──── PROMPT B COMPLETE ────
          Start HEAD:        $(cat /tmp/prompt_b_start.txt)
          Final HEAD:        $(git rev-parse HEAD)
          Files modified:    backend/services/dash_ui.py + 1 new test file
          New helpers added: 8 compute + 2 builders + 1 header = 11 functions
          Layout:            3-column (left sidebar + center graph + right sidebar)
          Panels added:      9 right-sidebar panels + header strip
          Cell tags:         KING/FLOOR/CEIL/GATE/AIR computation (rendering deferred)
          New tests:         8 unit tests + Phase 3 visual confirmed
          Pushed:            yes
          Backup branch:     backup/prompt-b-YYYYMMDD-HHMMSS
          ──────────────────────────

  Final line: "DONE"

═══════════════════════════════════════════════════════════════════════════════
KNOWN-DEFERRED ITEMS (DO NOT IMPLEMENT IN THIS PROMPT)
═══════════════════════════════════════════════════════════════════════════════

  - Wiring STRATEGY panel to a recommendation engine: deferred to Round 8.
  - Wiring POSITION SIZING to live /api/position-sizing: deferred — needs
    user-account integration for equity input. The endpoint exists; the
    UI wiring needs design choices (where to ask for equity?).
  - Wiring MORNING BRIEFING to live /api/briefing: would require an async
    callback. For this round, derive briefing client-side from the chain
    payload (which is what _compute_gamma_regime already does).
  - Cell tags as Plotly annotations on heatmap: the `_compute_cell_tags`
    function computes them; rendering them ON the heatmap (vs in a side
    column) is a Plotly-specific challenge deferred to Round 8.
  - TOP MOVERS panel in left sidebar: deferred — Agent 3's snapshot store
    needs to be queried after the snapshot_chain.py script has run at
    least twice.
  - VIEW toggle Bars / Chain modes: still "Coming Soon" — deferred.

If you find yourself starting any of the above: HALT. Out of scope.

═══════════════════════════════════════════════════════════════════════════════
ANTI-DRIFT REMINDERS
═══════════════════════════════════════════════════════════════════════════════

  - You touch ONE file (plus the one test file). If you find yourself
    editing anything else, HALT.
  - Phases are sequential. Phase 3 visual verification BLOCKS on human
    input — do not invent visual changes while waiting.
  - Theme constants are immutable. No new colors.
  - Every commit message claim is verifiable via `grep` against the file.
  - You're on phone hotspot; API failures should render "—" not crash.
  - The other 9 tabs are sacred; do not touch them.

END OF PROMPT B. BEGIN AT PHASE 0 STEP S0.1.
═══════════════════════════════════════════════════════════════════════════════
