# U06 — Cline: Related admission verified, no repair required

Owner: Cline. Baseline `8194eca4`, worktree `work/host-cline`. New file:
`backend/tests/unified/test_related_admission.py` (11 tests), no source edits
(no fresh counterexample failed — existing repairs hold at this snapshot).

Admitted with injected facts, tmp SQLite store, zero provider/network calls:

- Exact adjacent-session pairs, never filled: a one-day gap drops the two
  adjacent pairs and none bridge it (22/24 pairs, `partial=true`).
- `MIN_PAIRED_RETURNS=20` enforced: 19 pairs → `insufficient_paired_returns`.
- Zero variance refused (`zero_variance`), never a fabricated coefficient.
- Clock validation: event_time not equal to the admitted session close →
  `invalid_series_clock`; stale (`event < expected` / `cache_stale`) →
  status `stale`/`dated_cache`, distinct from `partial`.
- Self-comparison excluded; missing registry file → coverage
  `available=false` (not fabricated); selected not in cached provider
  directory → `selected_not_in_cached_provider_directory`.
- Warming gating: without `FLOWW_AGENT_DEPLOYMENT=local` → 503 before any
  provider work; remote client or foreign Origin → 403 with warm handler
  never invoked.
- Cancellation: disconnected client mid-batch → 0 attempts, 0 reserved calls.
- Bounded reservation: 8-call cap enforced; a second symbol that does not fit
  the remaining budget is not attempted (`max_reserved_calls` never > 8).
- Bounded paging honored (`limit`/`has_more`/`comparisons_limit`).

Receipt: `../evidence/u06.log` — 11 passed, exit 0 (sha256 recorded in index).
Remaining per acceptance: browser/local-serving evidence separation is U17
scope. Ruff clean (checked with U12 batch).
