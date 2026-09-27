# Audit claims: VERIFIED vs DISPROVEN against `main`

Two independent audits have now been run against this repository. Both were
written against **other commits** (`7fed6012`, and one against a separate
clone), and both contain findings that are already fixed here or were never
true at all.

This file records what was actually checked, so the same claims are not
re-investigated — or, worse, "fixed" — a third time.

**Rule adopted: no finding is actioned until it is reproduced on the current
tree.** Two fixes in the `fix/audit-2026-09` series were nearly wrong because
of that, and one batch of proposed deletions would have deleted live
components.

---

## DISPROVEN — already fixed, or never true at `main` (71f83625)

| Claim | Reality | Evidence |
|---|---|---|
| CRITICAL — brokerage reads unauthenticated | `Depends(require_api_key)` on all 5 handlers in `routes/public_brokerage.py` | `:105, :243, :313, :367, :474` |
| CRITICAL — no live-trading kill switch | `_require_live_trading_enabled()` exists and is called before an order is placed | `routes/public_brokerage.py:50, :423` |
| CRITICAL — 5 plaintext creds in `MASTER_PLAN.md` | **Zero.** Once the secret scanner was pointed at this repo, it reported 0 findings outside its own test corpus. | `grep -cE "db-[A-Za-z0-9]{20,}\|AIza…"` → 0 |
| HIGH — `torch.load` pickle RCE | `weights_only=True`, plus `_resolve_checkpoint` resolving inside a fixed base dir, fail-closed | `routes/anomaly.py:39, :78, :184` |
| HIGH — `trust_remote_code` model download | `_validate_turboquant_model` enforces a regex **and** an allowlist; `trust_remote_code` stays False | `routes/llm.py:32, :44, :178` |
| HIGH — unauthenticated dev-token minting | 403 unless `FLOWW_ALLOW_DEV_TOKENS=1` | `routes/alphapod_compat.py` |
| HIGH — WS auth fail-open | Fails closed when `WS_API_TOKEN` is set, with a constant-time compare; both frontend sockets send the token | `auth.py:verify_ws_token`; `withWsToken(...)` |
| HIGH — Caddy reverse-proxies to itself | Already `backend:8000`, with a comment explaining why `localhost` is wrong | `infra/caddy/Caddyfile:5` |
| HIGH — two heatmap math bugs live on GitHub | `R7-F04` guards present: unknown option types are skipped, never default-signed; canonical S² via `dollar_gex_per_contract` | `services/gex_core.py` (16 sites), `routes/market_data.py:274` |
| HIGH — `/api/data/quote/{ticker}` shadowed by `/{ticker}` | **Not true.** A one-segment path param cannot match a two-segment path. All 6 routes on that router were exercised and return their own distinct payloads. | live `TestClient` run against `routes.data_providers.router` |
| MEDIUM — prod compose has no mongo | Documented as intentional at the point of use: the stack requires an external `MONGO_URL`. | `docker-compose.prod.yml:32-35` |
| 17 dead frontend files | Real number is 13, and only after resolving the `@/` alias **and** `React.lazy(() => import(...))`. | commit `c2fa3288` |

## CONFIRMED and fixed (`fix/audit-2026-09`)

| Defect | Fix |
|---|---|
| `parse_osi` unpacked 4 names from a 6-group regex — every call raised `ValueError`, so the Databento OI overlay could never return data | `databento_provider.py` |
| `MultiTimeframeGEXPanel` read `net_gamma`; the endpoint returns `net_gex` — the "Net Γ" cell was permanently blank | `MultiTimeframeGEXPanel.jsx` |
| `/ws/signals` had clients but no producer — `AlertOverlay` connected and showed nothing | added `broadcast_signal()` |
| The secret-scan gate scanned `/Users/nav/Documents/GitHub/floww`, a **different repo**, so it could never gate this tree | `tests/chaos/test_secret_scan.py` |
| `lint.yml` ran the silent-except gate with `working-directory: backend` while the script sits at repo root — exit 2 on every push, so the gate never ran once | `.github/workflows/lint.yml` |
| `lint.yml` pinned Python 3.11 while everything else ships 3.12 | same |
| The `KNOWN RED` block documented a `quant.py` SyntaxError fixed five commits earlier in `d29ae3f` | same |
| `docs/api/README.md` had an **empty Path cell in all 159 rows**; the spec held 156 paths against 369 real routes | generated from the app, gated in CI |
| `CLAUDE.md` told readers to run a nonexistent Windows venv and to **never** use the one that works | `CLAUDE.md`, `README.md` |
| 13 dead frontend modules (verified by build + full jest run) | commit `c2fa3288` |

