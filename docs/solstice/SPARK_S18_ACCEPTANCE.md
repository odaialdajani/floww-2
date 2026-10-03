# SPARK S18 — Acceptance (Spark lane, 3 Oct 2026)

Lane: `solstice/spark-r17` (see MUSE_STATE §46 for exact head).
Base: `origin/main` `6eaa3343`.
No merge, no deploy, no activation, no orders, no flag changes.

## Contracts (all additive, versioned)

| Contract | Version | Lives in |
|---|---|---|
| execution admission (required) | `execution-admission.v1` | `backend/services/execution_admission.py` |
| account policy | `account-policy.v1` (global) / `account-policy.v2` (account-keyed) | lifecycle + admission |
| operator registry | `operator-registry.v1` | `backend/services/operator_registry.py` |
| account risk ledger | `account-risk-ledger.v1` | `backend/services/account_risk_ledger.py` |
| executor lease | `execution-lease.v1` | `backend/services/execution_lease.py` |
| protection/expiry | `execution-protection.v1` | `backend/services/execution_protection.py` |
| execution intent / receipt / draft | `execution-intent.v1` / `execution-receipt.v1` / `intent-draft.v1` | lifecycle (unchanged shapes) |
| coverage reads | `coverage-read.v1` | price-paths routes (Cline-owned; untouched) |
| lifecycle inventory | `lifecycle-inventory.v1` | brokerage route (unchanged shape) |
| consumer controls fixture | `execution-controls.v1` | `docs/solstice/r15/evidence/execution_controls_v1.json` |

## Fixtures (sha256 at this head)

- `execution_controls_v1.json` (56 refusal codes — strict mode, limits; sha256 in MUSE_STATE §46)
- `execution_intent_v1.json` `ae76c8d1…` — immutable intent example
- `price_path_swing5m_v1.json` `91572712…` — swing-5m price-path example
- `public_matrix_v1.json` `cfafa94f…` — 27-op capability matrix
- `lodestar_brief_v1.json` `8471b50c…` — brief handoff fields

## Test matrix (exact head, Python 3.14.6 vs ship 3.12 disclosed)

| Layer | Suite | Result |
|---|---|---|
| Service (S1/S5/S9 admission) | `test_s18_admission` (18) | **passed** |
| Service (S2/S7/S8/S9 commissioned) | `test_s18_commissioned` (15) | **passed** |
| Service (S3/S6/S10 deployment) | `test_s18_deployment` (14, spawn-isolated real processes) | **passed** |
| Service (hardening/resurrection) | `test_r17_hardening` (22) | **passed** |
| Service (legacy lifecycle) | `test_r15_execution_lifecycle` (42) + wiring (8) + r17 reads (9) + inventory (5) | **passed** |
| Mounted-route guards | existing brokerage/agent disarmed suites + `test_public_brokerage_admission` | green (in full run) |
| Real read-only adapter observations | `test_public_api_only` + `test_public_spot_validation` + `test_solstice_exec_disarmed` | **63 passed** |
| Full `tests/solstice/` (backend CWD) | unmasked | **687 passed** |
| Ship-runtime check (Python 3.12 + pinned `requirements.txt` scratch venv) | s18 deployment (14/14) + admission/commissioned/hardening/lifecycle (94) | **passed** |
| Lint/security/docs | ruff + silent-except (359 files) + bandit (touched) + openapi `--check` | clean / OK / clean / **380 paths current** |
| External commissioning | live account, entitlement, production capture, paid turns | NOT RUN — labeled, see below |

## Refusal matrix

