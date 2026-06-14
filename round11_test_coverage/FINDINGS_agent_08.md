# Round 11 — Agent 08 Findings

## Services Covered

- `services/agentfield_hub.py` (293 lines)

## Test File

- `tests/services/test_agentfield_hub.py` — 41 tests, all passing

## Test Coverage Summary

| Category | Tests | Description |
|---|---|---|
| AgentFieldHub.__init__ | 4 | Default state, router prefix, router tags, cost tracker |
| get_hub() singleton | 3 | Creates on first call, returns same instance, None before first call |
| init() wiring | 9 | Agent creation, node_id, version, dev_mode, default model, custom model from env, idempotency, initialized flag, include_router |
| init_hub() coroutine | 2 | Returns hub, initializes |
| Reasoner registration | 10 | Count (13), signal/risk/briefing/data/execution paths, all callable, tags nonempty |
| classify_regime reasoner | 4 | BULLISH, BEARISH, NEUTRAL, status ok |
| execution_health reasoner | 4 | status ok, node_id, version, cost fields |
| Error boundary | 1 | gex_regime returns status=error on exception |
| Signal reasoners (async) | 3 | gex_regime calls compute_gex_profile, vpin returns value, hawkes returns state |
| Ticker normalization | 2 | gex_regime uppercases, vpin uppercases |

## Bugs Found

None. All 41 tests pass against the current source.

## Notes

- The `agentfield` SDK is not installed in the test venv. Tests mock the entire SDK
  (Agent, AgentRouter, AIConfig, CostTracker) at the module level before importing
  agentfield_hub. This tests the hub's wiring logic without requiring the actual SDK.
- The `classify_regime` reasoner is async and delegates to
  `services.morning_briefing.classify_regime`. Tests verify deterministic
  BULLISH/BEARISH/NEUTRAL classification with independently-chosen inputs.
- The `execution_health` reasoner accesses `self.cost_tracker` directly, confirming
  the hub's cost tracker is properly wired.
