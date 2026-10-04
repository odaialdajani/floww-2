# range-analytics.v1 — Cline producer contract (R18, post-repair head)

Prepared 2026-10-03 in lane `cline/r18-analytics` (worktree
`.worktrees/cline-c1-r18`), base `22df6fe67463acc8a41283804e710d07dff105bd`
(PR105 combined head). Producer: Cline. Consumer owner: Zed (range consumer
Z1 replays/renders this envelope; field mismatch is a REFUSAL, not a hidden
edit on either lane).

**Additive.** `coverage-read.v1` listing routes are unchanged — a listing is
not a map. The existing `dte le=30` display envelope on `/heatmap` is
unchanged. Nothing here admits execution.

## Content integrity (R18-C6 + R18-C11) — `content_schema: rga-content.v3`

The canonical evidence content digest covers the COMPLETE payload:
version, status, refusals, symbol, query, axes, grids (metric identity,
units, model, populations, dense cells), metric_registry, the derived
`metrics.{admitted,partial,unavailable}` summary, clocks, coverage,
provenance, grounding and synthetic. Explicitly EXCLUDED transport/storage
fields: `record_id`, `content_digest`, `persistence`. The digest is
recomputed on WRITE and on REPLAY; supplied digests are never trusted.
Typed refusals: `INCOMPATIBLE_CONTENT_SCHEMA`, `DIGEST_MISMATCH`,
`RECORD_ID_MISMATCH`, `ROW_HEADER_MISMATCH`, `STORED_DIGEST_MISMATCH`,
`STORED_RECORD_CORRUPT`, `IDENTITY_INCOMPLETE`, `IDENTITY_CONFLICT`,
`CORRUPT_PAYLOAD`, `STORE_READ_FAILED`. `record_id = "rga1-" + digest[:24]`.

**rga-content.v3 (R18-C11, consumer review):** the top-level `metrics`
summary joined the digest subject — under v2 a tampered summary (a partial
metric relabeled admitted) kept a valid digest. v2 payloads are refused
`INCOMPATIBLE_CONTENT_SCHEMA`, never silently upgraded.

**Shared row binding (R18-C11):** ONE exception-safe validator
(`services.heatmap_history.bind_range_row`) serves the duplicate-write
check, replay retrieval and the read-only index, so a row's verdict can
never differ between paths. It binds the row's record_id, ticker, window
(a NULL window is a typed refusal, never a TypeError), as-of date, status,
received-at clock AND stored digest column to the canonical payload — a
fully self-consistent forgery stored under someone else's row refuses, and
the replay wrapper only echoes bound payload values.

Superseded digest generations (provenance only, never replayable):
v2-at-c085f8fb `54f0a823…` (complete), `095a3553…` (partial);
pre-repair v1-at-e6d35745 `c5ca4b61…` (complete), `b63650aa…` (partial);
`0af9a715…` (refused envelope — refusal envelopes carry no content).

## Population truth (R18-C7 + R18-C11)

Each grid section carries a kernel-CORRESPONDING `population`: the counters
of the kernel that actually produced its cells. `delta_weighted` and
`volume` report their registered kernels' own counters (`usable`,
`missing_delta`, `invalid_delta`, `invalid_mult`, `quarantined`,
`invalid_type`; volume's silently-skipped missing volume is mirrored as
`missing_volume`). The `raw_oi` Black-Scholes surface reports a mirror of
`gex_core.compute_gex_grid`'s exact per-contract filter order
(`oi/iv/t_missing_or_nonpositive`, `strike_invalid`, `expiry_missing`,
`type_unknown`, `gamma_nonpositive`) — vendor gamma is NOT an input to
that kernel, so a missing-IV contract is an EXCLUSION (never "admitted")
and absent vendor gamma cannot zero `usable` against finite BS cells.
`input_contracts` stays the raw contract count; unknown counts remain
unknown. A finite cell or an overall ok map NEVER admits a metric:
`metric_admitted` is true only for a clean `ok` section, and
`metrics.{admitted,partial,unavailable}` summarize per-surface truth.

## Route and persisted identity

- Producer: `GET /api/heatmap/{ticker}/range-analytics?min_dte=14&max_dte=60[&as_of=YYYY-MM-DD][&persist=false]`
  (additive route on the already-mounted `market_data` router).
- **Capture guard (R18-C10):** `persist=true` writes only under the explicit
  capture policy — env `FLOWW_RANGE_CAPTURE_ENABLED` AND authenticated
  `X-API-Key`. Otherwise 503 `CAPTURE_DISABLED` / 401. Default reads never
  write. Real capture remains an operator commissioning step.
