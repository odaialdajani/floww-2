# SPARK R15 — Lodestar brief handoff spec (Spark → Zed)

Zed owns Lodestar model config and all frontend. This spec gives Zed the exact
backend-owned fields for an editable, dated brief — nothing more. Static
observations copied into a brief do NOT become a continuous feed, and a local
trace reference does NOT prove Public ingested anything. Secrets and
chain-of-thought stay out of logs and briefs.

## Brief fields (backend supplies; Zed renders + dates)

| Field | Source | Freshness / refusal |
|---|---|---|
| `selected_wall` (wall id, strikes, metric S¹/S² + units) | owning stored snapshot via replay/contract routes | owning-snapshot-only; before-available-at → refusal |
| `evidence_timestamps` (`event_time` vendor, `fetched_at`, `available_at`) | stored record clocks | vendor vs fetch kept separate; stale keeps actual ages |
| `exact_contract` (OSI, expiry, type, `strike_exact`, multiplier + provenance) | `contract_facts` admission | incomplete/conflict/missing provenance → typed refusal; unknown≠zero |
| `quote_pair` (bid×ask + `bid_ts`/`ask_ts`, spread_ticks) | `candidate_quotes_v1` at decision time | stale/missing/crossed → `STALE_QUOTE`/`MISSING_QUOTE_SIDES`; never mid-fabricated |
| `spread_limit_ticks` (max spread in ticks for the brief) | operator review policy | breached → brief marked unexecutable; counted, not hidden |
| `cash_margin_choice` (`CASH`\|`MARGIN`) | operator, explicit | absent → `UNRESOLVED_MARGIN`; no vendor default inherited |
| `budget` (preflight total/fees/buying-power, `asof`) | `preflight_*` at intent hash + ctx fingerprint, 60s TTL | expired on any change; estimates are NOT fills |
| `affordability` (budget total vs buying power) | `INSUFFICIENT_BUDGET` gate | unaffordable → no place, notify; absent power skips, never invented |
| `session_loss_cap` (per-session loss limit or explicit none) | operator commissioning policy | unset → labeled unset; enforced only against measured fills, never estimates |
| `consecutive_bid_check` (threshold, interval, count, freshness, reset) | reviewed stop policy | any field missing → policy incomplete, no default thresholds |
| `confirmation` (quoted/observed + policy version) | session policy + risk policy | missing policy → `MISSING_POLICY` |
| `entry_pause` (11:30–14:00 ET state at brief time) | `is_entry_pause` | paused → `ENTRY_PAUSE` for new entries; cancels/exits unaffected |
| `protection` (native type + eligible quantity, or explicit none) | broker-native support × account eligibility | unverified → `protected:false`; stop ≠ guaranteed ceiling |
| `expiry_policy` (allowlisted expiry, cutoff, assignment exposure note) | `supported_expiries` + commissioning policy | unlisted → `UNSUPPORTED_EXPIRY` |
| `execution_owner` (`FLOWW_BACKEND`\|`PUBLIC_NATIVE_AGENT`) + `correlation_ref` | ownership registry | open native overlap → `OVERLAP_NATIVE` blocks backend entry |
| `approval` (id bound to intent hash + scope + validity) | server approval desk | expired/scope-mismatch/tampered → `APPROVAL_INVALID` |
| `outcome_linkage` (decision → price path → label + reason codes) | `outcome_labels_v1` + `price_paths_v1` | missing/dual-barrier → censored/unknown, never wins |

## Freshness contract for the brief

- Every numeric field carries its `asof`; anything older than its stated
  freshness is labeled stale with actual age, never refreshed silently.
- Replay-derived briefs carry `replay_id` and REQUIRE `replay_authorization`;
  otherwise `UNAUTHORIZED_REPLAY`.
- A worked example (fixture, not market data):
  `docs/solstice/r15/evidence/lodestar_brief_v1.json`.

## Explicit non-claims

- No native-Agent create/invoke API was verified; no external live-GEX receiver
  exists in this lane — do not present the brief as ingested by Public.
- Lodestar model selection/configuration belongs to Zed; Public's internal model
  is not established as user-selectable GPT-6.1-Sol.
