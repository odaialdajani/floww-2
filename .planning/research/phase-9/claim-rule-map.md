# Claim-to-Rule Map — Agent 4

**Rule:** confidence confirmed = abstract+record opened · partial = abstract-only or secondary ·
unverified = not confirmed, never cite. Every product rule carries its WITH § cite.

## Informed-flow papers

### Pan & Poteshman 2006 — CONFIRMED
- Core claim: buyer-open put-call volume ratio predicts; low PC (call-heavy) outperforms high PC by
  >40bp next day, >1% next week; stronger for high-leverage OTM.
- Product rule: unsigned put/call concentration rising + short-dated OTM puts bid up →
  bearish-informed-positioning candidate; requires second confirmation (smirk or parity gate) before score ≥92.
- ROUND-2 CAVEAT: backend `put_call_ratio_signal` uses OI totals, NOT P&P buyer-open volume — OI-based PCR
  must never cite P&P without the "different input" disclaimer (see refuted-claims-audit V5).
- UI allowed: "put-heavy positioning vs calls (unsigned snapshot proxy)".
- UI prohibited: any "7–90 DTE band", "3×OI rule", "$25k rule" attributed to P&P (REFUTED attributions).
- Fixture: pulse-rows put/call concentration pair.

### Johnson & So 2012 (JFE, NOT a Reg-SHO paper) — CONFIRMED
- Core claim: high O/S predicts lower future returns; stronger when short-sale costs high.
- Product rule: hard-to-borrow/high-short-interest + abnormally high options share → upweight bearish
  options signals; borrow-constraint tag.
- UI allowed: "elevated options share with borrow constraints (Johnson–So 2012 context)".
- UI prohibited: citing it as a Reg-SHO / short-sale-constraint paper.
- Fixture: Reg SHO context + scanner row with borrow flag.

### Roll, Schwartz & Subrahmanyam 2010 — CONFIRMED
- Core claim: O/S rises around earnings; higher O/S predicts lower post-earnings abnormal returns.
- Product rule: earnings ≤7d + elevated options share → bearish-leaning bias; tighten stops; demand
  smirk confirmation for bullish alerts.
- UI allowed: "elevated activity into earnings — efficiency literature leans cautious".
- UI prohibited: "earnings will pop/drop".
- Fixture: earnings-proximity scanner rows.

### Cremers & Weinbaum 2010 — CONFIRMED (ROUND-11: abstract verified verbatim — 51bp/wk, both legs, not borrow-driven, decay over sample)
- Core claim: call-IV-minus-put-IV (matched pairs) predicts; expensive calls outperform by ~51bp/wk;
  not explained by short-sale constraints.
- Product rule: persistent positive call-minus-put IV across ≥2 strikes (borrow/div/rate sanity-checked)
  → bullish informed tilt; mirror for bearish.
- UI allowed: "calls priced rich vs puts on matched strikes".
- UI prohibited: "parity guarantees convergence".
- Fixture: overview/scanner IV-deviation rows.

### Xing, Zhang & Zhao 2010 — CONFIRMED (ROUND-11: abstract verified verbatim — 10.9%/yr, 6mo+ persistence, worst next-Q earnings)
- Core claim: OTM-put-minus-ATM-call smirk; steepest smirk underperforms ~10.9%/yr; worst next-quarter
  earnings shocks; persists ≥6 months.
- Product rule: smirk in top decile of name's own 6-mo history → bearish informed flag; gates bullish alerts.
- UI allowed: "steep smirk vs own history (defensive positioning)".
- UI prohibited: "crash coming".
- Fixture: smirk-boundary scanner rows.

### An, Ang, Bali & Cakici 2014 — CONFIRMED (ROUND-11: abstract verified verbatim — IV CHANGES both directions, slow diffusion)
- Core claim: 1-month CHANGES in call IV (+) / put IV (−) predict returns (~1%/mo QUINTILE spread — round-11 correction, abstract says first-vs-fifth quintile — slow-diffusion implication).
- Product rule: use IV changes on monthly lookback, not levels.
- UI allowed: "call IV rising on the month".
- UI prohibited: "high IV is bullish" (levels claim — refuted as attribution).
- Fixture: IV-change tracker items.

### Ge, Lin & Pearson 2016 — CONFIRMED
- Core claim: opening call purchases strongest predictor; closings mostly uninformative; OTM/high-leverage stronger.
- Product rule: weight OI-increase + volume proxies far above OI-decrease signals; falling-OI-only
  signals suppressed below 92.
- UI allowed: "new-positioning proxy (OI rising)".
- UI prohibited: "confirmed opening buy".
- Fixture: ΔOI column cases (rising vs falling OI).

### Garleanu-Pedersen-Poteshman 2009 — VERIFIED FULL TEXT (round 3)
- Full citation CONFIRMED from publisher PDF (fetched 2026-09-03, 117k chars cached):
  "Demand-Based Option Pricing", RFS 22(10), 2009, doi 10.1093/rfs/hhp005 (© Author 2009, Advance Access
  Feb 2009; 2008 = SSRN WP year only). Source: https://pages.stern.nyu.edu/~lpederse/papers/DBOP.pdf.
- Core claim (verified, abstract+intro): end-user net demand → market-maker inventory → option price
  effects proportional to unhedgeable variance/covariance; explains index-option expensiveness/skew
  (time series) and single-stock expensiveness (cross-section).
