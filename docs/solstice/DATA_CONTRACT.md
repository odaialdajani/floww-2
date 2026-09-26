# Solstice DATA_CONTRACT — HeatmapSnapshotV2 (schema 2)

One immutable snapshot per analytical update; grid/sidebar/inspector/alerts/AI/replay share identity.

- schemaVersion/queryKey/snapshotId (content-addressed)
- instrument {displaySymbol, currency} (+ quote/chain types where resolved)
- scope {expiries, metric, basis, signConvention, formulaVersion}
- times {receivedAt, calculatedAt, sourceMinAt/MaxAt, oiEffectiveDate} — fresh local build never resets upstream age
- quality {state usable|partial|stale|unavailable, reasonCodes, setupEligible, executionEligible=false, tradeSideCapability=none}
- contracts[]: OSI, strike_exact (Decimal string), type, multiplier/deliverable, expiry/T/T_floored/T_model, bid/ask/last + bid/ask/last_timestamp (null=unknown), volume/OI (null=unknown), Greeks + greeks_source, received_at, provider, exposure_basis
- cells[]/strikeProfiles[]/walls[]/interactions[]/scenarios[] (walls carry wall_id stable across refreshes)

Unknown/no-data/no-candidate are valid. Provider switch resets baselines and invalidates continuity-dependent scenarios.
