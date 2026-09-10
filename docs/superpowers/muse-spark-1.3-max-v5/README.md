# Floww four-agent recovery harness v5

This launch package replaces v4's stale startup queue, not its historical receipts.
Read CURRENT-TRUTH.md and SHARED-PROTOCOL.md before a role prompt.
Exactly four sessions: Agent 1 coordinates; Agent 2 repairs backend;
Agent 3 completes frontend; Agent 4 independently reviews.

Requested model profile: Muse Spark 1.3 MAX. This is a requested profile, not
verified provider availability or an installed runtime setting. Record the
actual provider/model/context/output limits at boot. Never invent a model ID,
change credentials, or route proprietary source to an unapproved provider.

Launch Agent 1 first, then Agent 4. Builders start only with one current,
non-overlapping admission card each. No fifth worker or nested swarm.
Use fresh sessions after checkpointing; do not paste days of old transcripts.

Files:
- CURRENT-TRUTH.md: observed state and concrete repair gates.
- INVENTORY.json: timestamped 40-worktree, 222-ref inventory; not live state.
- SHARED-PROTOCOL.md: ownership, evidence, restart, and completion rules.
- agent-1-architect.md through agent-4-reviewer.md: copy-paste role prompts.

Live runtime root: /Users/nav/Documents/GitHub/floww-run-state/2026-09-10-v5/
This directory is NOT provisioned or admitted by this document. Agent 1 creates
it after reconciling v4 checkpoints. Never overwrite v4 receipts.
No scheduler has been configured. Prompts alone do not run agents for days.
