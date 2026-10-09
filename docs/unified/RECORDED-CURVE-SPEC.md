# Recorded multi-resolution GEX curve — bounded build spec (approved scope, NOT activated)

Status: SPECIFIED. No recorder runs: default is OFF and there is no
auto-enable path. Activation needs the checklist at the bottom plus the
standing H-CAPTURE authorization; until then the code below does not exist
and no production records are written.

## Why this shape

The gap (lane `b0de55c`) is a 1m/5m/15m/1h recorded GEX curve. Stored-session
replay (`solsticeReplay.js`, `ReplayStrip`) covers whole sessions, not
multi-resolution series; history tables (`heatmap_snapshots_v2`) persist
snapshots, not interval curves. A curve cannot be derived — GEX needs chains,
not prices — so recording is inherent. This spec bounds it so activation is a
small deliberate act, not an open-ended tap.

## Contract

- Table `gex_curve_frames_v1`: aggregates ONLY —
  (frame_id, ticker, resolution, expiry_scope, taken_at, event_time,
  spot, total_gex, king_strike, regime, formula_version, units).
  No per-contract rows. Immutability follows the research-history pattern.
- Recorder ticks at the finest enabled resolution from {1m, 5m, 15m, 1h};
  coarser frames roll up from finer stored frames, never from live refetch.
- Failed provider reads write NOTHING (a gap stays a gap, never a flat line).
- Retention: 30-day TTL AND 50,000-row cap with oldest-first delete, enforced
  in the same write path (storage bounded by construction, not by ops habit).
- Read API `GET /api/curves/gex/{ticker}?resolution=&window=`: recorded rows
  with clocks; empty range returns unknown, never synthesized points.
- UI: curve pane inside the analytical range only, with its own clocks and
  the shared palette; never overlaid on live readings as one signal.

## Activation checklist (owner)

1. Set `FLOWW_GEX_CURVE_RECORDER=1` (default 0; no other value enables it).
2. Set ticker allowlist (default `SPY` only).
3. Confirm provider budget + storage budget in writing; confirm retention.
4. First 24h: verify row counts, gaps-stay-gaps, TTL/cap enforcement.
5. Only then reference curves in any research surface, with clocks shown.

## Test contract (to be built with the code, failing first)

Retention cap + TTL eviction; OFF-by-default (no writes without the flag);
empty range → unknown; clocks preserved end to end; rollup math pinned
against fixtures; no live-provider calls in tests (recorded fixtures only).
