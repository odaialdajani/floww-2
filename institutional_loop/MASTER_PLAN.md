# INSTITUTIONAL MASTER PLAN — Prop-Firm-Grade Options Flow on Paid Public Data
**Program:** Tidehunter Pro / Confluence Decoder institutional rebuild
**Data foundation:** Public.com Advanced API (paid, primary) → cvserver (strict failover) → yfinance (last resort)
**Execution:** 4 agents × ~24h, parallel, same repo (`/Users/nav/Documents/GitHub/floww`), continuous
**Doctrine:** every claim must be measured; every threshold must show its work; nothing fires that we cannot defend on a desk.

---

## 1. Objective (one paragraph)

Turn the scanner from a day-volume-vs-OI screen into an institutional flow desk: signed aggression from NBBO truth (Lee–Ready discipline), toxicity and price-impact reads from bars (VPIN/Kyle/Amihud), dealer-positioning context on every alert (walls, gamma regime, skew), campaign tracking across days, and a closed money loop (alert → sized paper trade → measured outcome → calibrated probability). All of it replayable, audited, and budget-aware — because we now pay for data, every upstream call must earn its keep.

## 2. Non-negotiable laws

1. **Public primary, cvserver failover.** Any new market-data read goes to Public first. cvserver paths stay working but secondary. No new yfinance dependencies.
2. **No fabricated evidence.** Unknown = unknown (None, `stale`, `unmeasured`). Proxies are labeled as proxies in code, payloads, and UI.
3. **Parity locks hold.** `scan_score` ↔ `scanScoreOf` identical math; GEX S¹/S² scale convention untouched; frozen files (`ml/inference.py`, `dash_ui.py`, `App.js`, model artifacts) need Nav approval.
4. **TDD everything.** Failing test → patch → passing test. No test edits that weaken assertions without a written reason in the commit body.
5. **Contracts frozen.** `CONTRACTS.md` shapes (rows, ckey, extras, dealer, alerts, budgets, env) change only by 4-agent agreement, logged in `LEDGER.md`.
6. **File ownership (Section 7).** Touch another agent's files only to read; writes need owner sign-off in the ledger. Agent D alone resolves merge conflicts. Staging: `scripts/loop_guard.sh stage <AGENT>` only — `git add -A` / `commit -a` are banned and enforced by the Sync-1 staging gate (D7b) against `institutional_loop/OWNERSHIP.md`.
7. **Green before push.** Module suite + ruff + related route tests, every commit. Full-suite gate at each sync point, owned by D.
8. **Secrets never in code/logs.** Keys via env only. Any pasted secret = stop, rotate, disclose in ledger.

## 3. Research bibliography → build map

Only papers with a concrete module target and available (or proxy-able) data are listed. "Proxy" marks where we adapt (and must label).

### 3A. Informed flow (Agent A)

