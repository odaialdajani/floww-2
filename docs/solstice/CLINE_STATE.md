# CLINE_STATE — Cline (Kimi K3 / Max) FLOWW analytical-data lane checkpoint

Adopted ownership per `FLOWW-Three-Agent-Ownership-and-Contracts.md`
(2026-10-03): Cline owns `public_api_adapter.py`, `market_data.py`,
`solstice_price_paths.py`, the new bounded analytical-range producer,
additive `heatmap_history`/`recorder_health`/price-fetch seams, producer
tests, namespace-specific analytical migrations and CLINE_-prefixed evidence.
Zed owns mounts/frontend/combined acceptance. Spark owns execution boundary.
71 protected files + other lanes' checkpoints: untouched, read-only.

## Baseline + lane

- Verified heads (2026-10-03): main `6eaa3343`; PR104 receipt `77b8a127`
  (4/4 green); PR105 combined `22df6fe67463acc8a41283804e710d07dff105bd`
  OPEN with ALL FOUR hosted gates SUCCESS (CI/CD 37146495720 re-run +
  lint 37146495700). PR103/104/105 remain open/unmerged.
- This lane: worktree `.worktrees/cline-c1-r18`, branch
  `cline/r18-analytics`, created at exact `22df6fe6`. Prior lane worktrees
  (zed-*, spark-*, combined-*) and the dirty main checkout preserved.
- CLINE_STATE is the cross-host recovery record; Cline checkpoint restore is
  used only inside this worktree after inspecting uncommitted changes.

| ID | Task | Status | Evidence / next action |
|---|---|---|---|
| C1 | Owning bounded 14–60 analytical producer (range-analytics.v1) | DONE | `services/solstice_range_analytics.py` + adapter seams `fetch_option_expiry_listing` / `fetch_chain_for_expiries` (skip-accountable, 2+N budget, identity-bound cache) + additive route `GET /api/heatmap/{ticker}/range-analytics`. Registered kernels reused (gex.v2: raw_oi/delta_weighted/volume; window surface explicitly unavailable until recorded baseline). |
| C2 | Full range persistence/replay + TRUE subprocess proof | DONE | `heatmap_history.range_analytics_envelopes_v1`; writer→exit→independent-reader subprocess proof with distinct PIDs + exact digest/axes/cells/clocks equality; corrupt/missing/legacy cases explicit. |
| C3 | Read-only evidence inspector + outcome sufficiency | DONE | `services/solstice_evidence_inspector.py` (explicit-store, read_only). |
| C4 | Acceptance matrix + contract/fixture handoff | DONE | Contract + frozen digests + lane PR106 (draft). |
| C5 | Budget: failed required debits refuse, ZERO vendor calls | DONE | All 3 acquire_n sites (legacy chain walk + new listing + new window fetch) refuse on non-BudgetExhausted debit exceptions. Tests pin zero broker calls. |
| C6 | Evidence integrity: canonical content contract | DONE | `content_schema: rga-content.v2`; digest covers axes/cells/metric identity/units/model/populations/clocks/coverage/provenance/synthetic/status; explicit excluded transport/storage fields; recompute+validate on write AND replay; typed refusals (DIGEST_MISMATCH/RECORD_ID_MISMATCH/ROW_HEADER_MISMATCH/STORED_DIGEST_MISMATCH/STORED_RECORD_CORRUPT/INCOMPATIBLE_CONTENT_SCHEMA/CORRUPT_PAYLOAD); duplicate success requires recomputed equality both sides. Old v1 fixture digests marked superseded. |
| C7 | Governed populations + per-metric admission | DONE | Sections carry `population` from registered domain aggregates (genuine input_contracts + per-reason exclusions) + kernel counters; `metric_admitted` only for clean ok; `metrics.{admitted,partial,unavailable}` summary; invalid-delta/quarantined inputs with finite cells stay partial (tested). |
| C8 | Inspector: ticker scope, classification, qualification | DONE | All censuses accept ticker scope; synthetic/production/unknown classification for price paths, decisions, envelopes; sufficiency counts QUALIFIED (non-censored, lineage-linked, production-classified, actual NY-date) sessions only — 30 synthetic days → INSUFFICIENT EVIDENCE (tested). |
| C9 | Read-only range record index/replay API | DONE | `GET /api/solstice/price-paths/range-records` (+`/{record_id}`), identity filters, bounded pagination (≤200), per-row integrity verdicts, 404/422/503 typed refusals; legacy replay namespace untouched; frozen list/replay fixtures published. |
| C10 | Capture guard + grounding identity | DONE | persist=true ≈ now requires FLOWW_RANGE_CAPTURE_ENABLED + operator API key (503 CAPTURE_DISABLED / 401); default reads never write. `grounding` block: stable `record_query_identity` for Zed, per-expiry contract population + contracts_digest, contract drafting explicitly REFUSED (`RANGE_RECORD_REFERENCE_ONLY`). |
| C11 | Consumer-review repairs (Zed 2026-10-04 PR106 qualification HOLD) | DONE | `rga-content.v3`: metrics summary joined the canonical digest (v2 refused, never upgraded). ONE shared exception-safe `bind_range_row` behind duplicate-write/replay/index: binds row record_id, ticker, window (NULL → typed refusal, no TypeError), asof, status, received_at AND stored digest to the payload; replay wrapper echoes only bound payload values; index verdicts == retrieve verdicts; duplicate write validates the STORED payload's own identity. Kernel-CORRESPONDING populations (BS mirror for raw_oi; kernel counters for delta/volume + mirrored missing_volume) — missing IV is an exclusion, absent vendor gamma never falsifies unavailable. Debit now PRECEDES cold `_get_broker()` auth/accounts at all three seams (warm-singleton cache serve stays debit-free). Inspector: `paper` class distinct from production ("public-paper" never production/qualified), envelope census integrity-validated via the shared binder (tampered/forged never production), 500-group cap disclosed (`truncated`), naive timestamps read as UTC (recorder contract), store-wide tables note. Full v3 ok/partial/refused replay fixtures with version+envelope for Zed. 19 new tests (`test_r18_consumer_repairs.py`). |

