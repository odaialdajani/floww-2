# Phase 3 — Public API Data Layer Integration Plan

> Deep-dive findings + engineering plan for wiring PublicBroker into floww as the primary data source.
> Status: 2026-08-30 — Assessment Complete, Plan Finalized.

---

## 1. Executive Summary

**The situation:** Two Python backends coexist:
- **floww backend** (`/Users/nav/Documents/GitHub/floww/backend/`) — FastAPI app on `:8000`. Already running, 2717-line server.py + ~50 route modules. Data sources: cvserver (CVForge/ConvexValue) → yfinance → Databento → Polygon → AlphaVantage → FlashAlpha. Schwab WebSocket present but disabled. No Public API key in `.env`.
- **Standalone backend layer** (`/Users/nav/backend/`) — NOT a git repo, NOT a server. Pure service layer with `public_api.py` (1050 lines, full PublicBroker class), `finnhub_client.py`, `finnhub_api.py`, `gflows_integration.py`. Tests in `tests/services/` (547-line test_public_api.py, all mocked). Has `.env.example` with `PUBLIC_API_KEY=PkdDGcMzqMie0f6I823q6nHtmkGJyRsu`.

**The problem:** The FlowBroker in `/Users/nav/backend/services/public_api.py` is fully implemented and tested but NOT wired into floww. Floww currently uses cvserver as its primary chain source.

**The goal:** Wire PublicBroker into floww as the PRIMARY data source for options chains (heatmap, Solstice tab), with Public API first, fallback routing to cvserver/yfinance/Databento when Public API is rate-limited or unavailable, and Tidehunter Pro as a documented (but not-yet-built) fallback for heatmap when Public API is limited.

---

## 2. Deep-Dive Findings

### 2.1 Standalone Backend Layer (`/Users/nav/backend/`)

