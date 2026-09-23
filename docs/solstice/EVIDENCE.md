# Solstice EVIDENCE (T21/T22) — packet, tools, evaluation

Packet: solstice.evidence.v2 {snapshot_id, query_id, scope, versions, quality,
environment, facts[], patterns, scenarios, allowed_actions:[EXPLAIN,REPLAY]}.
Every numeric fact carries units/scope/sources/timestamps/formula. Derived
claims cite rule IDs + constituent facts. Account state is separate.

Tools (read-only, no broker credentials): get_snapshot, get_wall_evidence,
get_changes, get_scenario, list_eligible_candidates, get_rejection_reasons,
replay_event, get_methodology — implemented as `/api/solstice/*` + packet
validator `validate_explainer_output` + `deterministic_fallback`.

Eval corpus: ai_eval.v1 (8 cases: stale, unknown time, cancellation, scope
change, empty 0DTE, wrong-side dwell, unknown fill, injection/pressure).
Gates: no tool violations, no invented numerics, refs resolve, no promotion,
no leakage, fallback on outage. Run: `solstice_ai_eval.run_corpus()`.
Model/latency/cost logged per render; prompt version pinned in packet digest.