## Acceptance checks at this lane head (reconciled exact counts)

New focused suites (C1–C10): **36 passed** —
`test_r18_range_analytics.py` 15, `test_r18_range_replay_subprocess.py` 2,
`test_r18_evidence_inspector.py` 4, `test_r18_adapter_range_seams.py` 4,
`test_r18_repairs.py` 11.
(Count reconciliation: e6d35745 had 24 = 15+2+3+4; the earlier CLINE_STATE
"20" predated the adapter-seam file. The guard sweep below runs 313 total.)

Combined exact command (this head):
`python3 -m pytest backend/tests/solstice/test_r18_*.py backend/tests/test_public_api_only.py backend/tests/services/test_public_api_adapter_regressions.py backend/tests/test_public_spot_validation.py backend/tests/routes/test_public_api_chain_routes.py backend/tests/solstice/test_r12_recovery_kernel.py backend/tests/solstice/test_r13_recorded_display.py backend/tests/solstice/test_r13_next_listed.py backend/tests/solstice/test_r14_window_producer.py backend/tests/solstice/test_r14_vertical_slice.py backend/tests/solstice/test_r11_metric_contract.py backend/tests/solstice/test_r15_execution_lifecycle.py backend/tests/solstice/test_r17_lifecycle_inventory.py backend/tests/solstice/test_r17_hardening.py backend/tests/solstice/test_r17_reads.py backend/tests/solstice/test_r15_price_producer.py backend/tests/solstice/test_r15_price_wiring.py backend/tests/solstice/test_evidence_packet_redaction.py -q`
→ **313 passed, 0 failed**. `ruff check backend/` clean.

Local CI-gate parity at c085f8fb: `ruff check backend/` clean; bandit with
the CI's exact flags clean; `qc/audit/check_silent_excepts.py` OK (355 files);
`qc/audit/truth_audit.sh` 228 passed/0 failed. Hosted gates at c085f8fb:
frontend-build PASS; lint run 37160242517 fails ONLY on docs/api freshness
(openapi.json + README.md — the recorded Zed-owned regeneration handoff);
backend-tests pending at publication time (no CI polling per instructions;
Zed verifies hosted gates when assembling the combined candidate).

## Session re-verification 2026-10-04 (at lane head 2d0aa703, tree clean)

- Exact recorded sweep command re-run VERBATIM from the repo root →
  **313 passed, 0 failed** (the record was already correct; a transient
  mismatch during re-verification was the operator running a hand-stripped
  path list from `backend/`, not a record defect). 36 new focused tests
  re-run → 36 passed. Per-file counts re-derived from source:
  15+2+4+4+11 = 36; at e6d35745: 15+2+3+4 = 24; the pre-adapter-seams "20"
  was 15+2+3. No count was silently promoted.
