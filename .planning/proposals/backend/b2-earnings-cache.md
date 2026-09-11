# PROPOSAL (apply-blind): B2 Finnhub earnings-calendar cache

Status: PROPOSAL-ONLY. Owner lane: architect/backend.

## 0. Verify first
1. Confirm `finnhub-python` exposes `earnings_calendar(_from, to)` in the
   pinned version (no earnings method exists in
   `services/finnhub_client.py` today — quote/chain/profile/news only).
   If absent, call the REST endpoint directly with `requests` + env key.
2. Confirm free-tier shape + the 1-month history limit on a live call
   before freezing the schema.

## 1. Design (do NOT reuse the retired path)
- `routes/alpha_advantage.py:136-138` (`GET /earnings/{ticker}`) is
  RETIRED (`_gone` → Finnhub). New route: `GET /api/data/earnings/{ticker}`
  (fresh namespace, no compat baggage).
- Client: new `earnings_calendar()` on the existing Finnhub client
  (`services/finnhub_client.py`, key from env only — precedent line 34,
  never a new key path).
- Cache: 24h TTL per ticker (earnings dates move slowly) + `stale`
  envelope on miss-hit; aggressive because free tier is 60/min shared
  with quotes.
- Honesty: Finnhub history caps at ~1 month → response carries
  `history_limited: true` always; missing/unknown date → typed
  `{ daysTo: null, state: "missing"|"unknown" }`, never zero or a guess
  (matches Agent 2 `context/earningsProximity.js` contract).
- No surprise/SUE series: PEAD stays BLOCKED (no new vendor).

## 2. Fixture (pytest sketch, recorded response)
- Recorded calendar payload → endpoint returns mapped shape +
  `history_limited: true`; second call within TTL → zero upstream calls.
- Unknown ticker → typed missing state, 200 (not 404 — it's data-empty,
  not route-missing).

## 3. OpenAPI sketch
- `GET /api/data/earnings/{ticker}` → `{ ticker, next_earnings_date,
  daysTo, history_limited: true, asof, stale }`.

## 4. Acceptance
7-day paper run: upstream calls/day ≈ tickers (not polls); every
response carries asof + stale; unknown tickers never 500.
