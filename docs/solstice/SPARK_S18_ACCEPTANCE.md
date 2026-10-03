# SPARK S18 — Acceptance (Spark lane, 3 Oct 2026)

Lane: `solstice/spark-r17` at `c95ca8ddb0d87fedc00a943a217db212e971ddce`
(+ docs-only follow-ups). Base: `origin/main` `6eaa3343`.
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

- `execution_controls_v1.json` `29433fb7…` — strict mode, 28 refusal codes, limits
- `execution_intent_v1.json` `ae76c8d1…` — immutable intent example
- `price_path_swing5m_v1.json` `91572712…` — swing-5m price-path example
- `public_matrix_v1.json` `cfafa94f…` — 27-op capability matrix
- `lodestar_brief_v1.json` `8471b50c…` — brief handoff fields

## Test matrix (exact head, Python 3.14.6 vs ship 3.12 disclosed)

| Layer | Suite | Result |
|---|---|---|
| Service (S1/S2/S3 new) | `test_s18_admission` (11) + `test_s18_commissioned` (5) + `test_s18_deployment` (8) + `test_r17_hardening` (21) | **45 passed** |
| Service (legacy lifecycle) | `test_r15_execution_lifecycle` (42) + wiring (8) + r17 reads (9) + inventory (5) | **64 passed** |
| Mounted-route guards | existing brokerage/agent disarmed suites | green (in full run) |
| Real read-only adapter observations | `test_public_api_only` + `test_public_spot_validation` + `test_solstice_exec_disarmed` | **63 passed** |
| Full `tests/solstice/` | unmasked, Mongo up | **663 passed** |
| Lint/security/docs | ruff + silent-except (359 files) + bandit (touched) + openapi `--check` | clean / OK / clean / **380 paths current** |
| External commissioning | live account, entitlement, production capture, paid turns | NOT RUN — labeled, see below |

## Refusal matrix

28 submit/coverage codes in `execution-controls.v1` (verified against code);
plus S1–S3 codes: `STORE_UNAVAILABLE`, `POLICY_STORE_UNAVAILABLE`,
`POLICY_UNSET`, `POLICY_CORRUPT`, `POLICY_EXISTS`, `APPROVAL_STORE_UNAVAILABLE`,
`RECOVERY_UNKNOWN`, `RECOVERY_INCOMPLETE`, `UNKNOWN_ORDERS_PENDING`,
`OPERATOR_UNKNOWN`, `OPERATOR_UNAUTHORIZED`, `OPERATOR_EXISTS`,
`OPERATOR_STORE_UNAVAILABLE`, `RISK_FACTS_INCOMPLETE`, `RISK_LIMIT_EXCEEDED`
(+ `RISK_MAX_POSITIONS_EXCEEDED`, `RISK_NOTIONAL_EXCEEDED`,
`RISK_DAILY_LOSS_EXCEEDED`), `NATIVE_CENSUS_UNAVAILABLE`, `OVERLAP_NATIVE`,
`PROTECTION_UNVERIFIED`, `EXPIRY_TOO_NEAR`, `GUARD_UNCONFIGURED`,
`EXPIRY_INVALID`, `LEASE_HELD`, `LEASE_NOT_OWNER`, `LEASE_EXPIRED`,
`LEASE_ABSENT`, `LEASE_CORRUPT_HOLDER`, `LEASE_IO_ERROR`, `BAD_CONTRACT`.

## For Zed (integration)

- Mount patch: `backend/routes/execution_admission.py` (UNMOUNTED,
  `require_api_key` on all paths, no broker use). Suggested mount:
  `app.include_router(execution_admission_router, prefix="/api")` —
  your review required; do not weaken the `FLOWW_ENABLE_LIVE_PUBLIC` gate
  or the authenticated-cancellation path.
- Executor lease wiring into submit is a proposal, not code — review first.
- Known residual: mounted `POST /order` bypasses admission by design
  (money-path caution); the patch to gate it needs Nav/your review.
- Fixture + refusal codes above are the consumer contract; additive only.

## Remaining externals (HOLD, not engineering)

NAV-ACCOUNT (exact account/rights/policy values), NAV-CAPTURE (approved
storage + admitted production restart records), NAV-NATIVE (native
workflow/position review), NAV-MODEL (owner save + authorized turn),
NAV-VISUAL (production visual review), NAV-RELEASE (merge/deploy/activate).
Zero durable admitted records → INSUFFICIENT EVIDENCE. No profitability
claim. Activation OFF.
