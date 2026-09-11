# Refuted-Claims Audit — Agent 4 (2026-09-03)

**Scope searched (rg, case-insensitive, fixed strings):** frontend/src, backend/services,
backend/routes, backend/tests, docs, .planning. Excludes node_modules/.git.
**I do NOT edit copy — violations are reported with file:line for the owning lane.**

## 1. Checklist verdicts

| Claim | Verdict | Found in repo? |
|---|---|---|
| P&P 7–90 DTE band | REFUTED as attribution | VIOLATION — live in flow_alerts.py:165-167 (+4 boost) + :322 UI label; see V15 (round-1 "clean" verdict corrected) |
| Ni GX formula `gamma×DDOI×100×S²×0.01` as paper claim | REFUTED | See §2 — practitioner formula presented as paper methodology |
| Ni calls(+)/puts(−) sign rule | REFUTED as paper claim | See §2 (OI-signed gamma wrapped as "paper-accurate") |
| ΓIB-as-Barbon (`ΓIB = GEX/(S×ADSV)×100` as "Barbon-Buraschi Eq. 2") | REFUTED as cited (full text: imbalance is Eq. 3/4, see V3 verdict) | backend/services/gex_paper_accurate.py:40 "1. Gamma Imbalance (% of ADV) — Barbon-Buraschi Eq. (2)" + formula derivation lines 40–50 |
| flip-as-academic (zero-gamma flip detection as Barbon–Buraschi) | REFUTED as paper claim | gex_paper_accurate.py:19 "2. Zero-Gamma Flip Distance — Barbon-Buraschi Section II.B" |
| Crash probabilities | REFUTED (association only, never calibrated) | gex_paper_accurate.py:24,428,447: `flash_crash_risk()` returns `crash_probability_estimate` with hardcoded 1%/3%/8%/18% bands; line ~1111 comment "flash crash probability ≈ 2-5x" |
| Phantom papers ("Ni et al. Option Market Maker Hedging and Stock Market Liquidity"; "Charming!/retail follow-up") | "Hedging/Liquidity" title not found in repo — clean. "Charming!" VARIANT PRESENT: gex_paper_accurate.py:1005-1007 cites 'Charming! Retail Option Volume, Delta Hedging, and the...' SSRN 5054370 — see V6 (round-1 "clean" verdict for this row superseded) |
| -$200mm folklore (GEX rarely < −$200mm as SqueezeMetrics claim) | REFUTED | No "-200mm"/"200mm" string in backend/services, docs, .planning (only correctly as folklore in planning docs) — clean |
| VPIN-from-snapshots | PROHIBITED as "VPIN" label | backend/routes/vpin.py (full VPIN API), backend/services/vpin_toxicity.py (bulk-volume VPIN over call/put volume buckets — NOT signed trade flow), backend/routes/microstructure.py:124, backend/routes/quant.py:124-136 ("VPIN-based market toxicity"), backend/routes/ensemble.py (VPIN+QI ensemble). FRONTEND COPY IS HONEST: FlowseekerProBlademap.jsx:1353,1948 correctly state VPIN/Kyle-λ need a trade-level feed (n/a on snapshot chains); ToxicityGauge.jsx:136 honest empty state |
| Dark pool buy/sell claims | PROHIBITED | None found in frontend/src, backend, docs — clean |
| Confirmed buyer/seller claims | PROHIBITED | None in product code (only in planning docs as prohibited-example text + CONTRACTS.md:48 "No confirmed buyer/seller identity. Ever.") — clean |
| True sweep claims without venue data | PROHIBITED | No "true sweep / confirmed sweep / sweep detected" in product code; only docs/superpowers spec line 94 correctly states true sweep needs OPRA-grade data — clean |
| "guaranteed" / "will move" / "institutional buying detected" | PROHIBITED | Zero hits in frontend/src — clean |

## 2. File:line violations requiring owner action

All in backend lane (Agent 3 / backend owner). Agent 4 proposes relabeling only:

1. backend/services/gex_paper_accurate.py:6 — "Ni, Pearson, Poteshman & White (2020)" — wrong year;
   journal version is RFS 34(4), April 2021. Fix: correct citation + note working-paper 2006 draft.
2. backend/services/gex_paper_accurate.py:11-19 — module docstring presents practitioner GEX wrapper as
   "the paper-prescribed normalizations and decompositions" and "academic risk metrics proven in the
   literature". Fix: relabel as practitioner constructions "in the spirit of" the papers; cite Ni §1
   mechanism only for sign-of-gamma zones.
3. backend/services/gex_paper_accurate.py:40-50 — "Barbon-Buraschi Eq. (2)" with ×100 scaling the
   docstring itself admits differs ~13× from paper scale. Fix: drop "Eq. (2)" attribution or verify
   against full text; label ours.
