# R7 RUN_STATE (sustained harness)

Model: Muse Spark (muse-spark-1.3-contributor-free). Base `7fed6012` (post-#47).
Branch: `solstice/r7`. Packet: R7-00–09, NO merges authorized.
Env: macOS, python 3.14.6, node v24.14.1. Formula `gex.v2`, schema movers
target `movers.v2`, fixtures `comprehension_v1.json`.

## Package ledger (implemented / integrated / acceptance-tested / blocked)

- R7-00 reconciliation: acceptance-tested (head==origin/main==pin, tree clean
  except kanban, env ok, counterexamples reproduced below).
- R7-01 Top Movers: pending. Failing case: route emits `pct` unsorted +
  UI reads `change` + endless ellipsis on error.
- R7-02 delta/VEX contract: pending. Failing cases: no `vex_grid` from
  vendor path; `dollar_vex_per_1pct_vol_change` 99x (0.99 vs 0.01);
  unknown-type/adjusted divergence grid-vs-registry.
- R7-03 display/replay/readout: pending (stale click value, GEX-under-VEX,
  replay Trade callback, snapshotId normalization).
- R7-04 compare workspace: pending. R7-05 review workflow: pending.
- R7-06 calendars/capability: pending. R7-07 episode policy/pending-final:
  pending (extends NEED_EPISODE). R7-08/09 study/gates/handoff: pending.

## Before-fixtures (all reproduced 25 Sep 2026, main@7fed6012)

- VEX: `dollar_vex_per_1pct_vol_change(.2,100,100)` = 198000.0 (expect 2000.0).
- Movers: `App.js` reads `r.change`, route sends `pct`; `data[:limit]`
  unsorted; catch-noop + `…` forever.
- `_display_surfaces` returns GEX surfaces only; grid `vex` view reads
  `data.grid.vex_grid` (absent).

## Next (1–3 steps)

1. R7-01: movers.v2 route (Public bars, completed sessions, rank-then-limit)
   + UI states + route→component test. 2. R7-02: vex surface + .99 fix +
   population parity. 3. R7-03 readout/replay guards.

External blockers: SPX entitlement, participant study, commissioning,
browser pixels, live sessions. None blocks R7-00–08 engineering.
