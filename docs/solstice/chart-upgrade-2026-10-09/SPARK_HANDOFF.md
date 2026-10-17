# OpenCode Spark 1.3 — bounded implementation handoff

Canonical repo: `/Users/nav/Documents/GitHub/floww-2`.
Packet: `docs/solstice/chart-upgrade-2026-10-09/`.
Task: improve the React ticker candle workspace; **preserve the current heatmap**. The packet is a researched plan, not a claim that features are installed.

## Model identity — actually discovered

`opencode models` exposed:
- `opencode/muse-spark-1.3-contributor-free`
- `openrouter/meta/muse-spark-1.3`
- `openrouter/meta/muse-spark-1.3-contributor`
- `nvidia/z-ai/glm-5.3`

Use the first as the default OpenCode-hosted Spark candidate, or the configured OpenRouter alternative when that is the user's intended provider. These are **catalog identifiers**, not evidence of Spark inference/account availability. No Spark implementation run was launched during research. Do not rename the model to a guessed `spark-1.3` API slug.

Research used `nvidia/z-ai/glm-5.3` in isolated read-only OpenCode runs and attempted bounded direct `z-ai/glm-5.3` source-packet reviews at NVIDIA NIM. A real NIM completion returned that model and the requested connectivity phrase. Three initial tool-agent lanes timed out; the data/replay lane completed. All four direct followups were also incomplete (reasoning-budget exhaustion or HTTP timeout); **none is counted as a review result**. NVIDIA's model-specific documentation identifies low/high/max reasoning with max as default; a low-effort connectivity attempt also timed out. The remaining source/engine/UX/test audits were completed by the parent from real source/docs/tests, with a separately identified native-model refuter completing independent review; eight findings were applied before packet acceptance. See `EVIDENCE.json` and `RESEARCH_REPORTS.md` for completion, limits and adjudications.

## Read order and absolute prohibitions

1. Current repo `CLAUDE.md`, git branch/HEAD/status and active lane instructions.
2. `MASTER_PLAN.md` for decisions/current code, then `CONTRACT.md` for data/time/math semantics.
3. `CAPABILITIES.json` to see what is supported/new/data-gated/deferred.
4. `IMPLEMENTATION_TASKS.json` for exactly one ready block and its five microsteps.
5. `EVIDENCE.json` and current packet gate: evidence is historical, so recheck installation/runtime before relying on it.

Do not rewrite the dashboard, remove the existing heatmap controls, change formulas/model artifacts, rebase/reset/clean others' work, start/restart another owner's service, modify credentials or package frozen files. Existing dirty files are unrelated WIP; never stage or repair them to make a chart task green.

Architect-frozen paths include `backend/services/ml/inference.py`, `backend/services/dash_ui.py`, `backend/tests/conftest.py` unless a specific waiver applies, `backend/models/` artifacts, `frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`, and `frontend/src/App.js`. If an implementation needs one, stop that change and ask Nav for explicit scope approval. The proposed Lightweight Charts dependency is **not** pre-approved by this packet.

## Launch only the first ready task

The following is a future execution command, not executed as part of this research. The `--pure`, `--model`, `--dir` options were checked against the local CLI help. Do not add `--auto` or secretly change persistent OpenCode/Hermes config.

```bash
/Users/nav/.opencode/bin/opencode run --pure \
  --model opencode/muse-spark-1.3-contributor-free \
  --dir /Users/nav/Documents/GitHub/floww-2 \
  --title 'Solstice chart B01 contract only' \
  'Read CLAUDE.md and docs/solstice/chart-upgrade-2026-10-09/SPARK_HANDOFF.md. Read MASTER_PLAN.md, CONTRACT.md and IMPLEMENTATION_TASKS.json. Implement ONLY B01 one fixture and invariant at a time. Preserve all unrelated WIP and forbidden files. Do not install dependencies, restart services, invoke brokerage writes, commit or push. Show actual RED then GREEN receipts and explicit owned diff. If a prerequisite fails, report it without inventing results. Do not proceed to B02 or another block.'
```

Change the prompt/approval only after a task-specific review. A model being free/contributor does not relax acceptance or secret controls. Keep research review agents read-only, allowlisted public sources only, no `.env`/credential files, no nested task spawning or shell writes. Implementation workers get bounded owned file lists; reviewers do not get broker credentials.

## Safe parallel lanes

One integration owner controls `PriceNodeHistory.jsx` and `SkylitDashboard.jsx`.
- Contract/data lane: B01 → B02/B03; additive service/route fixture changes.
- Render lane: B04 candidate spike after package gate, then B06 integration after B05.
- Pure-state lane: exposure ranking and pane reducer tests; do not independently alter renderer integration.
- Persistence/drawing lane: schemas/pure reducers after agreed contract; server-auth task B13 separately reviewed.
- Review lane: spec compliance first, then code quality/security/provenance. Review exact task diff and run named batteries; never blanket-mark all downstream features accepted.

Scheduling is release-specific: B04 may return a measured Plotly-only discovery verdict; B13 may report account identity unavailable while local drawing presets proceed; B23 has independent bar/calendar and tape-profile variants. Select an R1/R2/R3 profile and enumerate enabled capability IDs plus accepted variant dependency closure before B28/B29. Discovery-unavailable and explicit deferral are not implementation GREEN, but do not stall unrelated supported releases. Serialize shared price_history router and chart_capabilities edits under one owner.

