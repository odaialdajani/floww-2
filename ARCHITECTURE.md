# ARCHITECTURE.md — Project Oracle / Confluence Decoder

## Overview

Project Oracle is a real-time options microstructure analytics engine built on four
core pillars. It ingests live market data, computes microstructure metrics in
real-time, and exposes results through FastAPI routes, a React dashboard, and an
embedded Dash UI.

## The Four Pillars

### 1. REST Market-Data Ingestion
Market data enters through the **Public.com adapter**
(`services/public_api_adapter.py` → `fetch_spot_and_chains_merged` in
`server.py`), which cascades Public.com → cvserver → yfinance, with
Databento supplying open interest. Chain data is then written to DuckDB.

**There is no WebSocket market-data feed.** `websocket_streamer.py` is
unrelated to market data — it is the *client-push* manager that broadcasts
computed results to the browser, and it is live.

Schwab was a data source until 2026-09-03 and has since been **fully removed**:
the streamer, the source-failover handler, their test suites, the Grafana
panels that queried Schwab metrics, and the token-expiry alert are all gone.
Nothing named schwab remains in live code.

`ingestion_pipeline.py` remains for the DuckDB tick/LOB write path and is
driven in development by `mock_synthetic_feed.py` — a purely synthetic GBM
generator behind `FLOWW_ENABLE_MOCK_FEED=1`. It opens no socket and reads no
credential. (It was called `mock_schwab_feed.py` until 2026-09-27; the old
name was the only Schwab thing about it, and it was misleading.)

### 2. DuckDB OLAP Engine
`duckdb_engine.py` provides a columnar analytical store for tick data, options
chains, and computed features. All services read from and write to DuckDB via
async batch writes. DuckDB handles time-series aggregation, window queries, and
joins that would be expensive in MongoDB.

### 3. Numba JIT Compilation
Computationally intensive calculations (GEX surfaces, Greeks, VPIN classification)
are JIT-compiled via Numba (`numba_greeks.py`, `gex_aggregator.py`). This brings
C-level performance to numerical Python without leaving the codebase.

### 4. Asyncio Batching
All I/O-bound operations use `asyncio` with batching. The ingestion pipeline
accumulates ticks and flushes in batches. The DuckDB writer uses a bounded queue
with backpressure. Route handlers are fully async.

## Data Flow

```
Public.com API ──┐        (primary chain + spot source)
cvserver       ──┼──→ public_api_adapter.py ──→ DuckDB (chains, ticks)
yfinance       ──┘
Databento OI   ───→ (open-interest overlay only)
                                                        ▼
                                              ┌─── services/*
                                              │
                    ┌─────────────────────────┼──────────────────────┐
                    │                         │                      │
                    ▼                         ▼                      ▼
            vpin_engine.py          gex_aggregator.py      hawkes_process.py
            anomaly_detector.py     trinity_alignment.py   stochastic_vol.py
            liquidity_metrics.py    node_lifecycle.py      flowseeker.py
                                              │
                                              ▼
                                        routes/*
                                              │
                         ┌────────────────────┼────────────────────┐
                         ▼                    ▼                    ▼
                   FastAPI REST          WebSocket /ws/*      Dash UI /dashboard/
                         │                                         │
                         ▼                                         ▼
                   React Frontend                        Embedded Plotly charts
```

## Service Taxonomy

### Phase 1 — Ingestion & Storage
| Service | File | Purpose |
|---------|------|---------|
| Ingestion Pipeline | `ingestion_pipeline.py` | Normalize and route market data |
| DuckDB Engine | `duckdb_engine.py` | Columnar OLAP storage |
| Client-Push Manager | `websocket_streamer.py` | Pushes computed results to the browser over WS (not market data) |
| Public API Adapter | `public_api_adapter.py` | The live market-data source (Public.com → cvserver → yfinance) |
| Schwab (REMOVED) | — | Retired 2026-09-03. Streamer, failover handler, tests, dashboards and alert all deleted 2026-09-27. |

