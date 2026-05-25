# Hermes Round 8 — Per-Agent Missions A through J

> **HOW TO USE:** Each section below is paste-able after the universal preamble
> in `HERMES_ROUND8_TEMPLATE.md`. So for Agent A, copy the template +
> the Agent A section. Same for B–J. Or paste both files concatenated.
>
> **All 10 agents WAIT until DeepSeek Phase 0 (proxy fix) confirms 200 JSON.**

═══════════════════════════════════════════════════════════════════════════════
AGENT A — App.js: toggles + Skylit ticker + Dashboard tab style
═══════════════════════════════════════════════════════════════════════════════

OWNED FILES:
  - frontend/src/App.js  (sole owner — no other agent touches this file)

FORBIDDEN (in addition to template's forbidden list):
  - any frontend/src/components/* file
  - any frontend/src/hooks/* file

MISSION:
  (1) Make the Heatseeker toggle groups COMPOSE correctly:
      - View (2D Grid / Bars / Chain) × Mode (DAY / SWING / SCALP)
      - × Indicator (GEX / VEX / CHARM) × DTE (0 / 1 / Week / All) × Expiries (2/4/6/8/12)
      Currently DAY+GEX works; DAY+CHARM doesn't switch the chart;
      DTE doesn't filter; Expiries doesn't change the fetched expiry count.
  (2) Add a TICKER DROPDOWN to the Skylit page (currently only SPY).
      Reuse `DEFAULT_TICKERS` from `./lib/helpers`.
  (3) Restyle the Dashboard tab — it currently embeds the Dash app via
      iframe with default browser styling that doesn't match the dark UI.
      Wrap the iframe in a `panel-2 p-3` container, set iframe `style`
      to match background `BG_DARK = #0a0a1a` and no border.

MISSION-SPECIFIC PHASES (after the template's Common Phase 0):

PHASE 1 — TOGGLE COMPOSITION

  S1.1  grep -n "viewMode\|setViewMode\|charm\|/api/chain" frontend/src/App.js | head -30
        Locate the data-fetch effect that fires when toggles change.
        Identify which toggle values are passed to the API and which are not.

  S1.2  Decide the canonical endpoint shape per toggle (read backend routes):
          - View `grid|bar`        → which client-side rendering component
          - View `chain`           → switches to OptionsChainTable (data source: /api/chain)
          - Mode `day|swing|scalp` → passed as `?mode=` (verify backend accepts; if not, document and fall back)
          - Indicator `gex|vex|charm` → switches WHICH chart renders, NOT the URL
          - DTE `0|1|week|all`     → passed as `?dte=` to /api/chain OR filtered client-side
          - Expiries `2|4|6|8|12`  → passed as `?expiries=N` to /api/chain
        Use `curl http://localhost:8000/api/chain/SPY?expiries=2` to validate.

  S1.3  Wire the missing axes:
          - useEffect deps must include [view, viewMode, mode, filters, expiriesCount]
          - URL building must include the params
          - Chart component selection must switch on viewMode (gex/vex/charm)
        Use Edit tool with targeted replacements; do not rewrite App.js.

  S1.4  Verify by toggling each combo in your browser if you can; else by
        printing the constructed URL via console.log temporarily, then
        remove the log.

  S1.5  Commit:
          git add frontend/src/App.js
          git commit -m "fix(heatseeker-toggles): compose view × mode × indicator × dte × expiries

          Before: $ grep -c 'dte\\|expiries\\|charm' frontend/src/App.js
                  <count>
          After:  Charm view switches chart; DTE param hits API; Expiries selector changes fetched count.

          Co-Authored-By: Hermes <hermes@floww.dev>"

PHASE 2 — SKYLIT TICKER DROPDOWN

  S2.1  Locate the Skylit page rendering block:
          grep -n 'page === "skylit"' frontend/src/App.js
        Currently passes `ticker={ticker}` which uses the global ticker.

  S2.2  Add a local Skylit ticker state + dropdown:
          // near other useState calls
          const [skylitTicker, setSkylitTicker] = useState(ticker);

          // inside the skylit page block, BEFORE <HeatseekerDashboard …>
          <div className="flex items-center gap-2 mb-3">
            <label className="label">Ticker:</label>
            <select
              value={skylitTicker}
              onChange={(e) => setSkylitTicker(e.target.value)}
              className="btn"
            >
              {DEFAULT_TICKERS.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>

          // change ticker prop to:
          <HeatseekerDashboard ticker={skylitTicker} …/>

PHASE 3 — DASHBOARD TAB STYLE

  S3.1  Locate dashboard page block:
          grep -n 'page === "dashboard"' frontend/src/App.js

  S3.2  Wrap the existing iframe (or add one if missing) inside a panel:
          {page === "dashboard" && (
            <div className="flex-1 overflow-auto p-3">
              <div className="panel-2 p-2">
                <iframe
                  src="http://localhost:8000/dashboard/"
                  title="Confluence Decoder Dash"
                  style={{
                    width: "100%",
                    height: "calc(100vh - 120px)",
                    border: "none",
                    background: "#0a0a1a",
                    borderRadius: "4px",
                  }}
                />
              </div>
            </div>
          )}

PHASE 4 — COMMIT + RUN COMMON CLOSURE

  S4.1  Commit Skylit + Dashboard changes (Phase 1's commit was separate):
          git add frontend/src/App.js
          git commit -m "feat(skylit,dashboard): ticker dropdown for Skylit + dark-themed Dashboard iframe

          Co-Authored-By: Hermes <hermes@floww.dev>"

  S4.2  Run Common Closure (Phase C from template).

ACCEPTANCE:
  - Each of 5 Heatseeker toggle axes changes what's rendered or fetched
  - Skylit page has ticker dropdown with ≥ 6 tickers
  - Dashboard tab iframe is wrapped in panel-2, no light-theme leakage

═══════════════════════════════════════════════════════════════════════════════
AGENT B — PaperTrade.jsx: null safety + form wiring
═══════════════════════════════════════════════════════════════════════════════

OWNED FILES:
  - frontend/src/components/PaperTrade.jsx
  - frontend/src/components/PaperTrade.test.jsx  (create new)

FORBIDDEN:
  - any other frontend/src/components/* file
  - any backend file

MISSION: PaperTrade crashes with `Cannot read properties of undefined (reading 'toFixed')`.
Root: `portfolio` is null when fetch fails; `portfolio.total_pnl_pct.toFixed(2)` blows up.
Fix every unguarded property access; add form submission; add re-fetch after submit.

PHASES:

  S1.1  Find every unguarded numeric access:
          grep -n "\\.toFixed\\|\\.toLocaleString" frontend/src/components/PaperTrade.jsx

  S1.2  Convert each to optional-chain + nullish-coalesce:
          OLD: portfolio.total_pnl_pct.toFixed(2)
          NEW: portfolio?.total_pnl_pct?.toFixed(2) ?? "—"
          OLD: spot.toFixed(0)
          NEW: spot?.toFixed(0) ?? "—"
        Apply uniformly.

  S2.1  Wire form submission. The form already collects fields (symbol,
        option_type, strike, expiry, quantity, is_long, entry_price).
        Find the submit handler (or add one):
          const handleSubmit = async (e) => {
            e.preventDefault();
            setLoading(true); setErr(null);
            try {
              await axios.post(`${API}/paper-trading/execute`, {
                symbol: form.symbol,
                option_type: form.option_type,
                strike: parseFloat(form.strike),
                expiry: form.expiry,
                quantity: parseInt(form.quantity),
                is_long: form.is_long,
                entry_price: parseFloat(form.entry_price) || undefined,
              });
              await fetchPortfolio();   // re-fetch
              setForm(f => ({ ...f, strike: "", expiry: "", entry_price: "" }));
            } catch (e) {
              setErr(e.response?.data?.detail ?? e.message);
            } finally {
              setLoading(false);
            }
          };

        Attach to the form's onSubmit.

  S3.1  Add a minimal test:
          // PaperTrade.test.jsx
          import { render } from "@testing-library/react";
          import PaperTrade from "./PaperTrade";

          test("does not crash when portfolio is null", () => {
            const { container } = render(<PaperTrade ticker="SPY" spot={null} />);
            expect(container).toBeTruthy();
          });

  S3.2  cd frontend && npm test -- --watchAll=false PaperTrade

  S4.1  Commit + run Common Closure.

ACCEPTANCE:
  - grep "\\.toFixed" PaperTrade.jsx | grep -v "?\\." returns 0
  - Form submission posts to /api/paper-trading/execute, re-fetches portfolio
  - Tab loads without React crash even when backend is unreachable

═══════════════════════════════════════════════════════════════════════════════
AGENT C — SidebarPanels.jsx: null-guard + dark-theme error states
═══════════════════════════════════════════════════════════════════════════════

OWNED FILES:
  - frontend/src/components/SidebarPanels.jsx

FORBIDDEN: any other component/hook file.

MISSION: panels FlipZonesPanel, StackedNodesPanel, TugOfWarPanel,
ScenarioPanel, RiskDashboardPanel, OpportunitiesPanel, ImpliedMovePanel,
VolAnalyticsPanel, GreekReferencePanel, UsagePanel, LivePolicyPanel.
Each renders error messages like "Vanna data unavailable — Unexpected token '<'".
After DeepSeek's proxy fix, the underlying error goes away, but you still
need to harden these panels so they show clean states.

PHASES:

  S1.1  grep -n "loading\\|error\\|data\\." frontend/src/components/SidebarPanels.jsx | head -40
        Identify each panel function and its render structure.

  S1.2  For each panel function, ensure:
          - if (loading) → show <Spinner /> or "Loading…" with `text-slate-500`
          - if (error) → show <ErrorBox message={…} /> with `text-rose-400`
          - if (!data || empty) → show "—" with `text-slate-500`
          - else → render normally

  S1.3  Add null-chains to all numeric accesses (same pattern as Agent B).

  S1.4  Define a tiny shared helper at top of file (no new imports):
          const dash = (v, fn) => (v == null ? "—" : (fn ? fn(v) : v));

  S2.1  Commit + Common Closure.

ACCEPTANCE:
  - Every panel handles loading / error / empty / data cleanly
  - No raw "Unexpected token" error message reaches the user
  - Dark theme classes (panel, label, mono, text-slate-*) used consistently

═══════════════════════════════════════════════════════════════════════════════
AGENT D — AdvancedAnalyticsPanel.jsx: same hardening
═══════════════════════════════════════════════════════════════════════════════

OWNED FILES:
  - frontend/src/components/AdvancedAnalyticsPanel.jsx

FORBIDDEN: any other component file.

MISSION: same pattern as Agent C for MarketRegimePanel, ImpliedPDFPanel,
HedgeImpulsePanel, PressureCloudPanel, CharmIntegralPanel.

PHASES: identical to Agent C — substitute file path.

ACCEPTANCE: identical to Agent C.

═══════════════════════════════════════════════════════════════════════════════
AGENT E — PortfolioPanel.jsx: scenarios + hedge button wiring
═══════════════════════════════════════════════════════════════════════════════

OWNED FILES:
  - frontend/src/components/PortfolioPanel.jsx

FORBIDDEN: backend files (read-only for endpoint discovery via curl), other component files.

MISSION: Portfolio scenarios + hedge buttons are currently dummy (no onClick
or onClick is a no-op). Wire them to real backend endpoints.

PHASES:

  S1.1  Locate the buttons:
          grep -n "scenario\\|hedge\\|onClick" frontend/src/components/PortfolioPanel.jsx | head -20

  S1.2  Discover available endpoints:
          curl -s http://localhost:8000/api/portfolio/scenarios 2>&1 | head -1
          curl -s "http://localhost:8000/api/portfolio/hedge?ticker=SPY" 2>&1 | head -1

        Two outcomes:
          A) Endpoint returns 200 with JSON  → wire to onClick that GETs and shows result
          B) Endpoint returns 404           → display "Coming Soon" in a tooltip;
             button shows a clear deferred state but doesn't crash

  S2.1  Implement the onClick handlers per outcome. Pattern:
          const [scenarioResult, setScenarioResult] = useState(null);
          const runScenario = async () => {
            try {
              const r = await axios.get(`${API}/portfolio/scenarios`);
              setScenarioResult(r.data);
            } catch (e) {
              setScenarioResult({ status: "deferred", note: "Endpoint not yet implemented" });
            }
          };

  S2.2  Render the result panel (or "Coming Soon" message) in the existing
        layout. Use dark theme classes.

  S3.1  Commit + Common Closure.

ACCEPTANCE:
  - Scenarios + Hedge buttons trigger fetches OR show clean deferred state
  - No silent failures or React crashes

═══════════════════════════════════════════════════════════════════════════════
AGENT F — heatseeker/*.jsx: 10 Wave panel components
═══════════════════════════════════════════════════════════════════════════════

OWNED FILES (10 panel components):
  - frontend/src/components/heatseeker/HeatseekerDashboard.jsx
  - frontend/src/components/heatseeker/FlipZonesPanel.jsx
  - frontend/src/components/heatseeker/StackedNodesPanel.jsx
  - frontend/src/components/heatseeker/TugOfWarZonesPanel.jsx
  - frontend/src/components/heatseeker/NodeLifecyclePanel.jsx
  - frontend/src/components/heatseeker/NodeClassificationPanel.jsx
  - frontend/src/components/heatseeker/RollingFloorsCeilingsPanel.jsx
  - frontend/src/components/heatseeker/AirPocketsPanel.jsx
  - frontend/src/components/heatseeker/BeachBallIndicator.jsx
  - frontend/src/components/heatseeker/ReverseRugIndicator.jsx
  - frontend/src/components/heatseeker/RainbowRoadIndicator.jsx
  - frontend/src/components/heatseeker/TrinityConfluenceMeter.jsx
  - frontend/src/components/heatseeker/VelocityModeBadge.jsx

  Plus their *.test.jsx siblings (you may update existing tests).

FORBIDDEN: SidebarPanels.jsx (Agent C), AdvancedAnalyticsPanel.jsx (Agent D),
PaperTrade.jsx (Agent B), App.js (Agent A).

MISSION: After DeepSeek's proxy fix, each Wave panel should fetch real data
from `/api/heatseeker/<name>?ticker=<T>` and render. Standardize each
panel's loading / error / empty states. Match the dark theme.

PHASES:

  S1.1  Read HeatseekerDashboard.jsx — note which panels it composes.
        Run a curl check against each endpoint to confirm shape:
          for ep in flip-zones node-lifecycle reverse-rug rainbow-road \
                    velocity-mode rolling-floors-ceilings node-classification \
                    tug-of-war air-pockets beach-ball; do
            code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8000/api/heatseeker/$ep?ticker=SPY")
            echo "$ep: $code"
          done

  S1.2  For each 404 → flag in your closure card as "deferred endpoint"
        and render "—" in the panel.
        For each 200 → trust the existing hook (useHeatseeker) and harden
        the render logic with null-chains.

  S2.1  Standardize the panel skeleton across all 10 files. Pattern:
          export default function FooPanel({ ticker }) {
            const { data, loading, error } = useHeatseeker("foo", { ticker });
            if (loading) return <div className="panel p-3 text-slate-500">Loading…</div>;
            if (error)   return <div className="panel p-3 text-rose-400">{String(error)}</div>;
            if (!data)   return <div className="panel p-3 text-slate-500">—</div>;
            return (
              <div className="panel p-3" data-testid={`hs-foo`}>
                {/* render data… */}
              </div>
            );
          }

  S2.2  Update the existing *.test.jsx to assert each state renders the
        right testid (already in many tests).

  S3.1  Commit + Common Closure.