| # | Paper | Signal to build | Data | Module |
|---|---|---|---|---|
| R1 | Pan & Poteshman (2006, RFS) — option put-call ratios predict underlying returns | Per-ticker, per-expiry P/C **volume and OI ratios** with the paper's direction (low PC → positive drift); add to score + WHY | Have (chains) | `flow_skew.py` (NEW), score/conviction |
| R2 | Cremers & Weinbaum (2010, JFQA) — call-put IV spread predicts returns | Already have CW proxy; harden: volume-weighted, matched-strike only, expiry-bucketed, significance floor | Have (real IVs now) | `flow_quality.py` (extend), tests |
| R3 | Xing, Zhang & Zhao (2010, RFS) — volatility smirk slope predicts | OTM-put minus ATM-call IV slope per expiry; steepening = institutional protection demand | Have (real IVs + chains) | `flow_skew.py` |
| R4 | Yan (2011, JFE) — smirk slope and downside risk | Jump-risk proxy: left-tail slope vs right-tail slope asymmetry; gate 0DTE LOTTO vs informed | Have | `flow_skew.py` |
| R5 | Johnson & So (2012, JFE); Roll, Schwartz & Subrahmanyam (2009) — option-to-stock volume (O/S) predicts | O/S ratio per ticker (option volume ÷ underlying share volume from bars); high O/S = informed venue shift | Have (chains + Public bars) | `flow_toxicity.py` (NEW) |
| R6 | Ge, Lin & Pearson (2016, RFS) — why option volume predicts (new positions, not hedging) | Decompose volume into opening-proxy (vol≫OI, rising OI next day) vs closing; weight opening 3:1 | Have (OI + prev-OI) | `flow_quality.py`, desk pass |
| R7 | Easley, O'Hara & Srinivas (1998, JF) — leverage hypothesis | Weight deep-OTM/high-leverage flow higher in conviction (leverage = notional/premium); test ITM-vs-OTM predictive split in ledger | Have | conviction weights + ledger study |
| R8 | An, Ang, Bali & Cakici (2014, JFE) — call-minus-put IV spread, cross-section | Cross-ticker IV-spread leaderboard (relative, not absolute) for the universe view | Have | universe panel |
| R9 | Hu (2014, JFE) — signed option volume conveys information | Justification for signing everything (R10); sign-weighted volume sums per ticker | Have (NBBO) | `flow_signing.py` |
| R10 | Lee & Ready (1991, JF) — quote-rule + tick-test signing | **Per-contract Lee–Ready**: quote rule on last-vs-NBBO at print time; tick test on mid drift across sweeps; aggressor-Ω per ticker | Have (last/bid/ask/mids) | `flow_signing.py` (NEW) — highest value/paper ratio in the program |

### 3B. Microstructure & toxicity (Agents A+B)

| # | Paper | Signal to build | Data | Module |
|---|---|---|---|---|
| M1 | Easley, López de Prado & O'Hara (2012, JFE; book 2013) — VPIN flow toxicity | **Bar-VPIN per universe ticker**: volume buckets from Public 1-min bars, daily toxicity series; gate: no fresh directional size into toxic tape | Have (bars) | `flow_toxicity.py`, toxicity panel |
| M2 | Kyle (1985, Econometrica) — lambda price impact | **Rolling Kyle-λ** per ticker (5-min return on signed sqrt-volume, daily fit); size alerts by expected slippage, not raw premium | Have (bars) | `kyle_lambda.py` (exists — wire to bars + alerts) |
| M3 | Amihud (2002, JFM) — illiquidity ratio | Daily Amihud per ticker from bars; mid-cap alerts scaled by illiquidity (a $600k SNDK print > $600k SPY print) | Have | `amihud_illiquidity.py` (exists — wire in) |
| M4 | Roll (1984, JF) — effective spread from serial covariance | Server-side Roll on per-contract mid rings (port `rollPooled` from frontend to backend, run on sweeper marks) | Have (mids) | backend Roll service (NEW, small) |
| M5 | Glosten & Milgrom (1985, JFE) — adverse selection spreads | Relative-spread regimes per contract (spread/price percentiles); wide-spread + aggressive = informed urgency | Have (quotes) | signing context |
| M6 | Hasbrouck (1991, JF) — information content of trades (VAR) | Permanent-vs-transitory decomposition on ticker tape: 5-min VAR on signed volume → information share per ticker, weekly | Have (bars) | research-grade, Phase 2 |
| M7 | Chordia, Roll & Subrahmanyam (2001, JFE) — market-wide liquidity | Market-mode volume factor (we subtract median for SIGMA — extend to full cross-sectional factor + breadth stats) | Have | SIGMA v2 |

### 3C. Dealers & volatility (Agents A+B)

