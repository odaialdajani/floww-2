# Tidehunter Pro — Architecture Handoff for External Review

Date: 2026-09-03. Repo: floww/Confluence Decoder (private). Audience: professional
software architect (HFT background preferred). Purpose: critique and improve our
build plan. Lane note: 4+ agents work this repo concurrently; `frontend/src/App.js`
and all of `backend/` are owned by other lanes — propose, don't touch.

## 1. What Tidehunter Pro is

Institutional options-flow surface inside a retail trading terminal (FastAPI :8000 +
React 18/CRA :3000 + Mongo + in-memory DuckDB + 15s poll cadence). Three views:

- **Pulse tape** — per-ticker live table. 14 columns: FLOW ET / SYM / STRIKE / C/P /
  OTM% / EXP / DTE / PRICE / SIDE / SIGNAL / BADGES / SCORE / SIZE / PREM (+90s
  rollup subline). Gates: ticker scope, DTE band (0-7/21/45D), min score.
  Reference design: BladeMap Pulse (screenshot spec in repo notes).
- **Scanner** — market-wide, one row per contract (volume, premium, bid/ask mix,
  sentiment, OI change, sweep %). Alert engine fires SCORE≥92 / WHALE≥$25M /
  SIGMA≥6σ / 0DTE rules with per-rule TTL dedup + 4/hour noise cap.
- **Conviction/outcomes** — per-alert conviction scoring; outcome ledger measures
  hit-rate by band (read-only calibration; thresholds are the desk's dials).

Data reality (read this first): we have **snapshot chains, not a print tape**.
Public API chains carry bid/ask/last/vol/OI/IV/greeks per contract. There is no
OPRA feed, no signed prints, no multi-exchange sweep visibility. Therefore SIDE
(last-vs-mid inference), sweep classification, and any "VPIN" are heuristics or
explicitly labeled proxies. Anything in this doc or the code claiming otherwise
is a bug — file it as such.

## 2. Current state (all shipped + tested this week)

- Pulse rebuild + trailing-90s print buffer + ticker-coupled feed (commits 6948ffe,
  bf00d48). Frontend Jest: flowseeker trio 146/146; full suite 40 suites / 291 tests.
- Threshold parity (SCORE 92 / $25M / 6σ enforced in engine defaults, 0DTE loophole
  closed with volOI≥2), put-ASK keeps reference-BULLISH + HEDGE? tag (f55bd4a).
- Solstice token retoken, reference chrome (refresh/pause/HOW-TO-READ/tooltips),
  formatter unification (scanLogic single source), dead-view deletion (bdd57c0,
  0f7fbb2, 6a0a366).
- Universe fully open: all allowlists/priority gates deleted; quality gates intact
  (c5cba5a). 23 dead files (~5k lines) deleted incl. unmounted panel cluster.
- GSD Phase 7 CLOSED. Phase 9 (Academy Flow Build) PLANNED with waves W0–W7 —
  see `.planning/phases/phase-9-academy-flow/PLAN.md` + REQUIREMENTS.md.

## 3. The build plan you are reviewing (Phase 9, condensed)

- W0 spikes: OPTION-bar support?, heat-score inputs, yfinance field check.
- W1 tracer: spread-position bar + Fill cols + overview bar (NetPrem, P/C, defined
  FIR, formula-gated session label; RVOL honest-empty pre-baseline).
- W2: earnings proximity (Finnhub free calendar), sector filter (free profile2 +
  static map), ΔOI col (Mongo snapshots), strategy badge port.
- W3: chart modal v1 (2 views), Tracker v1 (bookmark + live P/L, localStorage-first),
  Size>OI/Vol>OI highlighting, ONE per-tab config substrate.
- W4: NetPrem trend, strike distribution, Vol/OI-14d, 10 tabs, ticker !exclude,
  cap/sort, CSV. Fixture-first; live on snapshot cadence (backend dependency).
- W5: signed score spec (display-only) + Databento backtest harness.
- W6 filter depth: equity-type toggle, sweeps/side chips, OTM/OPEX/strike-range,
  OI-growth/sentiment sliders, row icons. W7 methodology: starter tabs,
  in-modal investigation checklist, funnel empty-states, dark-pool levels overlay,
  right-click actions.
- Verification per wave: new signal ⇒ new evaluator; full suite green; numeric
  metrics (not adjectives); six-gate loop incl. perf profile + states-per-surface.

## 4. Academic grounding (all opened + checked 2026-09-03; full reports in
/tmp/wf_smart/, since cleaned — ask for re-pull if needed)

CONFIRMED and used: Pan-Poteshman 2006 (buyer-open PC predicts; stronger OTM);
Johnson-So 2012 (O/S × borrow costs); Roll et al. 2010 (O/S + earnings);
Cremers-Weinbaum 2010 (parity-dev ~51bp/wk); Xing-Zhang-Zhao 2010 (smirk ~10.9%/yr);
An et al. 2014 (IV changes); Ge-Lin-Pearson 2016 (openings predict, closings don't);
Ni et al. 2021 RFS (hedger gamma dampens/amplifies — mechanism only);
Barbon-Buraschi Gamma Fragility (imbalance × illiquidity → momentum/reversal,
association only); Baltussen et al. 2021 (EOD momentum); Boehmer et al. 2021
(retail scope-limited); Zhu 2014 / Comerton-Forde-Putnins 2015 (dark = unsigned).
REFUTED and removed from code/copy: P&P 7–90 band, Ni GX formula + sign rule,
ΓIB-as-Barbon, flip-as-academic, crash probabilities, two phantom papers,
-$200mm folklore, VPIN-from-snapshots.

## 5. Known constraints (design around these)

- Snapshots are request-driven (no scheduler cadence yet) and capped at 50/ticker
  in Mongo; shared DuckDB is :memory:. History-backed features need backend B1.
- /bars route is equity-only; no contract bar history (snapshots substitute).
- Finnhub earnings free = 1-month history; multi-quarter surprise trends impossible.
- Tradier sandbox = delayed, no Greeks; realtime needs funded account.
- No free real-time dark-pool prints exist (FINRA weekly + Reg SHO daily only).

## 6. What we want from you

1. Wave order and scoping: what would you cut, merge, or reorder, and why.
2. The signed-score spec: sanity-check the sign matrix (SIDE×C/P×hedge) and magnitude
   weights against the papers in §4 — what's overfit orlaunders noise as signal.
3. Alert-gate economics: are 92/$25M/6σ + per-ticker cap + 4/hour the right throttle
   shape for a whole-market universe, or would you gate differently.
4. Data architecture: given snapshot-only inputs, what is the highest-leverage
   backend investment (cadence? file-backed DuckDB? OPRA slice?) and in what order.
5. Anything in §4 you'd dispute, plus papers we're missing (0DTE-specific and
   2023+ intraday-momentum literature are known thin spots).
6. Failure modes: where does this design lie to the user, and what breaks first
   at 10× flow volume.

Key files: `frontend/src/components/flowseeker/FlowseekerProBlademap.jsx`,
`scanLogic.js`, `.planning/phases/phase-9-academy-flow/`. Tests:
`cd frontend && npx craco test --watchAll=false`. Please return comments as a
marked-up copy of §3/§6 or a ranked issue list with severity + rationale.
