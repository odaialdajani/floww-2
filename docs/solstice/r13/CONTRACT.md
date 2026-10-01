# R13 bounded continuation contract

Base: PR90 merge `9a6c02954557922e9b0d73d6011daf7430f72c16`.
Owner: Zed only. PR89/PR90 formulas, exclusions and layouts are retained.

## Next listed

- Triad requests `GET /api/heatmap/{ticker}?expiry_scope=next`; it supplies no guessed expiry or session date.
- The server chooses ONE earliest actual returned listed date on/after the New York calendar date, within 30 calendar days. Same-date OI remains a structural date scope even after close; this is **not** a next-tradable-contract or entry-permission selector. Existing calendar/series/session execution gates still apply.
- `dte`, scalp and swing combinations are refused (422). 0DTE is never relabeled or populated with a future expiry.
- `map_query.expiryScope/sessionDate`, `scope_selection`, separate cache key, scoped wall lifecycle and next-scope snapshot digest bind the selection. Legacy cache keys/identities are unchanged.
- An empty bound returns an unavailable empty matrix, null exposure and `NO_LISTED_EXPIRY_IN_BOUND`, not a fallback date or zero exposure. No archive record is promised for an empty request.
- Recorded query/selection metadata travels with the record. Triad restores its disabled recorded scope label without starting a second fetch. Older records use an honest recorded-scope label, not invented query metadata.

## Lodestar admission

- Live Raw behavior and legacy ticker-conflict handling remain compatible. Version-2 adjusted contexts admit delta-weighted OI, unweighted session activity and session volume×|delta| only when their server surface matches the exact observation.
- Resolve symbol, query/version, snapshot ID, provider, formula, pane/metric/basis, listed axes, selected cell and raw wall. Client numbers never enter the fact ledger. A conflicting adjusted symbol/pane/surface is not answered using another observation.
- Raw wall gross/net/bounds remain the structural anchor. Adjusted wall facts describe **that same wall** over the full recorded map scope; visible profile facts describe the declared displayed axes. Neither is dealer intent or a directional trade signal.
- Preserve valid profile contributions and measured zero. Missing/invalid delta counts are separate series; excluded observations are never inserted as zero exposure. Partial coverage is explicit and cannot support an unqualified interpretation.
- Adjusted display reads are map-only. Replay reads are record-only: no live chain, map, flow, bars, history watch, or model invocation is substituted. Recorded answers are descriptive/degraded, not current-trading evidence or live-history anchors.
- New records preserve an allowlisted request/source metadata envelope alongside existing grids/metrics. Old records without authoritative query metadata remain unavailable to replay research; no backfill or live reconstruction is performed.
- Window research, exact-contract model answers, price-history and non-GEX replay contexts remain explicitly unavailable. The existing authoritative exact-contract drawer/review remains read-only and tested. Provider absence remains explicit/deterministic; no credentials or paid calls were configured here.

## Acceptance boundaries

Historical `r11/evidence/browser-receipt.json` is unchanged: source `72cdd943`, CSS zoom simulation, 13 shots/60-resize/profile evidence. It is not this head's browser receipt.

New finite workflow: `scripts/r13_fixture.py` (real patched producer/route/recorder; no lifespan, transports blocked and missed-seam attempts fail closed), `scripts/r13_source_binding.cjs` (build with pre/post source hashes), then `scripts/r13_browser_receipt.cjs` (isolated ephemeral loopback preview; API/WebSocket fixtures only; served bundle hashes checked).

Native 200% means Chromium `chrome.tabs.setZoom(2)`, verified by halved layout viewport, doubled DPR, CSS zoom 1 and visual scale 1. This tests the browser-native page-zoom engine, **not a manual browser-menu click**. Matrix access through ordinary container scrolling is recorded. It is not CSS zoom or pinch emulation.

Two browser findings were repaired without rebuilding the layout: responsive cell pruning no longer reopens a dismissed inspector (repeat-selection dismissal stays intact), and short-height/native-zoom desks keep a 280px allocated matrix area with desk scrolling instead of a 4px clipped matrix container. Neither changes analytical scope or values.

Browser receipts separately record viewport/resize/profile/keyboard/linked-pane/Follow evidence. Jest tests cover loading geometry, stale-response cancellation, replay sequencing, safe Expand, exact-contract review and armed/live boundaries; those mocked tests are not represented as live browser or live-market acceptance. No illustrative graphics are used as an implementation oracle.

Final-head CI/local receipts are published on the continuation PR. A browser receipt's source hashes must match the final source; an evidence-only commit is not permission to relabel older acceptance.

## Still external

SPX entitlement, commissioning/capture activation, participant comprehension study and empirical live-session/strategy validation. Native automation is not human comprehension; engineering acceptance is not profitability validation. No deploy, restart, live order, capture activation, credential change or model retraining.
