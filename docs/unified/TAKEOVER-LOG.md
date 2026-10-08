# Takeover log — OpenCode edits in Cline's lane (human-authorized)

Cline halted mid-U15 by human instruction; OpenCode took over both queues.
Every edit below is in `work/host-cline` (Cline's lane) so its work stays
whole. Nothing was deleted, renamed, committed, or published. If Cline
resumes, reconcile against this list before writing.

## 2026-10-08 — U10 (closes my REPAIR_REQUIRED)

File `backend/scripts/export_legacy_decisions.py`:
1. Docstring: replaced the `--require-stopped` claim with the accurate guard
   description (existing `.duckdb` file + `read_only=True` + DuckDB file
   lock; no separate stopped-process check; malformed rows counted).
2. `export()`: added `normalized_rows` counter, incremented when stored
   `reason_codes`/`features` JSON fails to parse.
3. Receipt: added `"normalized_rows"` field.

File `backend/tests/unified/test_legacy_export_completeness.py`:
4. New `test_malformed_stored_json_is_counted_not_silently_normalized`
   (malformed row exports with `[]`, receipt counts 1).
   (One edit misstep during insertion absorbed the neighboring test's def
   line; repaired immediately and verified all 6 test defs present.)
Suite: 6/6 green after the change.

No other Cline-lane files touched by OpenCode. All other takeover work
(U15 dossier, U13 sweep, U16 map, U06–U08 probes/verdicts) lives in
OpenCode's own lane; Cline-lane test executions were read-only runs.

## 2026-10-08 — U15 C17 slice (OpenCode lane, authorized continue-both)

Own-lane files (`work/host-opencode`):
1. `backend/services/triad_projection.py` — per-strike records carry
   `n_measured`/`n_total`/`partial` (same canonical sums, no new metric);
   new `exposure_by_strike()` projection (series shape + coverage counts).
2. `backend/routes/public_api.py` — read-only
   `GET /api/public/chain/{ticker}/exposure-by-strike`.
3. `backend/tests/unified/test_exposure_by_strike.py` — 6 tests
   (partial/zero/null/fractional/version/empty/route+latch) 6/6 green.
4. `frontend/src/agent/chatNavigation.js` — exact multi-word target names
   resolve before single-key bindings: bare "stock chart" opens the chart
   with no pseudo-ticker.
5. `frontend/src/unified-tests/context-generation.test.jsx` — updated
   expectation (26/26 green with chatNavigation tests).
6. `docs/unified/C17/DEFERRAL.md` — deferral history preserved; addressed
   via counts-construction pitch.
7. `docs/unified/T03-LEDGER-STATUS.md`, `docs/unified/SCOREBOARD.md` —
   C17 pending → closed (baselines notated).

Cross-lane mirrors (floww-unified): identical bytes for 1, 2, 3, 4, 5.

No old failure hidden. No ledger rewrite (deferral preserved as history).
