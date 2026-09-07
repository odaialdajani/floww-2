# Architecture Decision Records — Index

ADRs capture architecturally significant decisions with their context and
consequences. Numbered sequentially; never rewritten — supersede instead.

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [0001](0001-model-promotion-policy.md) | Model promotion policy (4 gates) | Accepted | 2026-07 |
| [0002](0002-data-source-policy.md) | Data source policy & priority chain (Public API → cvserver → yfinance + Databento) | Accepted | 2026-08 |
| [0003](0003-backtest-equity-model.md) | Backtest engine equity model (cash-basis, single slippage deduction) | Accepted | 2026-08 |
| [0004](0004-deploy-cors-headers.md) | Deploy CORS headers & exception handler origin echo | Accepted | 2026-08 |
| [0005](0005-test-discipline.md) | Test discipline & data-source assertion policy | Accepted | 2026-08 |
| [0006](0006-black-friday-coupling.md) | Black Friday / Ferrari coupling boundary | Accepted | 2026-08 |
| [0007](0007-alert-persistence.md) | Alert persistence policy (MongoDB-backed rules + history) | Accepted | 2026-09 |
| [0008](0008-agent-tool-boundary.md) | Lodestar agent tool boundary (read-only research) | Accepted | 2026-09 |

## Conventions

- Filename: `NNNN-short-title.md` (zero-padded, lowercase, hyphens)
- Sections: Status / Context / Decision / Consequences
- Superseding an ADR: mark the old one `Superseded by NNNN`, link both ways

## Candidate decisions worth recording (from BACKLOG / GSD CONCERNS)

- DuckDB engine lifecycle & teardown registry (`services/duckdb_engine.py`)
- Module-global singleton memoization pattern in routes (hazard documented in `.planning/LEARNINGS.md`)
- torch excluded from production image (`Dockerfile.backend`)
- Mongo FTDC disabled + healthcheck rationale (`deploy/free/docker-compose.yml`)
