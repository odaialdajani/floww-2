# Confluence Decoder — Heatseeker GEX Terminal

Institutional-grade options analytics terminal. Replicates and extends skylit.ai functionality with real-time GEX analysis, options flow, and advanced volatility analytics.

## Features

- **GEX Heatmap** — 2D strike×expiry gamma exposure visualization with positive/negative gamma zones
- **Options Chain** — Full chain with Greeks (Δ, Γ, V, Va, Ch), GEX, vanna/charm exposure, moneyness
- **Multi-Timeframe GEX** — 0DTE, 1DTE, weekly, monthly GEX breakdowns
- **Advanced Analytics** — Implied PDF, market regime detection, hedge impulse curve, pressure cloud, charm integral
- **Unusual Options Activity** — Sweep detection, block trades, volume/OI anomaly scoring
- **Alerts** — Configurable GEX cross, spike, OI spike, IV spike alerts
- **Portfolio Tracking** — Position management, Greek aggregation, scenario analysis, hedge calculator
- **Live WebSocket Streaming** — Real-time GEX updates via WebSocket
- **Trinity View** — SPY/QQQ/^SPX confluence analysis

## Tech Stack

- **Backend:** FastAPI + Python 3.12
- **Frontend:** React 19 + Tailwind CSS + Recharts
- **Database:** MongoDB (snapshots, alerts, portfolio)
- **Data:** Databento (OPRA OI), yfinance (IV/chains), Polygon (aggregates)

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- MongoDB running locally
- Databento API key (Historical access)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Create .env from template
cp ../.env.example .env
# Edit .env with your Databento API key

# Run
uvicorn server:app --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install

# Development (separate local backend on port 8000)
cp .env.example .env.development.local
npm start

# Production build
npm run build

# Serve the prebuilt bundle on :3000 (proxies /api/* + /ws/* to :8000)
#
# Two startup options — both render the prebuilt bundle in frontend/build/:
#
#   1. Node (permanent, this repo's preferred path)
#      node frontend/serve.js
#      Requires the ajv-keywords/ajv v8 compatibility pin in
#      frontend/package.json (ajv-keywords@5.1.0 + ajv@^8.17.0).
#      If a future `npm install` breaks ajv-keywords, recover with:
#          rm -rf frontend/node_modules/ajv-keywords \
#                 frontend/node_modules/.package-lock.json
#          (cd frontend && npm rebuild ajv-keywords)
#
#   2. Python (documented dev fallback — no Node toolchain needed)
#      python3 frontend/static_proxy.py
#      Sidesteps the ajv-keywords/ajv v8 incompatibility entirely.
#      ~90 LOC, mirrors frontend/serve.js line-for-line.
```

### Docker

```bash
docker-compose up --build
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/heatmap/{ticker}` | GEX heatmap with strikes, nodes, patterns |
| `GET /api/chain/{ticker}` | Full options chain with Greeks |
| `GET /api/advanced/{ticker}` | All advanced analytics (PDF, regime, impulse, cloud, charm) |
| `GET /api/gex-timeframes/{ticker}` | Multi-timeframe GEX breakdown |
| `GET /api/uoa/{ticker}` | Unusual options activity |
| `GET /api/regime/{ticker}` | Market regime detection |
| `GET /api/implied-pdf/{ticker}` | Implied probability distribution |
| `GET /api/hedge-impulse/{ticker}` | Hedge impulse curve |
| `GET /api/pressure-cloud/{ticker}` | Pressure cloud zones |
| `GET /api/charm-integral/{ticker}` | Charm integral (time decay pressure) |
| `GET /api/alerts` | List alerts |
| `POST /api/alerts` | Create alert |
| `DELETE /api/alerts/{id}` | Delete alert |
| `GET /api/portfolio/{name}` | Get portfolio |
| `POST /api/portfolio/{name}/position` | Add position |
| `GET /api/trinity` | Trinity (SPY/QQQ/^SPX) confluence |
| `WS /ws/gex/{ticker}` | WebSocket live GEX stream |
| `GET /health` | Health check with dependency status |

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1` | Trinity view |
| `2` | Heatseeker |
| `3` | Portfolio |
| `G` | Grid heatmap view |
| `B` | Bar heatmap view |
| `C` | Options chain view |
| `D` | Day mode (±15%) |
| `S` | Swing mode (±25%) |
| `X` | Scalp mode (0DTE, ±2%) |
| `E` | GEX overlay |
| `V` | VEX overlay |
| `H` | Charm overlay |
| `↑/↓` | Cycle tickers |
| `?` | Show shortcuts modal |

## Testing

```bash
# Backend integration tests
cd backend
source .venv/bin/activate
python -m pytest tests/ -v

# Load test
python scripts/load_test.py
```

## Project Structure

```
confluence-decoder/
├── backend/
│   ├── server.py           # Main FastAPI app
│   ├── bs_greeks.py        # Black-Scholes Greeks
│   ├── vol_analytics.py    # IV surface, skew, RV
│   ├── advanced_analytics.py  # PDF, regime, impulse, cloud, charm
│   ├── portfolio.py        # Position tracking
│   ├── databento_provider.py  # Databento integration
│   ├── tests/
│   │   └── test_api.py     # Integration tests
│   └── logs/               # Application logs
├── frontend/
│   ├── src/
│   │   ├── App.js          # Main app component
│   │   ├── components/     # React components
│   │   ├── hooks/          # Custom hooks (WebSocket, debounce)
│   │   └── lib/            # Helpers, utils
│   ├── build/              # Production build
│   └── serve.js            # Static file server
├── scripts/
│   ├── warm_cache.py       # Pre-fetch yfinance data
│   ├── warm_endpoints.py   # Pre-warm backend cache
│   └── load_test.py        # Load testing
├── Dockerfile.backend
├── Dockerfile.frontend
├── docker-compose.yml
└── .env.example
```

## License

Proprietary — All rights reserved.
