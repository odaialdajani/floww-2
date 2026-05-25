# Round 8 Master Plan — React UI Restoration

> **Architect:** PhD math/physics, ex-Jane Street HFT lens. Authored 2026-05-24.
> **Status:** Round 7 (Dash dashboard right sidebar) is COMPLETE but INVISIBLE to user because user lives in the **React app**, not the Dash app.
> **Round 8 mission:** Fix the React app — restore data flow, fix toggle combinations, repair PaperTrade, style the Dashboard tab to match.

---

## 1. Critical Pivot (this is why Round 7 felt empty)

The Floww terminal has TWO frontends:

| App | Port | Tech | Status |
|-----|------|------|--------|
| **React app** | 3000 | React + axios + custom hooks | **THE REAL UI** Nav uses |
| Dash app | 8000 `/dashboard/` | Dash + Plotly | Embedded as an iframe in React's "Dashboard" tab |

All Round 7 work (9-panel right sidebar, header strip, cell tags) went into `backend/services/dash_ui.py` — the Dash app. **It's only visible if Nav clicks the "Dashboard" tab inside React.** The Heatseeker / Skylit tabs Nav actually uses are React components in `frontend/src/components/`.

**The work was not wasted** — it shows up in the Dashboard tab. But the bigger gain in Round 8 is fixing the React tabs directly.

---

## 2. Root Cause #1 — Why every panel says "Unexpected token '<', "<!doctype "..."

```javascript
// frontend/src/App.js:56-57
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;   // ← undefined (no .env file!)
const API = `${BACKEND_URL}/api`;                         // ← "undefined/api" → browser uses "/api"
```

- React dev server on port 3000 returns `index.html` (HTML) for any unknown path
- Every `axios.get('/api/heatseeker/flip-zones')` hits port 3000, gets HTML back
- `JSON.parse('<!doctype html>...')` throws "Unexpected token '<'"
- **EVERY panel that hits an API endpoint fails this way** — Skylit, Vanna, Charm, Portfolio, PaperTrade

**Fix:** create `frontend/.env` with `REACT_APP_BACKEND_URL=http://localhost:8000` OR add `"proxy": "http://localhost:8000"` to `frontend/package.json`. ONE file change resolves ~80% of visible errors.

This is **DeepSeek's job** (Phase 0) — must complete before any Hermes work.

---

## 3. Root Cause #2 — PaperTrade React crash

```javascript
// frontend/src/components/PaperTrade.jsx:121
{portfolio.total_pnl_pct >= 0 ? "+" : ""}{portfolio.total_pnl_pct.toFixed(2)}%
```

`portfolio` is `null` when the API call fails (which it always does because of #1). Accessing `.total_pnl_pct.toFixed(2)` on null crashes React. Need optional-chain `portfolio?.total_pnl_pct?.toFixed(2) ?? "—"` everywhere.

---

## 4. Root Cause #3 — Toggle combinations don't compose

React state IS wired (App.js:299-301 — `view`, `viewMode`, `mode` state hooks; keyboard shortcuts at 437-446). But the fetch logic doesn't always pass all toggle values to the right endpoint. Specifically:

- DAY + GEX works (default path)
- DAY + CHARM doesn't render charm data (the data is fetched but the chart component doesn't switch)
- DTE filter (0DTE/1DTE/Week/All) doesn't pass to `/api/chain` as `?dte=...`
- Expiries selector (2/4/6/8/12) might not pass `?expiries=N` either

---

## 5. Current State Summary (verified)

| Area | State | Owner |
|------|-------|-------|
| Backend `/api/*` endpoints | ✅ Working (`curl localhost:8000/api/heatseeker/flip-zones` → 200) | already done |
| Backend port | ✅ 8000 listening | already done |
| React dev server | ✅ port 3000 listening | already done |
| React → backend proxy | ❌ **MISSING** — no `.env`, no proxy in package.json | **DeepSeek Phase 0** |
| React Heatseeker panels | ⚠️ Components exist; data fails to load | **Hermes after DeepSeek** |
| Heatseeker toggle composition | ❌ DAY+CHARM, DTE, Expiries don't propagate | **Hermes A** |
| PaperTrade | ❌ React crash from null toFixed | **Hermes B** |
| Skylit ticker dropdown | ❌ Only SPY hardcoded | **Hermes A** |
| Portfolio scenarios/hedge buttons | ❌ Dummy (no onClick wiring) | **Hermes E** |
| Dashboard tab style | ⚠️ Embeds Dash but theme doesn't match | **Hermes A** |
| Dash app right sidebar (Round 7) | ✅ Done, ~400 lines in dash_ui.py | already done |
| Test suite | ✅ 2299/68/12-xpassed, 2 hotspot flakes | already done |
| Truth audit | ✅ 17/1 (1 known overfit) | already done |

---

## 6. Round 8 Agent Plan — 1 DeepSeek + 10 Hermes

### Execution order

```
t=0:   DeepSeek Phase 0   (proxy/.env fix)     ~5-10 min
       ↓ (gate: confirm `curl localhost:3000/api/chain/SPY` returns JSON not HTML)

t=10:  All 10 Hermes launch in parallel
       Hermes J (visual regression) runs LAST after others commit
```

### File ownership matrix (zero overlap = safe parallel)