### Phase 2 — Microstructure Analytics
| Service | File | Purpose |
|---------|------|---------|
| VPIN Engine | `vpin_engine.py` | Flow toxicity (Easley et al. 2012) |
| Hawkes Process | `hawkes_process.py` | Self-exciting point processes |
| SABR Model | `stochastic_vol.py` | Stochastic vol surface (Hagan et al. 2002) |
| SVI Model | `stochastic_vol.py` | Implied vol parameterization (Gatheral 2004) |
| Vol Surface Constructor | `stochastic_vol.py` | Full IV surface builder |
| Kyle Lambda | `liquidity_metrics.py` | Price impact (Kyle 1985) |
| Amihud Illiquidity | `liquidity_metrics.py` | Illiquidity ratio (Amihud 2002) |
| Market Fragility Index | `liquidity_metrics.py` | Composite fragility score |

### Phase 3 — GEX & Options Analytics
| Service | File | Purpose |
|---------|------|---------|
| GEX Aggregator | `gex_aggregator.py` | Gamma/Vomma exposure surfaces |
| GEX History | `gex_history.py` | Historical GEX analysis |
| Node Lifecycle | `node_lifecycle.py` | King Node state machine |
| Trinity Alignment | `trinity_alignment.py` | SPX/SPY/QQQ ZG confluence |
| Flowseeker | `flowseeker.py` | Options flow analysis |
| Heatseeker | `heatseeker.py` | Flip zones, stacked nodes, tug-of-war |

### Phase 4 — Anomaly Detection & ML
| Service | File | Purpose |
|---------|------|---------|
| Anomaly Detector | `anomaly_detector.py` | 1D-CNN autoencoder + statistical fallback |
| ML Features | `ml/features.py` | Feature engineering |
| ML Gate | `ml/gate.py` | Model quality gates |
| ML Registry | `ml/registry.py` | Model versioning |
| ML Quality | `ml/quality.py` | Model evaluation metrics |
| ML Training | `ml_training.py` | Training pipeline |

### Phase 5 — Intelligence & Reporting
| Service | File | Purpose |
|---------|------|---------|
| LLM | `llm.py` | AI-powered analysis |
| Briefing | `briefing.py` | Morning briefing generation |
| Social Flow | `social_flow_pipeline.py` | Social sentiment pipeline |
| UOA | `uoa.py` | Unusual options activity |

## Module Dependency Graph

```mermaid
graph TD
    A[server.py] --> B[routes/*]
    A --> C[services/duckdb_engine.py]
    A --> D[services/websocket_streamer.py]
    A --> E[services/dash_ui.py]

    B --> C
    B --> F[services/vpin_engine.py]
    B --> G[services/gex_aggregator.py]
    B --> H[services/hawkes_process.py]
    B --> I[services/stochastic_vol.py]
    B --> J[services/liquidity_metrics.py]
    B --> K[services/trinity_alignment.py]
    B --> L[services/anomaly_detector.py]
    B --> M[services/node_lifecycle.py]
    B --> N[services/flowseeker.py]
    B --> O[services/heatseeker.py]

    C --> P[services/observability.py]
    F --> P
    G --> Q[services/numba_greeks.py]

    R[services/ingestion_pipeline.py] --> C
    R --> D

    S[services/public_api_adapter.py] --> R
    T[services/ml/*] --> C
    T --> U[services/ml/features.py]
```

## Operating Laws

1. **No synthetic data in production.** All models train on real market data only.
   Synthetic data is for testing only.

2. **Truth-audit gated.** Every model must pass the truth audit (11 checks) before
   promotion. See `qc/audit/truth_audit.sh`.

3. **Model quarantine.** Models that fail audit rules are quarantined — not deleted,
   but excluded from live inference. Quarantined: SPY/TLT/IWM v1.0.

4. **Decimal for money.** All monetary calculations use `Decimal`, not `float`.
   (Exception: internal microstructure math where float64 precision is acceptable.)

5. **Structured logging.** All services use `structlog` with JSON output in production.

6. **No polling.** All data ingestion is event-driven via WebSockets or async HTTP.

7. **Rate limiting.** API routes enforce 60 req/min per IP (bypassed in TESTING mode).

8. **Graceful degradation.** If MongoDB is unavailable, the system continues with
   DuckDB-only mode. If PyTorch is unavailable, the anomaly detector falls back to
   statistical z-score detection.
