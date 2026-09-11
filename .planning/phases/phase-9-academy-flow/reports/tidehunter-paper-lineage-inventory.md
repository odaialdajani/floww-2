# Backend paper-lineage inventory (task 40) — Tidehunter lane, 2026-09-03

Read-only audit. Backend :8000 hung at check time (process alive, Mongo alive,
all routes time out; Agent 4 round-12 already notes backend-unreachable). All
wiring claims below are from code reads, NOT live curls.

## Lineage → implementation → route wiring

| Lineage | Live impl (wired) | Route | Shadow/dead impl |
|---|---|---|---|
| Amihud (2002) ILLIQ | `services/liquidity_metrics.py: AmihudIlliquidity` (stateful update/compute) | `routes/liquidity.py` POST `/api/liquidity/{ticker}/amihud` | `services/amihud_illiquidity.py` (191 lines, doc-heavy) — imported ONLY by `tests/test_amihud_illiquidity.py`. Not wired anywhere. |
| Kyle λ (1985) | `services/liquidity_metrics.py: KyleLambda` | `routes/liquidity.py` POST `/api/liquidity/{ticker}/kyle` | `services/kyle_lambda.py` (208 lines) — imported ONLY by `tests/test_kyle_lambda.py`. Not wired anywhere. |
| Kyle এটি → fragility | `liquidity_metrics.MarketFragilityIndex` | GET `/api/liquidity/{ticker}/fragility` | — |
| Hawkes (1971; Bacry 2015) | `services/hawkes_process.py` (535 lines, exp + power-law kernels, branching ratio) | `routes/hawkes.py` fit/intensity/simulate/state + `microstructure` GET `/hawkes/{ticker}` | — |
| VPIN (Easley-Lopez-O'Hara 2012, BVC) | `services/vpin_engine.py` (478) + `vpin_toxicity.py` + `vpin_cdf.py` | `microstructure` GET `/vpin/{ticker}`, `/toxicity-dashboard` | — |
| SABR (Hagan 2002) + SVI (Gatheral 2004) | `services/stochastic_vol.py: VolSurfaceConstructor` | `microstructure` GET `/vol-surface/{ticker}` | — |
| IV skew / term structure | `services/iv_skew_analyzer.py` (IvSkewAnalyzer, percentile, flags) | via quant_full (check on live backend) | — |
| Overnight drift / dealer fragility / gamma spillover | `services/gex_paper_accurate.py: overnight_drift_risk:2013, dealer_balance_sheet_fragility:2165, cross_asset_gamma_spillover:2339` | consumed by `services/morning_briefing.py` (init + return dict) | — |
| Max-pain drift | `services/max_pain_drift.py` (DuckDB daily accumulation, per-expiry) | internal (briefing/history) | — |

## Findings for Phase 9

1. **Duplicate Amihud/Kyle implementations.** The standalone `amihud_illiquidity.py` /
   `kyle_lambda.py` are reference-grade docs with tests but zero route wiring; the
   live path is `liquidity_metrics.py`. Recommend: Agent 3 either deletes the
   shadows or re-exports them (operator rule: delete whatever we don't need).
   Frontend must target ONLY the wired routes.
2. **Flowseeker scan path consumes NONE of these.** `flowseeker.py` /
   `flow_quality.py` / `routes/flowseeker.py` have zero imports of the above.
   All paper lineages live on parallel quant routes (`/api/liquidity`,
   `/api/hawkes`, `/api/microstructure`, briefing). W2/W3 frontend use = new
   fetches, not existing state. Until backend is reachable, frontend work
   against these stays fixture-first.
3. **VPIN honesty gap (open, Agent 3):** Phase 7 prohibits VPIN-from-snapshots.
   `VpinEngine.push_bucket` input source not yet traced to bar/tape origin —
   needs Agent 3 to confirm it eats real bars, not snapshot-derived buckets.
   Do NOT surface VPIN in Tidehunter UI until that traces clean.
4. **SABR/SVI + skew are display-ready candidates** for W3 modal / W5 depth once
   backend is up: `/vol-surface/{ticker}`, skew analyzer outputs. No paid key.
5. **Overnight/fragility already in briefing** — W4 history views can quote the
   briefing endpoint instead of rebuilding; no new backend needed.

## Implementability map (task 42 seed)

- Frontend-only NOW: burst highlight (shipped), strategy badges (shipped),
  spread/Fill/overview (shipped), tracker v1 on Public quotes (needs :3000 proxy).
- Fixture-first, wire when backend back: ΔOI (Mongo snapshots), earnings
  proximity (B2), FINRA/RegSHO panel (B3), vol-surface/skew modal tabs.
- Blocked on Agent 3 proof: VPIN display, B1 cadence (RVOL baseline, W4 trends),
  min_volume align (B5), quiet-accumulation gate (B6).
