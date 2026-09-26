# Final independent foundation closure - 2026-09-26 22:41 UTC

The earlier low-severity precision-mode mismatch is CLOSED at the final hashes below. The historical finding and initial evidence remain in this file for traceability. No new blocking foundation finding was reproduced. This remains preparation-only, not order admission or full paper lifecycle approval.

Independently reran all14current arithmetic tests:14passed. Re-executed the original boundary reproduction unchanged: both price and cash slippage methods now succeed with exactly -1124.106789012345678901234567800 cash change. Additional direct assertions verify the two helpers refuse a1e-200fee combined with1e72notional instead of silently discarding it, and an ambient decimal precision of6does not round the supported original boundary. Logs and closure JSON are in output/paper-foundation-review-20260926/final-*.

Source review: derived fill price now stays inside the exact calculation instead of being treated as a new raw input. Derived fees have separate finite/size bounds and nonnegative validation. exact_context uses256digit precision and traps Inexact, translating decimal failures into ValueError. This avoids both the prior false refusal and silent loss beyond supported exact precision. Raw quantity/reference/factor/increment validation remains separate.

Compared the final manifest to every live listed file before and after the targeted execution: all14hashes matched throughout. Within the original foundation scope, only accounting.py and its arithmetic tests changed since this review's last receipt-helper closure; repository.py, recovery.py, initialization, verification script and accounting ADR retain their reviewed hashes. No repeat storage run was needed for unchanged storage. The previous independently run30real-store checks and six follow-up ownership/concurrency/receipt checks remain tied to their recorded hashes.

Inspected the separate execution review's final closure and exact hashes: execution.py, service.py, accounting.py and both focused test files match the final owner manifest. That review independently covers bounded close capacity, quote mutation, archived/replenished obligations, receipt reuse, inexact-fee refusal and backward-clock fencing. I did not duplicate that complete review or claim its controller checks as my own. The owner's final17real-controller and28combined-unit results are separately documented in paper-preparation-verification-20260926.md; complete Mongo crash/power-loss, production confirmation/risk composition, lifecycle and activation remain unproven/unmounted as documented.

## Final foundation hashes

- backend/services/agent/paper/__init__.py: e8ec4ef5029464791d418499e0e9689f3b53f75596ecafc98a8bc7d274b7ad50
- backend/services/agent/paper/accounting.py: 0ea3b327b1b9e6f7f8e6304de45f353a281aa7f3afdc932f9c8a609f0436a8c7
- backend/services/agent/paper/repository.py: 3cbea0a497e6b024b04ffa8be03158c2952a55f9c0e8054e03bdd8007520eb09
- backend/services/agent/paper/recovery.py: dfe307c03021e7465e92208afb53cb3f73d5bd0e18a0bbf552bfd49c2064489a
- backend/scripts/verify_paper_storage.py: 38d48e626d3bbd02c0d4b14631abd89cab2b8eee584ab1c625085aa6107570b2
- tests/test_agent_paper_arithmetic.py: 80a8def25e2d8bbce5493c4ee585a610dc1bf7f02d02568a7f0c6e7d26c8c33f
- docs/adr/0010-paper-accounting-proposed.md: 67c6011dd5d9eb8081ec4e9efb0f8095dfacfb59e4d4442c2de1e6bb64ffe40d

---

# Preserved initial review and finding

# Independent paper foundation review - 2026-09-26 22:21 UTC

Bounded read-only production-source review under hard-tasks. Scope: accounting, storage, checkpoint recovery, verification script, arithmetic tests and ADR-0010. execution.py was deliberately not opened. Source owner declared this foundation stable. Seven reviewed files were byte-identical across the supplied checks. Later owner edits added a public receipt() helper and reformatted verification imports; this narrow delta was inspected and independently probed, with original hashes preserved below.

## Verdict

No blocking storage correctness finding reproduced in this bounded foundation. One low-severity accepted-precision inconsistency is confirmed below. This is NOT paper lifecycle, order admission, executable quote, risk limit, live activation or complete crash-durability acceptance.

## Low: accepted exact inputs have different supported domains by slippage method

simulated_fill(quantity=1,factor=100,reference='1.234567890123456789012345678',fee='0.65',increment='10',enabled=True) accepts each input under exact(). Price mode adds the increment to make29significant digits, then fill_cash_change revalidates this internally derived price against the external28digit limit and raises ValueError. Cash mode accepts the same inputs and returns cash_change=-1124.106789012345678901234567800. This is a safe refusal, not double charging or corruption, and occurs at a precision edge outside ordinary quoted price increments. It nevertheless contradicts equal admissibility of the two equivalent slippage modes across the declared accepted-input domain.

Reproduction: output/paper-foundation-review-20260926/precision_probe.py. Suggested narrow repair: validate external operands once, then calculate internally derived values under the declared exact context without reapplying an external-input precision limit; alternatively explicitly document and consistently enforce a common representable-result restriction. Do not silently round or alter fee/slippage policy.

## Executed evidence