4. backend/services/gex_paper_accurate.py:19 (:19 in docstring list) + flip function — "Barbon-Buraschi
   "Section II.B" zero-gamma flip. FULL-TEXT VERDICT (round 5): REFUTED — §II.B is "Gamma Imbalance" (the
   definition subsection); no flip/zero-gamma-level concept exists anywhere in the paper.
   Fix: remove section numbers until verified; label flip a practitioner level.
- V3-FULL-TEXT VERDICT (round 5 — UniSG Alexandria open-access PDF verified 2026-09-03): code's
  "Barbon-Buraschi Eq. (2)" for ΓIB cites the WRONG EQUATION — Eq. (2) defines dollar-gamma aggregates;
  the imbalance proxies are Eq. (3) ΓIB¹=(Γ$Call−Γ$Put)/ADV×100 (dealers-long-calls/short-puts assumption)
  and Eq. (4) ΓIB²=(Γ$Call+Γ$Put)/ADV×100 (long-both). Code's GEX/(S×ADSV)×100 matches neither and drops
  the dealer-position assumption. Also the spread result (~15bps per −1σ) is Table VII, not Table V as
  code :449 claims (Table V = illiquid×negative interaction — real). Fix: cite Eq. (3)/(4) with assumption
  stated, or drop paper numbering and label ΓIB-proxy ours.
5. backend/services/gex_paper_accurate.py:24,428-470 — `flash_crash_risk()` / "Flash Crash Probability
   Proxy — Barbon-Buraschi Sec. III.C" returning `crash_probability_estimate` (1/3/8/18% bands).
   REFUTED: paper shows association only. Fix: replace numeric probability with fragile/stable tag;
   keep "Table V ~16bp High-Low" as context only if verified. Highest severity.
6. backend/routes/vpin.py, backend/services/vpin_toxicity.py:55 (`push_bucket(call_vol, put_vol, ...)`),
   backend/routes/quant.py:124-136, backend/routes/ensemble.py — snapshot/bucket volume imbalance
   served under the name "VPIN". Per Easley-Lopez de Prado-O'Hara 2012 §§2–3, VPIN requires signed
   volume-time buckets. Fix: rename served metric "toxicity proxy (not VPIN)" everywhere user-visible;
   keep engine internals but quarantine the label. Note: frontend already does this correctly.

## 3. Clean areas (explicitly verified, no action)

- frontend/src: no "guaranteed", no "will move", no "institutional buying detected", no dark-pool
  directional language, no confirmed-buyer language. VPIN mentions are honest n/a-on-snapshot disclaimers.
- No P&P band / $25k / 3×OI citations in product code.
- No phantom-paper citations anywhere.

## 4. Recommended product changes (for CONTRACT_REQUESTS / backend owner)

- R1 (P0): kill numeric `crash_probability_estimate` from API responses; serve fragility tag.
- R2 (P0): rename all user-facing "VPIN" to "toxicity proxy"; add "requires signed flow for true VPIN" footnote.
- R3 (P1): fix Ni year (2020→2021 RFS) and strip unverified "Eq./Sec./Table" numbers from gex_paper_accurate.py
  docstrings; file exact replacement patch via Agent 3 workstream (B8).
- R4 (P2): add copy-checklist CI grep (terms in §1) to block regressions.

## 5. Round-2 addendum (re-verification pass, same day)

New violations missed in round 1, all with file:line. Severity upgraded where user-servable.

- V5 (P0): `put_call_ratio_signal` (gex_paper_accurate.py:616) computes PCR from **OI totals** but cites
  Pan-Poteshman 2006, whose result used non-public CBOE **buyer-open VOLUME**. OI-based PCR is a
  different input with different information content (Ge-Lin-Pearson 2016: closings uninformative —
  OI mixes both). Served via morning_briefing (routes/briefing.py, morning_briefing_api.py, server.py).
  Fix: label "OI-based PC proxy (not P&P buyer-open volume)" or drop citation.
- V6 (P0): `charm_hedging_pressure` (gex_paper_accurate.py:1000) cites "Ni-Pearson-Poteshman-White (2021)"
  for charm. The gamma verification pass explicitly REFUTED any Ni-team charm paper and ruled
  "charm stays out of v1". Morning-briefing comment (morning_briefing.py:750) repeats "Ni-Pearson 2021 Charm".
  Fix: remove attribution; hold charm behind unverified flag.
- V6-UPGRADED (round 4): the docstring (gex_paper_accurate.py:1005-1007) names the phantom paper outright:
  "'Charming! Retail Option Volume, Delta Hedging, and the...' SSRN 5054370" attributed to
  "Ni-Pearson-Poteshman-White (2021)". This is the exact phantom title the gamma pass refuted
  ("no Ni-team paper matching 'Charming!' found in author publication lists"). A named SSRN number
  attached to a nonexistent paper is a fabricated citation — highest fix priority in backend lane.
  Same docstring's Args list documents `gamma` and `net_gamma` params absent from the signature
  (delta, theta, dte_days) — stale docs. Fix: delete citation + phantom SSRN, correct Args.