- Gate parity re-run at 2d0aa703: `ruff check . --select F841` clean;
  `ruff check .` clean (backend/); bandit with the CI's exact flags clean;
  `check_silent_excepts.py` OK (355 files). Truth audit is commit-subject
  scoped: 228 passed/0 failed at c085f8fb (code head, as receipted);
  226 passed/0 failed at 2d0aa703 (docs-only receipt head) — both 0 failed.
- Protected71 re-check at 2d0aa703 via `git hash-object --stdin-paths`
  against `docs/solstice/r11/PROTECTED_MANIFEST.txt`
  (SHA256 c5bea4270f1b6a79d60c22468db261644d43dcf2ee5aeb653cad4a3fff1e6e94):
  **71/71 identical**. Lane diff vs base 22df6fe6 touches only Cline-owned
  paths (21 files, all under backend/services|routes|tests/solstice +
  docs/solstice CLINE_* + r18 fixtures). No Spark/Zed/watchdog/frozen file
  changed.
- Visible writer→exit→reader proof re-run (synthetic fixtures only):
  writer PID 75012, reader PID 75018, driver 75008 — all distinct;
  content_digest equal both sides
  `54f0a823b635f938492cbfb3e0531e638338fc29aa7117a38d9d18c360cb955c`
  (rga-content.v2); axes (3 expiries 2026-10-26/11-09/12-04 × 2 strike
  keys), clocks and raw_oi cells equal; `synthetic: true`; replay note
  "exact stored envelope restored; canonical content digest recomputed and
  verified; no recomputation". C5–C10 tests re-run by name: all PASS.
- Hosted PR106 snapshot at 2d0aa703 (single check, no polling):
  backend-tests **PASS** (12m8s), docker-build **PASS** (4m0s),
  frontend-build **PASS** (3m0s); lint run 37160585839 FAILS ONLY the
  "API docs match the app" step (stale docs/api/openapi.json + README.md —
  Zed-owned; regenerate with `python3 qc/audit/generate_api_docs.py` in the
  combined candidate). PR106 remains OPEN/draft; it is NOT all-green while
  lint is red.
- Runtime/model verification (per harness rule — record, never invent):
  this host session's actual Cline provider config
  (`~/.cline/data/settings/providers.json`) is `lastUsedProvider: nvidia`,
  model `z-ai/glm-5.3`, reasoning effort `xhigh`. No Kimi/Moonshot provider
  is configured on this host; the packet's "Kimi K3 / Max" label is not the
  effective model. No global setting was changed. Tool permissions:
  read/search/edit/commands available; no broker/MCP execution exposure;
  runtime capture/activation remain OFF (no FLOWW_RANGE_CAPTURE_ENABLED set).

Resume: continue READY work only if new scope appears; otherwise the C queue
is complete and remaining items are NAV-* external (account/policy/capture
approval) — report HOLD for those with the exact input required.

## C11 session (2026-10-04, consumer-review repairs at this head)

Scope: every defect in Zed's 2026-10-04 PR106 review comment
("Full qualification HOLD: …"). New focused suite
`tests/solstice/test_r18_consumer_repairs.py`: **19 passed** (failed-first:
each defect reproduced before its fix). Full lane+guard sweep at this head:
**332 passed, 0 failed** (313 prior + 19 new). `ruff check .` clean.

- Content schema bumped `rga-content.v2 → v3` (metrics summary in the
  digest); v2 payloads/envelopes refuse `INCOMPATIBLE_CONTENT_SCHEMA`.
  Superseded digest generations recorded in the contract doc.
- New shared exception-safe `heatmap_history.bind_range_row` (row
  record_id/ticker/window/asof/status/received_at/stored-digest ↔ payload);
  used by record-duplicate, replay and index — verdict parity tested against
  cell tamper, header tamper, digest-column tamper, NULL window and a fully
  self-consistent forgery (all refused; forgery caught by the row
  record_id/digest binding the v2 code never had).
- Kernel-corresponding populations: raw_oi BS mirror
  (`oi/iv/t_missing_or_nonpositive`, `strike_invalid`, `expiry_missing`,
  `type_unknown`, `gamma_nonpositive`), delta/volume kernel counters +
  mirrored `missing_volume`. Tests pin: missing IV → partial/not-admitted;
  no vendor gamma + iv/T → raw_oi stays finite/admitted (never
  "unavailable"), delta/volume honestly unavailable.
