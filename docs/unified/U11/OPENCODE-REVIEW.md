# U11 review — storage integrity (OpenCode → Cline)

Scope: one-line repair in `services/related_price_series.py` +
`test_storage_restart_integrity.py` (Cline lane, uncommitted).
Nothing copied or modified.

## Independent re-run

`python3 -m pytest tests/unified/test_storage_restart_integrity.py -q`:
**5 passed**. Restart survival, digest-tamper refusal, corrupt-file
typed outage, missing-file cold cache, scan restart with clocks — all
reproduce. Fixtures use fixed dates (no live-calendar dependence).

## Adversarial verification

- The widened `except sqlite3.Error` sits on the READ path only (query +
  fetchall → `[]` + `read_error` flag). Write paths still raise — loud
  writes, quiet-cache-reads is the right split for a cache.
- `read_error` distinguishes integrity refusal (`None`, per tamper test)
  from storage outage (`cache_storage_unavailable`) — the disclosure
  this repair exists for is preserved, not blurred.
- Tamper test pins degradation to disclosed empty-bars attempt records,
  never served payloads. Missing file claims no crash-safety. Both honest.

## Verdict: ACCEPT

One-line, correctly scoped, pinned 5/5 on two runtimes. No findings.
