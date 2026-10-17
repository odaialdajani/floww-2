# Research sources and confidence ledger

Scope: public vendor/library documentation, supplied field guide, retrieved English video transcript, exact local source, real focused tests and one live API probe. External marketing/tutorial statements are not empirical trading claims or proof of floww support. No authenticated Skylit app or paid API was accessed.

## Source IDs

**SRC-GUIDE — supplied Atlas field guide.** The attached text is retained by the user in `/Users/nav/.hermes/composer-pastes/pasted_content_2026-10-09_19-32-45-089_bb5fee.txt`; this packet maps its capabilities rather than redistributing its whole text. Public canonical page: https://www.skylit.ai/docs/guides/atlas (HTTP200 checked). It defines positioning/flow/darkpool/studies/docks/layouts/drawings/replay and includes October2026 changes. This is reference product behavior, not our source implementation.

**SRC-VIDEO — https://www.youtube.com/watch?v=9Hn_OLBJRVY.** Supplied title: “How To Setup SkylitAI's Atlas For Index Trading.” The English timed transcript was actually fetched through youtube-transcript-api and is retained in `VIDEO_TRANSCRIPT.md`. The supplied metadata date is2026-09-28; description chapters are a navigation aid. No complete video visual inspection was performed. Automatic-caption wording/undocumented slider numbers cannot establish an exact UI value or API guarantee.

**SRC-CODE — canonical repository source.** Baseline branch/head and tracked SHA256 inventory are in `PRESERVATION_BASELINE.json`. Findings are explicitly tied to file/symbol/line in the master plan; implementation paths in the task inventory are proposals. Key exact files:
- `frontend/src/components/heatseeker/PriceNodeHistory.jsx`, `priceNodeTraces.js`, their tests and `SkylitDashboard.jsx`.
- `frontend/src/components/TrinityView.jsx:WallPricePath` — SVG recent-close consumer of same legacy endpoint, not a separate full candle renderer.
- `frontend/src/components/heatseeker/AskLodestar.jsx:admissionBlock`; `frontend/src/agent/AgentProvider.jsx` — current screen-context and refusal boundary.
- `frontend/src/components/flowseeker/chart/ChartModal.jsx` — separate investigation lists, not migration target.
- `backend/routes/price_history.py`; `backend/services/price_node_history.py`, `market_bars.py`, `public_api_adapter.py`, `public_api.py` — interval/session/data availability and legacy contracts.
- `backend/services/heatmap_history.py` — existing optional full-grid archive and atomic recorder lineage.
- `backend/services/gex_aggregator.py:41–53`, `gex_core.py:1496–1509` — legacy VOMMA versus canonical VANNA VEX trap.
- `backend/services/solstice_time.py`, `solstice_calendar.py` — maintained exchange/settlement clock reuse candidate, not futures calendar proof.
- `CLAUDE.md`, `docs/adr/0002-data-source-policy.md` — freeze/ownership, display-vs-ML scale and source policy.

**SRC-RUN — actual execution evidence.** `EVIDENCE.json` preserves real test output and live route fields. It does not assert a full test suite, browser render, precise historical provenance or provider entitlement. Frontend craco was absent at the tested path; installation was not changed to conceal this blocker.

## Atlas primary documentation researched

- https://www.skylit.ai/docs/guides/atlas
- https://www.skylit.ai/docs/atlas/indicators/gex-vwap
- https://www.skylit.ai/docs/atlas/indicators/vwap
- https://www.skylit.ai/docs/atlas/indicators/cvd
- https://www.skylit.ai/docs/atlas/indicators/volume-profile
- https://www.skylit.ai/docs/atlas/drawing-presets
- https://www.skylit.ai/docs/api-reference/history/ohlcv-price-bars-for-a-symbol-and-resolution
- https://www.skylit.ai/learn/reading-flow-on-atlas
- https://www.skylit.ai/learn/reading-dark-pool-prints
- https://www.skylit.ai/docs/guides/heatseeker

The supplied guide covers TPO and broader features even when guessed deep links returned sparse/not-found pages. An attempted deep link is not cited as successfully retrieved. Round2 successfully retrieved the actual TPO, Volume Profile, CVD, VWAP, GEX VWAP and drawing-preset subpages listed below; their detailed defaults now appear in acceptance criteria. Vendor price API docs describe a separate paid service and do not mean floww owns credits, authorization or redistribution rights. Footprint/advanced drawings and numerical definitions absent from public indicator pages remain independently reviewed implementation specs.

