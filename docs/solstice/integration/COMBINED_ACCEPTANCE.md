# Historical combined candidate — 2 October acceptance HOLD

This report describes CODE `047153ec` and its then-current HOLDs. PR96 was later merged and Spark fixed generated docs/producer issues in PR97/98; current merged base is `08f3793c242d943ab3b61b84e5394ce4602daa0a`, with CI/CD37091898123 and lint37091898108 SUCCESS. Do not treat the old API-doc blocker below as still open. Current continuation, remaining producer requirements and model/operational blockers are in [ZED_STATE](../ZED_STATE.md) and [COMMISSIONING](COMMISSIONING.md); current [R17_ACCEPTANCE](R17_ACCEPTANCE.md) supersedes the R16 candidate, includes main6eaa3343/PR102 and PR103 coverage consumers. The old report below remains historical.

## Integrated sources

- Verified main/base: `1530ccd7f52a0de03512f383283463525a44134b`.
- Zed code: `483704fc0fe9cccd7b9578c8c7dbe859e389a974`, draft [PR95](https://github.com/odaialdajani/floww-2/pull/95).
- Spark frozen code: `1fdf403d878378eb2d4c42d517071fe9559186b7`, open [PR94](https://github.com/odaialdajani/floww-2/pull/94).
- Combined CODE head: `047153ec74d903b8c2c08d5bbfdfd176e6207a30` in `.worktrees/combined-integration-20261002`, branch `solstice/combined-integration-20261002`.
- Composition: isolated branch from frozen Spark head, cherry-picked Zed change. Merge-base with verified main is exactly the base above. No PR/main merge, deployment, service restart, order or activation.
- Contract `floww-integration.v1`; additive trace/draft/report/Pro boundary contracts remain distinct from Spark's unmounted `execution-intent.v1`.

## Actual combined checks

| Gate at combined CODE head | Result |
|---|---|
| Full required backend pytest command, UNMASKED | **7050 passed**,37 pre-existing skips; **68.79%** coverage,60% gate met;329.01s. No skip/xfail added. |
| Full frontend Jest after fresh lane npm ci | **126 suites /1091 tests passed**;25.865s. |
| Production CRA build | **PASS**, compiled during source-hash-bound browser acceptance. |
| Storybook build + state interactions/axe | **PASS**,16 states; no accessibility rule disabled. |
| Ruff0.15.22 repository gate | **PASS**. |
| Bandit configured medium gate | **PASS**. |
| Truth audit | **227 passed /0 failed**. |
| Silent-except gate | **PASS**,353 files scanned. |
| Protected manifest | **71/71 identical hashes**, zero protected changes. |
| Compiled full-app browser | **PASS**:8 direct routes/refreshes/active states, back/forward/query/hash,6 captures at1440/1280/narrow, owning contract/draft/manual bridge and replay steps/Live exit, native200% zoom;0 uncaught page errors/0 execution mutations. |
| Generated API-doc drift gate | **FAIL / ownership blocked**: saved375 paths versus actual376; missing `/api/agent/handoffs` GET/POST. Both `docs/api/openapi.json` and `docs/api/README.md` need regeneration. No shared schema file was silently edited. |
| Local Docker | **UNAVAILABLE**, daemon absent. |
| Hosted Docker / ship-runtime gates for combined head | **PENDING publication/checks**; standalone PR95 frontend/backend/Docker successes are not this combined head's proof. PR95 lint fails API-doc drift, not Ruff rules. |

Current generated browser receipt includes exact combined source commit, per-source hashes across frontend/backend services/routes/server, bundle hashes and fixture hash. It references the unchanged committed R14 synthetic engineering fixture (`8fefacf5c52d58c0271fcabd535c7eea61d5fb0ab24b134ba89b75aa5c821f12`), not live market/account/model/capture data.

`npm ci` corrected the isolated lane's exact optional fsevents2.3.2 yarn entry. That owned lock metadata is included in the receipt update; npm/package-lock/runtime source is unchanged. Watchdog-written `kanban/BOTTLENECK_ALERTS.md` remains unstaged/untouched. Other worktrees/checkpoints and protected/frozen files remain intact.

## Reproduction commands actually used

Run each from its documented directory, not from the shared dirty checkout. Interpreter is the verified existing working venv; local Python3.14.6/Node24.14.1 differ from hosted ship3.12/Node20.

From combined `backend`:

```sh
MONGO_URL=mongodb://localhost:27017 DB_NAME=confluence_decoder_test DATABENTO_API_KEY= POLYGON_API_KEY= ALPHA_VANTAGE_KEY= FINNHUB_API_KEY= OPENROUTER_API_KEY=test-key-ci GEMINI_API_KEY=test-key-ci APCA_API_KEY= APCA_SECRET_KEY= FLASHALPHA_API_KEY= MARKETSTACK_API_KEY= API_SECRET_KEY= PUBLIC_API_KEY= /Users/nav/Documents/GitHub/floww-2/backend/.venv/bin/python -m pytest tests/ -v --tb=short --cov=. -m 'not flaky_env'
ruff check . --output-format=github
/Users/nav/Documents/GitHub/floww-2/backend/.venv/bin/python -m bandit -r . --severity-level medium -q --exclude ./.venv,./tests --skip B101,B108,B301,B310,B313,B314,B324,B604,B608,B614,B615
```

From combined `frontend`:

```sh
npm ci --legacy-peer-deps --no-audit --no-fund
CI=true npm test -- --watchAll=false --runInBand
FLOWW_BROWSER_CHANNEL=chrome npm run test-storybook
npm run build-storybook
```

From combined root:

```sh
bash qc/audit/truth_audit.sh
/Users/nav/Documents/GitHub/floww-2/backend/.venv/bin/python qc/audit/check_silent_excepts.py
/Users/nav/Documents/GitHub/floww-2/backend/.venv/bin/python qc/audit/generate_api_docs.py --check
node scripts/r15_browser_receipt.cjs /Users/nav/Documents/GitHub/floww-2/backend/.venv/bin/python '/Users/nav/Library/Caches/ms-playwright/chromium-1223/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'
```

The Python full-suite exit was propagated with `&&`, unlike the earlier disclosed lane log mistake. The committed code's first commit-message browser command used path shorthand; the complete literal interpreter/browser invocation is recorded here and in the actual tool run.

## Why acceptance is not green

1. **Shared-file acknowledgment:** proposal in Zed's checkpoint is that Zed regenerates ONLY the two derivative API-doc files for owned agent routes/combined surface, preserving all Spark runtime schemas/server/routes. Spark must acknowledge in its own checkpoint, or Nav must explicitly authorize that exception. No agreement is manufactured.
2. **Producer engineering:** PR94 still has in-memory lifecycle/restart state, caller-supplied approval identity, opt-in approval/preflight, missing risk-limit enforcement, CLOSE intents affected by the entry pause, real `Order`/dict mismatch and missing vendor-clock substitution. Zed will not wire or repair those Spark files silently. Green fake-broker tests are not production executor acceptance.
3. **Operational/operator:** no durable admitted live recorder/session inventory/range producer is established; actual authenticated Sol/xhigh owner preference/dispatch and Public account/entitlements/policy remain unverified/UNSET. Native activation/control/trace ingestion are not verified APIs.

Commissioning, entry/capture/price workers, paid model work, PR merge and deployment remain OFF/unauthorized. Native private operator reports are not permission or broker verification. Underlying outcome labels and synthetic tests are not option P&L or profitable trading evidence.
