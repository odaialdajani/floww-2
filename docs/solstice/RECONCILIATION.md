# Solstice RECONCILIATION — merged PRs vs Revision-3 master plan (23 Sep 2026)

## Revision-4 audit reconciliation (P01, branch solstice/r4-p01-p02)

Independent R4 audit of `5f325e10` reproduced 19 counterexamples (A01–A19).
Status per finding at current head — verified, not assumed:

| ID | Verdict | Evidence / target |
|---|---|---|
| R4-01 snapshot IDs/content | **Repaired P02** | content-hash IDs + deepcopy immutability; red tests fail-before/pass-after |
| R4-02 quality unknown-first/clocks | **Repaired P02** | `normalize_quality()`; unknown→unavailable/ineligible; clocks separate |
| R4-03 evidence scope drift | **Repaired P02** | evidence-by-recorded-ID + full-scope rebuild, identical query keys |
| R4-04 validator/corpus strictness | **Repaired P02** | typed number binding, required schema/refs, failure≠pass, real injections |
| R4-05 interaction side semantics | Confirmed by inspection | Target: P04 explicit side vocabulary + dwell clocks |
| R4-06 interaction persistence/selection | Confirmed by inspection | Target: P04 persisted states + scoped-ID joins (P05 selection) |
| R4-07 same-side nearest/gaps/IDs | Confirmed by inspection | Target: P03 below/inside/above, zero-mass, gap clustering |
| R4-08 scout freshness/0DTE/NaN | Confirmed by inspection | Target: P06 eligibility gates |
| R4-09 session calendar/0DTE clock | Confirmed by inspection | Target: P06 calendars + horizons |
| R4-10 OI baseline dating | Confirmed by inspection | Target: P03 dated-pair matching |
| R4-11 outcome chronology | Confirmed by inspection | Target: P10 encounter-first labels |
| R4-12 study scoring/quiz | Confirmed by inspection | Target: P09 actual-grid tasks (Q1 on hold per packet) |
| R4-13 recorder atomicity/coverage | Confirmed by inspection | Target: P07 atomic commit + recovery tests |
| R4-14 window activity/missing metric | Confirmed by inspection | Target: P03 matched-epoch windows, no raw fallback |
| R4-15 local ratios/replay scope | Confirmed by inspection | Target: P05 wall-local values, real replay |
| R4-16 patterns/regime/timer bounds | Confirmed by inspection | Target: P12 research quarantine |
| R4-17 ablation config/costs | Confirmed by inspection | Target: P10 single frozen config + costed outcomes |
| R4-18 capability/event producers | Confirmed by inspection | Target: P07/P11 production writers |

Scope key: ✅ implemented + verified · 🔶 implemented, validation needs
sessions/time/user · ⬜ incomplete (no code) · ⛔ externally blocked.
Evidence = tests/docs/live runs in this repo. "56 tests pass" never stands in
for whole-plan completion — this table does that job instead.

## PR ledger
| PR | Content | State |
|---|---|---|
| #13 | T00–T29 read-only desk (foundation + all tickets) | MERGED |
| #14 | Sweep-5: grid depth, capture scheduler, SOURCES, reconciliation test | MERGED |
| #15 | Sweep-6: envelope zone fix, volume windows, compare UI, vanna check | MERGED |
| #16 | Sweep-7: scale-lock control, exact-spot chip | MERGED |
| #17 | Sweep-8: OI findings, comprehension harness, ablation ladder, SPX draft | MERGED |

