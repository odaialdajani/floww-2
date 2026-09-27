# Paper risk preparation verification

Verified 2026-09-27 UTC. This is an unmounted pure preparation slice, not completed account admission, a production risk controller, or product lifecycle support. No application restart, provider/model request, paper activation or live order occurred.

## Source and scope

Exact four-file cohort: paper-risk-source-manifest-20260927.json. It adds explicit full owner-accepted policy records, immutable independently checked trade-risk records, deterministic stage/later-fill candidates and an opt-in isolated-store verification command. It does not change the existing prepared controller or mount routes.

Policy values and metric semantics must all be supplied; there are no account/risk defaults. Supported test-only semantics are long-only cash, marked holdings plus remaining committed debits and separately retained linear exit/lifecycle buffers, sampled peaks, strict loss/drawdown boundaries and inclusive exposure boundaries. This supported formula is an explicit choice to be approved; it is not an automatic owner recommendation. Existing chosen slippage modes charge adverse cost once.

Full contract-source content and an explicit lifecycle subset are bound to both saved evidence hashes for every held or working entry, including a pending-only book. A changed verification/source record requires reverified risk evidence. Verified lifecycle evidence remains a trusted composition input; hashing it is not proof that option lifecycle processing exists.

## Executed evidence

- 66 root paper checks pass: 19 new policy/risk cases and 47 existing arithmetic, execution and valuation cases. Full verbose output is preserved locally at output/paper-risk-all-tests-20260927.json. Exact invocation: backend/.venv/Scripts/python.exe -m unittest discover -s tests -p test_agent_paper_*.py -v.
- Ruff passes on all four new source/test files.
- Five actual isolated-store checks pass. An explicitly fresh synthetic account saves the full policy; twelve duplicate stage writes produce one order/receipt; two competing stage/fill candidates with distinct operation IDs yield one exact whole candidate and one conflict; stale expected version returns no candidate and writes nothing; a fresh child process reopens exact policy, trade evidence, sampled observations and decision, then verifies every projected event body (including decisions), an emptied pending queue and unchanged account state.
- Independent final replay in a second fresh isolated store also passes all five checks, process exit 0 and no stderr. The final review records both corrected proof gaps and their rerun.
- Sanitized actual-store proof: paper-risk-store-proof-20260927.json. Reproduce using backend Python from backend: -m scripts.verify_paper_risk --run --report <new local report>. Verification imports synthetic fixtures from tests and restricts itself to new prefixed local test databases. No production account is accessed. Isolated test records remain for inspection.
- Independent review: paper-risk-preparation-review-20260927.md. An initially reproducible defect accepted changed option terms under unchanged risk evidence. It was fixed and independently rechecked across settlement/deliverable, right, strike, underlying, lifecycle deadline and pending-only cases.
- Independent cash examples preserve entry reservations outside equity. Partial entry cash 794.35 and marked equity 984.35 match literal hand calculations in both chosen slippage methods. A bounded risk-reducing close after a 311.30 loss passes with cash633.05 and retained remaining cost buffer7; an excessive closing fee refuses without a candidate.

## Mandatory unfinished composition

1. Persist trusted actual pre-action equity and sampled peaks even when an order is refused, or persist explicit uncertainty that blocks later increases until reconciled. A reproduced refused-entry observation at1188.70 followed by1028.70 is a160 drawdown; the pure result alone does not save that first high. Never save hypothetical post-refused-fill equity. Coordinate this with account versions and prepaid exit capacity; a mandatory extra ordinary observation write must not block a reducing exit at capacity. This remains unimplemented, not a passing durable-risk claim.
2. Bind trusted owner acceptance, current session/opening equity, full-account prices and verified product/proposal/lifecycle/cost sources. Digests and True-returning synthetic callbacks do not authenticate an owner or establish source truth.
3. Compose the exact candidate, risk decision, reservations and conditional account update in the real action service. The isolated direct repository proof establishes atomic saved candidates only. It does not establish request-level duplicate handling, policy/fill race orchestration, slow-callback/write-time freshness or durable refusal behavior. Freshness is explicitly decision-time with recheck before fill.
4. Specify/verify actual option exercise, expiry, settlement and delivered holdings; specify/verify share corporate actions/dividends. Unknown lifecycle never drops holdings. Product admission remains disabled.
5. Obtain actual owner account/risk choices, build trusted proposals and exact human confirmation, and satisfy earlier research release requirements before enabling paper use. Live use remains separately unapproved. Mobile remains paused.

The 2026-09-27 read-only design investigation remains historical evidence of the prerequisites. This new pure preparation implements part of that design but does not supersede its admission gates or claim the full goal complete.
