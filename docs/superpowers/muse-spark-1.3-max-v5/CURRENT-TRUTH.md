# Current truth — 2026-09-10 audit

Observed main: 2c33de0d1115eb764cdc7d787305ef3fa629a2a6.
PR59 and PR60 appear in its current first-parent history. Re-fetch at boot.

Open PRs at the initial scan:
| PR | Head | Required next step |
|---|---|---|
| 57 | 8c55302b3af56f6b08cad1239267515c897491b3 | Isolation pair reproduced: 11 passed, 20 warnings. Main update requested and produced 1a0036ef1ab6567b259c60ac5a79ef0a803f7a5b; new-head CI required. |
| 58 | 76d771784bf019cdb99c721b7d7c538e9618a79d | Block: order-to-journal attribution must be repaired before merge. |
| 61 | e65111b1abee90f9d174183e12aa2024bf8544d8 | Preserve dual VEX scales; update base, review, exact-head CI. |
| 62 | 13b82a7826968407c9d1afdf3d786b635b9673d3 | Formula correction is partial: header still says four orthogonal components; no statistical orthogonality proof. No weight changes. |
| 63 | 6869bc7c89ea9924d1abfa4196f660502aa4aafb | Registry test-path existence is not value-pinning proof; validate claims and refresh after PR61/62. |
| 64 | 40542b090e93bd1a8514bb14f8c01f33fabf07b0 | Proxy-copy diff only; clean worktree. No committed sweep-filter or viewport behavior work found in this payload. |

PR57 has no closing issue linkage. GSD review pass applied gsd:escalated;
it did NOT produce a GSD approval. Link a real contract and resolve escalation
before GSD automation resumes. Ordinary owner-authorized integration review is
a separate process and must not be represented as a completed GSD pass.

PR58 local b9d611a is an ancestor of remote 76d7717: remote contains main updates,
not a divergent replacement. Do not force-push the local branch.
reconcile_pending_close accepts symbol/order_id independently; a filled order
is handed to a symbol-wide journal closer without matching symbol, side,
quantity, or a recorded close intent. A matching symbol alone cannot distinguish
an entry order or a replayed old close against newly opened cards.
Also validate finite positive prices/quantities and distinguish failed position
reads from genuinely empty positions. A GET that initializes tables is not
strictly non-mutating. These are repair requirements, not venue-tested claims.

Preservation:
- 40 worktrees, 222 refs, 34 local branch tips not ancestors of main.
  Non-ancestry is not proof of lost payload: inspect squash/replacement patches.
- Seven dirty worktrees; two detached worktrees have merges in progress:
  /private/tmp/agent4-pr48-49-50 and /private/tmp/pr50-merge-check.
- Literal untracked path ...[truncated] exists in control worktree status.
- Dirty WAVE1-VERDICTS.md duplicates a heading and claims unverified main merges.
  Preserved untouched; do not commit as current truth.
- Other dirt: old yarn.lock, G3 kanban timestamp, platform task-card receipt.
See INVENTORY.json for exact paths/statuses. No deletion, reset, stash,
rebase abort, or cleanup was performed by this audit.

This is NOT an all-work-complete receipt. No live/paper broker witness,
production readiness, calibrated alpha, or comprehensive dead-code clearance
is established by this snapshot.
