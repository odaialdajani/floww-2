# Solstice PLAN — T00–T29 ticket map (authoritative: master-plan §27)

Base: local `main` 5db4971a (origin/main 61d17917 + PR #11). Branch:
`solstice/t00-t03-foundation`. Formula gex.v2, snapshot schema 2, evidence
solstice.evidence.v2. Status: all tickets implemented read-only; execution
disarmed; commissioning + live capture remain.

| Ticket | Deliverable | Status |
|---|---|---|
| T00 | Baseline/ref + PR reconciliation | done (STATUS.md) |
| T01 | Metric/units/sign registry + schemas | done (domain/exposure_metrics.py) |
| T02 | Parser/timestamps/instrument types/Decimal | done (public_api.py, adapter, solstice_provenance pair/volume checks) |
| T03 | Canonical exposure engine + exact clock | done (gex_core vendor engine, solstice_time.py) |
| T04 | Raw/delta/activity surfaces | done (grids + switch, walls raw-locked) |
| T05 | Wall registry/zones/unknown states | done (wall_structure.py) |
| T06 | Grid/query-state repairs | done (scope-safe expand, single-flight, stable scale) |
| T07 | Inspector/scenarios/interaction | done (WallInspector, ScenarioStrip, wall_interaction.py) |
| T08 | Enrichment | done (solstice_enrichment.py) |
| T09 | Recorder + replay | done (heatmap_history.py, REPLAY_PROTOCOL.md) |
| T10 | Read-only 0DTE scout | done (contract_scout.py + counts + /scout) |
| T11 | Labeling/evaluation | done (solstice_labels.py; live sessions pending) |
| T12 | Bracket adapter, disarmed | done (contract fixes + disarmed tests; NOT authorized for live) |
| T13 | Shadow/SLO/rollback | done (ROLLOUT.md; commissioning pending) |
| T14 | Tooltips + guide | done (METHODOLOGY.md + popover) |
| T15 | Regime/zero-gamma contract | done (solstice_regime.py) |
| T16 | Pattern library | done (solstice_patterns.py) |
| T17 | Vanna/expiry-removal views | done (solstice_vanna.py) |
| T18 | Capability registry | done (public_capability.py) |
| T19 | Session/playbook orchestration | done (solstice_session.py) |
| T20 | Strategy expression/costs | done (solstice_strategy.py) |
| T21 | Evidence tools + fallback | done (solstice_evidence.py, routes) |
| T22 | Prompt/model eval harness | done (solstice_ai_eval.py, 8-case corpus) |
| T23 | Workflow + guided replay | done (status/replay strips, inspector) |
| T24 | Ticket/session harness | done (solstice_harness.py) |
| T25 | Missed-opportunity review | done (solstice_missed.py) |
| T26 | Measured manifest/governor | done (capability_manifest.py; live measures pending) |
| T27 | Fixture registry + canaries | done (foundation + slice2 + mutation canaries) |
| T28 | Q1/Q2/Q3 + sizing ablation | done (solstice_research.py; frozen, diagnostic) |
| T29 | Longevity/migration/ownership | done (solstice_longevity.py) |

Blocked (need authority/access, not code): full CI rerun, account-level
commissioning probes (SPX types, OI cadence, quota, entitlements), live-session
capture, PR review/merge, any broker execution.
