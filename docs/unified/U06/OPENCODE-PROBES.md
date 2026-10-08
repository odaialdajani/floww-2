# U06 probe handoff — OpenCode → Cline (2026-10-08, human-authorized assist)

File: `backend/tests/unified/test_related_admission_opencode_probes.py`
(6 tests, green on system interpreter; NEW file, no source touched).
The file lives in the OpenCode lane:
`work/host-opencode/backend/tests/unified/` — copy or run from there;
it is not duplicated into other lanes.
Scope respected: probes only, design/repair stays Cline's. Warming,
cancellation, and storage probes deliberately left for your deeper slice.

## Honest accounting: 4 initial REDs were all probe bugs

1. Calendar sessions are pandas Timestamps, not ISO strings → normalized.
2. Underlying-stock synthesis (`underlying_stock` entry for the selected
   symbol's underlying) is by design — pinned as documented behavior.
3. Today's session close lies in the future before 16:00 ET — probes now
   use completed sessions only (real semantic edge, handled in-probe).
4. The pairing window must carry the FULL calendar including gap days;
   only bars lack them — this is exactly what makes gap pairs refuse
   instead of bridging. Probe corrected; behavior verified.

The SOURCE held in all four cases. These are characterization pins locking
correct behavior your repair must preserve — not defect finds.

## What the pins lock

- Gap days skipped, never bridged (37 true adjacencies from a 40-day
  window with one gap; coefficient finite).
- Flat (zero-variance) pairs → typed `zero_variance`, never a number.
- Event-after-receipt and future-receipt clocks → `invalid_series_clock`.
- Self-comparison excluded.
- Registry: independent underlying/benchmark membership, malformed entries
  skipped, missing file → `registry_unavailable`, provider flags None when
  catalog unavailable, underlying synthesis pinned.

## Suggested next (yours)

Warming reservation/cancellation/storage probes need store + provider
fakes and your design calls — untouched. If any pin conflicts with your
repair direction, say the word and this file is renamed or removed.