## Schwab retirement — COMPLETE (2026-09-27)

Schwab was retired as a data feed on 2026-09-03. All market data is
**Public.com**, with cvserver / yfinance / Databento-OI as fallbacks. On
2026-09-27 it was removed from the tree entirely.

**Deleted**
- `services/schwab_streamer.py` — zero importers, no key, unreachable host
- `services/data_fallback.py` — Schwab-primary failover, tests only
- `tests/schwab/`, `test_schwab_streamer_reauth.py`,
  `test_schwab_streamer_reconnect.py`, `test_data_fallback.py`
- `tests/integration/test_api_resilience.py` — 15 of its 19 cases tested the
  two deleted modules. The 4 circuit-breaker cases exercised the **live**
  `services/circuit_breaker.py` and were salvaged into
  `tests/integration/test_circuit_breaker.py`.
- `tests/integration/test_network_resilience.py` — 4 Schwab-specific cases
  removed; the 7 feed-based resilience cases (offline mode, data integrity,
  no-loss-during-outage, graceful degradation, multi-symbol, recovery) kept.
- Grafana panels "Schwab API Calls vs Daily Limit" and "Schwab Token TTL" —
  both queried metrics that no longer exist.
- The `SchwabTokenExpiring` Prometheus alert and the RUNBOOK row for it.

**Renamed**
- `mock_schwab_feed.py` → `mock_synthetic_feed.py` (`MockSchwabFeed` →
  `MockSyntheticFeed`). It was never a Schwab connection: no socket, no
  credential, no network — a GBM random generator modelled on the old
  streamer's message shape. Live via `FLOWW_ENABLE_MOCK_FEED=1`.

**Corrected**
- `ARCHITECTURE.md`, `CLAUDE.md`, `RUNBOOK.md`, `deploy/free/README.md`,
  `HEATSEEKER_ARCHITECTURE.md`, and the four `.claude/commands/` checklists
  all described Schwab as a live data source. `CLAUDE.md` and the agent
  commands also documented a `FLOWW_ENABLE_LIVE_SCHWAB` kill-switch that was
  removed some time earlier; they now describe the real control,
  `ALLOW_MARKET_ORDERS = False` in `services/order_router.py`.
- `FLOWW_ENABLE_LIVE_SCHWAB=0` dropped from two test env fixtures.

**Guards** (`tests/test_compose_consistency.py`): no Schwab host, credential
or env var in live backend code; the deleted modules must not reappear; the
streamer must never gain an importer; the frontend must not name Schwab; no
retired provider may declare an API key; ARCHITECTURE.md must not list one
as active.

Left alone: dated historical logs (`MORNING_BRIEFING.md` and the `ROUND*` /
`DISPATCH*` / `LAUNCH_PROMPTS*` records) which describe what was true when
written. Rewriting history would be dishonest.

## Still open — needs a human, not a code change

- **Secret rotation.** Anything ever committed (`db-PBRQ…` and others) is in
  git history. Rotate at the provider first, *then* purge history. History
  rewrites are not made without explicit authorization.
- **prod compose mounts `./frontend/build`**, which is not in the repo and is
  not built in that stack. Whether to build it into the image or document the
  deploy step is a deployment decision.
