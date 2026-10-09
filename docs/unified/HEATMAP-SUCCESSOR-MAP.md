# Heatmap requirements → successor evidence map (slice 5, supplemental, 2026-10-09)

Supplements (does not edit) the frozen-candidate map
`FLOWW-Heatmap-Requirement-Map.md` (packet `FLOWW-OpenCode-Hermes-Handoff 2`,
subject `61d03f1c`). Subject here: successor branch
`fix/floww-finish-20261008` at `95a17b47` plus uncommitted Slice-2/3/4 work
(stream identity, unknown-IV/volume rendering, plain-float greeks, lane
appendices). Method: source + test + live-probe inspection on the successor
tree. Missing attachment bodies (33 uploads, sandbox downloads) remain
missing — nothing unseen is claimed checked. No trading value is claimed.

## Requirement → successor evidence

| # | Requirement (conversation) | Successor evidence (this turn unless noted) | Status |
|---|---|---|---|
| 1 | Dense familiar heatmap, look preserved | `SkylitHeatmapGrid.jsx` + `signedGridPalette.js` unchanged by this turn; 35 palette/grid/r11 tests pass | PRESENT, unchanged |
| 2 | GEX / VEX / Charm tabs | Unchanged; VEX row `WallInspector.jsx:143-155`, `test_charm_grid_surface.py` passes | PRESENT, unchanged |
| 3 | Profile + aligned expiries + Calendar/Multi; Focus Matrix default | `RangeAnalyticsWorkspace` + stories unchanged; 103 `RangeAnalytics*` tests pass | PRESENT, unchanged |
| 4 | Raw + Δ compare, same wall/selection linked | Unchanged (`RangeAnalyticsWorkspace.jsx:128,155-156`); lane `Workspace.jsx` variant explicitly rejected — it would regress the shared palette (7-line diff reviewed, Slice-4 record) | PRESENT, regression blocked |
| 5 | Raw = where / adjusted = how; same wall, expiry, observation | **Strengthened**: TriadDesk strict validation unchanged (18 tests pass); exposure route live 200 with same-snapshot agreement verified by probe (ticker/spot/fetched/version/counts); Slice-2 stream identity (`gex-stream.ws.v1`, `gex.v2`, USD, 4-exp scope, coverage) + separation note so stream/snapshot never read as one signal | PRESENT, strengthened |
| 6 | Basis adjustment inside GEX; basis/formula/version/status shown | Unchanged + Slice-2 adds the same identity discipline to the stream channel (`streamScopeLabel`: exp · units · formula, unknown-safe) | PRESENT, extended to stream |
| 7 | "Volume × \|Δ\|" basis option + session-volume entries | Still no separate "Session volume" label/option in compare or Triad UI; plumbing unchanged | PARTIAL, unchanged — user scope call |
| 8 | Exact expiries + observation clocks | Unchanged; TriadDesk receipt caption verified in tests; stream now carries `asof` + `source_event_time` + `chain_event_time` with unknown-safe rendering | PRESENT, extended to stream |
| 9 | Lodestar explanations on demand, research-only | `AskLodestar.jsx` unchanged; `AskLodestar.test.jsx` passes | PRESENT, unchanged |
| 10 | Conditional watches, never dealer intent | **Strengthened**: dealer-intent sentences removed from `SidebarPanels.jsx` + `HeatseekerDashboard.jsx` (`01c1a6ab`, tests pin the conditional wording and assert no `Dealers` text); Triad per-wall watch labels still absent | PRESENT in Solstice; Triad labels still absent (user scope call) |
| 11 | strike_totals backend aggregation for Profile | Unchanged (`gex_core.py`) | PRESENT, unchanged |
| 12 | wall_read backend module + PlayWalls dealer doctrine | DECLINED (acting owner, 2026-10-09): dealer-intent/front-running instructions are a trading-safety harm class, not a scope call; safe subset already ships (king-by-construction, TriadDesk doctrine, conditional watches). History preserved untouched; any rebuild is a fresh reviewed design, never a lane merge. | ABSENT by decision, not by deferral |
| 13 | Surface usability/coverage counts | Unchanged + stream coverage (`n_contracts`, `n_strikes`) now in WS payload and pinned by `test_gex_stream_identity.py` | PRESENT, extended |
| 14 | Stars = concentration maxima | King ★ marker unchanged; trading-value validation still explicitly not claimed | PRESENT as markers only |
| 15 | Working Top Movers | `SolsticeLeaderboard.r11.test.jsx` passes | PRESENT, unchanged |
| 16 | Honesty rules (missing/invalid/partial/measured-zero distinct; no invented returns; no zero-for-unknown) | **Strengthened**: null IV/volume → "—" (genuine 0 kept); producer `fillna(0)` removed (`steal_three.py` NaN→None) with `iv_unknown`/`volume_unknown` flags through `_normalize_contract` into ranked rows and rendering (7 backend + 2 frontend regression tests); greeks plain-float; ADJ == RAW×\|delta\| pinned | PRESENT, strengthened — producer hole closed |
| 17 | Sept audit defects fixed upstream | Re-verified subsets this turn: DUO product-rule form + oracle (30 tests), VWAP bad-wire guard (23 with OSI), sign-vs-pixels palette (35), plain-float (237). Full upstream re-verification remains out of scope | PRESERVED-UPSTREAM, subsets re-verified |
| 18 | 33 upload bodies + sandbox downloads | Still placeholders only | MISSING, unchanged |
| 19 | Opus 23 unpublished commits | **RESOLVED by Slice-4 this turn**: every non-equivalent item has an included/superseded/conflict/defer disposition with test/file evidence in `docs/unified/U16/RECONCILIATION.md`. History preserved in lane checkouts; nothing cherry-picked wholesale | DISPOSITIONED |
| 20 | Full Lodestar integration | Still research-only drawer; deferred per conversation phasing | DEFERRED, unchanged |

## Deltas since the frozen map

1. Item 19 moved USER-DECISION → DISPOSITIONED (Slice-4, this turn).
2. Items 5, 6, 8, 13 extended to the stream channel (Slice-2, this turn).
3. Item 16 strengthened on four fronts (Slice-3 + greek types + producer
   flags); no known producer hole remains on this path.
4. Item 10 strengthened in Solstice wording (prior `01c1a6ab` + verified).
5. Owner decisions (2026-10-09): item 12 moved to DECLINED with safety
   rationale; camera split-decided (price-chart PNG export present+tested,
   grid snapshot blocked on dependency-install safety); recorded curve
   SPECIFIED with activation checklist (`RECORDED-CURVE-SPEC.md`, not built,
   H-CAPTURE). Items 7, 18, 20 and Triad watch labels stay user scope calls.
