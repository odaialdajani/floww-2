# U08 probe handoff — OpenCode → Cline (2026-10-08, human-authorized assist)

File: `backend/tests/unified/test_history_opencode_probes.py`
(5 tests, green on system interpreter; OpenCode lane only). No source touched.

## Honest accounting: both REDs were probe-side

1. The 900s node-age bound is INCLUSIVE — pinned as `[usable, gap]` for
   ages `[900, 1900]` rather than assumed exclusive.
2. Same-clock tie-break keeps the FIRST view (the documented
   "later-arriving different view cannot choose this chart's default"
   rule) — probe now gives the newer scope a strictly later `asof`.

Source held throughout: future snapshots never leak into earlier bars,
stale nodes become gaps, scopes never mix, foreign tickers excluded,
expiry depth in scope keys, malformed bars/epochs/clocks refused.

## Pins delivered

Epoch parsing (ms/s/naive/garbage/bool/nonfinite), node filtering
(malformed JSON, non-dict, non-positive), future-snapshot exclusion,
inclusive age boundary, scope default + isolation + ticker match.

## Left for your slice (untouched)

Paging/cursor binding under new inserts, ticker/state cursor scope,
bounded lock/query timeouts, malformed clock/ID handling at the route
layer, known_at/age intervals across DST. Rename/remove this file on
your word if it conflicts.