| Agent | Files owned | Mission |
|-------|------------|---------|
| **DeepSeek** | `frontend/.env` (new), `frontend/package.json` | Add proxy config; verify all `/api/*` calls now hit port 8000 |
| **Hermes A** | `frontend/src/App.js` (sole owner of this monster file) | (1) Fix Heatseeker toggle composition (DAY×CHARM, DTE, Expiries), (2) add Skylit ticker dropdown, (3) restyle Dashboard tab embed |
| **Hermes B** | `frontend/src/components/PaperTrade.jsx` | Null-safe all `.toFixed()` calls; wire form submission to `/api/paper-trading/execute`; ensure portfolio re-fetches after submit |
| **Hermes C** | `frontend/src/components/SidebarPanels.jsx` | Add null-safety + error states to FlipZonesPanel, StackedNodesPanel, TugOfWarPanel, VolAnalyticsPanel (Vanna/Charm) |
| **Hermes D** | `frontend/src/components/AdvancedAnalyticsPanel.jsx` | Add null-safety + error states to MarketRegime, ImpliedPDF, HedgeImpulse, PressureCloud, CharmIntegral panels |
| **Hermes E** | `frontend/src/components/PortfolioPanel.jsx` | Wire scenarios + hedge buttons to backend endpoints (find them, or create stubs that return "—") |
| **Hermes F** | `frontend/src/components/heatseeker/*.jsx` (10 panels) | Verify each Wave panel handles loading/error/empty consistently with the dark theme |
| **Hermes G** | `frontend/src/hooks/*.js` (`useDataSource`, `useHeatseeker`, `useWebSocketGex`, `useDebounce`) | Audit all API hooks: ensure they use `API` constant correctly, handle 4xx/5xx without crashing, expose `error` state cleanly |
| **Hermes H** | `frontend/src/components/TradeJournal.jsx`, `DashboardSummary.jsx`, `TradeEntry.jsx`, `TradeAnalytics.jsx`, `MorningBriefing.jsx`, `PositionSizing.jsx` | Null-safe + error states for all journal/dashboard widgets |
| **Hermes I** | `backend/routes/paper_trading.py`, `backend/routes/portfolio.py` (existing) — **verify only, don't add** | Confirm endpoints React expects actually exist with the shape React assumes; flag mismatches |
| **Hermes J** | `frontend/src/__tests__/visual.test.jsx` (new), `docs/ROUND8_COMPLETION_LOG.md` (new), kanban card | **Runs LAST.** Playwright/RTL snapshot tests per tab + write closure doc |

### Why this matrix is safe

- Only Hermes A touches `App.js`
- Each component file has exactly one owner
- DeepSeek owns config (no React code)
- Hermes I only READS backend files
- Hermes J writes only NEW files (tests + docs)

---

## 7. Universal Hermes Prompt Template

Each Hermes agent gets the same preamble (operating laws + safety rules) plus their specific mission. See `HERMES_ROUND8_TEMPLATE.md` for the template and `HERMES_ROUND8_AGENT_<X>.md` for each agent's specifics.

---

## 8. Acceptance Criteria for Round 8 Close

- [ ] `curl http://localhost:3000/api/chain/SPY | head -1` returns JSON, not HTML
- [ ] Every Skylit panel renders without "Unexpected token '<'" errors
- [ ] Heatseeker toggles compose: DAY+VEX shows vanna, DAY+CHARM shows charm, 0DTE filter works, Expiries selector works
- [ ] PaperTrade tab loads without React crash; form submission works end-to-end
- [ ] Portfolio scenarios + hedge buttons either work or show "Coming Soon" with no console errors
- [ ] Skylit tab has a ticker dropdown (SPY, QQQ, IWM, TLT, DIA, SPX at minimum)
- [ ] Dashboard tab visual style matches the rest of the dark UI (no light-theme leakage from the Dash iframe)
- [ ] Visual regression tests pass for all 8 tabs
- [ ] Test suite ≥ 2299 passing, 0 failed (current hotspot flakes counted as known)
- [ ] Truth audit still 17/1
- [ ] `docs/ROUND8_COMPLETION_LOG.md` exists with real SHAs (not fabricated like Round 7's first attempt)

---

## 9. Anti-Drift Defenses Carried Forward From Round 7

1. **Grep-verify every commit message.** If you can't prove it with `grep`, don't claim it.
2. **No `xfail` / `skip` without explicit human approval.** DeepSeek hid 12 passing tests behind fake xfails last round.
3. **File-ownership FORBIDDEN list, not just OWNED.** Explicit "do not touch" for every other agent's files.
4. **Halt-and-report format.** When stuck, halt with one specific question — never improvise.
5. **Phase-gated execution.** Phase 1 must complete before Phase 2 starts.
6. **DeepSeek for mechanical, Hermes for judgment.** The proxy fix is mechanical → DeepSeek. The React component fixes are judgment → Hermes.

---

## 10. Files Created In This Plan

- `ROUND8_MASTER_PLAN.md` (this file)
- `DEEPSEEK_ROUND8_PROXY_FIX.md` (DeepSeek's prompt — must run first)
- `HERMES_ROUND8_TEMPLATE.md` (universal preamble used by all 10 Hermes agents)
- `HERMES_ROUND8_AGENT_A.md` through `HERMES_ROUND8_AGENT_J.md` (per-agent specifics)
