# Independent backend merge review - 2026-09-27

Final bounded verdict (19:55 UTC): PASS. All material findings raised in this review were corrected and independently rechecked. This verdict covers the reviewed merge boundaries, not the owner's separate full-suite result or live-provider behavior. Earlier pending statements below are chronological evidence and are superseded by the final closure.

Scope: read-only review of the resolved integration worktree, with one bounded pure-function adversarial probe. This report is the only file owned/edited by this reviewer. No network, provider, model, or order calls were made.

## Material finding sent to integration owner

At review time `compute_charm_grid_local` in `backend/services/gex_core.py` ignored explicit contract size and adjusted/nonstandard quarantine, despite neighboring vendor GEX and local VEX honoring those inputs. It returned `quarantined: 0` unconditionally.

Reproduction used the existing Python 3.11 environment with `DUCKDB_PATH=:memory:`. Input: spot 500; strike 500; expiry 2030-01-18; call; OI 100; charm 0.01; charm unit per_year.

- Standard contract returned 500.0.
- Explicit multiplier 10 returned 500.0, but the consistent dollar convention requires 50.0.
- Adjusted contract returned 500.0 with status ok and quarantined 0.
- Nonstandard contract returned the same unsupported result.

The owner accepted responsibility for correcting this finding. Until its correction is independently rechecked, this review does not clear the Charm merge.

Related compatibility note: OI input currently only reads `oi`, whereas adjacent vendor GEX accepts `open_interest` when `oi` is absent. This can remove previously available coverage for compatible caller inputs.

## Verified by current source inspection

- The chain response retains both incoming `gex_unit` and existing data/spot source, observation/fetch time, stale and cache-age fields.
- All four newly introduced lifecycle persistence functions use `guarded_connection`, sharing the same reentrant connection lock as other database operations.
- Wall restoration now compares the event state with the already chosen full/memory state; the original stale-full-state precedence issue is removed from the selection logic.
- Charm cells use string strike keys, explicit per-day/per-year vendor conversion, local Black-Scholes fallback with IV/time, canonical dollar scaling and option-type sign.
- Missing usable input on another row in the same Charm cell removes that cell rather than presenting a partial sum as complete.
- Charm uses volume weighting when the selected main exposure basis is volume, and replay serialization retains charm metadata.
- Public order submission retains authentication and the disabled-by-default live submission switch. Cancellation retains authentication while remaining available when new submissions are disabled.
- A targeted source search found no remaining Python imports of the removed Schwab streamer/data fallback/mock Schwab modules or references to the removed positions alias in backend/tests.

## Limits and coordination

This reviewer did not rerun the owner's broad checks. The initial default-Python probe failed before execution because scipy was unavailable; the reproduction above succeeded with the project's existing Python 3.11 environment. The owner separately reported and is resolving alert function shadowing, node-confluence compatibility, old cancellation expectations and test isolation issues. Those items are not cleared by this report.

## Additional requested review: mounted node confluence

This is an actual reachable path: `App.js` mounts `HeatseekerDashboard` for the skylit/Zenith page; that dashboard mounts `NodeConfluencePanel`; the panel requests the registered heatseeker `/node-confluence` route. The route supplies cumulative call/put option volume and persisted `flow_alerts_daily` observations to `node_brief`.

Material findings:

1. Cumulative call-versus-put volume becomes a signed research contribution. A pure-function probe with call volume 1000 and put volume 0 returned microstructure value 1.0, contribution +15.0 and total +15.0. The existing agreement service correctly keeps the final direction `insufficient_evidence`, which prevents a final bullish verdict, but the displayed signed total and green volume skew still falsely imply directional evidence. Option activity composition does not identify buyer/seller initiation.
2. The actual persisted alert contract includes separate `side`, `type` and `bias`. `side=BUY,type=put,bias=BEARISH` is counted as `call_side=1,direction_net=1`; bought puts are reversed by the incoming node flow calculation. SELL call/put cases have the corresponding flaw.
3. Snapshot alerts carry side FLOW and no directional bias. With any matching row, `_flow_skew` marks the dimension ok with value zero, upgrading unknown direction to known neutral. The screen calls these cumulative alert observations "prints", despite their existing source contract explicitly saying trade direction is unknown.
4. `_row_price` accepts premium or option price as an underlying strike. The price-before-strike issue is latent for the present persisted table because it has strike/est_entry/premium/under_price but no price column. A pure probe confirms a row with strike 500 and option price 2 is excluded from strike 500, while a premium-only 500 row is included. Missing-strike alerts must not be assigned by dollar premium.

Bounded recommendation: match only explicit contract strike; retain call/put activity as descriptive context without directional weight; mark flow direction unavailable unless the incoming row has appropriate observed trade evidence and an option-type-aware interpretation. Snapshot observations must stay unavailable for directional agreement and must not be called executed prints. This preserves the completed feature while respecting the existing research truth contract.

These issues were reported to the integration owner immediately. No source edits were made by this reviewer.

## Independent correction recheck - 19:54 UTC

Charm findings are now closed by direct pure-function execution: contract size 10 returns 50 instead of 500; adjusted/nonstandard inputs are excluded; the exclusion count is populated; open_interest-only inputs retain coverage; an explicitly invalid contract size remains unavailable. Five assertions passed. Call-heavy volume now yields no signed total, independently confirmed. Source inspection confirms saved-alert wording, strike-only matching, separate alert-bias interpretation and distinct synchronous/awaited alert broadcast functions sharing frame normalization.

Two persisted-record boundary issues remain at this checkpoint:

- The route filters `expiry`, but the actual table and raw `read_alert_feed` result use `exp`. A stored-row-shaped pure probe confirms a matching selected expiry is dropped.
- The direction guard reads `context`, but persisted rows use `context_json`. A stored-row-shaped fresh BUY/BEARISH alert whose context_json marks cumulative_snapshot returns direction_status ok. The snapshot provenance is therefore bypassed for contradictory stored side values.

Both findings were sent immediately to the owner. Requested fix is bounded to accepting the real persisted field names at the boundary and testing stored-row shapes. Review status remains pending those corrections; this is not a claim that the owner's whole suite passed.

## Final closure - 19:55 UTC

The route now accepts the persisted exp field, and direction provenance accepts context_json. Independent pure-function checks confirmed cumulative persisted context remains unavailable and a fresh declared bearish bought-put alert stays negative rather than becoming bullish.

Executed the actual corrected route test `test_real_stored_exp_column_is_used_for_selected_expiry` and service test `test_persisted_snapshot_context_stays_nondirectional` with the project's existing Python 3.11 environment and `DUCKDB_PATH=:memory:`. Result: 2 passed, 27 existing deprecation/collection warnings, exit 0. The route test uses in-process FastAPI with a stubbed chain and stored alert rows; no service startup or external provider call occurs.

No unresolved material finding remains from this review. No production source or test file was changed by this reviewer.
