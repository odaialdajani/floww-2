# SPARK R17 — Receipt (Spark lane, 3 Oct 2026)

Base: `origin/main` `6eaa3343` (PR102 merge). Lane: `solstice/spark-r17`.
No merge, no deploy, no activation, no orders, no flag changes.

## Changes (Spark-owned; one taken shared boundary)

- `backend/routes/solstice_price_paths.py` (+3 read-only routes, contract
  `coverage-read.v1`): `/sessions` (stored NY session-day enumeration),
  `/expiries` (admitted 14–60 DTE window with per-expiry reasons; existing
  `dte≤30` display filter in `market_data.py` untouched), `/comparable`
  (exact `check_window_comparability` verdict over two replayed stored
  snapshots). No writes, no activation, no broker construction (cached
  adapter fetch only, 502 when unavailable like the chain route).
- `backend/tests/solstice/test_r17_reads.py` (6 tests: day enumeration,
  empty-ticker empty state, admit/mismatch/missing, session-roll/reversal
  refusals, window verdicts incl. 0DTE, 502 path).
- `docs/api/openapi.json` + `docs/api/README.md`: regenerated 376→379 (+3
  read-only GETs). Spark-taken generated boundary (precedent §12); diff is
  exactly the three new paths.
- `docs/solstice/MUSE_STATE.md`: §20 R17 queue (R17-1..3 DONE here).

Untouched: `server.py`, `market_data.py` (le=30 intact), agent tree,
`backend/routes/agent.py`, frontend, protected 71/71, frozen artifacts,
watchdog, all flags.

## Verification (exact lane head, Python 3.14.6 vs ship 3.12 disclosed)

- New: **6 passed**; R17-adjacent (r17 + wiring): **14 passed**.
- `ruff check` touched files: **clean** (2 auto-fixed).
- `generate_api_docs.py --check` equivalent: **379 paths**, regenerated.
- Full `tests/solstice/`, truth, silent, bandit, frontend, Docker: run at PR
  head via hosted CI. Recorded at exact head `611f3c2f` (PR103, OPEN,
  review-only): CI/CD backend-tests SUCCESS + frontend-build SUCCESS +
  docker-build SUCCESS (run 37096664993), lint ruff SUCCESS (run
  37096665007). All four hosted gates green at the posted head.

## Net outcomes (honest)

Read-only coverage/admission answers; no behavior change to existing paths.
Empirical outcomes: ZERO durable admitted records → INSUFFICIENT EVIDENCE.
Activation OFF. Admitted DTE range stays commissioning policy; the route
reports windows, it does not set them.

## Zed handoff / blockers

Zed's combined report (e5ee1404 green) + PR100/PR101 drafts acknowledged; zero
file overlap with this lane's 4 touched paths expected (recheck at PR).
Take-over sweep rechecked overlap: PR101 (20 files), PR102 (4 files) and this
lane (6 files) are pairwise disjoint — no conflict. Hole: `dcbc1492`/`e5ee1404`
predate PR102's disarmed-supersede fix `90f96227`; the combined acceptance is
stale vs `main` `6eaa3343` and must re-sync at main + Zed head `75c160c2`
before merge.
Remaining externals: SPX, feeds, fixed account/risk policy, native activation,
participants, durable production capture with admitted records, real-money
record, Nav visual review.

## Take-over additions (3 Oct 2026 — Cline, pass 2)

Addressing Zed's PR103 residual requests (1) and (2); (3) remains READY-owned
next:

- `/sessions` (coverage-read.v1): day attribution is now the stored `asof_ts`
  timestamp prefix — the same attribution `session_manifest`/
  `compare_snapshots` match with `LIKE day%` — plus ET-normalized `ny_date`
  (null when non-uniform) and an `overnight` flag. Prefix stays canonical;
  divergence is disclosed, never mixed. Overnight/offset fixtures pinned.
- `/expiries` (coverage-read.v1): reversed bounds refuse 422 `REVERSED_WINDOW`
  before any fetch; owning display envelope (`dte le=30` in `market_data.py`)
  projected per row as `display_envelope` — a DIFFERENT constraint from the
  admitted 14–60 window; honest `coverage` block replaces the silent firstN
  verdict; listings default 6→12, le 16. Both refusals return structured
  JSONResponse bodies (the global handler stringifies dict details —
  server.py untouched, shared-file protocol).
- `test_r17_reads.py` +3 tests (overnight/offset attribution, reversed-bounds
  refusal before fetch, display-envelope + coverage projection).
- `docs/api/openapi.json` regenerated (taken boundary, precedent §12): diff is
  exactly the /expiries+/sessions schema updates; 379 paths; README unchanged.

Verification (exact head, Python 3.14.6 disclosed): r17 9 + wiring 8 = **17
passed**; ruff touched clean; protected 71/71; no Zed-owned file touched.

Remaining: item (3) authenticated/default-deny stored approvals/preflight +
account-wide limits/inventory/protection/recovery boundary (lifecycle still
unmounted; server.py mounts are Spark-owned) — next exact action. Externals
unchanged: SPX, feeds, fixed account/risk policy, native activation,
participants, durable production capture with admitted records, real-money
record, Nav visual review.
