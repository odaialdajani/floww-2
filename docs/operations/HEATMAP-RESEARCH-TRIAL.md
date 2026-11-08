# Registered retained-heatmap research trial

This is a single manually admitted research task, `retained-heatmap-v1`.
It does not install a dispatcher, schedule, provider reader or trading executor.
The native investigator and auditor use the existing no-tool Hermes profiles,
one streaming POST per role, 1,024 output tokens, 25-second read timeout,
30-second native budget, 35-second helper alarm and 38-second parent deadline.

The source is `ops/fixtures/heatmap-retained-20261107.json`, SHA-256
`3e22636a60f77bd5987fb83921778a7463b8cbb418a6e3e442854bc612f3e3a5`.
This fixed 26,037-byte packet was extracted from the actual retained backend
`3948b9c71` SELECT responses. It binds SPY snapshot
`snap_496ef8db776ca7c6`, scope `SPY:4:day:None:False:True:80`, provider
`public_api`, formula `gex.v2`, November 9–12 expiries, 80 strikes and 640
recorded contracts. The packet retains GET clocks and response SHA-256 values.
It is a reviewed frozen first-trial source, not authenticated new market data.
Changing it requires a source review and compiled-pin change; no caller can
provide a replacement source path, facts, URL or digest.

The Saturday recording contains Friday bid/ask source events. Greek event time
and all OI effective dates are unknown. QQQ has no retained heatmap rows for the
two checked UTC days, November 6–7. VEX is a partial local vanna model with 107
missing inputs. Window activity is unavailable with `IDENTITY_UNDECLARED`.
Stored `setupEligible:true` and `stale:false` cannot remove these limitations.

The investigator may select only `cluster_retest` (SPY 734–741,
`w_6961d4e00f17`) or `weighting_divergence` (SPY 743–746,
`w_5ac6d95aa9dd`). Each selected object requires its exact raw OI,
delta-weighted OI and cumulative turnover facts, units and JSON pointers.
Scope, snapshot, mode, provider, formula and expiry population must match
exactly. Missing or duplicate claims, extra fields, altered citations or values,
unknown question types and omitted fresh-evidence requirements are refused.

The named types fix the conditional research questions. A rationale is limited
to 240 ASCII characters, contains no numbers and passes an action-word guard.
This lexical check does not prove semantic support. A separate auditor receives
the original pinned source projection plus the exact completed, validated
investigator response and its digest. It must assess every selected question,
including its rationale, with a closed reason code. Missing/invalid investigator
output prevents the audit POST. Missing audit output never falls back to the
investigator response, an example or a deterministic default.

Both responses remain `review_only`, `executable:false`, with mandatory root
review. An accepting auditor can only accept conditional research. There is no
direction, entry, stop, sizing, confidence, profitability or order authority.
SPY ETF option facts never supply a Liquid perpetual instrument mapping.

The task uses the unchanged `research_worker.ADMISSION_STATE` lease and
admission ledger: four prepaid pairs per UTC day, persistent dedupe and a global
failure circuit shared with the saved-observation task. A new task/state alias
cannot reset prior attempts or spend. Frozen-source dedupe is independent of
rule/code edits and local receipt retention. A failed or interrupted attempt is
terminal; no automatic retry or circuit resume occurs here.

The CLI registers a closed `--task` choice. Its separate proposed state is
`~/Library/Application Support/FLOWW/operations/heatmap-research`; the admission
state remains the existing fixed global directory. Explicit source overrides
through `--saved-input` are refused for this task. The prior saved-observation
task and its default state remain available unchanged.

After independent source acceptance and a fresh owner GO, the root may use the
registered `run-once` route and arrange the visible Hermes Desktop handoff.
Preparing code, a fixture, a mock SDK response or a board card is not native
completion. Root must observe both actual native results and perform semantic
review before using a report. No task-specific circuit reset is provided.

At the frozen implementation base `0cde876f`, independent review identified two
inherited blockers: ordinary offline replay imports real `hermes_bootstrap`,
and a later terminal `stop` can overwrite an earlier streaming `length`.
This task does not change those paths. Do not run a native offline/live trial
until the separately reviewed runtime correction is integrated. The installed
SDK wire proof uses `httpx.MockTransport`, with bootstrap/private-file access,
production writes, network and subprocess attempts denied; it is not a native
conversation or actual provider result.
