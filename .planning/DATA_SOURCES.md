# Data Sources — Meridian / Confluence Decoder

> Single source of truth for which API feeds what. Agents: read this before wiring any endpoint.

---

## Status: 2026-08-31 (Phase 3 CLOSED, Phase 5 COMPLETE)

- Schwab: **DELIBERATELY OUT.** Not using it, not building around it. Mock feed only for tests.
- Zenith: **UI tab only**, not a data service. API calls do not route to Zenith.
- **Public API (public.com):** **PRIMARY for everything.** Building all data flow around it. Key confirmed: `<REDACTED — see backend/.env; rotate this key, it was committed>`.
- **Tidehunter Pro:** **fallback** for heatmap ONLY when Public API is limited — see Phase 4 (built only if needed).
- PublicBroker implementation: already exists at `/Users/nav/backend/services/public_api.py` (1050 lines, tested with 547-line test suite). Copy into floww backend + wire as primary. See `.planning/PHASE3_PUBLIC_API_PLAN.md`.

---

## Data source priority matrix

### Options chain / OI / Greeks (heatmap — Solstice tab)

| Priority | Source | When |
|---|---|---|
| 1 | **Public API** (`PublicBroker` in `backend/services/public_api.py`) | Default — always try first. Key: `<REDACTED — see backend/.env; rotate this key, it was committed>` |
| 2 | **cvserver** (CVForge/MCP, `cvserver_client.py`) | Public API rate-limited/down |
| 3 | **yfinance** + **Databento** OI overlay | Both Public API + cvserver unavailable |
| 4 | **Tidehunter Pro** | Only if Public API + cvserver + yfinance ALL fail on chain data (Phase 4, built only if needed) |

**Rule:** Solstice heatmap always attempts Public API first. If Public API returns a rate-limit/error or the response is degraded, cascade through: cvserver → yfinance + Databento. yfinance alone is NOT acceptable as a chain source for heatmap — it doesn't have OI data. Tidehunter Pro is a Phase 4 fallback only when all other sources fail.

### Spot price + IV

| Priority | Source | When |
|---|---|---|
| 1 | **Public API** (`PublicBroker.get_quotes()`) | Default |
| 2 | **yfinance** | Public API spot unavailable, 5s cache |

### Design-time data inspection (you, the agent)

| Source | Use for |
|---|---|
| **cvserver MCP tools** | Inspect data, sanity-check assumptions, pull small samples to design around. floww backend already has `cvserver_client.py`. |
| `window.cvApi` (runtime) | What the rendered page actually calls via local proxy |

### Runtime page data (the rendered SPA)

- `window.cvApi.chain(symbol, fields?)` → `/api/data/chains`
- `window.cvApi.screen({columns, filters, sort, limit})` → `/api/data/screen`
- `window.cvApi.query(sql)` → `/api/data/query`
- `window.cvApi.call('/<endpoint>', body)` → escape hatch for any endpoint

The local proxy (`cv-bootstrap.js`) adds auth server-side. The page never handles API keys directly.

---

## Key registry

| Key | Value | Source | Status |
|---|---|---|---|
| **Public API** | `<REDACTED — see backend/.env; rotate this key, it was committed>` | User-provided (paste 2026-08-30) | **ACTIVE KEY** — this is the Public.com brokerage API key to use for everything. The `/Users/nav/backend/` service layer already has `PublicBroker` in `public_api.py`. |
| Public API (env.example) | `PkdDGcMzqMie0f6I823q6nHtmkGJyRsu` | `/Users/nav/backend/.env.example` | **STALE?** — existing env.example key. The user-provided key `d84ic...` supersedes this. Confirm which to use. |
| CVSERVER | `cv_liv...U6dY` | `backend/.env` (floww) | Local MCP proxy auth — existing floww capability |
| Databento | `db-PBR...GFrN` | `backend/.env` (floww) | OPRA OI cache — data moat |
| Polygon | `NT_RXl...kz1n` | `backend/.env` (floww) | Alternative chain/OI source |
| AlphaVantage | `cDNhZU...4Yz0` | `backend/.env` (floww) | Quote/fundamentals |
| Finnhub | `d84ic5pr01qutij93meg` | `backend/.env` (floww) | **NOTE:** same value as Public API key — may be a copy/paste or the same key used for both. Verify. |