- V5-ADDENDUM (round 4): `put_call_ratio_signal` docstring (:624) mistitles P&P as 'The Information OF
  Option Volume...' — actual title uses 'IN'. Trivial; fix with the V5 relabel.
- V19 (P2, acceptable-with-label): flow_outcomes.py:55 justifies N=2 forward sessions as "Pan-Poteshman
  next-day power". P&P did find next-day (+weekly) predictability, so the horizon heuristic is defensible —
  but it must read "heuristic" not derivation. oi_hygiene.py:18-20 + fetch_earnings.py:7-9 cite P&P as a
  caveat ("semantics don't transfer") — CORRECT usage, no action.
- V20 (P1, round 13): FIR DEFINITION DIVERGENCE. CONTRACTS (agent1 branch, overview payload ~:104) defines
  fir = |callPrem−putPrem|/(callPrem+putPrem) with sessionLean from |FIR|≥0.3. Shipped overviewStats
  (scanLogic.js:640-657) computes fir = |bullPrem−bearPrem|/(bull+bear) where bull/bear are SIGNAL-side
  premiums (call-ASK+put-BID vs opposite) — a different ratio with different semantics (directional
  conviction vs call-put positioning). Same name, same 0.3 threshold, different quantity. Lean thresholds
  match, rvol:null honest — but any evaluator built on the contract FIR (incl. Agent-4's own fixture
  P-overview 0.185) will disagree with the implementation. Fix: rename code's metric (e.g. signalFIR) or
  align to contract; Agent 1 triages at merge.
- V7 (P1): GPP year shuffle — `option_demand_pressure` says "(2008)" (gex_paper_accurate.py:781),
  `demand_pressure_premium` says "(2009) RFS" (:1676). Verified 2026-09-03: Garleanu-Pedersen-Poteshman,
  "Demand-Based Option Pricing", RFS 22(10):4259 (RFS vol 22 = 2009; 2008 = SSRN WP year) —
  https://academic.oup.com/rfs/article-abstract/22/10/4259/1590158, PDF at
  https://pages.stern.nyu.edu/~lpederse/papers/DBOP.pdf (not yet opened — PULL before citing beyond existence).
  The GEX+PCR proxy construction is ours either way. Fix: unify to "(2009)" + "proxy" label.
- V8 (P1): `overnight_drift_risk` (:2013) claims "overnight/next-day returns documented in
  Barbon-Buraschi (2021)" — but verified findings say EOD effects DISSIPATE/revert next day (Barbon EOD WP,
  Baltussen 2021). A next-day drift claim contradicts the fade finding. Fix: verify or remove.
  `dealer_balance_sheet_fragility` (:2165) cites vague "Post-SVB (March 2023) research" — no paper named.
  Fix: name a source or drop the research framing.
- V9 (P0, frontend): HOW-TO-READ popover (FlowseekerProBlademap.jsx:1301 — was :1266 before Agent-2
  edits; re-verified round 6) + column tooltips (:1330, was :1295)
  assert inference as fact: "SIDE = where the print crossed: ASK (lifted the offer → aggressive buy)",
  "Price paid per contract (last print…)", "latest print". No "inferred"/"proxy" anywhere on SIDE/SIGNAL;
  "print" implies a tape we do not have. Fix: "SIDE (inferred — last vs mid, no tape)" + "quote stamp".
- V10 (P0): THREE conflicting sweep definitions: CONTRACTS.md (dte≤2 AND premium≥$5M) vs
  FlowseekerProBlademap.jsx:83,594 (premium≥$50M→block, dte≤2→sweep regardless of premium) vs
  scanLogic.js:72-77 scanTypeOf (vol≥25000→sweep, vol≥80000→block, volOI bands — no DTE/premium at all).
  Plus certainty language: "Sweep (urgent)" (:1290), preset "High-Conviction Sweeps"
  (methodology/presets.js:10-13). NEW round 6: row tooltip (FlowseekerProBlademap.jsx:1351) reads
  "Sweep: urgent multi-exchange fill (heuristic)" — "(heuristic)" mitigates but "multi-exchange fill"
  asserts cross-venue visibility we do not have (no OPRA). Fix: "multi-print burst proxy" or equivalent
  with no venue noun. Only FilterBar.jsx:9 carries "(proxy)". Fix: single definition owned by
  scanLogic (formatter single-source rule), proxy label everywhere, reconcile CONTRACTS.
