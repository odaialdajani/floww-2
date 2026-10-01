# R14 admission continuation — Revision 2

Base/main: `3d39ca0975ab9e4758fa694e75adb25b7dbadac0` (PR91). Sole owner Zed.
PR89/90/R13 calculations, unknown/invalid/zero/exclusion conventions, Next listed policy and familiar layout remain binding. R13's original receipts remain historical; later source is not relabeled as that capture.

## Unit 1 — exact listed contract (focused acceptance)

- The existing read-only contract route/resolver and record projection are reused. Structured v2 selectors are admitted only against their **owning stored snapshot**, even when the displayed map is live. No chain, live map/quote, alerts, bars, model invocation or automatic refresh is substituted.
- Server query/version/snapshot/provider/formula/pane/basis/axes/wall/cell are verified before contract resolution. OSI or a complete exact tuple selects; the record supplies OSI, exact decimal strike, listed expiry/type, per-leg quotes/clocks, multiplier and provenance. Wall midpoint/nearest/first-expiry guesses are forbidden.
- Incomplete/truncated population, mismatched series/provider/snapshot/cell/wall, absent multiplier provenance, missing/invalid quote clocks, crossed/missing quotes and before-available-at reads return typed refusal. Unknown is not zero. Recorded measured-zero bids remain zero; stale quotes retain actual ages with stale status. Ages are seconds at the research read, not invented Greek timestamps or fresh live quotes. Replay remains descriptive/degraded (or stale), never current-trading evidence.
- Facts carry the owning observation ID and a selection-bound horizon digest. Client quote/multiplier fields never enter the fact ledger. Legacy opaque v1 contract context remains compatible, including explicit question-symbol conflict handling; it does not gain exact-contract admission.
- The existing review publishes only selectors and resolution state to the existing Solstice context/drawer. Its generation/key ownership rejects late success/error and conflicting response headers, clears pane ownership without another request, and keeps quote age/multiplier/source visible with AI closed. Resolved identity aligns the actual selected cell. No new panel/tab/polling or trade wiring.
- Regression: backend 18 failures before patch → focused suite green; frontend five failures → green, plus mounted publisher isolation. Current module acceptance: **99 backend checks**; **five frontend suites / 32 tests**; focused Ruff and whitespace pass. No assertion weakened or skip added. Browser and final integration/hosted CI are **pending**, not implied by mocked tests.

## Next families — not yet admitted

Comparable stored-window activity and complete registered VEX/Charm replay are next independent units. Missing baseline/old metadata will remain explicitly unavailable. No recomputed/live replay Greeks, aggressor-signed flow, cross-metric magnitude equivalence or invented outcomes.

## Boundaries

No deployment, process restart, daemon startup, capture activation, live orders, credentials or retraining. SPX entitlement, durable commissioning/capture, participant study and empirical live-session/strategy validation remain external. Engineering acceptance is not profitability validation.