---

## Public API — EXISTING IMPLEMENTATION (`/Users/nav/backend/services/public_api.py`)

**Full `PublicBroker` class already built and tested.** The `/Users/nav/backend/` service layer is a standalone Python backend with:

**Auth:** `PUBLIC_API_KEY` env var → JWT access token (55 min default validity, max 1440)
**Endpoints implemented:**
- `get_accounts()` — list all accounts
- `get_trading_account()` — active trading account
- `get_portfolio(account_id)` — cash, positions, P&L, options buying power
- `get_quotes([symbols], account_id)` — live quotes
- `get_option_chain(symbol, expiration, account_id)` — raw chain
- `get_option_chain_parsed(symbol, expiration, account_id)` — `{"calls": [...], "puts": [...]}` with `OptionContract` objects (strike, expiration, OI, IV, delta, gamma, theta, vega, bid, ask)
- `get_option_greeks(osi_symbols, account_id)` — max 250 symbols per call
- `get_bars(symbol, period, ...)` — OHLCV, multiple aggregations (1m to 1y)
- `place_order(...)` — equity/options/crypto/bond, market/limit/stop/stop-limit

**Test coverage:** `/Users/nav/backend/tests/services/test_public_api.py` (547 lines) — all network calls mocked, covers error paths (no key, API returning None, bulk quote mixed success/failure).

**Gaps to fill for Phase 3:**
1. ✅ Confirm which key is active — DONE. Key: `<REDACTED — see backend/.env; rotate this key, it was committed>` (user-provided). Old env.example key `PkdDGcMzqMie0f6I823q6nHtmkGJyRsu` should be overwritten.
2. ✅ Decide connection model — DONE. Option A: Copy PublicBroker into floww backend's `services/`. See PHASE3_PUBLIC_API_PLAN.md §3.3.
3. Wire PublicBroker into floww backend — modify `fetch_spot_and_chains_merged()` to try Public API first, then cvserver, then yfinance+Databento
4. Add `/api/public/chain/{ticker}` + `/api/public/quotes/{ticker}` endpoints
5. Frontend wiring: Solstice/Triad tabs call new floww backend endpoints
6. Tidehunter Pro fallback — Phase 4, NOT started yet (only if Public API is actually limited)

---

## yfinance fallback behavior

- yfinance is the spot/IV fallback, 5s cache
- If yfinance 429s from a datacenter IP (Oracle VM), set `FLOWW_DATA_SOURCE=finnhub` in `.env.prod`
- yfinance is NOT a chain/OI source — only spot + IV

---

## Decision tree (for agents wiring data fetches)

```
IF need options chain / OI / Greeks (heatmap):
  → Try Public API first (PublicBroker.get_option_chain_parsed / get_option_greeks)
  → If Public API fails/rate-limited → cvserver (existing cvserver_client.py)
  → If cvserver also fails → yfinance + Databento OI overlay (existing)
  → Only if ALL fail → Tidehunter Pro (Phase 4, not yet built)
  → yfinance alone is NOT acceptable for chain data (no OI)

IF need spot price:
  → Try Public API (PublicBroker.get_quotes)
  → If unavailable → yfinance (5s cache)

IF need bars / OHLCV:
  → Try Public API (PublicBroker.get_bars)
  → If unavailable → yfinance

IF designing / inspecting data (agent, not runtime):
  → Use cvserver MCP tools (existing floww backend capability)

IF runtime page:
  → Call floww backend endpoints that use PublicBroker under the hood
  → OR window.cvApi (goes through local proxy, auth server-side)
```

---

## What doesn't exist (don't go looking)

- **Zenith API** — Zenith is a UI tab, not a service. No API calls go here.
- **Schwab live key** — doesn't exist. Don't try to wire it.
- **Tidehunter Pro key** — not yet needed. Only Phase 4 fallback when Public API is actually limited.
