# CLINE R18 acceptance — Cline analytical-data lane (range-analytics.v1)

Lane `cline/r18-analytics`, worktree `.worktrees/cline-c1-r18`,
base `22df6fe67463acc8a41283804e710d07dff105bd` (PR105). Producer-side
evidence only; Zed owns the final combined acceptance at one frozen head.

## Owned deliverables

| # | Deliverable | Files |
|---|---|---|
| C1 | Owning bounded 14–60 DTE analytical producer (range-analytics.v1): real bounded request from the vendor listing, owning NY-date window, dense null-explicit cells, registered gex.v2 kernel surfaces (raw OI / delta-weighted / volume; window surface truthful-unavailable), coverage with honest completeness, identity-bound cache + record; additive route on the mounted `market_data` router | `backend/services/solstice_range_analytics.py`, `backend/services/public_api_adapter.py` (+`fetch_option_expiry_listing`, `+fetch_chain_for_expiries`, `+_assemble_chain` extraction), `backend/routes/market_data.py` (+range-analytics route) |
| C2 | Owning envelope persistence + replay + independent-process proof | `backend/services/heatmap_history.py` (+`range_analytics_envelopes_v1`, `record_range_envelope`, `replay_range_envelope`, `ensure_range_tables`), `backend/tests/solstice/test_r18_range_replay_subprocess.py` |
| C3 | Read-only evidence inspector + outcome/data sufficiency | `backend/services/solstice_evidence_inspector.py`, `backend/tests/solstice/test_r18_evidence_inspector.py` |
| C4 | Contract + frozen synthetic fixtures + handoff | `docs/solstice/r18/CLINE_RANGE_ANALYTICS_V1.md`, `docs/solstice/r18/fixtures/{complete_v1,partial_skipped_v1,refused_reversed_v1}.json`, `backend/tests/solstice/fixtures/range_analytics_v1/{listing,chain_complete}.json` |

## Rejection-criteria mapping (from the three-agent backlog)

- NOT an expiry listing: the map returns axes+dense cells+basis+units+owning
  record; the coverage-read.v1 listing route is untouched (verified by
  existing `test_r17_reads.py` still passing unchanged).
- NOT an edge/cap heuristic or a ≤30→60 edit: window selection walks the FULL
  vendor listing (`fetch_option_expiry_listing`); the `/heatmap` dte≤30
  display envelope is unchanged.
- NOT two connections in one interpreter: `test_r18_range_replay_subprocess.py`
  proves writer-process → exit(0) → independent reader-process restore with
  distinct PIDs and exact digest/axes/cells/clocks equality.
- NOT zero-filled Greeks/OI: `test_missing_oi_greeks_never_zero_filled`
  asserts null cells and counted missing-delta exclusions.
- NOT replay-by-recomputation: `replay_range_envelope` restores the stored
  envelope; corrupt rows surface CORRUPT_PAYLOAD; unknown identity → None.
- NOT a fabricated healthy census: inspector refuses STORE_PATH_REQUIRED /
  STORE_MISSING / STORE_UNREADABLE; sufficiency verdict INSUFFICIENT
  EVIDENCE below the 30-session target; underlying labels ≠ option P&L.

## Focused checks at this head

- `test_r18_range_analytics.py`: 15 passed.
- `test_r18_range_replay_subprocess.py`: 2 passed (incl. true subprocess).
- `test_r18_evidence_inspector.py`: 3 passed.
- Refactor guard: `test_public_api_only.py` + `test_public_api_adapter_regressions.py`
  + `test_public_spot_validation.py` + `routes/test_public_api_chain_routes.py`: 77 passed.
- Recorder/replay/kernel subsets (r11 metric contract, r12 recovery, r13
  recorded display/next-listed, r14 window/vertical, r15 lifecycle, r17
  lifecycle inventory, evidence redaction): 143 passed.
