# U10 review — legacy export (OpenCode → Cline)

Scope: `backend/scripts/export_legacy_decisions.py` + `test_legacy_export_
completeness.py` (Cline lane, uncommitted). Nothing copied or modified.

## Independent re-run

`python3 -m pytest tests/unified/test_legacy_export_completeness.py -q`:
**5 passed**. Round-trip, atomicity, digest refusal, duplicates, exporter
gate, quote-truth all reproduce.

## Findings (both minor, both in Cline's files — not edited here)

1. **Docstring overclaims a guard.** The module docstring cites "an explicit
   `--require-stopped` check", but `main()` parses only `--database` and
   `--out`. Real protection is `read_only=True` + DuckDB's own file lock
   (sound), but the docstring must be corrected to describe exactly that —
   a recovery-integrity tool must not claim checks it lacks.
2. **Silent normalization.** Malformed `reason_codes`/`features` JSON becomes
   `[]`/`{}` without a trace. The exported document stays digest-verifiable,
   but stored values are altered silently. Minimum: count normalized rows
   in the receipt (or refuse). Current tests don't cover a malformed-JSON
   row end to end.

## Verdict: ACCEPT (takeover repair applied 2026-10-08)

Under human takeover authorization, OpenCode applied the two minor items
directly in Cline's lane (Cline halted; exact diffs in `TAKEOVER-LOG.md`):
docstring now describes the real guards; malformed rows counted in
`normalized_rows` + pinned by a new end-to-end test. Suite now 6/6 green.
Real-store completeness remains HELD on NAV-CAPTURE.
