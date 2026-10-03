# range-analytics.v1 — Cline producer contract (R18-C1)

Prepared 2026-10-03 in lane `cline/r18-analytics` (worktree
`.worktrees/cline-c1-r18`), base `22df6fe67463acc8a41283804e710d07dff105bd`
(PR105 combined head). Producer: Cline. Consumer owner: Zed (range consumer
Z1 replays/renders this envelope; field mismatch is a REFUSAL, not a hidden
edit on either lane).

**Additive.** `coverage-read.v1` listing routes are unchanged — a listing is
not a map. The existing `dte le=30` display envelope on `/heatmap` is
unchanged. Nothing here admits execution.

## Route and persisted identity

- `GET /api/heatmap/{ticker}/range-analytics?min_dte=14&max_dte=60[&as_of=YYYY-MM-DD][&persist=false]`
  (additive route on the already-mounted `market_data` router — no server.py
  change required; Zed owns any further mounting decisions).
- `as_of` must equal the owning America/New_York date or the request refuses
  `SESSION_DATE_MISMATCH` — current quotes/Greeks never recreate history.
- `persist=true` records the admitted envelope via
  `heatmap_history.record_range_envelope` (namespace
  `range_analytics_envelopes_v1`); `replay_range_envelope(record_id)` restores
  the exact stored display. Default is read-only (`persist=false`).

## Envelope

`version` = `range-analytics.v1`; `status` ∈ `ok | partial | refused`;
`refusals[]` machine codes; `symbol`; `record_id` (`rga1-<digest[:24]>`) +
`content_digest` bind symbol/window/owning NY date/received_at/axes/cells —
another ticker/date/window/basis cannot reuse a record.

- `query`: `min_dte`, `max_dte`, `as_of_ny` (owning NY session date).
- `axes`: `expiries` `[{expiry, dte}]` (admitted, DTE-sorted) and
  `strike_keys` (ordered union). Dense `cells[expiry][strike]` — unavailable
  values are explicit `null`, never absent or zero.
- `grids`: `raw_oi` (gex_net_v1, OI, display S², BS gamma),
  `delta_weighted` (dadgex_net_v1, OI_DELTA_WEIGHTED, vendor gamma),
  `volume` (volume_gamma_v1, VOLUME, vendor gamma),
  `window` (window_dadgex_v1, VOLUME_WINDOW — UNAVAILABLE with
  `HISTORY_NOT_YET_RECORDED` until a recorded baseline exists; never raw,
  never zero). Each section carries metric_id/basis/formula_version(gex.v2)/
  model/unit/status/reason/population counts (`usable`, `missing_delta`,
  `invalid_delta`, `invalid_mult`, `quarantined`, `invalid_type`).
- `clocks`: `received_at`, `fetched_at`, `chain_event_time` (Public supplies
  no whole-chain OI/Greeks timestamp → null), spot source/event/fetched
  clocks, bid/ask timestamp presence counts, per-contract OI effective dates.
- `coverage`: requested window, n_listed/admitted/returned, `skipped[]` with
  per-expiry reason, attempt/budget envelope, `complete` only when BOTH
  listing edges observed AND zero skips AND admitted == returned; otherwise
  `complete_reason` names the limit (never implied by a count cap).
- `provenance`: data_source, stale, adapter identity, Greeks sources;
  `synthetic` true for fixture-derived payloads.

Refusals: `REVERSED_WINDOW`, `WINDOW_OUT_OF_RANGE`, `SESSION_DATE_MISMATCH`,
`UNPARSEABLE_AS_OF`, `VENDOR_UNAVAILABLE` (HTTP 502), `CHAIN_UNAVAILABLE`,
`NO_ADMITTED_EXPIRY`, `NO_CONTRACTS`. Partiality reasons: `STALE_CACHE`,
`PARTIAL_COVERAGE`. A partial map is research-only, never execution-eligible.

## Frozen consumer fixtures (synthetic; digests = sha256 of file bytes)

| Fixture | sha256 | status |
|---|---|---|
| `docs/solstice/r18/fixtures/complete_v1.json` | `c5ca4b6107a6dd79a91b130e14ff15a38f3081dceedfd6c7c7a50b42dbe26b0f` | ok (`rga1-87fcea668dbcfc194e161130`) |
| `docs/solstice/r18/fixtures/partial_skipped_v1.json` | `b63650aa0d38a140e1da0e8c672a3e1bda5cb2798a0d9e161e0cd56dd29c62ba` | partial |
| `docs/solstice/r18/fixtures/refused_reversed_v1.json` | `0af9a715fb92c4776b0bd0b649e359a4120e3d5701d1564dce456e02209584b4` | refused |

Producer-side input fixtures (Zed may reuse):
`backend/tests/solstice/fixtures/range_analytics_v1/{listing,chain_complete}.json`.

Artifact *(Kimi K3 / Cline lane, isolated worktree cline-c1-r18)*.