- Independently ran all12 supplied arithmetic tests: pass. Cases verify long/short/partial close, fractional shares, explicit factor, missing-mark refusal, slippage off/price/cash, invalid combined method refusal, fees once, and wide accepted scales.
- Independently reran the actual storage verification script on new isolated database floww_paper_verify_c5526e82db65479f86088d034215f4c9: all30checks pass. Saved report is output/paper-foundation-review-20260926/independent-storage.json. It uses real Mongo27017 with journal acknowledgement and a separate recovery process. The parent's earlier30check report was inspected as prior evidence but is not substituted for this run.
- Five new independently authored checks first passed against owned database floww_paper_verify_3a75c181499c4aae94d52c54287b1b10, then were repeated with a sixth receipt-helper check against floww_paper_verify_eb321ad25dd04797b16c6b9972a9f989:20different commands at the same expected version produce exactly1winner/19conflicts; cash and holdings belong to that same winner; identical account label under another owner remains unchanged;10simultaneous projections retain exactly1immutable history event; replaying the same operation and command with replacement state/body returns the original receipt and cannot change balances; public receipt() returns the saved event and refuses cross-owner access through its epoch guard.
- Probe and result: output/paper-foundation-review-20260926/probes.py and independent-probes.json. Child processes launched with Node spawnSync windowsHide:true; the storage script's recovery child uses CREATE_NO_WINDOW. No servers, providers, models, orders or existing paper accounts were used. Mongo27018 untouched. Owned synthetic databases remain for inspection.

## What the evidence supports

Single account update atomically changes version/state and adds its pending event. Thus cash, holdings and pending evidence move together as supplied by the caller. Unique scoped operations plus epoch/version checks and saved receipts prevent reapplying the same mutation before/after projection, after receipt pruning, and across restore epochs. Scoped account identity separates owner/account/internal venue; alternate venues are refused. Projection writes immutable history before removing a pending seed, can repeat after a lost response, and refuses conflicting history without discarding the seed. Account/event capacity checks refuse growth and preserve reserved recovery capacity.

Checkpoint exports bind a captured account version to continuous projected+pending history, tolerate concurrent projection, reject missing/conflicting history, and write manifest last. Restore checks owner, hashes, sizes and event sequence; preserves state into a new identity/epoch; leaves source intact; refuses same/existing target; remains recovery_pending so commit is blocked. Near-limit and escaped-JSON restoration paths ran successfully.

## Exact limits on claims

The repository accepts caller-supplied next_state and event bodies; it does not prove financial conservation, risk eligibility or that every fill uses the accounting helper. The operation digest binds command, while duplicate replacement next_state/body are intentionally ignored in favor of the original receipt. Caller services must validate trusted inputs; no service admission review was performed.

Journal acknowledgement plus independent-process read demonstrates durable acknowledgement and process-boundary persistence under a running Mongo service. The verification simulates projection crash windows but does NOT kill/restart Mongo, power-cycle storage, or prove disk/host disaster recovery. Export files are hash-checked but not fsync-certified or externally authenticated. Checkpoint validation preserves the saved state and verifies history shape; it does not recompute money from event economics. Frozen restore is therefore the correct current limit, not proof that restored trading may reopen.

Slippage/fee examples use signed quantity and declared premium factor. Price mode embeds adverse increment once and charges no extra slippage cash; cash mode keeps reference fill and charges adverse cash once; off preserves choice but adds no slippage. Explicit fee applies once per call. Exact functions alone do not prove a future execution caller invokes them once per actual fill.

## Reviewed SHA256

- backend/services/agent/paper/__init__.py: e8ec4ef5029464791d418499e0e9689f3b53f75596ecafc98a8bc7d274b7ad50
- backend/services/agent/paper/accounting.py: 8471dee33a0c9b3d56ba363a44cf228e08c7815ec409e37dad8c8be8c963d49e
- backend/services/agent/paper/repository.py: 3cbea0a497e6b024b04ffa8be03158c2952a55f9c0e8054e03bdd8007520eb09
- backend/services/agent/paper/recovery.py: dfe307c03021e7465e92208afb53cb3f73d5bd0e18a0bbf552bfd49c2064489a
- backend/scripts/verify_paper_storage.py: 38d48e626d3bbd02c0d4b14631abd89cab2b8eee584ab1c625085aa6107570b2
- tests/test_agent_paper_arithmetic.py: 8ee7c4ff8d7e851dd7cc7cd50a718bed0c4d5d21fc7d16563729c9b555672029
- docs/adr/0010-paper-accounting-proposed.md: 67c6011dd5d9eb8081ec4e9efb0f8095dfacfb59e4d4442c2de1e6bb64ffe40d

## Original tested hashes before owner delta

- backend/services/agent/paper/repository.py: 0fc12d1192bc681c34c995b2d69d3bd6b9c30d28ca72ceeba70c9a624db6534d
- backend/scripts/verify_paper_storage.py: b2cc349b0843aa018b5adf259b5dde6f9e9bac2e9dbf3bf3d1b5def7fa3ebb04

Owner changes after the first run: backend/services/agent/paper/repository.py, backend/scripts/verify_paper_storage.py. No further production edits by reviewer. Current hashes above were checked after the targeted helper probe.