Useful verified semantic distinctions: flow bars are premium dollars and bucket filters match drilldown; ask/sweep classifications are not proof of opening intent. Dark-pool overlays use one exact real print's transaction price, date and notional, not direction. Heatmap palettes can represent board-relative min/max rather than sign; read signed values. Vendor material itself warns these routines are not tested edges.

## Financial-chart engine primary sources

- https://tradingview.github.io/lightweight-charts/docs
- https://tradingview.github.io/lightweight-charts/docs/series-types
- https://tradingview.github.io/lightweight-charts/docs/plugins/intro
- https://tradingview.github.io/lightweight-charts/docs/plugins/series-primitives
- https://tradingview.github.io/lightweight-charts/docs/api/interfaces/IChartApi
- https://github.com/tradingview/lightweight-charts
- https://api.github.com/repos/tradingview/lightweight-charts — live GitHub license SPDX Apache-2.0
- https://registry.npmjs.org/lightweight-charts/latest — queried version5.2.1/license Apache-2.0
- https://raw.githubusercontent.com/tradingview/lightweight-charts/master/NOTICE — TradingView copyright/NOTICE fetched
- https://plotly.com/javascript/candlestick-charts/

Recommendation is conditional on v5 adapter spike and frozen dependency approval. Apache license is necessary, not a substitute for NOTICE/attribution/data rights; third-party plugin/sample licenses need their own check. Multi-pane series APIs are not a ready multi-symbol workspace, profile engine, drawing editor or feed. Current frontend dependencies were read from package.json; missing local test binary prevents a claim of installed versions.

## Harness / model verification

- https://opencode.ai/docs/config/
- https://opencode.ai/docs/permissions/
- https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation
- https://integrate.api.nvidia.com/v1/chat/completions — real authenticated z-ai/glm-5.3 completion; secrets resolved locally, never copied to packet.
- Local `/Users/nav/.opencode/bin/opencode models` and `run --help` were run. `--pure`, `--model`, `--dir`, `--format` are verified CLI options. Catalog lists actual Spark1.3 IDs; its inference path was not tested or launched.

Four tool-using read-only NIM lanes were attempted concurrently with write/bash/task denial. One completed and three timed out at750s. Four subsequent bounded direct source-packet review attempts were all incomplete: two consumed the6500-token generation budget entirely in reasoning and returned no answer, two timed out at210s. They contribute failure/usage evidence, **not findings**. A later low-effort pilot timed out at60s. The primary model docs at https://docs.api.nvidia.com/nim/reference/z-ai-glm-5-3 state that low/high/max reasoning is available and defaults to max; https://nvidia.github.io/TensorRT-LLM/1.3.0rc27/deployment-guide/deployment-guide-for-glm-5-on-trtllm.html says GLM5.3 cannot disable thinking with the older enable_thinking switch. The low-effort attempt does not establish hosted parameter effectiveness because it returned no response. Parent completed remaining source-backed audits inline; a native-model independent refuter completed separately and returned eight findings, all applied to the plan and recorded; it is identified as native fallback, never successful GLM/NIM research. Exact receipts and adjudications appear in evidence/reports.

## Conflicts / limits that affect design

1. Video narration says first column always current day; use nearest **eligible** tradable expiry, not an unconditional 0DTE assumption.
2. Video says dark-pool top10/30days; public article enumerates1/2/3/5 and30/45/90/180. Choose validated product settings, not undocumented parity-by-copying.
3. Video phrasing “within25%” is ambiguous; supplied guide says nodes **at least**25% of king. Contract pins inclusive magnitude ratio, not a percentile/proximity threshold.
4. The recorder already writes full grids where schema supports them. A reviewer proposal to add `orbs_json` everywhere is not accepted without archived-input coverage proof.
5. Current wall bands are not one strike's exposure and cannot silently be renamed orbs. Keep wall-role and strike-grid semantics separate.
6. Existing AI refuses history/replay; a client context field cannot waive server admission. Exact server-resolved surface support is a future task.
7. Provider final OHLC fetched today lacks historical revision-arrival evidence. Review mode is useful but not perfectly faithful historical playback.
8. Git/source identity is separate from backend-loaded modules and compiled frontend identity. HTTP200 cannot prove the running process loaded current files.
9. Performance targets are hypotheses pending actual browser measurements; full-suite/frontend/visual passes are not claimed.
10. Account-sync, futures/proxy volume, social/Nexus/paid plugin/tape rights remain independent commissioning items. Vendor feature presence is not our entitlement.

