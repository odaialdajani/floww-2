# PROJECT.md — Confluence Decoder (floww)

## Project Identity

**floww = Confluence Decoder** — a free options-intel platform. Real-time options
microstructure analytics engine that ingests live market data, computes
microstructure metrics in real time, and exposes results through a FastAPI REST
API, WebSocket streams, a React SPA (the primary UI), and an embedded Dash UI.

- **Backend:** FastAPI · Python 3.12 · port 8000 (`backend/server.py`)
- **Frontend:** React 18 SPA · create-react-app · craco · port 3000 (`frontend/src/`)
- **Databases:** MongoDB via Motor (async) + DuckDB columnar OLAP for ticks/chains/features
- **ML:** 5 production GBM models per ticker (SPY/QQQ/DIA/IWM/TLT), walk-forward CV,
  3-class predictions; truth-audit gated promotion per ADR-0001
- **Analytics core:** Numba JIT microstructure math (GEX surfaces, Greeks, VPIN,
  Hawkes, SABR/SVI vol surfaces, liquidity metrics)
- **Deploy target:** Oracle Cloud ARM Always Free ($0 forever), single docker-compose
  stack behind Caddy auto-HTTPS — runbook at `deploy/free/README.md`

A Dash app at `/dashboard/` is an embedded tab in the React UI — not a separate app.

## Scope

### In scope

- Real-time market-data ingestion (Public.com API primary; yfinance/cvserver
  emergency fallback only — Schwab + Alpha Vantage retired 2026-09-03, public-api-only policy)
- Options microstructure analytics: VPIN, GEX/VEX surfaces, Hawkes processes,
  stochastic vol (SABR/SVI), liquidity metrics, Heatseeker flip zones / stacked
  nodes / tug-of-war, Trinity confluence, Flowseeker flow analysis
- ML direction models with baseline-beat + Sharpe-sanity promotion gates
- Free-tier public hosting so friends can reach it from a URL

### Out of scope

- Live trading execution (paper-trading only; live promotion is a separate future ADR)
- Paid infrastructure beyond Always-Free tiers
- Synthetic data in production (testing only)

## Constraints

1. **Operating contract:** `CLAUDE.md` governs conventions — forbidden files
   (`ml/inference.py`, `dash_ui.py`, model artifacts, `App.js`, frontend config),
   forbidden git operations, HEREDOC commit style with inline verification evidence.
2. **Test discipline (non-negotiable):** no new skip/xfail on passing tests;
   self-written tests must fail before fix and pass after.
3. **No synthetic data in production**; every model passes the 11-check truth audit.
4. **Model quarantine:** failed-audit models excluded from live inference, not deleted.
5. **Decimal for money** (except internal microstructure float64 math).
6. **Structured logging** (structlog JSON in prod); rate limit 60 req/min/IP.
7. **Graceful degradation:** DuckDB-only mode without Mongo; statistical fallback
   without PyTorch; Public API primary with cvserver→yfinance emergency
   fallbacks on cloud IPs (Schwab/Alpha Vantage retired 2026-09-03).
8. **yfinance on cloud IPs may 429** — mitigated by caching + Public API primary.

## Locked decisions (from ADRs)

<decisions>
- **ADR-0001 (Accepted): Model promotion policy.** A model promotes to `models/`
  only when ALL of: (1) baseline-beat vs majority/persistence/logistic — fail-closed
  on missing baselines; (2) Sharpe ≤ MAX_PLAUSIBLE_DAILY_SHARPE (default 10);
  (3) no Rule-9 audit flag (sharpe > 5 or empty baselines → quarantine pending
  rolling-OOS); (4) populated `baselines` dict. Quarantine history: SPY v1.0,
  TLT v1.0, IWM v1.0. Reversal requires rolling-OOS ≥ 3 Sharpe + defending ADR.
</decisions>

## Success metric

Public URL serves the full Decoder to friend-scale traffic at $0/month with all
endpoints healthy (`deploy/free/smoke.sh` green) and test suites green
(backend 3 passed · frontend 56 suites / 409 tests · lane trio 4 suites / 178 tests · craco build clean — Phase 9 2026-09-04).

## Key documents

| Doc | Role |
|---|---|
| `CLAUDE.md` | Operating contract |
| `ARCHITECTURE.md` | System spec (four pillars, service taxonomy) |
| `docs/adr/0001-model-promotion-policy.md` | Model gate policy |
| `docs/ROUND10_PLAN.md` | Active round plan (P0/P1/P2 tickets) |
| `BACKLOG.md` | Phase A–J backlog + discovered issues |
| `deploy/free/README.md` | Oracle go-live runbook |
| `.planning/codebase/` | 7 GSD codebase intel docs |
| `.planning/LEARNINGS.md` | Session learnings (deploy prep + test infra) |