- V11 (P1): SIDE vol/OI fallback (FlowseekerProBlademap.jsx:88,595: voi≥1.5→ASK when quote missing) means
  the NO_QUOTE/unavailable path is UNREACHABLE for side — every row gets a confident ASK/BID. This
  contradicts CONTRACTS C1 honest-empty states and the score-spec "SIDE missing → unavailable" rule.
  Fix: NO_QUOTE rows render SIDE as "—" (unknown), never fallback-guess.
- V12 (P2): WHALE naming collision — $1M tape badge vs $25M alert rule. Mitigated by in-popover disclaimer
  (:1266). Keep disclaimer; consider rename to avoid desk confusion.
- V13-FULL-TEXT VERDICT (round 5): Table VIII is REAL (flash-crash dummy regression) but the code
  contradicts it: paper reports t-stat 5.99 ("−1σ shift DOUBLES crash probability; +25% when negative");
  code :1091 claims "coefficient −1.15, t=−2.97". Paper adds an explicit no-causation caveat ("correlation
  does not imply causation... do not interpret as evidence dealers cause flash crashes") and notes the effect
  weakened after 2010 circuit breakers — both omitted by the code. Sample: 77 large caps, 1997–2015,
  672 events (~1 crash/2yrs/stock, avg drawdown 3.71%, 5% if negative-gamma vs 3% if positive).
  Code's 1/3/8/18% bands remain fabricated; "≈2-5x" happens to rhyme with "doubles" but is presented as a
  general probability, which the paper never licenses. COR 2018 confirmed in-text (correct spelling Renò);
  COR detects bursts from high-frequency PRICES (30-min bandwidth, |T| crossing 3, ≥1% drop) — the gamma_proxy
  fallback path still misattributes price-based detection theory to a gamma proxy. Fix per V13.

Propagation note: V1/V5–V8 all flow into morning_briefing metrics (morning_briefing.py:885-925) served via
API — audit scope must henceforth include briefing consumers, not just gex_paper_accurate.py.

## 6. Round-3 addendum (hardening pass)

- V15 (P0, HIGHEST — live refuted attribution in scoring): backend/services/flow_alerts.py:165-167 adds
  +4 to the 0–100 composite when `7 <= dte <= 90 and vol_oi >= 3 and premium >= 25e3`, commented
  "Informed-positioning band (Pan & Poteshman, RFS 2006)". The 7–90 band, 3×OI, and $25k rules are all
  REFUTED as P&P attributions (P&P used buyer-open volume, no DTE band). User-facing label
  (flow_alerts.py:322): "Informed-positioning band (7–90 DTE, Pan-Poteshman)". WIRED: 8 import sites in
  backend/routes/flowseeker.py (lines 716, 1011, 1088, 1265, 1357, 1388, 1838, 1871 — round-5 recount;
  earlier "6" was undercounted) + alphapod_compat.py:78.
  CORRECTION: round-1 verdict "no P&P occurrence in product code" was WRONG — the grep missed the
  en-dash "7–90" form and under-searched backend/services. Fix: strip +4 band and citation, or relabel
  "internal tenor heuristic (not P&P)" with outcomes read.
- V16 (P0): V1 propagation CLOSED as served: GET /api/briefing/{ticker}
  (backend/routes/morning_briefing_api.py:160,194) returns `"metrics": result.metrics` wholesale, and
  metrics include `flash_crash_risk` with `crash_probability_estimate` (morning_briefing.py:898).
  The numeric crash probability is client-visible today.
- V14 (P2): "split" classification exists in scanLogic.js scanTypeOf, CSS (.fsb-type-split), and tests,
  but has ZERO hits in CONTRACTS.md — contract gap. Fix: Agent 1 adds split to C1 or code drops it.
- V17 (P1): flow_alerts.py:247 comment "paper-accurate ΓIB is our hardest" + :270-273 double-weights
  `gex_confluent` in confluence scoring on the unverified ΓIB formula (V3). Fix: down-weight until V3
  verified; label "ΓIB-proxy confluence".
- V18-CLOSED (round 5, NO VIOLATION): cw_iv_spread (flow_quality.py:82) pairs SAME under+exp+strike
  call-vs-put IV with min-volume weighting — exactly the matched-pairs construction CW requires. Label
  "Cremers-Weinbaum IV spread confirms" stands; suggest "volume-weighted CW proxy" polish (P2, optional).
- Score-spec reconciliation: product scores 0–100 backend composite (flow_alerts) / 0–10 pulse display
  (pulseScore10) / SILVER-GOLDEN-WHALE premium tiers. The signed −100..+100 spec is a NEW display overlay:
  sign = existing SIDE→SIGNAL (D2), magnitude = rescale of existing 0–100 with §4 caps. No existing
  score is replaced; mapping table belongs in the Agent 2 implementation ticket.
