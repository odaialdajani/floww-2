# Independent follow-up review

Reviewed 2026-09-26 UTC. Read-only source review with offline fixtures; no provider or model calls. No source files changed by this reviewer.

## Result

The partial-search disclosure is mounted on the same App pages as the global ticker search. Retry uses cancellation and an active-effect guard. Focused frontend checks passed: 25 tests in StockSearchNotice.test.jsx and tickerUniverse.test.js. Full-rotation regression passed: 1 test.

## Finding reproduced and fixed during review

A provider directory refresh between pages could previously produce a false complete result. Fixture: initial directory [A,B,C,D], first page [A,B]; provider removes A; second page [D] reports total 3. The previous helper returned [A,B,D] and complete=true, missing C. The revised helper rejects changes to asof or total across pages. Three added generation fixtures pass.

## Full-directory feasibility

Independent offline simulation visited 8,786 distinct names across 733 sweeps of 12; the final sweep wrapped to the first 10 names. No names were omitted, and never_scanned reached zero.

Assuming eight actual requests per second, one second between sweeps, no network overhead and no other account traffic:

- Four requests per name: 85.52 minutes; 108 names remained within the 60-second freshness window in the fixture.
- Five requests per name including average-volume data: 103.84 minutes; 96 names remained within the freshness window.

These are throughput illustrations, not measured live service times. They support the existing partial coverage disclosure and do not support an all-market real-time claim.

## Existing capacity limitation

The scanner retains at most 20,000 per-contract observations. Reproduced eviction of an early contract after 20,000 later contracts. A full broad pass exceeding that size can lose prior measurements before revisiting a stock, so velocity and other repeated-measurement results may remain unavailable. Preserve explicit unknown states; increasing the directory alone does not establish these measurements.

## Boundaries

The parallel session owns history research guards, response-rate-limit feedback, missing-data scanner rows and invalid candles. Those files were not edited here. No additional blocking defect was found in the partial-search changes after the generation fix.
