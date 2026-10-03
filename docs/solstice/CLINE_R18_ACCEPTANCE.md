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

## Not done here (by design)

No production capture/restart records (NAV-CAPTURE), no account/policy
values (NAV-ACCOUNT), no server.py mount changes (Zed reviews; this lane's
route rides the already-mounted market_data router), no frontend consumer
(Z1), no main merge/deploy/activation. Policy UNSET; activation OFF;
outcomes INSUFFICIENT EVIDENCE. Synthetic fixtures prove engineering only.