- **Replay API (R18-C9, read-only, `range-records.v1`):**
  `GET /api/solstice/price-paths/range-records` (identity-bound filters
  `ticker/min_dte/max_dte/as_of/status`, bounded `limit≤200&offset`, per-row
  `integrity` verdict) and `GET /api/solstice/price-paths/range-records/{record_id}`
  (404 unknown identity, 422 typed integrity refusal). Never fetches current
  chains; legacy snapshot replay routes are untouched.
- `as_of` must equal the owning America/New_York date or the request refuses
  `SESSION_DATE_MISMATCH`.
- Required budget-debit failure (malformed/unavailable budget service)
  refuses with ZERO provider calls at all three adapter fetch seams (R18-C5).
  **R18-C11:** admission now PRECEDES broker init — a cold `_get_broker()`
  (vendor auth/accounts) can no longer run before a denied debit; only the
  warm-singleton identity-bound cache serve stays debit-free.

## Grounding (R18-C10)

`grounding.record_query_identity` is the stable Zed-facing resolver identity
{symbol, min_dte, max_dte, as_of_ny}; `grounding.contract_population` gives
per-expiry contract counts and `contracts_digest` binds the captured
OSI/strike/type/quote-clock set. `grounding.contract_drafting.admitted` is
FALSE (`RANGE_RECORD_REFERENCE_ONLY`) — records are research evidence, not a
quote service for executable drafting.

## Envelope (unchanged surface keys, now digest-covered)

`version` = `range-analytics.v1`; `status` ∈ `ok | partial | refused`;
`refusals[]`; `symbol`; `record_id` + `content_digest` + `content_schema`;
`query`; `axes` (admitted expiries + ordered strike_keys; dense cells with
explicit nulls); `grids` (raw_oi gex_net_v1/OI/BS-gamma, delta_weighted
dadgex_net_v1/OI_DELTA_WEIGHTED, volume volume_gamma_v1/VOLUME, window
window_dadgex_v1/VOLUME_WINDOW — unavailable until a recorded baseline);
`metric_registry`; `clocks`; `coverage`; `provenance`; `grounding`;
`synthetic`.

## Frozen consumer fixtures (synthetic; sha256 of file bytes, rga-content.v3)

| Fixture | sha256 | status |
|---|---|---|
| `complete_v1.json` | `1376d7e8b2651b2bcc5e0fc7adcabe36dc17488cfe36a10021871dad2c8e7f24` | ok |
| `partial_skipped_v1.json` | `f478c49184cb802853f8fe7e15ed99427da9e0cb902bd12db907a4baa3507d21` | partial |
| `refused_reversed_v1.json` | `0af9a715fb92c4776b0bd0b649e359a4120e3d5701d1564dce456e02209584b4` | refused |
| `record_index_v1.json` | `b01666c327ce229291ce662fe7a7f9fd3f3913ca2427613a8fcf49c608cf93c9` | ok |
| `record_replay_v1.json` | `899a554a7d4add02e3a15fe8d67bc1fa023e90ec8a1227e318ee548ac19f53e0` | ok (FULL envelope) |
| `record_replay_partial_v1.json` | `ff6d36e5bfb43e42ac8e91a51f698fc9f9d838ef816335aaa1f6d2e1b89ab1f4` | ok (partial envelope) |
| `record_replay_refused_v1.json` | `39a2128a0737f3eb2ecdfd9d46f3b25d670d22d8f200d05c623c70a883bf263f` | refused (NO_RECORD) |

R18-C11: `record_replay_v1.json` now carries `version` + the COMPLETE bound
envelope (the earlier fixture was metadata-only, so the consumer could not
cross-check wrapper vs payload); `record_replay_partial_v1.json` (full
partial envelope: recorded skip + invalid-delta exclusion) and
`record_replay_refused_v1.json` (typed 404 NO_RECORD route body) complete
the ok/partial/refusal response set. Replay fixtures are in the exact
mounted-route shape `{"version": "range-records.v1", "status": …, **replay}`.

(complete envelope record_id `rga1-3ae0977fcd69e869ac8e3a11`,
content digest `3ae0977fcd69e869ac8e3a117536920f966c5ba57fe8f4f33c8094e36a4c0bb6`;
partial record_id `rga1-2213b262ffec0a9c11ac0ab3`.)

Artifact *(Kimi K3 / Cline lane, isolated worktree cline-c1-r18)*.