**Directory structure:**
```
/Users/nav/backend/
├── .env.example                          (15 lines — all env vars)
├── services/
│   ├── public_api.py                     (1050 lines — full PublicBroker class)
│   ├── finnhub_api.py                    (176 lines — Finnhub REST shim layer)
│   ├── finnhub_client.py                 (223 lines — Finnhub SDK wrapper)
│   └── gflows_integration.py             (396 lines — CBOE data + Greek profiles)
└── tests/
    └── services/
        ├── test_public_api.py            (547 lines — all mocked, comprehensive)
        └── test_dash_ui_heatseeker.py    (365 lines — heatseeker toggle tests)
```
- NOT a git repo (no version control)
- No server.py — pure service layer, meant to be imported
- Python 3.9.6 on system python (NOT venv'd — `python3` from CLT)
- Tests use pytest with `asyncio_mode=strict` (different from floww's `auto`)

**public_api.py — PublicBroker API surface:**
```python
class PublicBroker:
    def __init__(secret_key, token_validity_min=55, client=None)
    async def auth(validity_min=None) -> str              # secret key → JWT
    async def get_accounts() -> List[Account]
    async def get_portfolio(account_id) -> Portfolio     # cash, positions, orders, BP
    async def get_quotes(symbols, account_id) -> List[Quote]
    async def get_option_expirations(symbol, account_id) -> List[str]
    async def get_option_chain(symbol, expiration, account_id) -> dict
    async def get_option_chain_parsed(symbol, expiration, account_id) -> {"calls":[...], "puts":[...]}
    async def get_option_greeks(osi_symbols, account_id) -> dict  # max 250/call
    async def get_bars(symbol, period, ...) -> dict              # OHLCV
    async def place_order(...) -> Order                          # PAPER ONLY
    async def place_market_order(...) -> Order
    async def place_limit_order(...) -> Order
    async def place_stop_order(...) -> Order
    async def cancel_order(order_id, account_id) -> dict
    async def get_order(order_id, account_id) -> Order
    async def get_order_history(account_id, ...) -> dict
    async def get_unrealized_tax_lots(account_id) -> dict
    async def prefetch_quotes(...) -> dict                       # bulk
    async def prefetch_greeks(...) -> dict                       # bulk
```

**Key data classes:** Account, Quote, Position, OptionContract, Order, Portfolio

**Test coverage (test_public_api.py — 547 lines):**
- TestFinnhubClient — quote, options_chain, company_profile, fundamentals, news, technicals
- TestFinnhubClientApiError — error handling
- TestFinnhubClientNoKey — key missing scenarios
- TestPublicApiQuote — quote endpoint shape, missing ticker, no data
- TestPublicApiQuoteBulk — bulk returns, empty list, mixed success/failure
- TestPublicApiOptionsChain — chain endpoint, single expiry
- TestPublicApiOptionsChainForExpiry — parsed chain validation
- All network calls mocked — no live API access

### 2.2 Floww Backend (`/Users/nav/Documents/GitHub/floww/backend/`)

**server.py data source pipeline (lines 501–644):**
```python
# fetch_spot_and_chains(ticker) -> yfinance + Databento OI overlay
# fetch_spot_and_chains_merged(ticker) -> cvserver FIRST, then yfinance + Databento fallback
```

Current priority chain in `fetch_spot_and_chains_merged`:
1. cvserver (CVForge) — 32 expiries, 171 strikes, all greeks (lines 562-572)
2. yfinance + Databento OI overlay (lines 578-644)

cvserver client (`cvserver_client.py`, 638 lines):
- `fetch_chain_from_cvserver(symbol, exp_date, max_expiries)` — calls MCP `tools/call` → `get_chain`
- `fetch_chain_for_heatmap(symbol, spot, max_strikes)` — calls MCP `tools/call` → `screen` (near-ATM filter, OI>0)
- `screen_from_cvserver(...)` — grid screen
- Built-in TTL cache (60s chain, 120s heatmap), request coalescing locks, 429 cool-down (600s), per-key failure backoff
- `upstream_requests_last_hour()` — tracks CVForge API budget (20 calls/hour per Obsidian Meridian.md)
- Budget status endpoint for observability

**Route that serves chain data to frontend:**
- `GET /api/chain?ticker=SPY` → `routes/chain.py:17` → calls `server.fetch_spot_and_chains_merged(ticker)`

**Frontend API config:**
- `frontend/src/config/api.js` — BACKEND_URL = `http://localhost:8000` in dev, same-origin in prod
- Components call `axios.get(\`${API}/chain/${ticker}\`)` and related endpoints

**floww .env has:** CVSERVER_API_KEY, DATABENTO_API_KEY, POLYGON_API_KEY, ALPHA_VANTAGE_KEY, OPENROUTER_API_KEY, MONGO_URL, DB_NAME
**floww .env does NOT have:** PUBLIC_API_KEY, FINNHUB_API_KEY, FLASHALPHA_API_KEY

### 2.3 The Standalone backend is NOT imported by floww

```bash
$ grep -rn "public_api\|PublicBroker\|PUBLIC_API" /Users/nav/Documents/GitHub/floww/backend/
# Zero results — floww has zero awareness of the standalone backend
```

The two backends are completely independent. The standalone `/Users/nav/backend/` layer needs to be integrated INTO floww.

---

## 3. Agent Fleet Roster

### Agent 1 — You (First Agent / Orchestrator)
**Lane:** Planning + coordination + git hygiene
**Repo:** `/Users/nav/Documents/GitHub/floww`
**Current status:** In progress — deep-dive + plan + contract files
**Next:** Write this plan, update ROADMAP.md tickets, update AGENT_CONTRACT.md, spawn fleet, monitor

### Agent 2 — Backend Integration
**Lane:** Data source integration
**Repo:** `/Users/nav/Documents/GitHub/floww`
**Mission:** Wire PublicBroker into floww backend
**Deliverables:**
- Copy `/Users/nav/backend/services/public_api.py` → `backend/services/public_api.py`
- Add `PUBLIC_API_KEY` to `backend/.env.example` (key value provided by Nav: `<REDACTED — see backend/.env; rotate this key, it was committed>`)
- Add new route: `GET /api/public/chain/{ticker}?expiration=YYYY-MM-DD&expirations=N` → returns PublicBroker chain
- Add new route: `GET /api/public/quotes/{ticker}` → returns PublicBroker quote
- Modify `fetch_spot_and_chains_merged()` to try Public API first, then cvserver, then yfinance
- Add test file: `backend/tests/services/test_public_api_integration.py` (mock PublicBroker, verify routing)
- Run ruff + pytest verification
**Constraints:** Does NOT touch server.py routing logic (only adds new import + modifies the fetch function), does NOT touch cvserver_client.py, does NOT touch frontend

### Agent 3 — cvserver Alignment
**Lane:** cvserver client + data provider docs
**Repo:** `/Users/nav/Documents/GitHub/floww`
**Mission:** Ensure cvserver client is compatible as a fallback, update integration docs
**Deliverables:**
- Read cvserver_client.py fully, verify the fallback path from Public API → cvserver will work
- Update `.planning/codebase/INTEGRATIONS.md` to add Public API as primary source
- Update `backend/.env.example` if needed
- Add Public API to the data source priority matrix in server.py docstrings
**Constraints:** Does NOT modify cvserver_client.py logic (only docs), does NOT touch forbidden files

### Agent 4 — Frontend Wiring
**Lane:** Frontend Solstice/Heatseeker tab
**Repo:** `/Users/nav/Documents/GitHub/floww`
**Mission:** Update frontend to use Public API chain data
**Deliverables:**
- Add `/api/public/chain/{ticker}` call path to the data fetch in components that consume chain data
- Update `OptionsChainTable.jsx` — add Public API source option (it currently calls `/api/chain/${ticker}`)
- Update TrinityVolatility.jsx — add Public API source option (calls `/api/chain`)
- New endpoint: `/api/public/quotes/{ticker}` — wire into spot price fetching
- Zenith tab: NO changes (display-only, data comes from backend)
- Tests: any component changes must include jest test coverage
**Constraints:** Does NOT touch App.js (frozen), does NOT touch package.json/craco (frozen)

### Agent 5 — GSD Phase Execution
**Lane:** GSD process + phase plan scaffolding
**Repo:** `/Users/nav/Documents/GitHub/floww`
**Mission:** Execute Phase 3 as a GSD phase
**Deliverables:**
- Create `.planning/phases/phase-3-public-api/PLAN.md` (full GSD phase plan with verification loop)
- Create `.planning/phases/phase-3-public-api/REQUIREMENTS.md` (traced to ROADMAP tickets)
- Update `kanban/cards/` with agent status files (append-only format)
- Run gsd-spec-phase or manual equivalent to lock the plan
- Track Phase 3 → Phase 4 → Phase 5 handoff
**Constraints:** Does NOT touch backend code, does NOT touch frontend code, planning only

---

## 4. Data Source Routing — Final Decision Tree

```
NEED: Options chain / OI / Greeks (for Solstice heatmap)
  → Try Public API first (PublicBroker.get_option_chain_parsed + get_option_greeks)
    - Key: <REDACTED — see backend/.env; rotate this key, it was committed> (provided by Nav)
    - Env var: PUBLIC_API_KEY (add to floww backend/.env + .env.example)
    - Data shape: OptionContract dataclass (strike, expiration, OI, IV, delta, gamma, theta, vega, bid, ask)
  → If Public API rate-limited/down → cvserver fallback (fetch_spot_and_chains_merged, current priority #2)
    - Key: cv_live_... (already in .env)
    - Data shape: dict with "contracts" list, "spot", "expiries"
  → If cvserver also down → yfinance + Databento (legacy fallback, current priority #3)
  → If ALL public sources exhausted AND Public API has hard limits → Tidehunter Pro (Phase 4, not built yet)
  → NEVER use Schwab (out) or Zenith as API target (UI tab only)

NEED: Spot price
  → Try Public API (PublicBroker.get_quotes)
  → If unavailable → yfinance (5s cache) or Finnhub (via data_providers.py DataAggregator)

NEED: Bars / OHLCV
  → Try Public API (PublicBroker.get_bars)
  → Fallback → yfinance

NEED: Portfolio (paper trading)
  → Public API (PublicBroker.get_portfolio) — BUT paper-only, no live order execution
```

---

## 5. Phase 3 Detailed Ticket Breakdown (Updated from ROADMAP.md)

### 3.1 Confirm key + source model — DONE
- Public API key: `<REDACTED — see backend/.env; rotate this key, it was committed>` (provided by Nav, 2026-08-30)
- Standalone backend at `/Users/nav/backend/` already has full PublicBroker implementation
- `.env.example` in standalone backend has `PUBLIC_API_KEY=PkdDGcMzqMie0f6I823q6nHtmkGJyRsu` (stale default — Nav's key supersedes)
- **Connection model:** Copy PublicBroker into floww backend (NOT import across repos — they're separate, not in same Python path)

### 3.2 Copy PublicBroker into floww — Agent 2
- Source: `/Users/nav/backend/services/public_api.py` (1050 lines)
- Target: `/Users/nav/Documents/GitHub/floww/backend/services/public_api.py`
- Also copy: `finnhub_client.py` (223 lines), `finnhub_api.py` (176 lines) — these are referenced by test_public_api.py and may be needed for spot fallback
- Also copy: test file `tests/services/test_public_api.py` (547 lines)

### 3.3 Add PUBLIC_API_KEY to floww .env — Agent 2
- Add `PUBLIC_API_KEY=<REDACTED — see backend/.env; rotate this key, it was committed>` to `backend/.env`
- Add `PUBLIC_API_KEY=your_public_api_key_here` to `backend/.env.example`
- Verify .env is gitignored (it is — confirmed)

### 3.4 Wire Public API as primary chain source — Agent 2
- Modify `fetch_spot_and_chains_merged()` in `server.py` (line 555) to try PublicBroker first
- New priority: 1. Public API → 2. cvserver → 3. yfinance + Databento
- Add `PUBLIC_API_KEY` check — if not set, skip to cvserver
- Handle token auth: PublicBroker.auth() must be called once, token cached for 55 min

### 3.5 New routes: /api/public/chain/{ticker} + /api/public/quotes/{ticker} — Agent 2
- Create `backend/routes/public_api.py` (new file — NOT frozen)
- `GET /api/public/chain/{ticker}?expiration=YYYY-MM-DD` → PublicBroker.get_option_chain_parsed
- `GET /api/public/quotes/{ticker}` → PublicBroker.get_quotes
- Mount via `app.include_router(public_api_router, prefix="/api/public")` in server.py

### 3.6 Tests — Agent 2
- `backend/tests/services/test_public_api_integration.py` — mock PublicBroker, verify routing works
- Test: Public API returns chain → verify shape matches floww expectations
- Test: Public API fails → cvserver fallback kicks in
- Run: `cd backend && .venv/bin/python3 -m pytest tests/services/test_public_api_integration.py -v`
- Run: `cd backend && .venv/bin/ruff check services/public_api.py routes/public_api.py`

### 3.7 Update INTEGRATIONS.md + docs — Agent 3
- Add Public API to the data source priority list
- Update cvserver entry from "primary" to "fallback"
- Update STATE.md to reflect new data source architecture

### 3.8 Frontend wiring — Agent 4
- Add `/api/public/chain/{ticker}` and `/api/public/quotes/{ticker}` as options in data fetch paths
- Components to check: OptionsChainTable.jsx, TrinityVolatility.jsx, BarHeatmap.jsx, HeatseekerDashboard.jsx
- Spot price: add Public API as first source in DataAggregator priority

### 3.9 Phase 4 (Tidehunter Pro) — PENDING
- Only build if Public API has real limits. Don't start until Phase 3 is verified live.

---

## 6. Launch Sequence

1. **Agent 1 (you):** Push this plan + updated ROADMAP/AGENTS_CONTRACT/DataSources. Start Agent 2 and Agent 3 simultaneously.
2. **Agent 2:** Copy PublicBroker → add PUBLIC_API_KEY → modify fetch_spot_and_chains_merged → create routes → write tests → verify ruff + pytest pass.
3. **Agent 3:** Read cvserver_client.py fully → update INTEGRATIONS.md → verify fallback path compatibility.
4. **Agent 2 + Agent 3:** Sync on the fallback contract (PublicBroker data shape vs cvserver data shape).
5. **Agent 4:** After Agent 2's routes are committed, wire frontend to new endpoints.
6. **Agent 5:** Track all of the above in GSD phase plans + kanban cards.

---

## 7. Critical Constraints (Repeated from AGENT_CONTRACT.md)

- **Canonical repo:** `/Users/nav/Documents/GitHub/floww` ONLY
- **Pathspec commits only:** `git add <your-files>` — NEVER `git add -A`
- **Forbidden files:** `ml/inference.py`, `dash_ui.py`, `conftest.py` (waived), `App.js`, `package.json`, `craco.config.js`, model artifacts
- **Forbidden git ops:** push --force, commit --amend, rebase -i, reset --hard, clean -fd
- **Commit style:** HEREDOC with inline grep/pytest/curl evidence
- **Test discipline:** write failing test first, fix, then pass. No skip/xfail on passing tests.
- **Paper only:** no live order execution wiring
- **Anti-fabrication:** every claim needs real command output
- **15-min self-HALT:** if stuck for 15 min, write status and stop
