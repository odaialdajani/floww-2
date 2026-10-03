# R17 combined acceptance — reviewable, commissioning HOLD

## Exact composition

- Current verified main/base: `6eaa3343655a30fd38c40abaa6a903e8d3814530`.
- Includes PR102 fix `90f96227bbeb61ff5066274205e39206b048d4e6`: disarmed supersede cancels nothing. Ancestry verified; the regression is included in the full backend run.
- Prior Zed/combined PR101: `dcbc14926882d36d85c5b8647bf51d9052197af5`.
- Frozen Spark PR103 runtime: `611f3c2f71525d03ea77c5252c1c81642d424072`.
- **Tested combined CODE: `4bcc6f39c814abc6e40084af9c8b89a5c0983296`**, draft [PR104](https://github.com/odaialdajani/floww-2/pull/104), branch `solstice/zed-r17-integration-20261003`.
- Later Spark receipt/checkpoint head `d7f643a83ef49276254869f2b97dbb294a12593f` was merged locally into composition/metadata head `aaf49192ad577644c6da4b7ef4c236ee169a1c0d`. It changes only Spark's two documents; they are preserved verbatim. `git diff 4bcc6f39 aaf49192 -- frontend backend scripts .github qc` is empty. Later receipt HEAD is obtainable from PR104/git, not substituted for tested CODE.
- No GitHub PR merge, main push, deployment, existing-service restart, scheduler, activation, paid model turn or order by Zed. Old R14/R16 receipts remain historical. Local branch composition is not a production merge.

## Owned implementation and contracts

`floww-integration.v1` now consumes Spark `coverage-read.v1`. Existing replay/metric/trace/non-executable draft/native-handoff/TideHunter versions stay unchanged.

- ReplayStrip has explicit stored NY session inventory, empty/error/version/ticker admission, date selection, symbol/date reset and independent abort/generation guards. No index count claims capture readiness or complete gap coverage.
- Coarse last-two comparison fetches owning-pair admission before displaying numbers. Only matching IDs, version and literal admitted=true pass. Refusals hide arithmetic; starting another request/step, changing symbol/session or leaving replay clears obsolete numbers and prevents late restoration.
- Solstice provides an accessible **read-only**14–60 listing disclosure. It checks version/ticker/window/freshness/fetched observation and explains first12 listed-expiry limits. It does not mutate the map/selection, compute replacement Greeks, invoke Lodestar, choose contracts or read today's inventory during replay. The range-map control stays disabled with an updated truthful reason.
- New synthetic coverage fixture, four additional production stories and browser interactions cover these consumers. Existing comparison smoke fixture now declares ticker/pair admission; its assertions are retained rather than skipped/weakened.
- App.js change is one blocker sentence only. No package/dependency/server/schema/API-doc/producer/protected/watchdog edits by Zed. Spark files arrived from committed branch composition; Spark's other worktree/dirty files were not staged or overwritten.

## Checks actually executed at CODE4bcc6f39

| Check | Actual result |
|---|---|
| Full backend, unmasked, coverage-bound, not flaky_env | **7076 passed /37 existing skips /68.90%**, 60% gate met;296.05s. Blank vendor credentials, test Mongo DB, execution/capture/price/outcome flags OFF. No new skip/xfail. |
| Full frontend Jest | **126 suites /1115 passed**,32.253s, after fresh npm ci. |
| Focused replay/Triad/display sweep | **5 suites /120 passed**. Before implementation11 replay tests and8 expiry tests failed on absent inventory/admission behavior. |
| Storybook interactions and axe | **20 passed** across4 story files; no accessibility rule disabled. |
| Production CRA and Storybook builds | **PASS**. Production browser harness rebuilt and verified unchanged source/bundle hashes. |
| Ruff0.15.22 full backend | **PASS**. |
| Configured Bandit medium gate | **PASS**, separately fail-fast checked. |
| Truth audit | **227 passed /0 failed**; existing unverified-model SKIP lines remain disclosed, not profitability proof. |
| Silent-except gate | **PASS**,353 files. |
| Generated API-doc gate | **PASS**,379 paths. Spark-owned generation untouched. Existing root HEAD duplicate operation-ID warning retained. |
| Protected TideHunter/Flowseeker manifest | **71/71 git-object hashes unchanged**. Manifest SHA256 `c5bea4270f1b6a79d60c22468db261644d43dcf2ee5aeb653cad4a3fff1e6e94`. |
| Compiled complete-app browser | **PASS**,8 routes/direct links/refresh/active state, back/forward/query/hash,6 captures1440/1280/390, native200% zoom, Expand/selection, dated stored sessions/play/pause/scrub/steps/Live exit, admitted/refused comparison, expiry listing, owning contract/draft/manual bridge. **0 page exceptions /0 execution mutations**. |
| Current catalog via actual CodexBridge.catalog | **gpt-6.1-sol/xhigh supported**, fetched3 Oct05:47UTC. Default effort low, speeds default/priority. No owner save or effective dispatch was performed/verified. |
| Hosted ship-runtime CI/CD, lint and Docker | **SUCCESS on exact CODE4bcc6f39**: backend-tests14m29s, frontend-build2m59s, Docker3m21s, Ruff2m27s. CI/CD37100591587, lint37100591569. All four confirmed by bounded `gh pr checks104 --watch`. The later receipt-head checks are separate: at receipt publication pending, not claimed green; final results must be read on [PR104 checks](https://github.com/odaialdajani/floww-2/pull/104/checks). |

Local Python3.14.6/Node24.14.1 differ from ship Python3.12/Node20. Hosted exact-head checks are required. No local Docker build is claimed. React act, npm deprecation/peer, Vitest provider-options, FastAPI lifespan and build-size warnings remain disclosed.

## Browser/fixture receipts and previews

[Production preview index](README.md) links all screenshots and stories. [Browser receipt](evidence/browser-receipt.json) binds source commit4bcc6f39,664 source hashes and bundle hashes. It includes coverage GET identities, no execution mutations and actual chrome.tabs.setZoom(2) proof (1440→720 CSS pixels, DPR2, CSS zoom1, visual scale1). Captured document width matches viewport at1440/1280/390; matrices own their horizontal scrolling. Native zoom is not CSS/pinch emulation.

- Original R14 backend-generated synthetic fixture SHA256: `8fefacf5c52d58c0271fcabd535c7eea61d5fb0ab24b134ba89b75aa5c821f12`.
- R17 synthetic coverage fixture SHA256: `86051a7e89a86319dc26e2793d3f0b5a6653f8990600a0a72aa9b5e56ad9f641`.
- Browser receipt SHA256: `90e7ae76b9d72436be28d8e6c20425fdc30b4110f108c883c4088200cbe2306b`.
- [Fresh catalog receipt](evidence/lodestar-catalog-r17.json) is catalog-only, not settings/dispatch proof.

Browser traffic is fixture-isolated; account reads/research drafts are simulated.20 console warnings include intentionally blocked resources and existing icon warnings; no zero-warning claim. The first-use install overlay remains in captures and can obscure part of the narrow matrix. These checks do not replace Nav's visual review, real feed/reconnect rights, authenticated account or live capture commissioning. No browser/Storybook/Sentry/Public/Codex-task MCP is exposed; local CLI use does not establish connected/authenticated connectors or remote Sentry delivery.

## Remaining requirements — not all external

Concrete producer request: [PR103 comment](https://github.com/odaialdajani/floww-2/pull/103#issuecomment-5966038604). Spark/Cline owns the response and its checkpoint; Zed does not edit it to manufacture acknowledgment.

1. **Producer engineering:** NY session index versus timestamp-prefix manifest/attribute must agree for overnight/offset records. Complete admitted14–60 chain/map projection and reversed-bound refusal remain missing. FirstN expiry verdicts do not establish complete range coverage. Comparable gate admits declared ticker/provider/query/formula/session/order; it does not add independent metric-population provenance.
2. **Execution engineering:** unmounted injected lifecycle still has optional approval/preflight, supplied-field approval rather than authenticated server-stored approval, absent-budget/buying-power skip, optional/process-local rather than durable account-wide risk/native/open/unknown inventory and unresolved multi-writer exclusion/protection admission. Existing mounted Public venue gate/cancel route stays unchanged. Operator policy cannot substitute for these controls, and no new broker-reachable boundary is authorized.
3. **Lodestar owner operation:** authenticated owner explicitly saves catalog-supported Sol/xhigh; separately authorized grounded turn must prove effective model/effort/context trace. Zed did not guess owner, bypass auth or issue a paid turn.
4. **Operational/operator:** admitted production records surviving restart; exact Public account/rights/entitlements and every commissioning policy value; native workflow review/activation; licensed feeds/SPX rights; Nav visual review. Current zero-durable census is a prior documented report, not a new production-store census by this session.

[Commissioning packet](COMMISSIONING.md) keeps all values **UNSET**. Native bridge is manual/reviewed, not remote invocation/activation. Entry pause11:30–14:00NY is a required new-entry policy, not an enacted gate in a copied brief; risk exits/protection/reconciliation stay active under later supported execution. Underlying labels/synthetic fixtures/green CI are not realized option P&L or evidence of profitable options trading.

## Reproduction / continuation

From this isolated lane backend, using the existing root venv:

```sh
MONGO_URL=mongodb://localhost:27017 DB_NAME=confluence_decoder_test DATABENTO_API_KEY= POLYGON_API_KEY= ALPHA_VANTAGE_KEY= FINNHUB_API_KEY= PUBLIC_API_KEY= OPENROUTER_API_KEY=test-key-ci GEMINI_API_KEY=test-key-ci APCA_API_KEY= APCA_SECRET_KEY= FLASHALPHA_API_KEY= MARKETSTACK_API_KEY= API_SECRET_KEY= FLOWW_ENABLE_LIVE_PUBLIC=0 FLOWW_RECORDER_WORKER=0 FLOWW_PRICE_PATH_PRODUCER=0 SOLSTICE_OUTCOME_WORKER=0 /Users/nav/Documents/GitHub/floww-2/backend/.venv/bin/python -m pytest tests/ -q --tb=short --cov=. -m 'not flaky_env'
ruff check .
/Users/nav/Documents/GitHub/floww-2/backend/.venv/bin/bandit -r . --severity-level medium -q --exclude ./.venv,./tests --skip B101,B108,B301,B310,B313,B314,B324,B604,B608,B614,B615
```

From frontend:

```sh
CI=true npm test -- --watchAll=false --runInBand
FLOWW_BROWSER_CHANNEL=chrome npm run test-storybook
npm run build-storybook
```

From the lane root:

```sh
node scripts/r15_browser_receipt.cjs /Users/nav/Documents/GitHub/floww-2/backend/.venv/bin/python '/Users/nav/Library/Caches/ms-playwright/chromium-1223/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'
gh pr checks 104 --watch --interval 20
```

Watch is bounded by the caller; timeout is pending, not success. Before further mutation fetch current main/PR103 and read both checkpoints. Continue an owned consumer only when a concrete producer change unblocks it. Preserve watchdog dirt and old worktrees; do not auto-merge, deploy, restart, re-arm or claim background work after the session closes.
