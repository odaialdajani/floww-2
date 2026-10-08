# U17 prep — Related/saved/history frontend baseline (2026-10-08)

Lane: `work/host-opencode` (baseline `8194eca4` + parent work + U09 matrix).
These suites cover the frontend areas Cline's U06 (Related), U07
(saved-vs-fresh scanner) and U08 (history) will exercise from the backend.

Command: `CI=true npx craco test --testPathPattern=
"(RelatedTicker|savedStockActivity|Screener|PriceNodeHistory|
recordedPrice|Tidehunter|tideFeed)"`
Result: **15 suites, 130 tests, all green.**

Frozen-pass relevance: when U06–U08 land, re-run this exact pattern plus
the backend slices; any delta then belongs to the backend change, not the
screens. Not acceptance — prep only.
