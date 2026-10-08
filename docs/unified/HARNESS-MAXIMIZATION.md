# Maximized long-run harness — role-based, model-agnostic

This is the setup for multi-hour autonomous runs. It names ROLES, never
models: the platform selects and switches models; task identity never
includes a model name, so a usage-forced switch cannot duplicate or orphan
work. (Past incident: a third model wove in unnamed work that collided —
roles plus claimed paths now make that structurally impossible.)

## Roles (fixed words; use exactly these)

- **Builder (frontend/integration)**: owns product-surface evidence, the
  single full-suite gate, and review of backend slices. Lane: its own
  checkout. Never writes backend routes/services, never restarts services.
- **Prover (backend/recovery)**: owns backend evidence, provenance,
  storage/restart integrity, and review of frontend slices. Lane: its own
  checkout. Never writes product surfaces.
- **Coordinator**: owns shared mounts, entry imports, theme import,
  controller/config, manifests, scope promotion, and records. The only
  role that touches shared seams, and only with a logged handoff.
- **Owner (human)**: merges, deploys, restarts, captures, commissions,
  authorizes publication. No automation holds these.

## One writer per path, always

- Work happens only in the role's bound checkout (verified absolute path,
  not "current directory").
- A task is claimed in exactly one place (controller registry when live;
  otherwise the single shared queue file + a `CLAIMED-BY-<role>` marker
  inside the task's evidence dir). Never claim by memory of yesterday's chat.
- Peer lanes are read-only. Uncommitted peer work is never consumed,
  copied, or "finished for them" — review it, record the verdict, hand back.
- One write task per role at a time. A second READY task waits; it does not
  parallelize inside one role.

## The queue drives hours, not the clock

- Each turn: oldest READY task owned by the role → reproduce → repair →
  focused + neighbor checks → sealed evidence → next READY task.
- A normal final answer is a CHECKPOINT (task/head/files/hash/red-green/
  exact next command), never a stopping point while owned READY work exists.
- Stop only on: human cancellation/takeover, host/permission failure,
  provider limit, three turns with zero recorded evidence progress, or all
  owned tasks ACCEPTED-or-HELD with named holders. "Nothing feels new",
  elapsed time, and test-count milestones are never stop reasons.
- BLOCKED narrows to the task, never the queue: record the exact missing
  fact + holder, continue the next independent READY task.
- No filler to look busy: no unchanged full-suite reruns, no timed commits,
  no status essays. Quiet is correct when nothing is actionable.

## Evidence that survives handoffs (and model switches)

- Every task directory holds: baseline SHA, file SHAs, exact commands with
  exit codes, before/after (red then green) logs or a stated reason, and
  the exact next action. Reports cite these; memory cites nothing.
- Reviewers read sealed copies (snapshot hash + file manifest), never the
  writer's live directory. Verdicts bind baseline + snapshot, name the
  reviewer role, and list what was re-run — never "looks good".
- Queue labels are not acceptance. Counts are not acceptance. Screens are
  not acceptance. Only: exact evidence + independent verdict + frozen
  candidate + required gates.

## Model/usage switch procedure (the anti-duplication core)

1. Finish or checkpoint the current operation first (never mid-write).
2. Record: task, claim, baseline/head, owned diff, snapshot/evidence,
   outstanding jobs, exact next command.
3. New turn re-reads the claim record and CONTINUES it — same role, same
   task, same permissions. Never restate the task from memory, never
   re-derive what "seems" next, never rename models/variants in directions.
4. Reconcile postconditions before retrying anything interrupted; an
   interrupted operation is not assumed failed.
5. If two writers ever appear on one path, both stop writing immediately;
   the record decides the single owner; the other reviews.

## Forbidden (all roles, all runs)

Real orders/cancels, account connections, paid feeds/model turns, spending,
production capture/activation, service restarts, main merges, deployments,
global-settings expansion, protected-source edits, and publishing (commits,
pushes, PRs, comments) without explicit human instruction. Missing real
values stay UNSET and refuse loudly; fixtures never become receipts.

## What "done" means

All owned obligations ACCEPTED with bound evidence and peer verdicts, or
HELD with a named holder and exact missing input — plus a frozen candidate
through every required gate. Then park quietly and say so once.
