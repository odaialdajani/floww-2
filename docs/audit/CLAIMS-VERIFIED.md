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

## Schwab retirement — mapped, not deleted

Schwab was retired as a data feed on **2026-09-03**. All market data is
**Public.com**, with cvserver / yfinance / Databento-OI as fallbacks. This
branch corrected the documentation and added guards, but deliberately did
**not** delete the code, because each piece is load-bearing for something:

| Artifact | Status | Why it stays |
|---|---|---|
| `services/schwab_streamer.py` | dead — 0 importers, no key | has a reconnect-chaos test suite (`tests/schwab/`); deleting means deciding what to do with those tests |
| `services/data_fallback.py` | dead — tests only | has a 37-reference test file; same trade |
| `services/data_quality.py::compare_gex_sources` | dead method on a **live** class | the live route correctly compares cvserver vs yfinance; removing the method touches a mounted router |
| `services/mock_schwab_feed.py` | **not dead** | synthetic tick generator behind `FLOWW_ENABLE_MOCK_FEED=1`, imported by `server.py`. The name is legacy; it makes no Schwab connection. Renaming is behaviour-neutral but deserves its own commit. |
| `prometheus/alerts` SchwabTokenExpiring | **deleted here** | watched a metric nothing emits, pointed at a route that does not exist |
| `ARCHITECTURE.md`, `CLAUDE.md`, `RUNBOOK.md` | **corrected here** | all three described Schwab as a live data source |

The guards now in `test_compose_consistency.py` fail if a Schwab host,
credential or env var reappears in live backend code, if `schwab_streamer.py`
gains an importer, if the frontend names Schwab, if a retired provider
declares an API key, or if ARCHITECTURE.md lists it as active. So the
quarantine is enforced, not merely intended.

**Follow-up worth doing separately:** delete `schwab_streamer.py` +
`data_fallback.py` together with their test suites, and rename
`mock_schwab_feed.py` → `mock_synthetic_feed.py`. That is one coherent
"finish the retirement" commit, and it is mechanical once agreed.

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
