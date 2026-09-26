# Evaluation measurements - 2026-09-26

These opt-in helpers prepare a new evaluation. They do not rerun or alter the exposed v2 question set, spend model allowance, change production model routing, or establish AI acceptance.

## Boundaries

- Model method entry, managed turn/start attempt, completed pipe write, and returned turn acknowledgment are separate observed counts. Provider-side request totals remain unknown. A completed answer is not used as a proxy for dispatch counts.
- A reservation persisted before model entry is uncertain, not zero. The public model count is null while an entry is reserved; a separate lower bound remains available. A failed save prevents entry when possible and latches incomplete measurement. Completed pipe writes and acknowledgments saved before a later failure remain lower bounds until explicit successful trace closure.
- Durable usage evidence queries the owned turn admission and its daily reservation. Failure answers still retain their reservation. A different owner cannot inspect it. Managed subscription dollar cost is unknown unless a real recorded cost exists; no USD acceptance gate is waived.
- Read activity comes from the current production saved turn and validates its policy, limit, entries and counts. Legacy records remain unmeasured; unfinished records remain incomplete. Capability counts are not provider request counts.
- The client records request, admission, first streamed progress receipt, terminal receipt, saved-answer fetch and final verification separately. It uses a monotonic high-resolution clock with declared resolution. Buffered in-process test transports are rejected for receipt timing. Replaying a stream cannot reset earlier marks.
- Server saved-progress timestamps are pre-write wall-clock timestamps, not storage acknowledgments or browser visibility. Browser first display remains null. No first-paint claim is made.

The official [Codex app-server reference](https://learn.chatgpt.com/docs/app-server) describes turn/start returning an initial turn and later streamed events. That lifecycle does not establish provider request count or invoiced dollars.

## Verification

Fourteen focused checks pass with outbound network blocked; Ruff passes. Checks include real save-failure counterexamples for both reserved model entry and a completed pipe write, invalid saved counts, old missing metrics, owner privacy, buffered transport rejection, replay mark stability, and setup-failure cleanup.

The standalone controlled proof uses the actual research routes on one owned ephemeral loopback listener, a synthetic delayed cached spot-price callback, and an isolated in-memory research store. It admits a question, receives incremental progress, waits for completion, then reads the saved result twice and verifies equality. Final observed first progress receipt was 0.00555s; terminal receipt 0.52048s; saved answer received 0.52529s; verification finished 0.52749s. These are one controlled run, not production latency. One capability read and zero model entries occurred. External connection attempts: zero. Reported clock resolution: 0.0000001s. The exact controlled result is stored beside this report.

An outer cleanup scope restores prior environment values and connection methods and closes the owned socket on setup failures and normal completion; asynchronous cleanup independently stops the owned server and research service. No existing application window, job or listener is closed.

The independent [review](research-evaluation-metrics-review-20260926.md) reproduced the original durable-zero and cleanup gaps before repair. It also checked actual bridge writes/drains/replies, owner isolation and real streaming replay. Its final verdict must be read separately.

## Remaining acceptance work

New independently frozen questions, complete candidate runs and grading are still required. These helpers are not yet a fresh evaluation runner. No model/provider calls were made for this change; old results and shared daily usage remain unchanged. A stronger candidate choice is still pending.

The independent [alert evidence readiness review](fresh-alert-evidence-readiness-20260926.md) found no verified volume-observation time in the inspected real captures. Recalculated saved alerts can test unknown freshness honestly, but cannot become fresh directional evidence. The live in-memory alert store was not observed, so actual production absence remains unknown. Synthetic positive cases and controlled empty-store cases must be labeled separately from real acceptance evidence.