## Ticket status
| Tickets | Status | Evidence |
|---|---|---|
| T00 baseline/branches | ✅ | STATUS.md, PLAN.md |
| T01 metrics registry/signs | ✅ | exposure_metrics.py + invariants/canaries |
| T02 parser/timestamps/SPX resolver | ✅ | timestamps preserved (live), resolver tested; SPX chain ⛔ (400, SPX_FOLLOWUP.md) |
| T03 canonical engine + clock + Rust parity | ✅ | vendor engine, solstice_time.py, cargo 29 pass, max-pain parity pin |
| T04 raw/delta/activity surfaces | ✅ | grids + switch + reconciliation test |
| T05 walls/unknown states | ✅ | wall_structure.py, unknown-first tests |
| T06 grid/query races/scales | ✅ | scope guards, single-flight, lock control, a11y |
| T07 inspector/scenarios/interaction | ✅ | payload interactions wired this slice |
| T08 enrichment | ✅ | moneyness/OI-change/RVOL-free (RVOL needs intraday bars — see T26) |
| T09 recorder/replay | ✅ code / 🔶 multi-day history | 7 tables, replay, manifest, compare; live captures exist; history <2 snaps |
| T10 0DTE scout | ✅ | side-first + rejection codes, live smoke |
| T11 labels/eval/comprehension | 🔶 | labels + walk-forward + ablation harness + comprehension harness; blinded human run + holdout pending |
| T12 execution adapter | ✅ disarmed / ⛔ live | mocked tests only; live activation explicitly out of scope |
| T13 rollout | ✅ doc / 🔶 commissioning | ROLLOUT.md, COMMISSION.md (account-dependent items blocked) |
| T14 tooltips/guide | ✅ | METHODOLOGY.md + popover + replay guide |
| T15 regime/roots | ✅ | reversed/multiple/no-root handling, no directional permission |
| T16 patterns | ✅ code / 🔶 calibration | numeric library + guards; thresholds unvalidated by design |
| T17 vanna/expiry-removal | ✅ | Vomma split, FD cross-check, removal view |
| T18 capability registry | ✅ | 27 ops + docs base/date; account probes in COMMISSION.md |
| T19 session/playbooks | ✅ | permissions + playbooks + reason codes |
| T20 sizing/costs | ✅ | whole-contract sizing, breakeven, stress; live costs need fills |
| T21 evidence/AI boundary | ✅ | packet + validator + fallback + 8-case corpus |
| T22 eval harness | ✅ | ai_eval corpus runner; model/latency reports need runtime traffic |
| T23 workflow/replay | ✅ | status strip, inspector, replay + compare UI, keyboard flow |
| T24 harness | ✅ | solstice_harness.py + STATUS receipts |
| T25 missed-opportunity | ✅ code / 🔶 data | causal ledger + review; needs recorded encounters |
| T26 manifest/governor | ✅ schema / 🔶 measures | unknown-first manifest; OI cadence/429 need time |
| T27 fixtures/canaries | ✅ | 16 canaries incl. parity, mutation, FD checks |
| T28 Q1/Q2/Q3 + sizing | ✅ frozen / 🔶 evaluation | FROZEN_PROTOCOL.md; paired evaluation needs sessions |
| T29 longevity | ✅ | migration, compat, retention, DUCKDB_PATH file backing |

## Findings F01–F27
All 27 addressed in code with tests, except F22 (execution adapter stays
disarmed by scope) and the SPX half of F06 (externally blocked, ticket open
with vendor). F12 Mongo display cache: typed ts + compat; research history
is DuckDB (file-backed when DUCKDB_PATH set).

## Revision 5 — R5-A–R5-F reconciliation (24 Sep 2026, main #31–#35 + R5-F)

Scope key: ✅ implemented + verified · 🔶 implemented, validation needs
sessions/time/user · ⬜ incomplete (no code) · ⛔ externally blocked.

| Package | Verdict | Evidence |
|---|---|---|
| R5-A observation contract | ✅ | idempotent quality, null source time, observation IDs, canonical payload + snapshotId (test_r5_a_red, 4) |
| R5-B recording/replay | ✅ | full cells, lossless adapter, epoch scope, tx truth, registry alias, replay isolation (test_r5_b_red, 3; Jest replay +4) |
| R5-C wall lifecycle | ✅ | dwell reset, adverse invalidation, scoped IDs, zero-break, gaps, newest-wins (test_r5_c_red, 6) |
| R5-D 0DTE context | ✅ | strict age/expiry, production callers, pre-open, eligibility gate (test_r5_d_red, 3) |
| R5-E explanation/study | ✅ code / 🔶 user | prose binding, wall facts, replay checks, fallback blocks, direction-aware scoring + selftest 15/15 (test_r5_e_red, 3). Actual participant study needs the user |
| R5-F research/ops | ✅ code / 🔶 data | encounter horizons, gap model, live decisions, cadence manifest, capability unity, health endpoint, COMMISSIONING_PACKAGE.md draft (test_r5_f_red, 4). Outcomes/sessions/commissioning need time + approval |

Remaining external/user items (unchanged): SPX entitlement probe, participant
comprehension study, deployment audience/data rights, durable-service
commissioning approval, 30–60 representative sessions. None blocks R5-A–R5-F
engineering, and none is claimed complete here.
