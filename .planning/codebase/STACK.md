# Technology Stack

**Analysis Date:** 2026-08-24

## Languages

**Primary:**
- Python 3.11 is the SHIPPED runtime (`requires-python = ">=3.11"` in `backend/pyproject.toml`; `Dockerfile.backend` line 1 is `FROM python:3.11-slim`; CI pins 3.11) — all backend application code (`backend/server.py`, `backend/routes/*`, `backend/services/*`) must compile on 3.11. Local dev venvs: `backend/.venv` = 3.11.15 (syntax oracle), `backend/.venv313` = 3.13.15 (the venv that actually has pytest/ruff)
- JavaScript/JSX — frontend application code (`frontend/src/`)
- Rust (edition 2021) — performance-critical math kernel (`rust/decoder-core`, crate `decoder-core`: Black-Scholes Greeks, GEX aggregation, chain normalization)

**Secondary:**
- Shell scripts (`scripts/`, `deploy/free/*.sh`)
- SQL (DuckDB DDL inline in `backend/services/duckdb_engine.py`)

## Runtime

**Environment:**
- Python 3.11.x virtualenv at `backend/.venv` (bare — no pytest/ruff; use it as the 3.11 syntax oracle); Python 3.13.x virtualenv at `backend/.venv313` (the working dev/test interpreter)
- Node.js 20+ for the frontend build (local dev box runs v24; no `engines` pin in `frontend/package.json`)
- Rust toolchain (cargo) to compile `rust/decoder-core` as a PyO3 extension module
- MongoDB 7 server (via `mongo:7` Docker image in `docker-compose.yml`)

**Package Manager:**
- pip with `backend/requirements.txt` (pinned/min-version style)
- npm for the frontend — both `frontend/package-lock.json` and `frontend/yarn.lock` present (npm/craco is primary per scripts)
- Cargo for Rust (`rust/decoder-core/Cargo.toml`)

## Frameworks

**Core:**
- FastAPI 0.136.3 + Starlette 1.3.1 + Uvicorn 0.25.0 — HTTP/WebSocket API server, entry point `backend/server.py` (`uvicorn server:app --port 8000` per `Dockerfile.backend`). Starlette is pinned explicitly in `backend/requirements.txt` (CVE reasons documented there); do NOT raise fastapi past 0.136.x without first rewriting the `app.routes` introspection tests — 0.137.0 stopped flattening `include_router()` results into `app.routes`
- React 19 (`react`/`react-dom` ^19.0.0) on Create React App 5 (`react-scripts` 5.0.1) customized via craco 7.1 (`frontend/craco.config.js` — `@` alias to `src/`, TS/ESLint plugins stripped)
- Dash ≥2.17 + Plotly ≥5.22 — embedded analytics UI mounted by FastAPI at `/dashboard/` (`backend/services/dash_ui.py`, mounted at end of `backend/server.py`)

**Testing:**
- pytest ≥8.0 (`backend/pytest.ini`, tests under `backend/tests/` including chaos/stateful/integration suites)
- Jest + React Testing Library (CRA default, via `craco test`; `@testing-library/react` ^16, `jest-dom` ^6.9)

**Build/Dev:**
- craco 7.1 overriding CRA webpack config (`@` path alias, disabled ForkTsChecker/ESLint plugins, hot devServer)
- Tailwind CSS (`tailwind.config.js`, `postcss.config.js`, `tailwindcss-animate`) with shadcn/radix component system (`components.json`)
- Cargo release profile: opt-level 3, LTO, codegen-units=1 (`rust/decoder-core/Cargo.toml`); built as cdylib+rlib PyO3 module
- Docker: `Dockerfile.backend` (python:3.11-slim base; strips torch from prod install), `Dockerfile.frontend`; orchestrated by `docker-compose.yml` / `docker-compose.prod.yml`

## Key Dependencies