Later tape-dependent tasks begin with B19 commissioning, not with UI that assumes trades exist. There is no requirement to buy vendor data or reproduce Nexus/paid plugins to complete the basic candle upgrade. Any unsupported capability remains visibly unavailable with its reason.

## RED → GREEN protocol for every invariant

For the selected block:
1. Read exact existing sources/callers and current runtime/ownership. Capture branch/HEAD/own-files baseline.
2. Write a tiny explicitly synthetic fixture and one assertion; run the listed command and inspect the actual failure. A missing test runner/import/path is a setup blocker, not TDD RED.
3. Implement the minimal allowed code for that assertion. No generalized plugin framework or unrelated refactor.
4. Re-run the identical command, legacy regressions and one boundary fixture. Repeat for the block's remaining invariants. Never skip/xfail a previously passing test.
5. Produce an implementation receipt naming source hash, test argv/exit/output, screenshot/benchmark only if actually captured, capability dispositions, own diff, unresolved data gates and reviewer verdict. Commit explicit owned paths only when that lane is authorized; push only with branch/remote verification.

A block is **not** a five-minute feature. Its five microsteps are a repeating workflow; split each named acceptance invariant into a small test/fix cycle. `145 microsteps` counts the enumerated workflow steps, not a promised implementation duration.

## Existing baseline commands — observed

```bash
cd /Users/nav/Documents/GitHub/floww-2/backend
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python ../tests/test_price_node_history.py
# Observed: Ran 8 tests ... OK
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/services/test_market_bars.py \
  tests/services/test_public_api_bars.py \
  tests/routes/test_public_api_bars_routes.py \
  -q --tb=short -p no:cacheprovider --disable-warnings
# Observed: 53 passed, 27 warnings
```

Frontend command attempted in the canonical checkout:

```bash
cd /Users/nav/Documents/GitHub/floww-2/frontend
CI=true ./node_modules/.bin/craco test --watchAll=false --runInBand \
  --runTestsByPath \
  src/components/heatseeker/PriceNodeHistory.test.jsx \
  src/components/heatseeker/priceNodeTraces.test.js \
  src/components/heatseeker/AskLodestar.test.jsx \
  src/agent/ScreenContextLifecycle.test.jsx
# Observed blocker: ./node_modules/.bin/craco: No such file or directory
```

Do not substitute raw Jest/vitest for the CRA/craco test contract. In an approved isolated implementation checkout, inspect its actual lockfiles and use the repo's lock-pinned install policy (`npm ci --legacy-peer-deps --prefer-offline` where applicable). Do not symlink another checkout's modules, edit package pins just to make installation work, or remove another worker's build. Browser performance, full suites and build acceptance remain future work.

Adding `lightweight-charts@5.2.1` requires explicit frozen-package approval plus ownership of corresponding lockfile changes. Retain upstream Apache license/NOTICE and requested chart attribution/link. If approval is absent, do contract/orb/Plotly work or stop the engine-only task, never inject a CDN as a workaround.

## Concrete first fixtures

- Legacy `build_history`: asof=14:00, received=14:02 absent at14:01; age900s eligible,901s absent; scope formula/basis mismatch never leaks.
- Strict parsing: `false`, `true`, `null`, `''`, whitespace, arrays, NaN/Infinity are not measured prices; valid numeric strings accepted only by explicit grammar; measured volume0 differs from missing volume.
- Exposure: signed values -100,+50 give the -100 node king; P50 includes+50; all measured zeros yields a measured-zero state, not an invented ratio; null VEX never becomes zero.
- Model trap: canonical `VEX_1VOLPT` accepted; legacy VOMMA `vex_surface` rejected for VANNA view.
- Contract caller: Trinity `WallPricePath` still receives old `frames[].close` and unavailable VWAP caption; old chart controls still work.
- Replay: historical provider final candle without revision-arrival evidence must be labelled review/limited provenance, not claimed perfectly time-faithful at an intra-bar cursor.

These are proposed expected results, not an already implemented fixture suite.

## Done means

For each shipped release: named capability IDs accepted or explicitly data-gated/deferred; task DAG prerequisites satisfied; current source tests passing with real outputs; frontend build/runtime identity and real browser interaction proven; recorded-only replay demonstrated; no altered heatmap/ML/broker safety; reversible incumbent flag; source/provider/attribution metadata visible; no unrelated source/status changes. The packet's `VERIFY.py` proves research integrity only and does not replace these application checks.

## Round2 acceptance expansion

Read C112–C143 and each block round2_acceptance_invariants before scheduling. The complete matrix has143 capabilities and29 blocks;145 workflow microsteps are repeating RED/GREEN recipes, not total implementation effort. Bar-occupancy TPO/bar-distributed profiles are labelled variants independent of tape commissioning. Every newly enabled setting gets a dedicated fixture; retain source precision, known-at, owner, variant and release gates. Original independent review remains preserved; no successful second-round independent refutation is claimed after provider failure. Publicv5.2 API/NOTICE checks are source evidence, never installed-runtime approval.

