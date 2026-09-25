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
- R7-02 delta/VEX contract: acceptance-tested. Canonical vex_net/gross_1volpt
  producers (local-bs-vanna.v1, signed vanna, coverage) wired into every
  display path as data.grid.vex_grid+vex_meta; grid vex view renders
  explicit unavailable (no blank-as-zero). Unknown option type rejected in
  all gex_core aggregations (registry already strict) with invalid_type
  accounting on grid dicts; adjusted quarantine unified. .99 helper fixed
  to x0.01 with version note; tautological test rewritten as oracle.
  NOTE: legacy local vex cells already used x0.01 numerically (naming
  confusion only); Rust-bridge bool coercion still defaults call (Rust
  inactive here — revisit on activation).
- R7-03 display/replay/readout: acceptance-tested. Recorded projection now
  persists full metrics (wall_window, nearest) + context
  (session/scout/regime/patterns/vanna/moneyness); replay restores them
  with dual snapshot_id/snapshotId spelling + complete/partial projection
  status (legacy records explicit, never reconstructed). Readout resolves
  the active viewMode+metric surface (missing = unavailable, never stale
  click value or GEX-under-VEX). Replay clicks cannot reach the live Trade
  handler (call boundary + armed-disarm on entering replay + disabled
  button); false eligibility with empty reasons shows a generic blocker.
  Also fixed a pre-existing broken replay-adapter test (stale fixture
  shape + assertion on an unused path).
- R7-04 compare workspace: acceptance-tested. Single (default, unchanged) /
  GEX+VEX toggle in the existing bar; two REAL grids over one
  snapshot/request (GEX left, VEX right; stacked <900px). Shared
  ticker/spot/scope/selection/live-replay; scroll synced by identity with
  loop guard; independent per-pane scales with a joint lock (cleared on
  scope change); VEX pane ignores weighting controls; missing VEX is
  explicit. Active pane owns the readout; inspector stays raw-anchored.
  Same desk inline and expanded.
- R7-05 review workflow: acceptance-tested. Inspector comparison string
  replaced by a small table (raw/Δ/VEX/session/window + basis/coverage);
  standalone window row removed (was duplicated). Observed interaction
  timeline + deterministic readiness (Observe/Wait/Confirmed for
  review/Invalidated) from the interaction record. Shortlist rows (3/side:
  OSI/expiry/delta/bid×ask/spread/ages) tagged in/out of the selected wall;
  no-candidate explains with reject counts. Advanced shows real per-expiry
  vanna + moneyness distributions (contract-vanna units labeled, no "view
  present"). Backend attaches shortlist rows; tick size honestly null.
- R7-06 series clocks + capability: acceptance-tested. last_trading_utc is
  now calendar-bound (clock.v2): expiry-day close (16:00/13:00 half-day),
  closed expiries fall back to last open close, AM SPX monthly uses the
  preceding open session 17:00 ET (settlement 09:30 never a deadline).
  resolve_series derives SPX/SPXW/EQUITY from root+expiry (third-Friday);
  adapter passes series into the clock and stores it on contracts.
  /capability gains a per-symbol matrix from recorded observations only
  (entitlement unobserved-by-default, no ticker substitution).
- R7-07 episode policy/pending-final: pending (extends NEED_EPISODE).

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