- The dead-code inventory for `scripts/` (54 files) was not re-derived at
  scale. The frontend list was re-derived and the reported number was wrong by
  a third, so treat the script count as unverified too.
- **`feedTabs.js` is unreferenced by the app but deliberately kept** — 58 lines
  of real logic with an 87-line test suite that `filterState.test.js` depends
  on. "Not imported by the app" is not the same as "dead".

## Method note

Both front-end dead-code passes, and one of the two secret-scan findings, were
wrong on the first attempt. Every deletion in this series was gated on a real
`craco build` and a full `jest` run rather than on static analysis — the build
is what caught the `React.lazy` import that the analysis missed.

**A static claim that disagrees with a build is a bug in the analysis.**

---

## Fan-out audit outcome (4 parallel subagents, 2026-09-27)

Four audits ran against disjoint areas: Triad, documentation, Solstice
backend↔frontend contracts, and dead-ends/broken-wires. Findings are
separated by whether acting on them was correct.

### Real defects, fixed

| Area | Defect | Fix |
|---|---|---|
| Solstice | Charm tab read `grid.charm_grid`, which the **vendor-greek** path never emitted — always "surface unavailable" | `compute_charm_grid_local` + `server.py` wiring, with honest `PARTIAL_CHARM_COVERAGE` |
| Solstice | `WallInspector` read `grids.grid.vex_grid`; `metrics.grids` is a **map of named overlays**, so `grids.grid` was always undefined | read `grid.vex_grid`; dashboard passes the real `grid` |
| Solstice | The test fixture for the above **encoded the same bug**, so it passed while broken | fixture corrected to the real shape |
| Triad | IV / Delta / per-row expiry read from the heatmap payload, which has **none of them** (27 aggregate keys, verified by calling the route) | repointed at fields that exist |
| Triad | `row.expiry \|\| expiries[0]` requested the **wrong contract expiry** on row click | expiry resolution from grid keys / `expiries_used` |
| Triad | `handleRowClick` `useCallback` omitted `data` — a real staleness bug | dep added |
| Docs | `CLAUDE.md` claimed `OrderRouter` "has no callers", so its MARKET gate "protects nothing" — `discord_bot.py` builds it | corrected |
| Docs | `RUNBOOK.md` pointed operators at `:3000` for Grafana after it moved to `:3001` (my own regression) | fixed, with a guard |
| Docs | `HEATSEEKER_ARCHITECTURE.md` still presented Schwab/Alpha Vantage as the ingestion source in 6 places (my own regression) | corrected |

### Reported, then DISPROVED — deliberately not "fixed"

These were raised as defects and turned out to be correct designs. Acting on
them would have caused harm.

- **`sweep_watch.note_sweep()` is never called.** The health endpoint reports
  `age_s: None` with the note "pending B hook" rather than a fabricated zero
  (`routes/health.py:69-70`). That is the app's honesty rule working: unknown
  is not zero. Wiring the hook would require a sweep loop that does not exist.
- **`/api/agent/claims` always returns `[]`.** It returns `[]` with a
  `"note": "no db"` when there is no database, and a 503 with a real message
  on failure (`routes/agent.py:243-257`). Nothing is fabricated.
- **DUCKDB_PATH is never set.** The code defaults to `:memory:` and reports
  `durable: false` rather than claiming a save. That is honest; the real gap
  was that the switch was undocumented, now fixed in the RUNBOOK with a test.
- **Alpaca env vars are set by no file.** Alpaca is **paper trading only**
  (`alpaca_client.py` hardcodes `https://paper-api.alpaca.markets`), so an
  unset key degrades the paper broker, not live money. The "mismatch" was
  between docs that used different spellings for the same variable.

### Lesson recorded

Three of my own fixes in this branch were caught being wrong by the guards
added for earlier fixes: an incomplete Grafana port rename, a partial Schwab
removal, and a provider test that matched method names instead of the client
variable and so passed with a real violation injected. A guard that has never
failed is not evidence of anything.
