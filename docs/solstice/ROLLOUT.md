# Solstice ROLLOUT (T13) — shadow rollout, SLOs, rollback (read-only first)

No execution milestone is required for grid value. Execution commissioning is
a SEPARATE explicit authorization; this receipt covers read-only rollout.

## Shadow
- Dual-run old/new computations behind `metrics` (default views unchanged).
- Compare row/cell/sidebar/inspector reconciliation + parity logs.
- Never select whichever result looks more profitable.

## SLOs (proposed, to measure — not achieved claims)
- Deterministic state ≤250ms p95 from ready snapshot (excludes provider age).
- Optional AI explanation ≤3s budget, then deterministic fallback.
- Recorder independent of tab visibility; quota headroom per manifest.

## Rollback
- Additive schema (v1→v2 migration helper in solstice_longevity).
- Feature surfaces (`metrics`, `gamma_regime_v1`, `patterns_v1`, solstice routes)
  degrade to absent; core grid/sidebar never depend on them.
- Prior implementation retained; rollback = stop reading new keys.

## Execution gate (NOT authorized here)
- Separate: idempotency/recovery/partial-fill/child-lifecycle tests,
  manual arm per session, kill switch, audit trail. Broker writes stay mocked.