56 codes in `execution-controls.v1` (verified against code);
S1–S3 codes: `STORE_UNAVAILABLE`, `POLICY_STORE_UNAVAILABLE`,
`POLICY_UNSET`, `POLICY_CORRUPT`, `POLICY_EXISTS`, `APPROVAL_STORE_UNAVAILABLE`,
`RECOVERY_UNKNOWN`, `RECOVERY_INCOMPLETE`, `UNKNOWN_ORDERS_PENDING`,
`OPERATOR_UNKNOWN`, `OPERATOR_UNAUTHORIZED`, `OPERATOR_EXISTS`,
`OPERATOR_STORE_UNAVAILABLE`, `RISK_FACTS_INCOMPLETE`, `RISK_LIMIT_EXCEEDED`
(+ `RISK_MAX_POSITIONS_EXCEEDED`, `RISK_NOTIONAL_EXCEEDED`,
`RISK_DAILY_LOSS_EXCEEDED`), `NATIVE_CENSUS_UNAVAILABLE`, `OVERLAP_NATIVE`,
`PROTECTION_UNVERIFIED`, `EXPIRY_TOO_NEAR`, `GUARD_UNCONFIGURED`,
`EXPIRY_INVALID`, `LEASE_HELD`, `LEASE_NOT_OWNER`, `LEASE_EXPIRED`,
`LEASE_ABSENT`, `LEASE_CORRUPT_HOLDER`, `LEASE_IO_ERROR`, `FENCED_OUT`,
`FENCED_ACTION_FAILED`, `STALE_FACTS`, `BAD_CONTRACT`.

## For Zed (integration)

- Mount patch: `backend/routes/execution_admission.py` (UNMOUNTED,
  `require_api_key` on all paths, no broker use). Suggested mount:
  `app.include_router(execution_admission_router, prefix="/api")` —
  your review required; do not weaken the `FLOWW_ENABLE_LIVE_PUBLIC` gate
  or the authenticated-cancellation path.
- `POST /admission/decision` is research-only: it forces
  `evidence_grade="client-asserted"`, so it returns EVIDENCE_UNVERIFIED and
  NEVER admits (pinned). Mounting it cannot authorize execution.
- `POST /public/order` progressive repair (Spark-owned, live): with NO
  admission store or NO account policy installed it keeps the legacy
  kill-switch-only path (disclosed); with a required v2 policy installed it
  demands a stored `approval_id` verified against the server-recomputed
  order fingerprint (403 otherwise). Full-enforcement-when-UNSET is a
  production-behavior change — needs Nav/your sign-off, not a lane edit.
- Mount context you must provide (server.py, your ownership):
  1. ONE DuckDB handle shared by the admission route, the `/public/order`
     gate (`_admission_store_conn`), and `lc.register_store` — mixing
     handles trips STORE_MISMATCH by design.
  2. Preflight priming before any executable decision:
     `lc.preflight(intent, ctx, broker)` within 60s with the same market
     ctx, else STALE_PREFLIGHT. Without priming, commissioned entry
     always refuses.
  3. Operator seeding via `POST /admission/operators` + account policy via
     `POST /admission/policies` (both durable-first); approvals expire
     1–24h server-stamped.
  4. Executor lease file location (single host, one shared volume):
     pick a path on the shared volume; all executor processes must use the
     same path. Lease dir needs write for `<path>.lock` sidecars.
     Cross-host/container-isolated deployments are OUT of scope
     (`deployment_scope()`); do not wire multi-host submit on this lease.
- Executor lease wiring into submit is a proposal, not code — review first.
- Known limitation (needs Nav decision, not lane code): operator identity
  is registry-bound but authenticated only via the shared master API key;
  per-operator credentials/sessions do not exist in this app (server auth
  architecture is Zed-owned). Treat `approved_by` as authorized-named-
  operator, not cryptographically authenticated principal.
- Broker-fact provenance now enforced on the commissioned path:
  `risk_facts` need `account_id` (= intent account), `source`, and `asof`
  within 300s (`FACTS_MAX_AGE_S`) of the decision clock — stale/foreign/
  unsourced facts refuse with zero broker calls.
- Fixture + refusal codes above are the consumer contract; additive only.

## Remaining externals (HOLD, not engineering)

NAV-ACCOUNT (exact account/rights/policy values), NAV-CAPTURE (approved
storage + admitted production restart records), NAV-NATIVE (native
workflow/position review), NAV-MODEL (owner save + authorized turn),
NAV-VISUAL (production visual review), NAV-RELEASE (merge/deploy/activate).
Zero durable admitted records → INSUFFICIENT EVIDENCE. No profitability
claim. Activation OFF.
