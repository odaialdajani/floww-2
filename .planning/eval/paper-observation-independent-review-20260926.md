# Independent paper observation review - 2026-09-26 23:21 UTC

Scope: valuation.py, observation_service.py and the 13 focused valuation tests, with the existing storage/clock/accounting contracts. Pure synthetic probes only; no provider/model calls, source edits or persistent-store changes.

## Initial verdict

The pure math correctly keeps execution costs in saved basis, values separate structures independently and separates reservations from equity. Persistence freezes callback inputs, preserves exit reservations and uses version-checked writes. Three reproducible defects remain before this observation slice can be considered internally consistent. Admission remains disabled throughout.

## Reproduced findings

1. **High - a lifecycle boundary can leave a known snapshot labelled current.** current_observation checks mark/snapshot age and account binding, but not the option's earliest lifecycle deadline or exchange-session close. A snapshot valued at 1028 ten seconds before a configured option cutoff was still labelled current one second after that cutoff. A fresh observe call with the identical frame correctly returned equity=None, but PreparedObservationService.record suppressed that changed result as a same-frame/book no-op. Persist and enforce a validity deadline covering source age, session boundaries and product events. Skip only semantically unchanged outcomes; crossing into unknown must not be discarded. The same defect applies to session-close transitions while marks remain young.

2. **High - previous risk provenance is not owner/account/epoch checked.** observe validates the new binding and book epoch, but does not validate previous.binding before importing risk_anchor and mark_watermarks. Passing a different owner's previous snapshot, then omitting this account's opening-equity evidence, produced risk status observed with an imported baseline of 1000. Reject a previous snapshot whose full owner/account/venue/epoch binding differs before using any of it. The current service normally reads its previous snapshot from the same stored account, which limits immediate reachability; it does not make the pure contract or future recovery integration safe.

3. **Medium - internally contradictory option metadata is accepted.** A metadata record with cash settlement but a shares deliverable yielded known equity 1028 and zero unknown positions. Validate settlement-style/deliverable-kind consistency, cash-deliverable currency, and any supported-product time ordering explicitly. A trusted evidence callback remains necessary for truth, but contradictory supplied fields should not pass deterministic validation. No settlement implementation should be inferred from the current option_lifecycle_not_implemented status.

## Initial probe evidence


```json
{
  "lifecycle_boundary": {
    "original_equity": "1028",
    "newly_computed_equity": null,
    "saved_reader_status": "current"
  },
  "same_frame_boundary_record": {
    "returned": [
      null,
      false
    ],
    "saved": false
  },
  "foreign_anchor": {
    "accepted": true,
    "risk_status": "observed",
    "imported_baseline": "1000"
  },
  "cash_settlement_with_share_deliverable": {
    "equity": "1028",
    "unknown_positions": 0
  }
}
```

## Additional checks and limits

Risk baselines/observed peaks survive missing same-session evidence in the reviewed logic, and changed same-session settings/capital remain unknown pending reconciliation. Baselines are not silently seeded from the first mid-session request. The sampled-only label appropriately avoids claiming an unobserved intraday high.

Source marks preserve per-structure monotonic time and immutable source identity; old watermarks survive missing data. Quote receipt timestamps are deliberately excluded from economic content identity. Any validated correction workflow remains a separate future capability.

No admission callback or syntactic source ID proves actual provider truth, option lifecycle support, research/proposal acceptance or production account risk settings. Risk limits passing inside a prepared snapshot do not authorize a trade; entry_allowed remains false. Dividend/corporate-event processing and settlement remain outside this slice.

Required regression additions: lifecycle and session deadline crossing in both pure reads and saved same-frame observations; foreign previous owner/account/epoch; contradictory deliverables/currency; exact last valid instant; stale marks with unchanged frames; callback mutation; mark/fill and competing-observation races; repeated observation suppression without falsely refreshing source time; and preservation of exit reservations at capacity.


## Additional reproduced state-validation finding - 23:23 UTC

**Medium - unsupported negative holdings understate gross exposure.** The prepared execution path only creates positive long lots, but observe currently accepts negative supplied lot quantities. Two long shares plus one negative share at 110 produce net marked holdings of 110 and pass a gross-exposure limit of 200, while absolute position exposure is 330. For the current long-only scope, reject or mark unknown negative/noninteger/zero lots and invalid basis/reservation values. Do not silently enable short-position valuation or net unlike exposure. If short support is added later, calculate absolute gross exposure separately from signed marked equity.

```json
{
  "known_value": "110",
  "unknown_positions": 0,
  "risk_limits_passed": true,
  "absolute_position_exposure": "330"
}
```


## Independent fix recheck - 2026-09-26 23:27 UTC

All four reproduced findings are closed in bounded synthetic rechecks. Before/exactly at/after the option deadline now reads current/stale/stale; recomputation is unknown, and the same frame is saved through PreparedObservationService with an in-memory repository double. Prior owner/account/venue/epoch mismatches all reject. Contradictory cash/share settlement and wrong deliverable currency produce unknown equity. Negative, zero, boolean, string and fractional lot quantities reject; negative reservations reject. The derived-cash edge preserves a value beyond the raw-input digit limit exactly. Evidence: observation-fix-recheck.json. No source edits, provider/model calls or persistent-store mutations were made for this recheck. This independently verifies the reviewed deterministic contracts; it does not establish provider truth, trading admission or settlement support.
