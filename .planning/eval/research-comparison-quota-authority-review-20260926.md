# Comparison quota authority clarification - 2026-09-26

Prospective reviewer clarification only. This note does not amend revision 3, grant model permission, select a candidate, change the daily cap or waive incomplete comparison results.

## Source authority

- Plan line 24, later user-directed transport update: managed ChatGPT path, durable maximum of 40 calls per UTC day, actual dollars unknown; original monetary acceptance is not automatically passed.
- Plan section 5.4, line 221: atomic reservation before **each paid request**. The original paragraph concerns bounded worst-case paid-request costs; line 24 supplies the managed-route call-cap substitution and does not create a comparison-cohort reservation requirement.
- Plan line 478: at least 30 representative frozen functional prompts, critical cases, comparative usefulness and truthful outcome/measurement reporting. It does not say the entire candidate must receive an indivisible allowance reservation before its first question.
- Revision 3 `quota_preflight.requirements[2]` adds "Atomically protect/preflight the complete candidate allowance before its first call" and distinguishes turn reservation from cohort reservation. That stronger prospective safeguard came from reviewer comparison planning; it is not an additional user-approved global requirement found in the cited plan.

Plan SHA256: `0702aa38984e636e1665af4814652d0d5ce13ffee01867731f145a6459a04253`.

Revision 3 SHA256 reviewed: `305a42af3a8d86ed8e39ad314a99c592ad2fb57ccab53faf575e507e3aa71c2b`.

## Recommended preseal clarification

The plan can be satisfied without inventing a new production batch-quota mechanism: before a candidate begins, calculate its complete bounded route/call requirement and read the actual shared available allowance, including unresolved reservations. Coordinate competing use, then retain the existing atomic per-turn durable 40-call protection at every actual model admission. If competing work, errors, admission failure or uncertain dispatch prevents completion, stop honestly and keep all resulting partial/unrun outcomes. Do not reset the ledger, raise the cap, bypass accounting, force a model on bypass/refusal paths, repeat exposed answers, or count an incomplete candidate as accepted.

Read-only full-candidate headroom checking is a point-in-time feasibility check, not a durable reservation or guarantee. Coordination reduces contention but must not be described as an atomic cohort lock. Per-turn protection remains the actual hard-cap enforcement; its concurrency/day-rollover/uncertainty behavior still requires the existing critical checks.

Because revision 3 currently contains the stronger sentence, record an explicit prospective clarification/revision before sealing rather than silently treating an ordinary preflight as proof of a cohort reservation. A proposed replacement could say: "Verify sufficient currently available shared allowance for the complete candidate's bounded admitted-call need before starting; coordinate competing use; enforce the unchanged durable cap atomically per admitted turn; retain partial/incomplete outcomes if allowance changes. This check does not reserve the cohort or guarantee completion."

This is a correction of reviewer-imposed scope, not a new waiver of the user's budget or acceptance requirements. Stronger-model choice, dollar-versus-call-limit acceptance, same frozen input comparisons and all critical truth/ownership/order-isolation rules remain unchanged. This note assesses authority; it is not a fresh audit of the production accounting implementation.
