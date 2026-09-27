# ROADMAP.md — Confluence Decoder

Derived from: deploy runbook (`deploy/free/README.md`), `docs/ROUND10_PLAN.md`
(CLOSED / HISTORICAL — kept for rationale, not a live queue), `BACKLOG.md`.
Immediate phase = Oracle go-live; later phases promote actionable backlog items.
This file is the live phase tracker.

## Phase 1 — Oracle Go-Live [IMMEDIATE]

**Goal:** Public URL serving the full Decoder at $0/month, smoke test green.
**Source:** `deploy/free/README.md`; state: deploy package hardened, awaiting VM.

- [ ] 1.1 Provision Oracle Always Free ARM VM (Ubuntu 24.04; ports 22/80/443)
- [ ] 1.2 Transfer bootstrap files + read-only deploy key (`oracle-vm-deploy`);
      chmod 600; run `oracle-setup.sh`, edit `.env.prod`, re-run
- [ ] 1.3 Configure DNS (DuckDNS or owned domain) → VM public IP
- [ ] 1.4 Bring up docker-compose stack (Caddy / React static / FastAPI / Mongo);
      verify Let's Encrypt cert issuance
- [ ] 1.5 Deploy verification: `deploy/free/smoke.sh` green; `/health` +
      `/api/health` over public URL; PWA loads from the public domain
- [ ] 1.6 Post-live monitoring: backend logs, yfinance-429 fallback check
      (`FLOWW_DATA_SOURCE` switch if blocked), monthly `df -h` disk watch

## Phase 2 — Round 10 P0 Closure [CLOSED]

**Goal:** Close the three P0 tickets from `docs/ROUND10_PLAN.md` (that file is now
CLOSED / HISTORICAL; any P1/P2 item still wanted must be re-promoted into a phase here).
P0.1 conftest waiver is applied.

- [x] 2.1 Verify P0.1 acceptance: collection errors = 0 (verified 2026-08-25)
- [x] 2.2 P0.2: restore `fetch_spot_and_chains`; flip-zones non-degraded (live-verified)
- [x] 2.3 P0.3: STALE_IMPORT cleanup; ruff F401 clean (zero findings)

## Phase 3 — Public API Data Layer [CLOSED 2026-08-31]

> **Status conflict (2026-09-04):** `.planning/phases/phase-3-public-api/PLAN.md` still
> says `**Status:** PLANNING → EXECUTION` and lists tickets 3.2–3.8 as TODO. That plan
> file is stale, not this header: `backend/services/public_api.py`,
> `backend/services/public_api_adapter.py`, `backend/routes/public_api.py` and
> `backend/tests/services/test_public_api_integration.py` all exist on disk, the router
> is mounted in `backend/server.py` as `public_api_router`, and commit 94c3c89
> ("feat(public-api): Phase 3 integration — PublicBroker wired as primary data source")
> is in `git log`. Phase 3 stays CLOSED; the phase PLAN.md needs the same edit and was
> out of lane for this pass.

**Goal:** Wire PublicBroker (from `/Users/nav/backend/`) into floww as the PRIMARY data source for chains + spot. Public API first, cvserver/yfinance as fallback. Tidehunter Pro is a documented fallback-only (Phase 4, not built unless Public API is actually limited).

**Source:** `.planning/PHASE3_PUBLIC_API_PLAN.md` (deep-dive + agent roster + decision tree), `.planning/DATA_SOURCES.md`, `.planning/AGENT_CONTRACT.md`

**Agent fleet:**
- Agent 2 (you): Backend integration — copy PublicBroker → add PUBLIC_API_KEY → modify fetch_spot_and_chains_merged → new routes → tests
- Agent 3: cvserver alignment — verify fallback path, update INTEGRATIONS.md
- Agent 4: Frontend wiring — Solstice/Triad options, Zenith unchanged
- Agent 5: GSD execution — phase plans, kanban cards, tracking

**Tickets (traced to PHASE3_PUBLIC_API_PLAN.md §5):**