- Supports: dealer-inventory-pressure CONTEXT display only ("dealers positioned long/short gamma
  inventory — demand-pressure context, GPP 2009").
- Does NOT support: the code's GEX+PCR proxy construction, any directional trade signal, or IV-premium
  calibration. Both backend docstrings must read "(2009)" + "our proxy" (closes V7 pending edit).
- ROUND-4 middle-section findings (verified from full text): end-users net LONG SPX (large OTM-put piles,
  "crashophobia") with dealers SHORT index options (daily delta-hedged P/L swings $100M↔$-$100M, ~$800M
  cumulative over 6y); end-users net SHORT single-stock options; ~1/3 of index expensiveness from demand;
  smirk steepness tracks demand skew. Usable context: index-vs-single-stock positioning asymmetry +
  demand↔smirk link (supports XZZ rule context). Still supports NO directional signal.
- NEW CANDIDATE (unverified, source-request): Bollen & Whaley 2004 — signed option volume ↔ IV changes
  (cited inside GPP). Pull before any use.

## Gamma papers

### Ni et al. 2021 RFS — CONFIRMED mechanism, REFUTED formula/sign-rule attributions
  (ROUND-6: 2006 working-paper full text verified — mechanism + no-formula confirmed at source)
- Core claim: hedger net-long gamma dampens, net-short gamma amplifies (trade WITH the move when short).
  Daily horizon, modest economics, no intraday timing, no dollar threshold.
  WP magnitudes (verified): −1σ net-gamma shock → 37bp absolute-return move on 310bp base (~12%).
- Product rule: sign-of-gamma → amplify/dampen zone labels only.
- UI allowed: "negative dealer-gamma zone — hedge flow leans with the move (Ni et al. 2021 mechanism)".
- UI prohibited: GX formula as "Ni et al."; calls(+)/puts(−) sign rule as paper claim; "short-gamma moves chase" quote.
- Fixture: gamma-zone scanner rows (± sign).

### Barbon & Buraschi Gamma Fragility — CONFIRMED paper, MIXED sub-claims
  (ROUND-5: FULL TEXT FETCHED from UniSG Alexandria open-access — verdicts below are full-text, not abstract)
- Core claim (abstract): dealer gamma imbalance × illiquidity → intraday momentum (negative) / reversal
  (positive); related to flash-crash frequency/magnitude (association, NOT calibrated probability).
- Product rule: negative gamma + illiquid → "momentum-risk (fragile)" tag; positive → "reversal-lean";
  never a crash probability number.
- UI allowed: "fragile — illiquid + short gamma".
- UI prohibited: ΓIB formula as "Barbon–Buraschi"; zero-gamma flip as academic; intraday regime
  prediction; crash probability.
- ROUND-5 full-text numbers (usable with caveats): ΓIB¹=(Γ$Call−Γ$Put)/ADV×100, ΓIB²=(Γ$Call+Γ$Put)/ADV×100
  (Eq. 3/4, dealer-position assumption required); autocorrelation effect peaks at h=30min but is small
  (~1% of a std); flash-crash relative risk doubles per −1σ (t=5.99) WITH no-causation caveat + post-2010
  decay; sample = 300 largest-by-dollar-OI names, 1996–2017. Copy must carry "association, large-cap
  sample, pre/post-2010 regime" qualifiers.
- Fixture: fragility-tag boundary cases.

### Baltussen et al. 2021 — CONFIRMED (ROUND-8: abstract verified verbatim, DOI 10.1016/j.jfineco.2021.04.029)
- Core claim: rest-of-day return positively predicts last-30-min return (hedging demand); reverts after.
- Product rule: large day-move into close + negative dealer gamma → EOD momentum lean; never promise
  next-day continuation.
- UI allowed: "end-of-day momentum lean (fades next session)".
- UI prohibited: "will continue tomorrow".
- Fixture: EOD-lean alert case (TTL/dedup interaction).

## Dark / retail papers

### Zhu 2014 — CONFIRMED, QUALIFIED (model, conditional) (ROUND-11: abstract verified verbatim)
- Core claim: informed cluster lit; adding dark pool CAN improve discovery under conditions. Says nothing
  about any single print's direction.
- Product rule: ATS share shown as venue mix with delay stamp; never bull/bear language.
- Fixture: FINRA context payload.

### Comerton-Forde & Putnins 2015 — CONFIRMED (key honest-product paper) (ROUND-11: abstract verified verbatim, DOI 10.1016/j.jfineco.2015.06.013)
- Core claim: dark trades less informed than lit; block dark trades show NO evidence of impeding discovery.
- Product rule: blocks labeled "execution footprint, no direction"; high non-block dark share = market-structure
  context, not a trade signal.
- Fixture: dark-pool level payloads.

### Boehmer et al. 2021 — CONFIRMED with hard scope limit
  (ROUND-10: abstract verified verbatim — ~10bp/wk, <half persistence, "suggestive (but only suggestive)")
- Core claim: SIGNED retail imbalance from subpenny TAQ markers predicts ~10bp/wk. Requires signed data.
- Product rule: with only unsigned aggregates → display "NOT computable here", no retail arrow.
- UI prohibited: any retail prediction without signed TAQ imbalance.
- Fixture: missing-field state (unsigned → unavailable).

### Barber & Odean 2000/2011 — CONFIRMED (behavioral, not directional)
- Product rule: retail-sentiment proxy carries "frequent trading historically lowers net returns" context.
- UI prohibited: "retail bought so price rises".