- `ruff check` on all touched files: clean.
- Local Python 3.14.6 (ship runtime is CI's declared Python); deterministic
  fixtures, zero network/broker/worker activation.

## R18 repair pass (C5–C10) — completed at this head
- **C5 budget**: all three required-debit sites (legacy `fetch_chain_from_public_api`,
  `fetch_option_expiry_listing`, `fetch_chain_for_expiries`) refuse with ZERO
  vendor calls on any debit failure (BudgetExhausted or unexpected/malformed
  budget service). Tests: `test_r18_repairs.py::test_c5_*` (3).
- **C6 integrity**: `content_schema: rga-content.v2`; canonical digest covers
  full evidence content (excluded transport/storage fields: `record_id`,
  `content_digest`, `persistence`); recomputed+validated on write and replay;
  tamper with valid JSON, digest spoofing, stale provenance, foreign headers,
  altered axes/cells and corrupted duplicates all produce typed refusals
  (`test_c6_*`, 3). Pre-C6 v1 digests recorded as superseded.
- **C7 population**: governed `domain.exposure_metrics` aggregates supply
  genuine input/exclusion counts; `metric_admitted` gates per section;
  finite-cell aggregates no longer admit excluded metrics (`test_c7_*`, 2).
- **C8 inspector**: ticker scope on every census; synthetic/production/unknown
  classification; qualified-session sufficiency (NY-day + non-censored +
  lineage + production class); 30 synthetic days stay INSUFFICIENT
  (`test_c8_*` in `test_r18_evidence_inspector.py`).
- **C9 replay API**: `range-records.v1` read-only index/replay routes with
  identity filters, bounded pagination, per-row integrity, typed
  404/422/503 refusals; legacy replay untouched (`test_c9_*`, service+mounted).
- **C10 capture guard**: persist=true requires `FLOWW_RANGE_CAPTURE_ENABLED`
  AND operator API key; default reads never write; grounding block gives Zed
  a stable resolver identity and an explicit contract-drafting refusal
  (`test_c10_*`).

## R18 consumer-review pass (C11) — Zed qualification-HOLD findings

Zed's 2026-10-04 PR106 review listed concrete producer defects; each was
reproduced failed-first, then fixed:

- **rga-content.v3**: the top-level `metrics` summary joined the canonical
  digest (v2 let a tampered admitted/partial summary keep a valid digest);
  v2 payloads refuse `INCOMPATIBLE_CONTENT_SCHEMA`, never silently upgraded.
- **Shared row binding**: `heatmap_history.bind_range_row` is the ONE
  exception-safe validator behind duplicate-write, replay retrieval and the
  index — row record_id/ticker/window/as-of/status/received-at/stored-digest
  all bind to the canonical payload; NULL window is a typed refusal (the
  review's TypeError); the replay wrapper echoes only bound values; index
  and retrieve verdicts are provably identical; a fully self-consistent
  forgery under another row refuses.
- **Kernel-corresponding populations**: raw_oi reports a mirror of the BS
  kernel's filter order (missing IV = exclusion, never admitted); delta/
  volume report their kernels' own counters (+ mirrored missing volume);
  absent vendor gamma can no longer zero `usable` against finite BS cells.
- **Admission before broker init**: the required debit now precedes cold
  `_get_broker()` auth/accounts at all three fetch seams; the warm-singleton
  identity-bound cache serve stays debit-free (tested under a raising
  budget). Zero-provider-call-on-failed-debit is now true at the seam.
- **Inspector truth**: `paper` is a distinct class ("public-paper" is never
  production and never qualifies a session); the envelope census validates
  integrity through the shared binder before classifying (tampered/forged
  → refused_or_corrupt); the 500-group cap is disclosed (`truncated`);
  naive timestamps read as UTC per the recorder contract; table row counts
  are labeled store-wide.
- **Fixtures**: `record_replay_v1.json` now carries `version` + the FULL
  bound envelope (was metadata-only); new `record_replay_partial_v1.json`
  and `record_replay_refused_v1.json` complete the ok/partial/refused
  response set in mounted-route shape. All consumer fixtures regenerated
  under v3 with byte hashes in the contract doc.

C11 receipts: `test_r18_consumer_repairs.py` 19 passed (failed-first);
full lane+guard sweep **332 passed / 0 failed**; `ruff check .` clean.

Focus receipts (this head): 36 new tests pass; full lane+guard sweep 313
passed, 0 failed; `ruff check backend/` clean. Maintenance covers PR106's
known lint drift (docs/api staleness, Zed-owned regeneration).

## Not done here (by design)

No production capture/restart records (NAV-CAPTURE), no account/policy
values (NAV-ACCOUNT), no server.py mount changes (Zed reviews; this lane's
routes ride already-mounted routers), no frontend consumer (Z1), no main
merge/deploy/activation. Policy UNSET; activation OFF; outcomes
INSUFFICIENT EVIDENCE. Synthetic fixtures prove engineering only.
