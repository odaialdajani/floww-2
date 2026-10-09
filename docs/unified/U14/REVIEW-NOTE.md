# U14 — Review: successor controller recovery and fencing

Owner: OpenCode (review of parent implementation). Reviewer: Cline.
Files reviewed (read-only, hashes below):
`tools/controller.py` (691 lines), `tools/host_adapters.py`,
`tools/fake_host.py`, `tools/test_controller.py`. No edit made —
parent owns all controller/config/runtime code.

## Behavioral receipt

`python3 -m pytest test_controller.py -q` in the tools dir:
**51 passed** (47.82s, isolated temp repos/registries/fake hosts only —
no product mutation, no host launch, no network).

## Findings: both audit issues are fenced

1. Duplicate ownership across model changes / takeovers:
   - `bind` requires `idle_proven` + exact session match; terminal states
     need explicit `recovery_ack`.
   - `acquire_run` takes `session:` + `workspace:` resource keys and refuses
     when claimed "including by another packet or repository".
   - `_assert_no_active` refuses takeover while child/pgid alive or owner
     alive; a dead owner still needs native idle reconciliation — no
     lease-expiry takeover.
   - `model_handoff` preserves role/task/source/checkpoint, drains
     IN_PROGRESS claims (generation bump, claim_run NULL), and refuses on
     session/permission change without proven idle.
   - Supervisor loop breaks on user takeover, permission/model change, and
     parks native-busy ends as WAITING_NATIVE with fences retained.

2. Evidence checked against the wrong worktree:
   - `claim`/`checkpoint` require the recorded `source_worktree` and the
     run cwd to equal the config repository; unfinished tasks carry their
     worktree and must continue there (explicit handoff otherwise).
   - `review` re-verifies the sealed snapshot against the RECORDED WRITER
     worktree (not the reviewer's), binds exact snapshot SHA, and fails
     closed if sealed task bytes or their file population changed after sealing.
     An unrelated successor commit can pass this task-scoped byte check;
     it is not a full-writer-HEAD fence. Final acceptance separately binds
     one frozen combined HEAD.
   - `seal_snapshot` fingerprints before/after and refuses on mid-seal
     change; checkpoint baseline must equal current full HEAD.
   - Note: all three unified lanes share one git common dir
     (`floww-2/.git`), so `repo_identity` alone does NOT separate lanes —
     separation comes from per-role configs (`repository` = the role
     worktree) plus the path-level checks above. One config per role
     worktree is therefore load-bearing; `load_config` enforces
     host-cwd == repository. Do not merge role configs.

3. Quiet/wait and anti-filler behavior:
   - No READY work → WAITING_REVIEW sleeps without model/test calls.
   - `no_progress_limit` parks repeated unchanged tasks as BLOCKED.
   - Writer cannot accept own work; reviews need an active reviewer child
     turn + prompt token (`verify_review_turn`); only task-specific
     dependency wakes on ACCEPT.
   - Shipped `controller-config.json` has `launch_enabled: false` and no
     registry exists — no controller is running; nothing here launches one.
     Direct-session work (like this dossier) proceeds outside the
     controller and is disclosed as such.

## Residual (for coordinator, not edits)

- This review read the code and ran its suite; it did not execute a live
  multi-host contention rehearsal. A fake-host contention drill through
  `start --execute` remains unproven by design (launch disabled).
- Cline's stale zero-message placeholder reconciliation (H-CLINE-BINDING)
  is a runtime binding step, unaffected by this code review.

## Verdict (OpenCode → Cline)

REVIEW_ACCEPT_SUBJECT_TO_PEER: fencing meets the U14 acceptance on code +
suite evidence. Cline: confirm on the sealed snapshot; live-drill proof, if
ever required, needs explicit human authorization to enable launch.

## File hashes (reviewed bytes)

- controller.py: `2d0634aad2f21df1999b554999cac3c907e788f4c6aa34c724c2d1cd22d2b6fb`
- host_adapters.py: `729d411c8457842a2b074610c8574e510a13fd4ab85459af405fcf4114e8afe7`
- fake_host.py: `9849e5ab058dd2e65ceee61dc16633e2284690e8bcb4b487ea85d8d3d5a3de64`
- test_controller.py: `8d182d39a49caf048d9a3ca03ea76f5c8839f004459b9e37d25cbfe9c6896fa5`
