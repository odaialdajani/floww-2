# range-analytics.v1 — Cline producer contract (R18, post-repair head)

Prepared 2026-10-03 in lane `cline/r18-analytics` (worktree
`.worktrees/cline-c1-r18`), base `22df6fe67463acc8a41283804e710d07dff105bd`
(PR105 combined head). Producer: Cline. Consumer owner: Zed (range consumer
Z1 replays/renders this envelope; field mismatch is a REFUSAL, not a hidden
edit on either lane).

**Additive.** `coverage-read.v1` listing routes are unchanged — a listing is
not a map. The existing `dte le=30` display envelope on `/heatmap` is
unchanged. Nothing here admits execution.

## Content integrity (R18-C6) — `content_schema: rga-content.v2`

The canonical evidence content digest now covers the COMPLETE payload:
version, status, refusals, symbol, query, axes, grids (metric identity,
units, model, populations, dense cells), metric_registry, clocks, coverage,
provenance, grounding and synthetic. Explicitly EXCLUDED transport/storage
fields: `record_id`, `content_digest`, `persistence`. The digest is
recomputed on WRITE and on REPLAY; supplied digests are never trusted.
Typed refusals: `INCOMPATIBLE_CONTENT_SCHEMA`, `DIGEST_MISMATCH`,
`RECORD_ID_MISMATCH`, `ROW_HEADER_MISMATCH`, `STORED_DIGEST_MISMATCH`,
`STORED_RECORD_CORRUPT`, `IDENTITY_CONFLICT`, `CORRUPT_PAYLOAD`,
`STORE_READ_FAILED`. `record_id = "rga1-" + digest[:24]`.

Pre-repair v1 digests (recorded at head e6d35745) are SUPERSEDED by
rga-content.v2 and listed here for provenance only:
`c5ca4b61…` (complete), `b63650aa…` (partial), `0af9a715…` (refused,
unchanged — refusal envelopes carry no evidence content).

## Population truth (R18-C7)

Each grid section carries `population` from the REGISTERED aggregates
(`domain.exposure_metrics` ExposureResult): genuine raw `input_contracts`
and per-reason exclusions (`missing_oi`, `missing_delta`, `invalid`,
`invalid_delta`, `missing_volume`), plus kernel-reported `quarantined` /
`invalid_mult` / `invalid_type`. A finite cell or an overall ok map NEVER
admits a metric: `metric_admitted` is true only for a clean `ok` section,
and `metrics.{admitted,partial,unavailable}` summarize per-surface truth.

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

## Frozen consumer fixtures (synthetic; sha256 of file bytes, rga-content.v2)

| Fixture | sha256 | status |
|---|---|---|
| `complete_v1.json` | `fa23ac1bdbce488163ed81d3f81dbe9bd75acb459ea6512420da21a1ae2e6909` | ok |
| `partial_skipped_v1.json` | `217172922332a807520e3e0b6471441c0ff93e2c6fd468a7bc354d8a80a5a92a` | partial |
| `refused_reversed_v1.json` | `0af9a715fb92c4776b0bd0b649e359a4120e3d5701d1564dce456e02209584b4` | refused |
| `record_index_v1.json` | `2259e2f5b4b38b5dcf4de87ab17c90a1c86c048f27af5cafc47ebcb0e3ad7232` | ok |
| `record_replay_v1.json` | `fc22360558e9bc1089fc3029540687154c5f2fc3bc68cbf6fdea0e542710df7e` | ok |

(complete envelope record_id `rga1-54f0a823b635f938492cbfb3`.)

Artifact *(Kimi K3 / Cline lane, isolated worktree cline-c1-r18)*.

