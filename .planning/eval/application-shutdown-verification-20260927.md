# Saved research shutdown correction - 2026-09-27

Status: PASS for graceful saved-research ordering. This is part of the user's narrowed critical research/screens/saved-work scope.

## Reproduced defect and correction

The actual registered shutdown ran Mongo closure before research cancellation. A real isolated-store reproduction left one completed answer, two running requests and one queued request after shutdown. A fresh observer read those states before any restart or repository initialization, so restart repair could not conceal the defect. The failed assertion and exact states remain in output/research-shutdown-red-20260927-0148.

The six-line production correction awaits research.close before closing Mongo in on_stop. It handles the optional absent service and retains the later idempotent research shutdown callback. Research cancellation can now save its interrupted state while storage is available. No user process was restarted, no production store modified, and no provider/model/order call made.

## Verification

- Root graceful test passes actual registered app shutdown and observes completed/interrupted/interrupted/interrupted through a new client BEFORE any restart. The exact completed answer and a single interruption event survive.
- Root abrupt-exit regression still passes expected exits73/0. Both tests exercise real local Mongo with unique proof stores and explicitly synthetic cache/model inputs.
- Independent final-source graceful repeat passes both child exits0, exact saved-state checks, subsequent startup idempotence, history/privacy/cursor behavior, duplicate request identity, and unchanged uncertain usage. Root verified every recorded final source hash against the current files.
- All16focused owned-research tests pass with the external-network guard, plus Ruff and the repository's configured medium-severity Bandit gate. An extra unfiltered scan reports the existing B608 medium/low-confidence string-built query in server; the committed check explicitly skips B608. This patch does not touch that query.
- [Independent review](application-shutdown-order-review-20260927.md) records no blocker to this targeted fix. [Sanitized receipts](application-shutdown-proof-20260927.json) retain the red/green evidence and final independent identity. Raw logs remain local.

The root0149 proof labels preceded a wording correction; the final independent0150 receipt correctly describes graceful shutdown. No assertion was weakened. Only actual research startup was invoked; all registered shutdown callbacks ran. This is not a full application startup claim.

## Remaining critical follow-up and limits

A sibling review identified detached stale-heatmap refresh tasks and a five-second tracked-task wait that does not inspect remaining tasks. Their actual behavior requires a separate bounded fix/check before claiming whole-app saved-work safety. DuckDB stop does not close its connection, so its ordering before ingestion drain is not a proven lost-row defect. Full production database crash recovery, production-scale backup/restore, live browser reconnection and real provider/model availability remain unproven. Optional roadmap expansion stays deferred by the user's decision.
