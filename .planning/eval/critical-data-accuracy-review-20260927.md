# Critical main-screen data accuracy review - 2026-09-27

Verdict: initial HIGH-IMPACT calculation/coverage defect corrected; final backend fix independently PASS as documented below. No production edits. Scope: substantive current dashboard regime accuracy; no shutdown/security/cosmetic expansion.

## Finding: missing model inputs can reverse the displayed regime or fabricate a zero-gamma state

The mounted status strip receives gamma_regime_v1.sign. solstice_regime.regime_at_spot treats every standard-multiplier contract as usable, while gamma_curve silently skips contracts with missing/nonpositive IV or remaining time. It does not return missing-model-input coverage. The surviving subset can therefore publish POSITIVE/NEGATIVE as the full requested population; if none survive it publishes ZERO/ZERO_CURVE plus apparent roots.

This is a reachable provider shape: public_api_adapter retains `_finite(oc.iv)` as None independently of valid gamma, OI and exact remaining time. The vendor-gamma display remains valid and usable, so no missing-model-input warning is supplied by main quality.

## Exact local reproduction

Pure inputs, spot 100, ticker SPY, expiry 2030-01-15, strike 100, T 0.1, multiplier 100, gamma 0.01 for each row:

- call: OI 200; put: OI 100.
- Both IV 0.2: modeled value +62741.0393568116; displayed sign POSITIVE; vendor net +10000.
- Change only call IV to None: modeled value -62741.0393568116; displayed sign NEGATIVE; vendor net remains +10000.
- Change both IV to None: modeled value 0; displayed sign ZERO with ZERO_CURVE; vendor net remains +10000; 100 touch-root entries returned.

Expected: losing calculation inputs must make the full-population modeled sign unavailable or explicitly partial. It must not present the surviving put-only subtotal as a complete negative regime, or absent model coverage as observed zero. This finding does not require modeled and vendor signs to agree: they legitimately use different assumptions. The defect is silently changed coverage, not that disagreement by itself.

Actual server `_display_surfaces` and `_display_quality` were also run for these inputs: every case stays OI/vendor-supplied-greeks, quality state usable and setupEligible true, with only GREEK_TIME_UNKNOWN. Those properties are appropriate for the vendor grid but do not disclose that the separately displayed model regime has lost coverage.

Evidence with exact inputs, full outputs, true display surfaces/quality and source hashes: `output/critical-regime-coverage-repro-20260927.json`. Guarded local child imported server only; no startup, provider/model/order calls or existing-store access. Analytics forced to memory, unique unused Mongo identity, denied attempts empty.

## Real mounted path

- Public adapter: backend/services/public_api_adapter.py around 611 retains optional IV and vendor gamma independently.
- Calculation: backend/services/solstice_regime.py usable list around 96 validates only multiplier; gamma_curve around 54-59 skips missing IV/T; modeled sign/zero branches around 134-166 omit coverage.
- Current response: backend/server.py around 1740 assigns gamma_regime_v1 from the same current raw contracts; quality around 1582 belongs to the vendor surface.
- Actual dashboard: frontend/src/components/heatseeker/SkylitDashboard.jsx around 537 mounts SolsticeStatusStrip with displayData.
- Direct consumer: SolsticeStatusStrip.jsx around 12 and 49 renders `Env: <sign> gamma proxy`; WallInspector.jsx around 393/416 also prints the sign as contextual regime.

The UI correctly labels this context, not trade direction. Nevertheless an unexplained sign reversal/false zero in the top-line gamma environment can materially alter a trader's interpretation. No directional permission is claimed by this review.

## Minimal correction

Compute explicit model eligibility/coverage separately from vendor-Greek eligibility, including finite positive strike/spot/IV/time and valid type/OI/multiplier. For the full-scope headline return UNKNOWN plus a specific missing-model-input reason when material positive-OI rows cannot be modeled; retain any partial subtotal only under explicitly partial fields. When no modeled rows exist, use unavailable values and no roots, never ZERO. Preserve legitimate measured zero/cancellation with complete coverage. Do not substitute vendor sign for model sign or guess missing IV.

Focused regression checks should cover the three cases above, true balanced complete call/put cancellation, legitimate zero-OI rows, and real mounted unknown-reason presentation. No other work is proposed by this report.

## Related basis contradiction: vendor zero must not overwrite modeled sign

The accepted methodology (`docs/solstice/METHODOLOGY.md`, regime row) explicitly defines regime sign as G_model(spot) under frozen OI/IV. `docs/solstice/SOURCES.md` likewise states roots are modeled. The module header agrees. The old `test_r4_p03_red.py` zero-gamma fixture contradicts that contract: one call with strike/spot 500, OI 100, IV .2, T .08 and vendor gamma 0 returns sign ZERO/reason ZERO_CURVE while modeled_at_spot is +351109.3476834954, vendor_at_spot is 0 and roots are empty. Independently executed locally during this review.

Retaining the vendor-zero override would preserve a numerical basis error. With complete model inputs, sign should remain POSITIVE in that example, vendor_at_spot should remain exactly zero, and the residual should remain visible. True complete modeled cancellation can yield ZERO. Missing vendor gamma does not invalidate otherwise complete model inputs; missing model IV/time cannot be replaced by vendor gamma. Update the old expectation to the documented separate-basis contract rather than treating the pre-existing test as mathematical authority.


## Final independent refutation - backend PASS, 02:08 UTC

Reviewed the revised regime.v2 implementation and ran eight new local cases rather than only repeating the author's inputs. Fresh contracts used spot 101, strikes 98/105, call/put OI 350/180, IV .24/.31, T .07/.12, and multipliers 100/50. An independently written normal-density Black-Scholes calculation (without calling the project's gamma helper) gives net modeled exposure +158479.5381686869; the corrected function matches to relative tolerance 1e-12.

- Full valid population: POSITIVE with matching arithmetic.
- Dominant call missing IV or remaining time: UNKNOWN, modeled value None and no roots.
- All rows missing model IV: UNKNOWN and no roots.
- Vendor gamma all explicit zero: modeled sign stays POSITIVE; observed comparison stays zero.
- Vendor gamma all missing: modeled sign stays POSITIVE; observed comparison and residual are None.
- Explicit zero-OI call with missing IV/time plus a valid put: complete coverage, NEGATIVE; arithmetic matches the put-only known contribution.
- Balanced complete call/put pairs at two strikes: true ZERO with no fabricated touch roots.

Actual server `_display_surfaces` and `_display_quality` were rerun for each non-balanced case, confirming vendor surfaces remain separately available while the regime result now truthfully reflects model coverage. No provider/model/order calls or existing-store access; guarded import only, in-memory analytics, no denied attempts.

Evidence: `output/critical-regime-independent-final-20260927.json` includes inputs, full result fields, actual display quality, independent numerical expectation and hashes. Source identities: solstice_regime.py `c48423f211706a02cfc28a2b979b6098a0722dacd0729ba53ad41465863568ef`; server.py `7f1b67f99785b8575e27ffd99f7cd0c096d189cb86076985672cd680a6e4585f`.

No remaining blocker was found for the scoped regime coverage/sign correction. Root is separately adding the mounted unknown-reason explanation; this backend review does not claim browser rendering was inspected or any trade direction validated.