| # | Paper | Signal to build | Data | Module |
|---|---|---|---|---|
| V1 | Barbon & Buraschi (working paper, gamma fragility) + Ni–Pearson dealer impact | Real ΓIB per scanned ticker (needs ADV: 21-day share volume from bars — computable in-house now); replace DEFAULT_ADV_SHARES stub with measured ADV | Have (bars+chains) | `gex_paper_accurate.py` + sweeper |
| V2 | Bakshi, Kapadia & Madan (2003, RFS) — risk-neutral skew/kurtosis | Model-free RN skew per ticker per week from OTM chains; regime context for directional alerts | Have (chains) | `flow_skew.py` |
| V3 | Bollerslev, Tauchen & Zhou (2009, RFS); Carr & Wu (2009, RFS) — variance risk premium | Wire existing RV/VRP cron OUTPUT into alert context (rich vs cheap vol per ticker; fade rich-vol chasing) | Exists, unwired | desk pass IV context upgrade |
| V4 | Goyal & Saretto (2009, JFE) — option returns and vol mispricing | IV-minus-HV edge per ticker as a standing context field (cheap-vol buyer edge) | Have (bars+IV) | context field |
| V5 | Hagan et al. (2002, SABR); Gatheral SVI | Already in `stochastic_vol.py`; task = validate wings against paid IVs, publish per-ticker smile snapshot for skew math | Have | validation + snapshot |

### 3D. Statistics of detection (Agents A+D)

| # | Method | Build | Module |
|---|---|---|---|
| S1 | Iglewicz & Hoaglin (1993) — MAD robust z-score | Replace raw σ with MAD-based robust scores on thin baselines (the whales_hunter lesson); dual-path by sample size | baselines + PRIME/SIGMA |
| S2 | Benjamini–Hochberg (1995) — have it; extend | FDR across the FULL rule set per sweep (not just SIGMA); q-budget ledger | `flow_quality.py` |
| S3 | Adams & MacKay (2007) — Bayesian online changepoint | Volume-regime changepoints per ticker (replaces brittle streak medians for FOLLOW v2) | `flow_toxicity.py` or NEW |
| S4 | Hawkes (1971) — self-excitation | Fit on universe sweep arrival times; burst intensity = sweep fingerprint without tape | `hawkes_process.py` (exists — wire to sweeps) |
| S5 | Brown & Warner (1985, JFE) — event study | Outcome ledger upgrade: abnormal returns vs SPY benchmark, multi-horizon, t-stats | `flow_outcomes.py` |
| S6 | Platt (1999); Niculescu-Mizil & Caruana (2005) — calibration | p_move promotion: Platt/isotonic with min-n gates, stage criteria, audit trail | `flow_calibration.py` |

### 3E. Capital & execution (Agent C)

