# U02 addendum — producer cross-read (2026-10-08)

Read-only check against the same baseline candidate
(`work/host-opencode/backend/services/solstice_range_analytics.py:644`):

```python
"oi_effective_dates": oi_dates or None,
"oi_date_note": "per-contract vendor OI effective dates; absent means unknown",
```

The producer itself emits explicit `null` when no per-contract vendor OI
dates exist, and labels absence as unknown. The admitted `null` in
`admitRangeEnvelope` therefore mirrors a real producer shape — not a
consumer relaxation. No backend file was modified or executed for this note.
