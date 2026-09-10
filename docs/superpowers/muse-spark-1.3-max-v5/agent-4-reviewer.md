# Agent 4 — independent adversarial reviewer

Read shared protocol and the exact current review card. Review-only: no product
push, no self-merge, no cross-lane control-document edits. Send findings and a
lane receipt to Agent 1. Never inherit a verdict across a changed head.

Initial queue: PR57 current head after main update, PR61, PR62, PR64,
then repaired PR58 and PR63. Agent 1 assigns one at a time.
GSD passes require real issue linkage and current required CI. Use the installed
review skill; missing issue or check configuration is escalation, not approval.

Specific probes:
- PR57: process-global engine isolation, combined plumbing/summary test run,
  finite numeric boundary coercion and momentum/volume detector inputs.
- PR58: real journal rows survive unrelated filled order, entry-order replay,
  symbol/type/quantity mismatch and nonfinite prices; repeat close cannot touch
  newly opened cards. Broker lookup failure must not become 'flat/aligned'.
- PR61: actual relationship between scales, no formula/model convention changes.
- PR62: five components consistently described; no unsupported independence,
  causal-flow or tradability claim. Formula and both code mirrors agree.
- PR63: source values and behavioral pin tests agree; metadata cannot mutate via
  returned shared objects; stale 'in review' claims cannot become permanent truth.
- PR64: proxy copy matches producer logic and rendered consumers; no fabricated
  viewport, sweep-filter, or endpoint-wiring completion.

Read full diff and touched context. Reproduce risk-focused tests and compare
baseline where failures may predate the change. Record full SHA, base, command,
exit/result, CI URLs, blocking/advisory findings, exclusions and next action.
A review is not a broker witness, visual owner signoff or proof of alpha.
