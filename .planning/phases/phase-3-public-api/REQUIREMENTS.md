# Phase 3 — Public API Data Layer: Requirements

## R-3.1: Public API Key
- **Source:** User-provided `<REDACTED — see backend/.env; rotate this key, it was committed>`
- **Location:** Standalone backend `.env.example` + needs to be in floww backend `.env`
- **Status:** DONE — key confirmed

## R-3.2: PublicBroker Service Layer
- **Source file:** `/Users/nav/backend/services/public_api.py` (1050 lines)
- **Key methods needed:** `auth()`, `get_option_chain_parsed()`, `get_quotes()`, `get_option_greeks()`, `get_bars()`, `get_portfolio()`, `place_order()` (paper only)
- **Data classes:** Account, Quote, Position, OptionContract, Order, Portfolio
- **Test coverage:** `/Users/nav/backend/tests/services/test_public_api.py` (547 lines, all mocked)
- **Action:** Copy to `backend/services/public_api.py`

## R-3.3: Environment Configuration
- **Add to floww `backend/.env`:** `PUBLIC_API_KEY=<REDACTED — see backend/.env; rotate this key, it was committed>` (gitignored)
- **Add to floww `backend/.env.example`:** `PUBLIC_API_KEY=your_public_api_key_here`
- **Env var name:** `PUBLIC_API_KEY` (confirmed from existing implementation)

## R-3.4: Modified Data Fetch Pipeline
- **Function:** `server.py:fetch_spot_and_chains_merged(ticker)` (currently line 555)
- **New priority:** 1. Public API → 2. cvserver → 3. yfinance + Databento
- **PublicBroker wrapper:** Add a helper `fetch_chain_from_public_api(symbol)` that returns the same dict shape as `fetch_spot_and_chains_merged` currently returns
- **Token caching:** PublicBroker.auth() token cached for 55 min (built into PublicBroker)

## R-3.5: New API Endpoints
- `GET /api/public/chain/{ticker}?expiration=YYYY-MM-DD&expirations=N` → PublicBroker.get_option_chain_parsed
- `GET /api/public/quotes/{ticker}` → PublicBroker.get_quotes
- **File:** `backend/routes/public_api.py` (new)
- **Mount:** `app.include_router(public_api_router, prefix="/api/public")` in server.py

## R-3.6: Tests
- `backend/tests/services/test_public_api_integration.py` — mock PublicBroker, verify:
  - Public API returns chain → correct shape
  - Public API fails → cvserver fallback
  - Public API key missing → skips to cvserver
- Must follow TDD: write failing test first, then implement, then verify pass
- Backend venv: `backend/.venv/bin/python3` (Python 3.13)

## R-3.7: Documentation Updates
- `.planning/codebase/INTEGRATIONS.md` — add Public API as primary, downgrade cvserver to fallback
- `backend/.env.example` — document PUBLIC_API_KEY
- Server.py docstrings for fetch_spot_and_chains_merged

## R-3.8: Frontend Wiring
- Components that call `/api/chain` or use chain data: OptionsChainTable, TrinityVolatility, HeatseekerDashboard
- Add option to use `/api/public/chain` for Public API source
- Zenith tab: NO changes (display only)

## R-3.9: Phase Execution
- GSD phase plan lives here at `.planning/phases/phase-3-public-api/PLAN.md`
- Kanban cards in `kanban/cards/` — append-only status
- Track in ROADMAP.md §3