| - [x] 3.1 Confirm key + source model — DONE. Key: `<REDACTED — see backend/.env; rotate this key, it was committed>`. Connection model: COPY PublicBroker into floww (separate repos, no import path)
|- [x] 3.2 Copy PublicBroker → floww backend — DONE. `services/public_api.py` (1050 lines), `finnhub_client.py`, `finnhub_api.py` copied; `finnhub_client.py` + `finnhub_api.py` shipped but NOT wired in (Phase 3 only uses PublicBroker)
|- [x] 3.3 Add PUBLIC_API_KEY to floww .env + .env.example — DONE. `PUBLIC_API_KEY=*** in `.env.example`; real key in `.env` (gitignored, never committed)
|- [x] 3.4 Modify fetch_spot_and_chains_merged() — DONE. Public API first (30s timeout) → cvserver → yfinance priority. server.py patched.
|- [x] 3.5 Create `/api/public/chain/{ticker}` + `/api/public/quotes/{ticker}` routes — DONE. `routes/public_api.py` with 3 endpoints; router mounted in server.py.
|- [x] 3.6 Tests — DONE. `test_public_api_integration.py` (11 tests, all passing). Ruff clean on all 4 Phase 3 files.
|- [x] 3.7 Update INTEGRATIONS.md + docs — DONE. AGENT_CONTRACT.md, DATA_SOURCES.md, ROADMAP.md all updated.
|- [x] 3.8 Frontend wiring — DONE. Phase 5 delivered: 5.1 Solstice [c5e3b18], 5.2 Triad [a1e69bc], 5.3 Tidehunter Pro [dd14e32], 5.4 Zenith [N/A — display-only]
|- [x] 3.9 Phase 3 execution tracking — DONE. PLAN.md + REQUIREMENTS.md + kanban cards in place.

**Phase 3 delivery (commit 94c3c89):**
- 9 files changed, +2016/-5
- `backend/services/public_api.py` (1049 lines)
- `backend/services/public_api_adapter.py` (178 lines)
- `backend/routes/public_api.py` (85 lines)
- `backend/server.py` (patched: Public API priority + router mount)
- `backend/tests/services/test_public_api_integration.py` (279 lines, 11 tests passing)
- `backend/.env.example` (+PUBLIC_API_KEY template)
- `kanban/cards/agent_*_status.md` (refreshed)

## Phase 4 — Tidehunter Pro Integration [GATED]

*(Status matches `.planning/phases/phase-4-tidehunter-pro/PLAN.md`: contingency work,
do not build until live Public API limits are confirmed.)*

**Goal:** Paid-tier fallback for heatmap when Public API is limited. **Only built if Phase 3 live testing shows real Public API limits.** Don't start until Phase 3 is verified against live Public API.

- [ ] 4.1 Tidehunter Pro API assessment — endpoints, data shape, rate limits, cost
- [ ] 4.2 Fallback routing — Solstice heatmap detects Public API limit → Tidehunter Pro
- [ ] 4.3 Threshold policy — when Tidehunter kicks in vs. just waiting for Public API recovery

> **Note:** Zenith is a UI tab (legacy Skylit GEX grid), NOT a data service. API calls do NOT route to Zenith. Zenith displays data produced by Solstice/Triad/Tidehunter Pro — no API changes needed for Zenith itself.

## Phase 5 — Frontend Public API Wiring [COMPLETE 2026-08-31]

- [x] 5.1 Solstice (Heatseeker) tab: Public API chain → GEX computation pipeline [c5e3b18]
- [x] 5.2 Triad tab: multi-ticker confluence from Public API chains [a1e69bc]
- [x] 5.3 Tidehunter Pro tab: live flow from Public API (primary) or Tidehunter Pro feed (fallback) [dd14e32]
- [x] 5.4 Zenith tab: legacy display — no API changes, data comes from above layers [N/A — display-only]

Phase 5 complete. All 4 tickets delivered. Header matches
`.planning/phases/phase-5-frontend-public-api/PLAN.md` (`**Status:** [COMPLETE]`).

> **Phase-status authority (checked 2026-09-04):** `.planning/phases/` contains exactly
> three directories — `phase-3-public-api`, `phase-4-tidehunter-pro`,
> `phase-5-frontend-public-api`. Phase 4 ([GATED]) and Phase 5 ([COMPLETE]) match their
> own PLAN.md headers; Phase 3 does not (see the conflict note under Phase 3). Phases 1,
> 2 and 6 have no phase directory, so this file is their only status authority.

## Phase 6 — Backlog Promotion (2026-08-31)

**Goal:** Promote actionable backlog items from `BACKLOG.md` into numbered sub-phases
with clear scoping. Many items are already partially built — this phase is mostly
consolidation, exposure, and closing known gaps.

**Source:** `BACKLOG.md` (synced 2026-08-31). State: most phases partially built;
Phase A complete, Phase C mostly built, Phase F (paper trading) operational.

### 6.1 — Observability & Prometheus (`/metrics` endpoint) [PARTIAL — endpoint shipped, coverage gaps]

**Goal:** Expose Prometheus metrics for production monitoring. The `/metrics` route
exists and is mounted directly on the app (not via a router).

- [x] `/metrics` route — `prometheus_metrics()` in `backend/server.py`
      (`@app.get("/metrics")`), returning `get_metrics_bytes()` /
      `get_metrics_content_type()` from `backend/services/observability.py`.
      Rendering the registry offline with `backend/.venv313` gives 34 metric
      families / 92 exposition lines at import time.
- [x] Per-endpoint latency histogram + error-rate counter — `metrics_middleware()`
      in `backend/server.py` observes `floww_api_request_duration_seconds`
      (labels: route/method/status, route template when available) and increments
      `http_requests_total` (labels: method/endpoint/status). It covers every route,
      not just /api/heatmap, /api/chain, /api/spot; `/metrics` itself is skipped to
      avoid recursion.
- [ ] Data provider health counters — PARTIAL. `floww_provider_calls_total`
      (status success / failure / rate_limited) and `floww_yfinance_calls_total` are
      incremented in `backend/data_providers.py`, which covers the `FreeDataProvider`
      subclasses (Finnhub, Polygon, AlphaVantage) plus yfinance. Public API and
      cvserver are NOT instrumented (`services/public_api.py` and
      `services/cvserver_client.py` contain no `observability` import); databento only
      publishes `floww_circuit_breaker_state`.
- [ ] MongoDB connection pool metrics — none. No mongo/pool metric is defined in
      `services/observability.py`.
- [ ] Dedicated data-source fallback counter — none. Fallback has to be inferred from
      `floww_provider_calls_total` by provider label.
- [ ] Live scrape test — NOT run. `curl -s localhost:8000/metrics` returned HTTP 000
      (backend not running on this box); only the offline registry render was verified.

> Rationale: deploy runbook calls for post-live monitoring; the remaining work is
> widening metric coverage (Mongo pool, Public API / cvserver providers, an explicit
> fallback counter), not building the endpoint.

### 6.2 — Backtest engine hardening [PARTIAL — slippage fix + `/run` live 2026-08-31]

**Goal:** Fix known double-slippage bug in `services/backtest/engine.py` and add
`/api/backtest/*` routes. Engine exists but has audit-flagged issues.

- [x] Verify/fix double-slippage bug in engine.py (FIXED in commit be3b7f8 — net_pnl
      now includes entry+exit slippage; verified: expected 0.6930, actual 0.6930 MATCH)
- [x] Add `/api/backtest/run` endpoint (BUILD completed — commit ebc6715, live-tested:
      SPY backtest returns trades=1, net_pnl=0.6930)
- [ ] Add `/api/backtest/report/{ticker}` endpoint (retrieve last backtest report) —
      still missing; `routes/backtest.py` exposes only `/run`, `/is-oos`,
      `/walk-forward`, `/monte-carlo`
- [x] Write a test that fails before fix and passes after (test discipline — done in
      test_heatseeker_v2.py + test_v3_costsave.py)

### 6.3 — Alert DSL completion [PROMOTED]

**Goal:** Persist alert rules to MongoDB (currently in-memory, lost on restart) and
add alert quality dashboard endpoint.

- [ ] Persist `_alert_rules` to MongoDB (create alerts collection + CRUD sync)
- [ ] Persist `_alert_history` to MongoDB (triggered alert history)
- [ ] Add `/api/alert-quality` endpoint (quality scores per rule/tier)
- [ ] Alert YAML validation (schema check on `alerts/definitions/gex_alerts.yaml`)

### 6.4 — Quant signal exposure [PARTIAL — endpoints live 2026-08-31]

**Goal:** Expose available quant signals through a catalog endpoint. The producer
infrastructure exists (`signal_translator`, `flow_alerts`, `trading_signals`,
`composite_flow_score`, `hmm_regime`); the catalog endpoints now exist too, but they
report no per-signal health and no normalized values.

- [x] Add `/api/quant/signals` endpoint listing available signals + their state —
      `quant_signal_catalog()` in `routes/quant.py` (`APIRouter(prefix="/api/quant")`),
      mounted in `backend/server.py` as `quant_router`. Shipped in ebc6715, fixed in
      da6ba17 + cd9a8a5. `/api/quant/full` (live heatmap + GEX totals + IV surface)
      added in e0a29e8 — `quant_full()` in `routes/quant_full.py`, mounted as
      `quant_full_router`.
- [ ] Add signal health/status per ticker (which signals are active for SPY/QQQ/etc.)
      — NOT DONE. `/api/quant/signals` returns `{ticker, signals, count}` and
      `/api/quant/full` returns `{ticker, signals, spot, iv_surface, gex_totals,
      contracts, expiries, data_source}` — no `count` on `/full`, and no
      health / status / active key in either module. A producer that raises is logged
      at debug level and dropped from the list, so "which signals are active" can only
      be inferred from absence, and a signal that is down is indistinguishable from one
      that was never registered.
- [ ] Normalize factor/z-score output across signal types — NOT DONE. Each catalog
      entry carries a free-text `unit` (`label`, `z-score`, `index (-1..1)`,
      `percentile (0..1)`); no normalization layer exists in `services/`.

### 6.5 — Portfolio & P&L foundation [PROMOTED]

**Goal:** Basic portfolio state service. Paper trading exists but there's no
portfolio/P&L tracking service.

- [ ] Add `services/portfolio.py` — position state, P&L, exposure tracking
- [ ] Add `/api/portfolio/*` routes (positions, P&L, equity curve)
- [ ] P&L attribution by ticker (later: by signal, by strategy)

### 6.6 — ADR expansion [PARTIAL — 5 ADRs written 2026-08-31]

**Goal:** Document key architectural decisions that are currently implicit.

ADR numbers below were re-verified 2026-09-04 by reading every file in `docs/adr/`;
they now match the filenames and the content.

- [x] ADR-0002: Data source priority policy (Public API → cvserver → yfinance → fallbacks)
      — WRITTEN in commit 3c4019f (docs/adr/0002-data-source-policy.md)
- [x] ADR-0003: Backtest engine equity model (cash-basis, slippage deducted once)
      — WRITTEN in commit 3c4019f (docs/adr/0003-backtest-equity-model.md)
- [x] ADR-0004: Deploy CORS headers + exception-handler origin echo
      — WRITTEN in commit 3c4019f (docs/adr/0004-deploy-cors-headers.md)
- [x] ADR-0005: Test discipline (no skip/xfail on passing tests; self-written tests must
      fail before fix) + data-source assertion policy — WRITTEN in commit 3c4019f
      (docs/adr/0005-test-discipline.md)
- [x] ADR-0006: Black Friday/Ferrari coupling boundary — WRITTEN in commit 3c4019f
      (docs/adr/0006-black-friday-coupling.md, EXTRA — not in original checkbox list)
- [ ] ADR-0001: Model promotion policy — EXISTS at docs/adr/0001-model-promotion-policy.md
      (pre-existing, not part of this batch)
- [ ] Deployment policy (Oracle Always Free, docker-compose, Caddy) — NO ADR WRITTEN.
      The deploy decisions still live only in `deploy/free/README.md`; the one
      deploy-adjacent ADR is 0004, and it covers CORS headers only.
- [ ] Backend/frontend coupling (same-origin runtime, no REACT_APP_* build args) —
      NO ADR WRITTEN. ADR-0004 does not cover it (no "same-origin" or "REACT_APP"
      text in that file).
- [ ] ADR-0007: Alert persistence policy — NOT YET WRITTEN (dependent on Phase 6.3 build)

---

**Phase 6 scope note:** Items 6.1–6.6 are ordered by dependency + impact. 6.1
(Prometheus) already serves `/metrics` with request-latency and error counters, so
Phase 1 deploy monitoring is unblocked; what is left there is metric coverage.
6.2 (backtest fix) is blocking Phase E alert gating. 6.3 (alert persistence) is
blocking alert reliability. 6.4–6.6 are incremental improvements.

**Not in Phase 6 (deferred):** Phase F live execution (needs ADR), Phase G full
portfolio/P&L (6.5 is the foundation only), Phase H App.js decomposition (architect
sign-off needed), ML pipeline OOS harness (Phase C — verify `scripts/backtest_oos.py`
exists first).

## Tidehunter Pro UI redesign follow-up [PLANNED]

- [ ] Carry the latest Blademap mockup's dealer drill-down into the live UI:
      focused ticker, regime, gamma flip and distance, volatility environment,
      net gamma bars by strike, and a cumulative line on the same strike axis.
      The panel sits below the existing Lattice dealer map and opens from ticker
      and Drill actions. Preserve keyboard access and colour-blind patterns.
      Full dashboard design, build steps, drill-down requirements and included
      preview reference are in the [UI redesign v3 plan](mockups/tidehunter-pro-2026-09-05/PLAN.md).
      Shared screen-context integration belongs to the separate
      [AI implementation plan](unknowns/lodestar-plan-v4-review-draft.md), section 7.1.
      The standalone mockup was updated on 2026-09-11; live delivery remains open.
