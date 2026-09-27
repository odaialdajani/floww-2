# Research worker abrupt-exit recovery - 2026-09-27

Status: root proof and independent final-source repeat passed. The complete AI/UI goal remains unfinished.

## What was exercised

The new reusable script runs the application's actual research startup callback and research routes against a uniquely named real local Mongo store. Cache reads and model transport are explicitly synthetic. It completes one answer, starts two waiting answers, queues a fourth, and abruptly exits only the newly created proof child with exit73. A fresh process calls actual research startup and validates all12 recorded properties.

The completed answer is unchanged. The two active requests and queued request become interrupted exactly once. Saved history, cursor continuation and owner-only access remain valid. Retrying each original request returns its saved identity without repeating work. A changed question under the same request is refused. Disabling new work retains history. A new explicit spot-price question completes without a model request. The three reserved model calls remain counted, including the two uncertain interrupted calls. Reinitialization does not duplicate events.

## Evidence and corrections

- Root output/research-worker-recovery-20260927-0140/result.json passed with expected child exits73/0, unchanged measured source files, no real model dispatch and no denied external attempts. One blank import line was then removed for Ruff. The independent output/research-worker-recovery-independent-20260927-0141/result.json passed on the final script identity; root rechecked every recorded source hash against the current files.
- First attempt failed before server import because Windows version discovery tried to spawn a command. The script now reads the actual OS version directly while retaining child-program denial.
- Second attempt correctly caught an extra synthetic-model attempt: the question lacked the explicit spot-price wording required by the existing factual-only path. The unchanged quota assertion was retained and the new-work question corrected. A deterministic fallback alone was insufficient evidence of no dispatch.
- Independent inspection found two isolation gaps before the successful run: inherited analytics storage and unrestricted local ports. The final script explicitly forces in-memory analytics, verifies the opened database list, and permits connections only to loopback port27017. The earlier run had no pre-import storage receipt. Post-run environment inspection found no inherited path and no backend .env assignment; source defaults to memory. This supports the default-path explanation but is not a retrospective no-write certificate.
- The [independent review](research-worker-recovery-review-20260927.md) records no remaining blocker within the declared worker-only scope. The [sanitized proof](research-worker-recovery-proof-20260927.json) preserves both successful results and the prior isolation limits.
- Focused Ruff and required-medium Bandit checks pass. No production source or user app was changed or restarted. Raw test stores/logs remain local; no deletion was attempted.

## Limits and remaining work

This proves research-worker recovery for this fixture schedule with local Mongo remaining available. It does not prove database crash recovery, production backup/restore, full application startup and background workers, listening-server/browser reconnection, actual upstream model availability, historical/predictive claim projection, paper or live trading. The broader research comparison, stronger-model and dollar-cost decisions, other test prerequisites and complete AI/UI plan remain open. Existing acceptance source proofs remain stale until intentionally refreshed against frozen source.