- Adapter: required debit now precedes cold `_get_broker()` auth/accounts at
  all three seams; tests assert `_get_broker` await_count == 0 when the
  debit raises. Warm-singleton identity-bound cache serve stays debit-free
  (tested under a raising budget). 2+N and per-expiry skip accounting
  unchanged (`budget_pre_debit == 4` still pinned).
- Inspector: four-way `_classify_source` (synthetic/paper/production/
  unknown; "public-paper" → paper, never production, never qualifies);
  envelope census integrity-validated via the shared binder + provenance
  paper classification; `truncated`/`listing_cap`/`n_groups_listed`
  disclosed at the 500-group cap; naive `at_ts` read as UTC (one-aware +
  one-naive same-instant test collapses to ONE NY day); `tables_note` says
  counts are store-wide.
- Fixtures regenerated under v3 (complete/partial/index/replay) plus NEW
  `record_replay_partial_v1.json` and `record_replay_refused_v1.json`;
  `record_replay_v1.json` now carries `version` + the FULL bound envelope
  (was metadata-only). Byte hashes in the contract doc; complete record
  `rga1-3ae0977fcd69e869ac8e3a11`, digest
  `3ae0977fcd69e869ac8e3a117536920f966c5ba57fe8f4f33c8094e36a4c0bb6`.
- Zed consumer impact: REGENERATE/refresh any mounted v2 fixture copies —
  v2 records now refuse `INCOMPATIBLE_CONTENT_SCHEMA` by design; the
  wrapper/envelope cross-check Zed planned is now fixture-backed. Contract
  version bump is the recorded handoff; routes and shapes are unchanged.

## C12 session (2026-10-04/05, review-5979463755 seam repairs, completed by coordinator)

Scope: the interrupted C12 repair (started in-session, session stalled at
11:19 EDT with "The operation timed out."; successor session cancelled at
17:18 EDT mid-red-test). The exact unfinished task — RED
`test_c8_ticker_scoping_and_classification` (`assert suf["n_qualified_sessions"]
== 1` got 0) — was reproduced, diagnosed and completed at this head by the
coordinator (Hermes GLM5.3) under the packet's takeover rule, preserving the
whole uncommitted predecessor diff.

Diagnosis: the uncommitted C12 qualification tightening requires a qualified
session to carry (1) non-censored production-classified lineage, (2) an actual
OPEN XNYS session day, and (3) actual OWNING snapshot evidence
(`heatmap_snapshots_v2`) for the scoped ticker on that NY day. The c8 fixture
seeded no owning snapshot, so the QQQ production day correctly stopped
qualifying — fixture gap, not a code defect. Repair: seed the owning QQQ
snapshot via the real `record_snapshot` seam (2026-10-01, verified open XNYS
day); consumer-repairs fixture gained the same seed plus a no-snapshot
negative store (qualified 0).

Verification (repo `backend/` cwd, venv 3.14, disclosed):
- R18 suites: **81 passed, 0 failed** (7 files incl. consumer/review repairs)
- Lane+guard sweep: **277 passed, 0 failed** (16 adjacent files; total 358 =
  332 baseline + 26 new/extended C12 tests)
- Mutation pins: dropping the snapshot requirement →
  `test_r8_open_days_need_owning_snapshot` RED; dropping the exchange-open
  requirement → `test_r8_thirty_closed_days_never_meet_target` RED; restored
  source passes 49/49. Non-vacuous.
- Gates: `ruff check backend/` clean (ruff 0.15.22 CI-pinned); bandit with
  CI's exact flags: 0 issues in services/routes/server.py (the two repo-root
  B102/B104 findings are pre-existing in files untouched by this diff);
  silent-excepts audit OK (355 files).
- Effective host of record for this completion: Hermes (this coordinator)
  on z-ai/glm-5.3, NOT the stalled Cline CLI session. The Cline session
  `1791083843521_pihto` (nvidia/z-ai/glm-5.3/xhigh, user-confirmed) remains
  the Cline identity; its backup is at
  `~/.cline/data/sessions/backup/1791083843521_pihto`.

## C12-CI session (2026-10-05, PR106 hosted-CI repairs at b93242f5)

First hosted run of the pushed lane (run 37295235629/37295235622 at
b5c58b27) failed backend-tests on two tests; both diagnosed from raw
logs and repaired (failed-first pins included):

