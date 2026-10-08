# U07 probe handoff — OpenCode → Cline (2026-10-08, human-authorized assist)

File: `backend/tests/unified/test_saved_scanner_opencode_probes.py`
(5 tests, green first run on system interpreter; lives in the OpenCode
lane `work/host-opencode`, not duplicated). No source touched.

Characterization pins (source held throughout — locks, not finds):

- Examples capped at 3 per symbol (count preserved separately).
- Stale `received` never overwrites newer.
- 7-day window excludes expired AND future-dated rows.
- `recent()` caps at 100; `saved_records()` reaches the full 500.
- `recent()` drops zero-contract rows.

Left for your slice: fresh-vs-rotating distinction, paging/cursor bounds,
failure/capacity states, duplicate/future/stale guards at the service
layer, and the `complete_realtime_market=False` honesty. If any pin
conflicts with your repair, this file is renamed or removed on your word.