## Round2 verified source IDs and confidence

- **SRC-R2-GEX** — https://www.skylit.ai/docs/atlas/indicators/gex-vwap; retrieved primary prose/API documentation, hash receipt in EVIDENCE.json. Vendor feature claims do not prove our feed entitlement or exact algorithm parity.
- **SRC-R2-VWAP** — https://www.skylit.ai/docs/atlas/indicators/vwap; retrieved primary prose/API documentation, hash receipt in EVIDENCE.json. Vendor feature claims do not prove our feed entitlement or exact algorithm parity.
- **SRC-R2-CVD** — https://www.skylit.ai/docs/atlas/indicators/cvd; retrieved primary prose/API documentation, hash receipt in EVIDENCE.json. Vendor feature claims do not prove our feed entitlement or exact algorithm parity.
- **SRC-R2-VP** — https://www.skylit.ai/docs/atlas/indicators/volume-profile; retrieved primary prose/API documentation, hash receipt in EVIDENCE.json. Vendor feature claims do not prove our feed entitlement or exact algorithm parity.
- **SRC-R2-TPO** — https://www.skylit.ai/docs/atlas/indicators/tpo; retrieved primary prose/API documentation, hash receipt in EVIDENCE.json. Vendor feature claims do not prove our feed entitlement or exact algorithm parity.
- **SRC-R2-PRESET** — https://www.skylit.ai/docs/atlas/drawing-presets; retrieved primary prose/API documentation, hash receipt in EVIDENCE.json. Vendor feature claims do not prove our feed entitlement or exact algorithm parity.
- **SRC-R2-FLOW** — https://www.skylit.ai/learn/reading-flow-on-atlas; retrieved primary prose/API documentation, hash receipt in EVIDENCE.json. Vendor feature claims do not prove our feed entitlement or exact algorithm parity.
- **SRC-R2-DP** — https://www.skylit.ai/learn/reading-dark-pool-prints; retrieved primary prose/API documentation, hash receipt in EVIDENCE.json. Vendor feature claims do not prove our feed entitlement or exact algorithm parity.
- **SRC-R2-API** — https://www.skylit.ai/docs/api-reference/history/ohlcv-price-bars-for-a-symbol-and-resolution; retrieved primary prose/API documentation, hash receipt in EVIDENCE.json. Vendor feature claims do not prove our feed entitlement or exact algorithm parity.
- **SRC-R2-LWC** — https://tradingview.github.io/lightweight-charts/docs/api/interfaces/IChartApi; retrieved primary prose/API documentation, hash receipt in EVIDENCE.json. Vendor feature claims do not prove our feed entitlement or exact algorithm parity.
- **SRC-R2-CODE** — direct reads of market_bars.py86–153, solstice_calendar.py36–61, solstice_time.py69–139, price_history.py25–42, priceNodeTraces.js1–27 and exposure_alerts.py18–20; standalone observed helper/calendar characterization. No product source changed.
- Additional official API confirmation: https://tradingview.github.io/lightweight-charts/docs/api/interfaces/ITimeScaleApi ; https://tradingview.github.io/lightweight-charts/docs/api/interfaces/ISeriesApi ; https://tradingview.github.io/lightweight-charts/docs/panes ; https://tradingview.github.io/lightweight-charts/docs/plugins/series-primitives . These describe publicv5.2, not an installed spike.
- Master NOTICE fetched from https://raw.githubusercontent.com/tradingview/lightweight-charts/master/NOTICE — TradingView Lightweight Charts™, Copyright2025 TradingView. Exact approved-release files still need inventory; a master-file check alone does not discharge installed-package obligations.
- Invalid guessed `/docs/atlas/reference/drawing-presets` and `/docs/atlas/api-reference` returned404; the successful canonical drawing and OHLCV subpage URLs above replace them as evidence. Changelog extraction returned a23-update/September2026 header but not all entry bodies. The supplied October guide remains a separate source, not independent changelog verification.
- Vendor OHLCV page has internal401/403 wording conflicts and supports published resolution tiers, not every advertised chart custom interval. Copy neither auth/error semantics nor credit/refund promises into our canonical route; our actual provider and HTTP contract must be characterized.
- R2 model failure/unusable-output ledger is explicit in EVIDENCE.json. Saved usable API artifact exists, but the failed independent refuter was replaced by parent inline review, not silently given an independent acceptance signature.