ACCEPTANCE:
  - All 10 panels render without crashing in loading / error / empty / data states
  - data-testid attributes match HeatseekerDashboard.test.jsx expectations

═══════════════════════════════════════════════════════════════════════════════
AGENT G — hooks/*.js: data-layer audit + error handling
═══════════════════════════════════════════════════════════════════════════════

OWNED FILES:
  - frontend/src/hooks/useDataSource.js
  - frontend/src/hooks/useHeatseeker.js (find this file; create if missing)
  - frontend/src/hooks/useWebSocketGex.js
  - frontend/src/hooks/useDebounce.js

FORBIDDEN: any component file.

MISSION: Hooks are the data layer. They MUST:
  - Build URLs using the API constant from process.env (not hardcoded localhost)
  - Catch + surface errors via { data, loading, error } returns
  - Not throw inside React render path
  - Not silently swallow exceptions

PHASES:

  S1.1  Read each hook. Identify any that:
          - hardcode http://localhost:8000 (should use env)
          - swallow errors with empty catch blocks (should setError)
          - return undefined for `error` instead of explicit null (consistency)

  S1.2  Standardize the return shape across all hooks:
          { data, loading: false, error: null }   // initial / empty
          { data: <result>, loading: false, error: null }   // success
          { data: null, loading: false, error: <msg> }   // failure

  S1.3  Ensure URL building uses:
          const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
          const url = `${BACKEND_URL}/api/...`;
        (After DeepSeek's fix, BACKEND_URL is defined.)

  S1.4  Add tiny unit tests if useHeatseeker doesn't have any:
          // hooks/useHeatseeker.test.js — mock axios, assert loading→data flow

  S2.1  Commit + Common Closure.

ACCEPTANCE:
  - Every hook follows the standard return shape
  - No hook hardcodes localhost:8000
  - No hook swallows errors

═══════════════════════════════════════════════════════════════════════════════
AGENT H — Trade/Journal/Dashboard widgets
═══════════════════════════════════════════════════════════════════════════════

OWNED FILES:
  - frontend/src/components/TradeJournal.jsx
  - frontend/src/components/DashboardSummary.jsx
  - frontend/src/components/TradeEntry.jsx
  - frontend/src/components/TradeAnalytics.jsx
  - frontend/src/components/MorningBriefing.jsx
  - frontend/src/components/PositionSizing.jsx

FORBIDDEN: any other component/hook/route file.

MISSION: Each widget needs:
  - Null safety on every numeric access (like Agent B's pattern)
  - Loading/error/empty states matching the dark UI
  - No console.errors when API is unreachable

PHASES:

  S1.1  For each owned file, run:
          grep -n "\\.toFixed\\|\\.toLocaleString\\|\\.map(" frontend/src/components/<FILE> | head -10

  S1.2  Apply Agent B's null-safety patterns and Agent C's loading/error/empty pattern.

  S2.1  Commit + Common Closure.

ACCEPTANCE:
  - All 6 widgets handle null gracefully
  - Console has no errors after proxy fix when navigating each tab

═══════════════════════════════════════════════════════════════════════════════
AGENT I — Backend route VERIFICATION (read-only audit)
═══════════════════════════════════════════════════════════════════════════════

OWNED FILES (read-only audit; no modifications):
  - backend/routes/paper_trading.py
  - backend/routes/portfolio.py
  - backend/routes/heatseeker.py
  - backend/routes/data_providers.py
  - any other backend/routes/*.py the React app calls

OWNED FILES (writable, ONE file only):
  - docs/ROUND8_BACKEND_AUDIT.md (new file you create)

FORBIDDEN: ANY modification to existing backend files. You audit, you don't fix.

MISSION: Catalog every `/api/*` endpoint the React app calls. For each:
  - Does the backend define it?
  - Does its response shape match what the React component expects?
  - Does it 200 / 404 / 500 right now (live curl)?
  Produce a markdown audit document. Flag mismatches for Round 9.

PHASES:

  S1.1  Inventory React's API calls:
          grep -rhoE "/api/[a-z-]+(/\\{[a-z_]+\\}|/[A-Z]+)?" frontend/src --include="*.jsx" --include="*.js" | sort -u > /tmp/react_apis.txt
          wc -l /tmp/react_apis.txt
          cat /tmp/react_apis.txt

  S1.2  Inventory backend's defined routes:
          grep -rhE "@router\\.(get|post|put|delete)\\(\"" backend/routes/ | sed 's/.*"\\([^"]*\\)".*/\\1/' | sort -u > /tmp/backend_routes.txt
          wc -l /tmp/backend_routes.txt

  S1.3  curl each endpoint and capture status:
          for ep in $(cat /tmp/react_apis.txt); do
            url="http://localhost:8000${ep//\\{ticker\\}/SPY}"
            code=$(curl -s -o /dev/null -w "%{http_code}" "$url")
            echo "$ep → $code"
          done > /tmp/api_audit.txt
          cat /tmp/api_audit.txt

  S2.1  Write docs/ROUND8_BACKEND_AUDIT.md:
          - Section 1: React API call inventory (with file references)
          - Section 2: Backend route inventory
          - Section 3: Mismatches table (React expects but backend doesn't define)
          - Section 4: Health table (status codes from S1.3)
          - Section 5: Recommendations for Round 9 (deferred)

  S3.1  Commit + Common Closure.

ACCEPTANCE:
  - docs/ROUND8_BACKEND_AUDIT.md exists with all 5 sections populated
  - No backend file is modified (verify: git diff --stat backend/)

═══════════════════════════════════════════════════════════════════════════════
AGENT J — Visual regression + Round 8 closure (RUNS LAST)
═══════════════════════════════════════════════════════════════════════════════

PREREQUISITE: do NOT start until Agents A through I have all reported DONE.

OWNED FILES:
  - frontend/src/__tests__/visual.test.jsx (new file)
  - docs/ROUND8_CLOSURE.md (new file)
  - docs/ROUND8_COMPLETION_LOG.md (append closure entry)
  - kanban/cards/hermes_r8_j_closure_<date>.md (new file)

FORBIDDEN: any component/hook/backend file.

MISSION: Add minimal Playwright visual-regression tests for the 8 React tabs.
Write final closure doc. Push.

PHASES:

  S1.1  Check Playwright is available:
          cd frontend && cat package.json | grep -E "playwright|@playwright"
        If missing, document and SKIP Playwright (use RTL snapshot instead).

  S1.2  Create frontend/src/__tests__/visual.test.jsx:

          // Tab-by-tab smoke test: each tab renders without crashing
          import { render } from "@testing-library/react";
          import App from "../App";

          jest.mock("axios");

          test.each([
            "trinity", "heatseeker", "skylit", "portfolio",
            "journal", "swarmspx", "dashboard", "papertrade",
          ])("renders %s tab without crash", (tab) => {
            const { container } = render(<App initialPage={tab} />);
            expect(container.querySelector(".nav-tabs")).toBeInTheDocument();
          });

        Note: if App doesn't accept `initialPage` prop, document that as a
        Round 9 followup and just smoke-test the default render.

  S2.1  Write docs/ROUND8_CLOSURE.md:
          - List every Round 8 commit (git log --grep="round-8")
          - Per-agent acceptance status
          - Known deferrals (from Agent I's audit + any HALT cards)
          - Final test count + truth audit result
          - Files held for human decision (if any)

  S2.2  Append final entry to docs/ROUND8_COMPLETION_LOG.md:
          ## Round 8 closed — $(date -u +%Y-%m-%dT%H:%M:%SZ)
          - Agents complete: 10/10 (A-J)
          - DeepSeek phase 0: ef… (proxy fix)
          - Visual regression: 8/8 tabs smoke pass
          - Final test count: <pass>/<skip>/<fail>
          - HEAD: $(git rev-parse HEAD)

  S3.1  git add + commit + push:
          git add docs/ROUND8_CLOSURE.md docs/ROUND8_COMPLETION_LOG.md \
                  kanban/cards/hermes_r8_j_*.md \
                  frontend/src/__tests__/visual.test.jsx
          git commit -m "docs(round-8-closure): visual regression + closure document

          Co-Authored-By: Hermes <hermes@floww.dev>"
          git pull --rebase origin main
          git push origin main

ACCEPTANCE:
  - frontend/src/__tests__/visual.test.jsx passes 8/8 tab renders
  - docs/ROUND8_CLOSURE.md is complete and accurate
  - Round 8 logged as CLOSED

═══════════════════════════════════════════════════════════════════════════════
END OF AGENT MISSIONS
═══════════════════════════════════════════════════════════════════════════════