1. `test_r5_generator_is_idempotent` — cross-platform byte divergence
   (Cline-owned): `grids.raw_oi` cells were the only float-bearing content
   in the canonical digest and carried raw 17-sig-digit double reprs; the
   last ulp differs between macOS and Linux libms, so macOS-generated
   fixtures could never byte-match the Linux producer. Fix: cells are
   QUANTIZED to 1e-6 at `_dense_section` assembly (six orders coarser than
   libm noise, far below decision thresholds) — envelope bytes and the
   content digest are platform-stable by construction. New pin
   `test_r5b_cell_bytes_are_platform_stable` (RED pre-fix, GREEN post).
   All 7 docs fixtures regenerated; staging regen re-run byte-identical.
   New hashes: complete `f67d84c2…`, partial `21c03bbf…`, record_id
   `rga1-f2600391594368d7c17bd2c5`.
2. `test_stale_observation_is_reported_as_stale` — wall-clock time bomb
   (shared test, not lane code): hard-coded "fresh" asof 2026-09-28 crossed
   the module's own 7-day staleness boundary on 2026-10-05 (age 642000s >
   604800s). Fix: asof stamps computed relative to the wall clock
   (30 days vs 1 hour old); semantics preserved forever.

Verification at b93242f5 (venv 3.14 disclosed): R18 suites 82/0;
lane+guard sweep 359/0 (24 files); conviction file 24/0; `ruff check
backend/` clean. Pushed b5c58b27..b93242f5; hosted gates re-running at
record time (single check, no polling). Known remaining red: docs/api
freshness — the recorded OpenCode-owned regeneration handoff.

Hosted verification of the CI repairs (run 37303460988 at 61164572):
backend-tests PASS 16m28s on the Linux runner — both repairs confirmed
cross-platform. frontend-build PASS; ruff red remains ONLY the docs/api
freshness handoff (OpenCode-owned).

Independent Cline-lane reviews of OpenCode's Spark lane (packet
references/): S01/S04/S05 at `1f3b4258` (ACCEPTED — see
cline-review-spark-s01-s04-s05-1f3b4258.md); S04/S12 cancel truth at
`a7609446` (ACCEPTED — real-task-cancellation probe: memory+durable
UNKNOWN annotated, retry reconciles original identity, zero new
placements); I04 mounted full-stack at `d24fedce` (ACCEPTED — matrix
reproduced 4/4 + 49/49 over real HTTP; fingerprint tamper refused;
CONFIRMED KNOWN GAP: same-approval replay places a 2nd order, the
recorded single-use/lease->submit design point); S02 principal authority
(ACCEPTED — cross-account mint OPERATOR_UNAUTHORIZED, removed-operator
replay OPERATOR_UNKNOWN, zero placements; shared-key residual stays
NAV-ACCOUNT); S03 entry enumeration (ACCEPTED for the Public.com money
path; disclosed residual: pre-existing authenticated-but-unadmitted
POST /api/alpaca/order PAPER entry, predates the lane, outside Spark
ownership — Nav/OpenCode decision). Queue: S01-S05, S12, I04, S03
ACCEPTED; S15 publish-only; I01 READY at producer head b5c58b27.

Full-suite receipt (2026-10-05, coordinator, at 9bc8ec39 tree): the
ENTIRE backend suite `pytest tests/ -q` → **7190 passed, 37 skipped
(pre-existing), 0 failures** in 4m03s (Mongo up, venv 3.14 disclosed) —
no cross-module regression from the quantization or clock-relative
staleness edits anywhere outside the 24-file lane sweep. Protected71
re-verified at this tree via `git hash-object` per manifest line:
**71/71 identical**. Hosted at 61164572 (identical code content):
backend-tests PASS 16m28s + frontend PASS; only docs/api freshness red
(OpenCode-owned handoff).

PR106 ALL-GREEN receipt (2026-10-05, coordinator): at `c39752bc` ALL
FOUR hosted gates PASS — backend-tests 12m01s (run 37308132541),
docker-build 3m09s, frontend-build 2m07s, ruff 2m15s (run 37308132584).
The final red gate (docs/api freshness) closed by regenerating
openapi.json + README.md for the three r18 routes (380→383 paths) —
verified additive-only (zero existing-path modifications, zero removals,
zero info drift; README 391→394 endpoints) and committed under the
user's explicit takeover authorization after confirming the OpenCode lane
idle 2h+; `generate_api_docs.py --check` passes (383 paths). Full local
suite at this tree: 7190 passed/0 failed; protected71 71/71.

