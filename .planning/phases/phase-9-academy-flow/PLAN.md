# Phase 9 — Academy Flow Build (Skylit Flowseeker parity, Public-API-first)

**Status:** PLANNED 2026-09-03 · **Parent:** ROADMAP.md (new; Phase 8 owned by another agent)
**Sources:** 6 Skylit Academy Flowseeker articles (user-pasted 2026-09-03),
`/tmp/wf_academy/gap_matrix.md` (HAVE/CAN/NEED + rethink + architecture decision),
`/tmp/wf_academy/repo_flow.md` (4 verified flow repos), `/tmp/wf_academy/repo_data.md`
(GEX libs, dark pool, providers), `/tmp/wf_academy/ui_spec.md` (BladeMap visual spec).

**Goal:** every Academy capability that Public API + existing services can support,
built tracer-first with measurable acceptance. Nothing that needs a paid key or a
true print tape ships as anything but an honest degraded state.

## Locked decisions (from verification, not opinion)
- D1 Pulse stays PER-TICKER on Public API chains (only rows with real bid/ask → real
  SIDE/PRICE). Market breadth lives in Scanner. mkScanRow has no bid/ask/mid —
  forcing scan rows into the tape would silently degrade the reference's core columns.
- D2 Reference SIGNAL spec stands (ASK→BULLISH incl. put-ASK + HEDGE? tag, Phase 7).
- D3 Calibration stays open (desk's dials) but every new signal ships WITH its
  evaluator from day one (steal [3]: no signal without Performance_Evaluation).
- D4 Adopt per-tag 30-min outcome tracking (steal [1]) in the outcomes module.
- D5 Dark pool ships as FINRA context panel only (weekly ATS + daily Reg SHO, keyless
  ETL). Never a live tape on free data. Real-time TRF prints = paid gate.
- D6 Greeks computed in-house (steal 1a/1b formulas); never depend on vendor greeks.
- D7 One chain interface yfinance→Tradier→Databento (steal 1c/1d adapter pattern).
  Tradier verified: sandbox = delayed chains WITHOUT greeks; realtime + hourly
  Greeks need a funded brokerage account. In-house Greeks matter on every tier.
- D8 Alert rule upgrade (steal [1]): volume >2σ AND price-range compression <1σ
  (coiled-price requirement) evaluated as an additional gate, display-first.

## Waves (tracer-first; commit per wave; Jest evidence each)
**Shipped 2026-09-03:** W1 [DONE be99db2] + W6 [DONE cfe073c] (full suite 54/54,
380/380). F4-OI-growth + |score| deferred per tickets; OI-growth needs B1.
- **W0 Spikes (cheap, de-risk):** OPTION instrument_type on public bars (fallback:
  snapshot-derived contract history); OpenTerminalUI [2] heat-score/sentiment read;
  yfinance earnings/sector field check. Output: go/no-go per item, no product code.
- **W1 Tracer — tape depth, frontend-only:** Spread-position bar + Fill cols on Pulse
  (bid/ask/last already in rows) + Overview bar v1 (Net Premium, P/C, FIR as defined
  below, session label; RVOL ships as honest "needs baseline" state). Metric: bar
  values ±1% vs manual calc on same payload; spread bar matches (last-bid)/(ask-bid).
- **W2 Context cols:** finnhub /calendar/earnings method + cache → earnings-proximity
  col+filter; sector/industry filter (finnhub profile2, free, + static
  industry→sector map); ΔOI col (Mongo snapshot OI history until file-backed
  DuckDB lands); strategy badge ported to Pulse mapper (backend detect_spreads logic).
  Metric: ΔOI matches next-day exchange truth on 5 sampled contracts.
- **W3 Workflow:** chart modal v1 (Contract history + Net Premium ONLY — 5 views is
  scope creep; remaining 3 are W5); Tracker v1 (bookmark + live P/L via quotes +
  STILL-IN/PARTIAL/EXITED via OI drift; localStorage-first, Mongo promotion = gate);
  Flow Highlighting (Size>OI yellow / Vol>OI purple, per-tab persisted, synthetic
  fixtures prove 100% fire rate); ONE per-tab config substrate (tabs + columns +
  highlighting + filters — single object, not three features). Metric: tracker P/L
  within a tick of mark; highlighting 100% on fixtures.
- **W4 History-backed:** Net Premium trend + Strike Distribution + Vol/OI 14d footer
  (needs B1 cadence; frontend ships against fixtures first, wires live when
  cadence lands). Feed tabs (10) + ticker-scope search (!exclude) + results cap/sort
  + CSV export. Metric: trend values reproduce from snapshots on demand.
- **W5 Score + depth:** signed Flow Score spec (-100..+100: sign matrix SIDE×C/P×hedge;
  magnitude from spread/volOI/premium/IV weights) DISPLAY-ONLY + backtest harness on
  Databento credits; remaining 3 modal views; scanner depth filters (OI growth,
  sentiment sliders, OPEX). Metric: score components unit-tested; backtest reports
  Sharpe-gated per ADR-0001. Alert-gating on the score is explicitly OUT (later phase).

## Definitions (no vibes)
- FIR = |callPrem − putPrem| / (callPrem + putPrem), 0..1, per session window.
- RVOL = session premium-to-time vs 20d same-time baseline (DuckDB rollups; until
  cadence exists the bar shows "baseline building n/20").
  CORRECTED (H2): daily-resolution first from Mongo-50 day-premium means;
  intraday time-of-day baselines wait on file-backed DuckDB. Session Lean =
  sign(NetPrem) gated by FIR (H1): |FIR|≥0.3 → Bullish/Bearish else Neutral.
- Quiet-accumulation gate [1]: contract vol z-score >2 AND (contract range z <1 AND
  underlying range z <1) over the bar window.

## Backend-lane proposals (NOT this lane; file:line)
- B1 Snapshot cadence job in scheduler.py (fixed-interval precedent) for chains;
  raise/segment Mongo 50-cap or roll to DuckDB for intraday baselines.
- B2 finnhub earnings-calendar cache endpoint (free tier, aggressive cache).
- B3 FINRA ATS weekly + Reg SHO daily ETL → venue-share + short-pressure panel.
- B4 (folded into B6/B7 below — kept numbering stable, no reuse).
- B5 Align force_refresh min_volume 1000 vs market_scan 2500 (found Phase 7).
- B6 Quiet-accumulation gate D8 (vol z>2 AND price-range compression, display-first)
  in the alert eval path — needs baseline plumbing the frontend doesn't own.
- B7 Per-tag 30-min outcome tracking in the outcomes module (steal [1]).
- B8 Citation hygiene in backend/services/gex_paper_accurate.py: docstring lines
  ~10-24 present Eq.(2)/Sec II.B/Sec I/Sec III.C/“Ni-Pearson Sec. 3” attributions
  now REFUTED or unverified (see /tmp/wf_smart/paper_gamma.md §§1-2) — relabel as
  practitioner method “in the spirit of,” never as paper equations.
- B9 O/S-borrow inputs for V6: stock-volume share + short-fee/short-interest feed
  (or honest “unavailable” state if unwired).

## Paid gates (later, priced before built)
P1 Databento OPRA backfill → P2 live OPRA (true SIDE/sweep) → P3 TRF websocket
(Massive pattern) → P4 Tradier realtime+Greeks. No paid key is on the critical path.

## Verification loop (every wave)
1. New signal ⇒ new evaluator (steal [3]); fixtures prove fire rates.
2. Full frontend suite green; backend suites untouched-and-green.
3. Metrics in the table above, not adjectives. 4. Heredoc commit, own files only.
5. Every new surface ships loading/empty/stale/error/frozen states (7.9 pattern).
6. Perf profile recorded once per wave (H3); lane discipline per H4.

## NOT in scope
Mobile card layouts, Discord share/image export (after P1), Atlas overlay (Heatseeker
cross-check already same-terminal), options-strategy modal legs beyond badge,
any CBOE scraping (prohibited), any repo clones (patterns only, Nav's rule).

## Re-verification corrections (2026-09-03 — broke the first draft, fixed here)
- C1 Snapshots are REQUEST-DRIVEN (server.py:1143 saves on heatmap build), not
  scheduled: history exists only for viewed tickers at view cadence. B1 cadence job
  is a HARD dependency for W4-history items, not nice-to-have. Frontend ships
  fixture-first regardless.
- C2 Shared DuckDB is :memory: (duckdb_engine.py:540). All durable history reads go
  to Mongo (50/ticker cap) until the backend lane ships file-backed DuckDB. RVOL
  20d intraday baselines cannot live in Mongo-50 — DuckDB file or raised cap first.
- C3 /bars route is EQUITY-only (public_api.py:146). No contract bar history exists:
  W3 modal contract history = Mongo snapshots first; OPTION-bars route = backend
  proposal, not an assumption.
- C4 Spread bar gets an explicit no-quote state (bid/ask/last often 0 on fallback
  paths — the bar must say so, never guess position).
- C5 detect_spreads port needs field mapping (under→ticker, exp→expiration); mapper
  rows carry the full leg set, so the port is feasible in the W2 ticket.
- C6 ΔOI metric is only meaningful if the previous snapshot is prior-day close —
  cadence (B1) defines truth, not the frontend.

## W6 Filter depth (frontend-only, needs only W1 — the plan's biggest miss)
The Academy's filter system IS the product for most users; Phase 9 scoped only
premium/DTE/side. All computable from rows already in hand:
- F1 Equity-type triple toggle (Stocks/ETF/Index): static map (SPY/QQQ/IWM/DIA/TLT
  etc = ETF; SPX/VIX = index; else stock). ETF macro flow separated from single-name
  conviction per the article. Metric: toggling ETFs off removes all ETF rows on fixture.
- F2 Sweeps-only + Side (Bid/Mid/Ask) chips on Pulse (classification exists).
- F3 OTM/ITM/0DTE toggles + OPEX-week-only + strike-range (min/max) inputs.
- F4 Scanner: OI-growth filter (needs B1 cadence; fixture-first), contract/chain
  sentiment sliders from bid/ask mix, absolute-value score mode (|score| > X).
- F5 Row icons: sweep waves + multi-leg Layers badge from existing classification.

## W7 Methodology surfaces (needs W3 Tracker + modal; turns docs into UI)
- M1 Starter tab presets ship by default: "Broad $100K Stocks" + "High-Conviction
  Sweeps $250K |score|>60" (the Academy's recommended first setup, not an empty page).
- M2 Investigation checklist IN the chart modal (NetPrem 5-7D → Underlying$ →
  Contract+IV+RVOL → Strike-1W → Vol/OI-14d → Heatseeker cross-check), each step a
  checkbox with its read; hypothesis verdict recorded (confirmed/skipped + reason).
- M3 Funnel guidance in empty states: "0 rows — widen shortage" with one-click
  widen actions (drop score gate / widen DTE / include ETFs), per the ELI5 funnel.
- M4 Dark-pool levels overlay on heatseeker (Top-N horizontal dashed lines + notional
  labels from B3 FINRA data; needs B3 first — specced here, built after).
- M5 Right-click row actions: filter matching trades, exclude ticker (!TICKER),
  track trade (needs W3 Tracker). M6 Pulse sort by Premium/Size with the documented
  $25K-premium floor quirk on non-Time sorts.

## Fourth-read corrections (verified 2026-09-03)
- C7 Finnhub /calendar/earnings is FREE tier but limited to 1 month historical +
  new updates (verified in their docs; symbol filter + bmo/amc/dmh hour + quarter
  included). Earnings PROXIMITY gating (R9.3) fully feasible; multi-quarter
  surprise trends are NOT — drop surprise-history from W2, keep proximity + hour.
- C8 R9.6 modal Net Premium + R9.7 Tracker close-detection both need OI/premium
  HISTORY → B1 cadence dependency (like W4). Frontend fixture-first regardless;
  close-detection ships as live-P/L first, OI-drift stages gated on B1.
- C9 ROADMAP.md has no Phase 9 section (file owned by another agent, currently
  in-flight). Phase 9 wiring into ROADMAP + kanban cards waits until their edit
  lands — this dir is the source of truth meanwhile.

## Fifth-read corrections (verified 2026-09-03)
- C10 Sector source verified free: Finnhub profile2 (/stock/profile2) is explicitly
  the free Company Profile and returns exchange + finnhubIndustry. GICS sector
  needs a static finnhubIndustry→sector map (or yfinance .info fallback) — W2
  builds the map, not a new vendor. All remaining external claims in this plan
  are now verified against primary docs except FMP-250/day and Tradier-delayed
  (both snippet-grade: re-verify at build time if chosen).

## Institutional hardening (seventh read — optimization pass)
- H1 Session Lean is now defined (was hand-waved): Lean = sign(NetPrem) gated by
  FIR — |FIR|≥0.3 → Bullish/Bearish, else Neutral. RVOL modulates urgency copy,
  never direction. R9.2 metric covers it.
- H2 RVOL corrected: daily-resolution first from Mongo-50 snapshots (day premium
  vs trailing-20d mean); time-of-day intraday baselines wait on file-backed
  DuckDB (C2). No intraday-RVOL claims before then.
- H3 Performance budgets (institutional discipline): overview-bar aggregation
  <100ms on a 5k-contract chain (measured, memoized per poll); Pulse render stays
  capped; trend charts downsample to ≤500 points. Each wave profiles once and
  records the number — jank is a defect, not a vibe.
- H4 Execution lanes (Phase 7 taught this): Lane F = Blademap.jsx serial
  (W1→W6→W2-cols→W3-modal/tracker→W7); Lane S = scanLogic serial (gates, score
  spec); Lane D = CSS parallel anytime; backend B1-B7 async. Never two agents on
  one file — the fan-out failure mode is documented, not repeated.
- H5 Session-state awareness: every live surface carries LIVE/CLOSED/PREMARKET
  state; frozen data is labeled frozen (tracker P/L, overview bar) — never silently
  stale. Extends the 7.9 states pattern, which is now REQUIRED per new surface
  (added to the verification loop below).
- H6 Sweep resolution limit, stated: intermarket sweep needs multi-exchange prints;
  ours is heuristic (short-dated/size/voi proxy) until P2 OPRA. UI copy must never
  claim exchange-sweep certainty. Same honesty rule as dark pool (D5).
- H7 W5 backtest depends on P1 funding (Databento credits): harness + fixtures are
  free; live backfill is gated on the funding decision, explicitly.
- H8 B1 rate safety: scheduler cadence inherits the existing scan 429-backoff
  pattern (verified in flowseeker.py) — undisclosed Public limits are assumed,
  backoff is mandatory, not optimistic.
- H9 M2 verdicts persist localStorage-first (same gate as Tracker); promotion with
  Tracker schema, never before.

## P1 Paper-verified smart-money map (2026-09-03 — every claim opened+checked)
Reports: /tmp/wf_smart/paper_{informed,gamma,dark}.md. Killed on sight: GX-as-Ni,
ΓIB-as-Barbon, flip-as-academic, −$200mm line, crash probabilities, charm rules,
"Charming!" paper, phantom hedging-liquidity title, 7-90-as-P&P, VPIN-from-snapshots.
- V1 Parity-dev tilt (Cremers-Weinbaum 2010, JFQA: call-IV minus put-IV predicts
  ~51bp/wk) → W2: matched-pair IV screens from chains. Metric: fixture pairs flag.
- V2 Expiry-pin emphasis (Ni-Pearson-Poteshman 2005 JFE clustering) → W1/W2:
  expiry-day high-OI strike emphasis, NEVER extended off-expiry.
- V3 EOD momentum lean + next-day fade (Baltussen et al. 2021 JFE; Barbon et al.
  ΓHP) → W5: last-30-min tag on big-day/negative-gamma names, fade next morning.
- V4 Open-vs-close weighting (Ge-Lin-Pearson 2016 JFE: opening purchases predict;
  closings don't) → suppress sub-92 on falling-OI-only signals (needs B1 OI deltas).
- V5 Smirk/IV-change (Xing-Zhang-Zhao 2010; An-Ang-Bali-Cakici 2014) → cadence-gated
  (6m/1m histories); until B1, fixture-only.
- V6 PC-leverage + O/S-borrow (P&P 2006; Johnson-So 2012 JFE; Roll et al. 2010 JFE):
  unsigned PC proxy + smirk confirm now; borrow/short-fee inputs = B9 (backend lane).
- V7 Toxicity-proxy honesty (Easley et al. 2012): never label VPIN from snapshots —
  already compliant in UI; keep the rule as RMA gate on any future gauge.
- V8 Dark honesty (Zhu 2014 conditional; Comerton-Forde-Putnins 2015; BJZZ 2021
  scope-limited): blocks = execution footprint, never signed; ATS = venue mix with
  delay stamps; retail arrows NOT computable from ATS-weekly — show "not computable".