**Critical (Python, from `backend/requirements.txt`):**
- fastapi 0.136.3 / starlette 1.3.1 / uvicorn 0.25.0 — API framework, ASGI toolkit (serves every HTTP request), ASGI server
- motor 3.3.1 / pymongo 4.6.3 — async MongoDB access (`AsyncIOMotorClient` in `backend/server.py`, `backend/deps.py`)
- duckdb ≥1.0.0 — embedded analytics store (`backend/services/duckdb_engine.py`)
- databento ≥0.34.0 — market data ingestion (`backend/databento_provider.py`, `backend/services/databento_oi.py`)
- yfinance 1.3.0 — fallback options/underlying data (`backend/server.py`)
- pandas ≥2.2.0 / numpy ≥1.26.0 / scipy 1.17.1 / numba ≥0.60.0 — numerical core
- torch ≥2.3.0 / scikit-learn ≥1.5.0 — ML pipeline (`backend/ml_pipeline.py`, `backend/ml_training.py`); excluded from prod Docker image
- dash ≥2.17 / plotly ≥5.22 — embedded dashboard
- pydantic ≥2.6.4, httpx 0.28.1, websockets ≥13.0, openai ≥1.30.0 (OpenRouter client), python-dotenv ≥1.0.1, prometheus-client ≥0.25.0
- iohttp-family support libs added by audit: aiohttp ≥3.9, beautifulsoup4 ≥4.12, pyyaml ≥6.0, tenacity ≥8.2, Pillow ≥10.0

**Critical (JavaScript, from `frontend/package.json`):**
- react ^19 / react-dom ^19, react-router-dom ^7.5.1 — SPA shell
- axios ^1.8.4 — backend API calls
- plotly.js ^3.5.1 + react-plotly.js ^2.6.0, recharts ^3.6.0 — charting
- Radix UI suite (~30 packages) + tailwind-merge + class-variance-authority — shadcn/ui components
- zod ^3.24.4 + react-hook-form ^7.56 — validation/forms

**Rust (`rust/decoder-core/Cargo.toml`):**
- pyo3 0.22 (extension-module feature), rayon 1.10, serde 1, libm 0.2

## Configuration

**Environment:**
- Backend config via dotenv: `backend/.env` (local), template `backend/.env.example`. Key vars: `MONGO_URL`, `DB_NAME=confluence_decoder`, `API_SECRET_KEY`, `WS_API_TOKEN`, `JWT_SECRET_KEY`, `DATABENTO_API_KEY`, `POLYGON_API_KEY`, `ALPHA_VANTAGE_KEY`, `FINNHUB_API_KEY`, `CVSERVER_API_KEY`, `FLASHALPHA_API_KEY`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `LLM_PROVIDER`, `GEMINI_API_KEY`, `FLOWW_DATA_SOURCE`, `CORS_ORIGINS`, `ENVIRONMENT`, `GFLOWS_DUCKDB_PATH`
- Production secrets template: `deploy/free/.env.prod` (adds `DOMAIN`, `ADMIN_EMAIL`); deployed via `deploy/free/docker-compose.yml`, `deploy/free/server-setup.sh`, systemd units in `deploy/systemd/`, cron in `deploy/cron.d`
- Frontend build-time var: `REACT_APP_BACKEND_URL` (set in `docker-compose.yml`)

**Build:**
- `frontend/craco.config.js`, `frontend/babel.config.js`, `frontend/tailwind.config.js`, `frontend/postcss.config.js`, `frontend/jsconfig.json`, `frontend/components.json` (shadcn)
- `backend/pyproject.toml`, `backend/pytest.ini`
- `rust/decoder-core/Cargo.toml`
- Root: `Makefile`, `docker-compose.yml`, `docker-compose.prod.yml`, `docker-compose.observability.yml` (Prometheus/Grafana: `prometheus/`, `grafana/`), `Dockerfile.backend`, `Dockerfile.frontend`

## Platform Requirements

**Development:**
- macOS, Linux or Windows with Python 3.11+ (code must stay 3.11-compatible — that is what ships), Node 20+, Rust toolchain, and a local MongoDB (or `docker-compose up mongo`)
- `backend/.env` populated from `backend/.env.example`

**Production:**
- Docker deployment (`Dockerfile.backend`: python:3.11-slim, non-root user, port 8000, `/health` healthcheck; `Dockerfile.frontend`: port 3000)
- Single-host free-tier setup scripted in `deploy/free/` (Caddy reverse proxy via `deploy/free/Caddyfile`, systemd services, cron jobs)
- Observability stack via `docker-compose.observability.yml` (Prometheus metrics endpoint exposed through `backend/services/observability.py`)

---
*Stack analysis: 2026-08-24*
*Dependency versions re-verified line-by-line against `backend/requirements.txt` on 2026-09-04 (fastapi 0.110.1 -> 0.136.3 + explicit starlette 1.3.1 for 7 CVEs; pymongo 4.5.0 -> 4.6.3; Python runtime corrected 3.12 -> 3.11).*
*Update after major dependency changes*