| # | Paper | Build | Module |
|---|---|---|---|
| C1 | Kelly (1956) — growth-optimal sizing | Wire Kelly fractions (capped) into paper-trade sizing from calibrated p + key levels | `position_sizing.py` + bridge |
| C2 | Almgren & Chriss (2001) — optimal execution | Size urgency by Kyle-λ + spread (have both after M2/M5): patient limit vs urgent take per alert | execution advisor (NEW, small) |
| C3 | Muravyev & Pearson (2013, RFS) — informed trading around news | Earnings-window policy upgrade:anneal (don't just demote — route to event protocol: smaller size, wider invalidation) | oi_hygiene + desk pass |

## 4. Target architecture (end state)

```
Public chains/quotes/bars ──┐
cvserver (failover) ─────────┼── ingestion (budget-gated, validated, quarantined)
                             ▼
                    ┌─ universe sweeper (45s RTH, background, always-on)
                    │        ├── rows (10-col) → Mongo baselines → DuckDB ledger
                    │        ├── extras (premium/side/velocity) → alert engine
                    │        └── dealer (walls/regime/ΓIB w/ measured ADV) → context
                    ▼
        ┌─ signing (Lee–Ready) ─┬─ toxicity (VPIN/Kyle/Amihud/O/S) ─┬─ skew (smirk/CW/slope/RN-skew)
        ▼                       ▼                                   ▼
                    institutional alert engine (OICONF/SCORE/WHALE/PRIME/0DTE/SIGMA/CLUSTER + v2 rules)
                    ▼
        desk pass (fresh-interest, campaign, IV/VRP context, toxicity gate, earnings protocol)
                    ▼
        money loop (calibrated p → Kelly-capped size → execution advisor → paper trade → event-study outcome)
                    ▼
        replay + audit + health (every sweep recorded, every alert explainable, every threshold measured)
```

## 5. Workstreams (4 agents, file ownership = merge-conflict firewall)

**Agent A — FLOW SCIENCE (signals).** Owns: `services/flow_signing.py` (NEW), `services/flow_toxicity.py` (NEW), `services/flow_skew.py` (NEW), `services/flow_quality.py`, `frontend/.../scanLogic.js` (+test). May read all, write only these (+ its tests). Tasks A1–A8 in brief.
**Agent B — DATA PLANE (feeds).** Owns: `services/public_api.py`, `public_api_adapter.py`, `public_scanner.py`, `public_budget.py`, `cache_router.py`, `fetch_coordinator.py`, `routes/flowseeker.py`, `routes/public_api.py`, `server.py` (sweep-loop region only), `FlowseekerProBlademap.jsx`. Tasks B1–B8.
**Agent C — MONEY LOOP (capital).** Owns: `flow_calibration.py`, `flow_outcomes.py`, `flow_trade_bridge.py`, `flow_desk.py`, `journal_store.py`, `position_sizing.py`, `oi_hygiene.py`, alerts/journal/outcomes routes, `flow_alerts.py` (`_mk_alert`/levels only — coordinate with A). Tasks C1–C8.
**Agent D — PROOF (hardening).** Owns: `tests/chaos/`, `tests/perf/`, replay harness, observability/health, `docs/handoff/`, `LEDGER.md`, merge duty. Touches NOTHING else except conflict resolution with owner sign-off. Tasks D1–D8.

Full task lists, order, and done-criteria live in `AGENT_{A,B,C,D}.md`. Dependency order: contracts (all, H0) → B feeds A rows → A signals feed C money → D proves everything continuously.

## 6. 24-hour runbook

| Hour | All agents | Sync artifact |
|---|---|---|
| 0–1 | Read master plan + CONTRACTS + own brief; post understanding + first 3 tasks to LEDGER | Ready posts |
| 1–6 | Build block 1 (tasks ×1–×3) | — |
| 6 | **Sync 1**: rebase, contract changes proposed, red tests triaged (D chairs) | Sync note |
| 6–12 | Build block 2 (tasks ×4–×6) | — |
| 12 | **Sync 2**: integration check (sweep→alert→paper→outcome live path), perf snapshot | Integration note |
| 12–18 | Build block 3 (tasks ×7–×8, hardening) | — |
| 18 | **Sync 3**: calibration report v1 on recorded data, kill/keep per rule | Calibration note |
| 18–23 | Polish, replay determinism, docs, backlog grooming | — |
| 23–24 | **Final gate** (D runs): full suites, replay check, latency SLOs, secret scan, handoff to Nav | HANDOFF note |

Loop discipline per task: plan (3 lines in ledger) → failing test → patch → module suite + ruff → commit (`type(scope): subject`, HEREDOC + evidence) → push → ledger line. Conflict rule: pull --rebase early and often; D resolves with owner.

## 7. Verification gates

- **Task gate:** new/changed behavior has a test that failed before and passes after; module suite green; ruff clean.
- **Sync gate:** backend scope suite + frontend flowseeker suites green; no forbidden-file diffs without Nav note; LEDGER current.
- **Final gate:** (a) full backend suite + full jest green; (b) replay determinism: same recorded sweep → identical alerts; (c) latency: p95 scan-public < 25s, chain < 8s; (d) secret scan clean; (e) calibration report with per-rule precision + sample sizes; (f) HANDOFF note with what changed, what was measured, what is still proxy.

## 8. Risk register

1. Vendor throttle (Public 429 storm) → budget cooler + cvserver auto-failover + sweeper backoff; D chaos-tests it.
2. Parallel-agent merge collisions → file ownership + D-only merges + rebase cadence.
3. Calibration on small-n (new PRIME/CLUSTER rules) → min-n gates, "uncalibrated" labels stay until earned.
4. Research overreach (papers needing tape we lack) → proxy-labeled, Phase-2 parked, never silent.
5. Secret leak → env-only rule + D's secret scan at every gate.
6. Scope creep into frozen modules → forbidden-file list in every brief; Nav approval required.

## 9. Environment & ops knobs (registry — add, don't rename)

`PUBLIC_API_KEY`, `CVSERVER_API_KEY`, `FLOWW_PUBLIC_UNIVERSE`, `FLOWW_PUBLIC_SWEEP{,_RTH_S,_OFFH_S,_SLICE}`, `CV_HOURLY_BUDGET`, `CV_SCAN_BUDGET`, `CV_SCAN_TTL`, `FLOWW_CHAIN_CACHE_MAX`. Budgets count upstream HTTP calls; caches serve stale-with-age, never silent empty.

## 10. Definition of done (program)

Scanner runs Public-first with failover; every alert carries signed side, true premium, velocity, dealer regime, and calibrated-or-uncalibrated p; money loop closes alert→sized paper→measured outcome; replay reproduces any session; health shows feed×budget×sweep×alerts at a glance; docs say what is measured vs proxy. Nav reviews HANDOFF, not hope.

## 11. Phase-0 punchlist — APPLIED pre-loop (2026-09-05, do not redo)

Red-team findings verified against code and fixed before agents start (full suite green: 4745 backend + 420 jest):
- **P0-0a (C):** backend 0DTE ≡ tape (score≥85 AND vol_oi≥2 AND dte≤1); pin test updated.
- **P0-0b (C):** alert dicts always emit `premium_truth`, `p_move: None`, `p_method: "uncalibrated"` (C6 additive contract; calibration overwrites when staged).
- **P0-0c (B/C):** dealer ΓIB pct is `None` (unknown), never `0.0`; engine None-guards (regime propagates, confluence needs magnitude). Law 2 upheld.
- **P0-0d (B):** scan-public `stale` computed from slice ages/drops, never hardcoded false.
- **P0-0e (B):** sweep RTH standardized 09:30–16:05 ET; off-hours first-tick skip; `FLOWW_PUBLIC_SWEEP_MAX_EXPIRES` added.
- **P0-0f (all):** P&P citation aligned to the honest wording (heuristic band; P&P cited for PC direction only).
- **P0-0g (B/C):** region markers (`B-REGION`/`C-REGION`) in `routes/flowseeker.py` + `server.py` sweep loop.
- **Verified, not bugs:** heatmap `nodes.regime` uses short vocabulary (positive/negative/neutral) — compatible; ckey parity test exists and passes; backend has no per-ticker cap BY DESIGN (feed completeness vs the frontend's notification-only `perTickerCap=2` — documented divergence, not a bug).

## 12. Phase-2 — Skylit-informed builds (prioritized from competitor research, 2026-09-05)

Competitor truth established: Skylit Flowseeker has 1-sec real tape, verified multi-exchange sweeps, dark pool, FlowScore(−100..100)+Bonus, VWF/SDF/FIR, contract aggregation, whale tracker with STILL_IN→EXITED, MCP with 40 tools. We cannot close tape/dark-pool gaps on Public data — doctrine: proxy-labeled or not at all. Everything below is buildable on chains+quotes+bars:

| # | Build | Owner | Data |
|---|---|---|---|
| P0-1 | Dual-score alerts: DIR(−100..100, signed aggression×moneyness×DTE×size/OI×IV-confirm) + BONUS(0–100, size outlier/sweep-proxy/cluster/wall proximity) alongside SCORE | A (A9) | chains+greeks ✓ |
| P0-2 | Vol/OI accumulation classifier: 0–100 + %new-positions per ticker/moneyness; unusual-OI opener/closer board (answers rolls/hedges noise) | A (A10) | vol/OI + ΔOI ✓ |
| P0-3 | Strike-concentration + bull/bear pressure board: top-N strikes by net premium + ask/bid mix + OI context | A/B (A owns math, B owns endpoint) | chains ✓ |
| P0-4 | Dealer walls v2: flip/polarity, ±stacks, air pockets, fresh-vs-tapped decay, wall velocity, 1-day expected move | A (math) + B (snapshot store) | chains+quotes+bars ✓ |
| P1-5 | Time-of-day baselines + momentum z (5m/30m/1h buckets) + similar-days; kills lunchtime false breakouts | B (buckets) + A (z-math) | intraday polls ✓ (chain-implied, labeled) |
| P1-6 | Market tide probe: universe call/put prem, FIR, RVOL vs same-time-20d, A/D, sector rollups, SPY overlay — one risk-on/off endpoint | B | universe agg ✓ |
| P1-7 | Whale tracker: bookmark alert → live mid/spot/P&L + auto STILL_IN/PARTIAL/EXITED/EXPIRED via Vol/ΔOI decay + badge | C | chains + ledger ✓ |
| P1-8 | MCP layer (~15 tools over existing FastAPI + 10 example prompts + budget guardrails) | B (tools) + D (prompt pack + guardrail tests) | none new ✓ |
| P2-9 | Atlas-lite overlays: walls as zones + flow-premium bars + click-buckets + replay slider on stored snaps | B (frontend canvases) | stored snaps ✓ |
| P2-10 | Explicit non-builds: NO claimed verified sweeps / HIRO / dark pool. Sweep-proxy carries confidence labels; chain-implied pressure instead of HIRO | All (D enforces in review) | — |

## 13. Ownership amendments (red-team resolutions)

- **Regions over splits (for now):** `routes/flowseeker.py` stays one file with `B-REGION` (chain/scan/budget/baselines) and `C-REGION` (alerts pipeline, /alerts/*) markers — no cross-region edits without owner sign-off. Full split to `routes/flow_alerts_api.py` is a Sync-2 decision, not Hour-0 work.
- **A9 (NEW, Agent A):** server-side Roll effective-spread service (port `rollPooled` to backend, run on sweeper mid-marks) — M4.
- **B9 (NEW, Agent B):** Hawkes wiring — expose sweep arrival timestamps; A consumes burst intensity — S4.
- **`vpin_toxicity.py` ownership → Agent B** (VPIN family lives with the bars adapter).
- **C13 Bars/ADV contract (CONTRACTS appendix):** B provides `get_1min_bars(ticker,days)`, `get_daily_bars(ticker,days)`, `get_adv_21d(ticker)` — budget-gated, cached, validated, errors as `{stale,age_s,reason}`, never raise. A consumes bars-lists only. Kyle/Amihud bars-methodology rewrite is B-owned with pinned output keys.
- **Budget honesty (B4 strengthened):** chain fetch = 2+N debits (acquire_n or looped-acquire with partial refund); adaptive slice; stress test asserts calls/min ≤ 60.
- **Forbidden list:** CONTRACTS C12 (8 entries) governs; §2.3's short list is subsumed by it.
- **LEDGER protocol:** append-only (D owns file, all agents append rows; conflicts resolve by union).
- **D2 replay freeze list:** recorder must capture rows, baselines, prev-OI, regimes, gex_context, oi_tags, calibration blob, and freeze `mins_since_open`/`asof` — else byte-identical is impossible.
- **RTH standard:** 09:30–16:05 ET everywhere (sweeps, session math anchors stay as-is where harmless).
