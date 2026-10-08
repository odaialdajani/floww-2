# U12 slice review — Trinity provenance honesty (OpenCode → Cline)

Scope: ONLY `backend/routes/trinity.py` + `test_trinity_provenance.py`.
Uncommitted slice in `host-cline`; nothing copied, integrated, or modified.

## Independent re-run

`python3 -m pytest tests/unified/test_trinity_provenance.py -q`
(system interpreter, read-only): **4 passed**. Confirms the pin file on a
second runtime. Cline's `u12-final.log` records 73/73 neighbor run —
read and consistent (warnings only).

## Adversarial verification

- Pins are non-tautological: distinct-ticker constant refusal, typed
  `unavailable` + null pct/regime, spillover refusal + null risk/driver,
  injected compute failure → typed `partial` with response identity
  (`ticker`/`spot`/`net_gex`) intact.
- `logger` is module-defined (no NameError path); silent `pass` removed.
- Frozen helpers untouched: backend diff limited to `routes/trinity.py`
  (+U13 `server.py`, reviewed separately). No scale/kernel edits.
- Consumer safety: `TrinityView.jsx` never reads the reshaped fields;
  `BriefingStrip.jsx` guards with `|| {}` / `!= null` and renders the new
  `interpretation` strings. No frontend change required.
- Out-of-scope siblings (`microstructure:176`, `steal_three:222`, 3-ticker
  table) correctly left for owner scoping — documented, not touched.

## Verdict: ACCEPT (slice only)

Constant-ADV dosing and SPX self-substitution are closed with typed
refusals; failures are loud and partial-never-silent. Remaining U12 scope
(qualified provenance wiring when an admitted volume store exists) stays
Cline's, openly noted in its dossier.

## Independent lint (2026-10-08)

`ruff check` (0.15.22, CI pin) on the slice files: All checks passed.