## External (not engineering): NAV-CAPTURE

Approved production capture/storage policy and admitted REAL records after a
real restart remain outstanding; the subprocess proof is synthetic-only
engineering. Policy UNSET, activation OFF, outcomes INSUFFICIENT EVIDENCE.

## Recorded shared-file handoff (Zed)

- PR106 hosted gates at `e6d35745`: backend-tests PASS, frontend-build PASS,
  docker-build PASS; **lint run 37155212834 FAILS ONLY on docs/api freshness**
  (openapi.json + README.md stale after the additive routes; verified locally
  and in CI logs — no Ruff source violation). `docs/api/*` are Zed-owned:
  regenerate when assembling the combined candidate. Now THREE additive
  routes: `GET /api/heatmap/{ticker}/range-analytics`,
  `GET /api/solstice/price-paths/range-records`,
  `GET /api/solstice/price-paths/range-records/{record_id}`.
- Spark needs only the stable analytical facts for its immutable intent:
  `record_id`/`content_digest` (rga-content.v2), `query` window + `as_of_ny`,
  per-section `metric_id`/`basis`/`formula_version`, `metric_admitted`,
  and `coverage.complete` / refusal codes.
- Zed resolver identity: `grounding.record_query_identity`
  {symbol, min_dte, max_dte, as_of_ny} + `record_id`; contract drafting from
  range records stays REFUSED (`RANGE_RECORD_REFERENCE_ONLY`) until real
  owning quote capture is commissioned (NAV-CAPTURE).

## C19 session (2026-10-06/07, C10 per-contract population closure)

OpenCode's independent C10 review at main 1fc5582c (packet
`references/evidence/c10-1fc5582c-probe.log`) returned PARTIAL: resolver
verified for the admitted aggregate population (16/16 incl. byte-identical
restitution, typed-refusal battery, no live-chain call graph) but per-contract
OSI/series/expiry/strike/right/multiplier restitution was UNPROVEN — no sealed
fixture carried a per-contract population. Prescription: seed synthetic
per-contract rows through the owning write path + replay proof, or Nav narrows
C10. Engineering path taken (real operator values not needed for synthetic
population truth).

Repair 62f29808 (branch `cline/r19-c10-per-contract`, base main 1fc5582c):

- `build_range_envelope` grounding gains `contract_rows` — the deterministic
  per-contract identity population (osi/series/expiry/strike_key/right/
  multiplier + multiplier_provenance via the SAME canonical
  `resolve_multiplier` as the kernels; explicit invalid rests null, absent
  carries DEFAULT_STANDARD). Reference identity ONLY: quotes stay inside
  `contracts_digest`, drafting stays RANGE_RECORD_REFERENCE_ONLY, and rows
  join the canonical content digest (tamper = typed refusal at
  replay/duplicate/index via the shared binder).
- chain fixture gains the adapter-faithful `series` field (SPY → EQUITY).
- Docs fixtures regenerated through the real producer + record/replay seams:
  complete `rga1-8e6217fe33a4978bede91bf0`, partial
  `rga1-b6370d7f35bd93e563da95d2`; both refusal fixtures byte-identical;
  C16 distinct received_at clocks preserved (13:59:30 < 13:59:35).
- Consumer impact disclosure for composition (OpenCode-owned frontend copy):
  `frontend/src/fixtures/integration/range-analytics.v1/replay-transport.json`
  still carries the 33843c65/f2600391 seal — self-consistent and green, but
  after this merges, the transport regen
  (`scripts/r18_range_transport_fixture.py`) must be re-run at the new seal
  and its source_commit re-stamped (same handoff pattern as the C16 regen).

Verification at 62f29808 (repo backend cwd, venv 3.14 disclosed, ruff 0.15.22
CI pin): new suite `test_r18_c10_per_contract_population.py` 7/7 with a
failed-first RED run (7/7 pre-repair); r18+agent focused slice 195/0 (9
files); FULL `tests/solstice/` + budget slice **844 passed / 0 failed**
(837 pre-existing + 7 new); `ruff check .` clean. Mongo up. No live calls,
no broker, throwaway :memory: DuckDB only; capture/activation OFF.

Status: REPAIRED, REVIEW_PENDING — awaiting OpenCode's independent review of
the raw patch (not a test rerun) before any ACCEPTED_AT_SHA bind of C10.
PR (review-only; merge is Nav's) publishes this branch.

