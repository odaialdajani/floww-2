# U06/U07/U08 verdicts — OpenCode independent review (takeover, 2026-10-08)

Cline authored, halted before verdicts. Reviewed from its lane (read-only);
nothing copied or modified. Baseline `8194eca4` + Cline's uncommitted tests.

## Re-runs (system interpreter, isolated fakes/stores, no provider)

- `test_related_admission.py`: **11 passed**.
- `test_saved_scanner_admission.py` + `test_history_integrity.py`: **16 passed**.
- My complementary probes (distinct files, my lane): 6 + 5 + 5 green —
  no overlap in coverage claims beyond the intended behavior locks.

## Claim checks (source read at baseline)

- U06: warming gate (`require_local` → 503/403 before provider work),
  8-call reservation + `disconnected` cancellation + `max_reserved_calls`
  cap all present in `warm_snapshot`; registry/paging/clock claims match
  the code paths I independently read for my probes.
- U07: monotonic retention, duplicate/conflict refusal, `live=false` /
  `trade_eligible=false` / `complete_realtime_market=false` truth block —
  consistent with `ScanFindings` semantics my probes pin.
- U08: keyset paging, HMAC cursor, node honesty — consistent with
  `price_node_history` pure functions my probes pin.

## Verdicts: ACCEPT (U06, U07, U08 — review complete)

Verified-no-repair stands. Remaining per acceptance is browser/serving
evidence separation (U17 scope), explicitly not claimed here.
