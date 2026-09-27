# Fresh alert evidence readiness - independent bounded review, 2026-09-26 22:07 UTC

## Verdict

NOT READY for real freshly observed directional-alert positive cases or confirmed live-store absence from the inspected artifacts. Ready for explicitly DERIVED controlled persistence/read cases with unknown source freshness, and controlled empty/unavailable-store cases. No valid timestamp propagation repair is justified by this evidence: actual recorded option-volume observation timestamps are absent upstream.

No production sources, stores, configuration, running process or other thread changed. No server startup, model request or provider request. Existing DuckDB files were opened read_only=True solely for table metadata. Derived probe used only a new process-local :memory: engine and blocked socket connections. No credentials were printed; only presence of DUCKDB_PATH was checked.

## Store and capture evidence

- backend/.env exists but has no DUCKDB_PATH key. Root .env is absent. This command process has no DUCKDB_PATH. These facts do NOT prove the already-running server's environment. Source _open_shared_db defaults to :memory:, falls back to memory for unusable configured paths, and server read_alerts calls stored_research_alerts(duckdb_engine.query_strict,ticker). Existing live-process memory was not inspected. Live ledger contents and absence remain UNKNOWN.
- Recursive workspace file inventory excluding dependencies found four DuckDB files; all were checked read-only. data/research_kg.duckdb (23867392bytes, research graph tables), data/journal.duckdb (1847296bytes, journal/chain/whale tables), backend/data/gflows.duckdb (1060864bytes, gflows_greeks), .planning/eval/journal-audit-20260911-2059/journal.duckdb (1323008bytes, audit journal tables). None has flow_alerts_daily. This establishes no usable alert table in those files, NOT a successful empty production-alert query. Audit journal WAL also exists; no attempt made to change it.
- Frozen v2 DIA/IWM/QQQ/SPY sources and supplemental AAPL explicitly bind no alert facts and disclaim actual alert-store contents. The v2 runner raises on alert read instead of asserting empty. All five raw chains have event_time=null. Contract counts are500/442/814/700/252. Every contract has last_event_time, bid_event_time, ask_event_time and oi_source; none has a volume observation timestamp. Spot event time and fetch time are present but are not option-volume observation time.
- Frozen v1 SPY does contain a saved actual research-turn derivative: seven signed values [0.7,0.54,0.62,0.54,-0.68,-0.68,-0.67], mean0.05285714285714279, old fact event_time2026-09-11T20:52:22Z. No raw chain or raw stored-alert rows accompany SPY there. Its preserved independent review explicitly identifies freshness as an earlier pre-correction source defect. This historical derivative must not become fresh current acceptance evidence.
- Additional inspected saved captures public-oauth-live-20260911-2030.json, public-solstice-real-20260911-2146.json, public-solstice-selected-real-20260911-2316.json and public-ui-real-20260911-2117.json contained no stored-alert facts. Some historical snapshots say alerts_status=ok; that label alone does not prove a real successful store query or confirmed absence.

## Source path and timestamp truth

public_api_adapter fetch_chain sets event_time=None explicitly and distinguishes quote-side timestamps from whole-chain OI/Greeks observations. Scanner slice retains chain event_time when available; unusual_rows_from_chain produces volume/OI/price rows and quote extras, not verified volume observation provenance. flow_alerts calculation/persist functions do not attach source_event_time/source_quality. stored_research_alerts uses producer context source_event_time ONLY with source_quality=ok; otherwise asof_ts becomesNone, while computed_at preserves creation time. ResearchReads requires the observation within900seconds and coherent directional readings within120seconds. Therefore these captured chains have no verified flow observation to propagate. Do not replace it with stock spot time, contract last/bid/ask time, fetch time, evaluation clock or alert creation time. Such enrichment would be synthetic, not repaired real evidence.

## Independent controlled proof

output/alert-readiness-20260926/derived_probe.py ran unchanged captured chains through actual unusual_rows_from_chain -> norm_rows -> apply_quote_truth -> eval_institutional(default rules) -> init_flow_alert_tables/persist_alerts -> stored_research_alerts. Date was frozen to each captured fetch time only for deterministic calculation and7day query window; no observation timestamp was supplied or changed. Optional historical baselines/regimes/calibration and desk pass were NOT supplied, so this is not a reproduction of the complete historical live decision path.

DIA19scan rows ->6generated/persisted/read alerts; IWM45->20; QQQ60->61; SPY60->61. All148 stored reads returned unknown source freshness. Results are saved in output/alert-readiness-20260926/derived-probe-result.json. This proves the production save/read functions can support a DERIVED, controlled legacy-alert fixture without new calls. It does not prove these alerts fired live, nor their source freshness, nor historical production absence.

## Honest bounded input recipe

1. Keep original capture bytes/hashes unchanged. Declare new questions, cases and clocks before grading; do not reuse old answer outputs as new source truth.
2. Use a new isolated store with real init/persist/read functions. Explicitly label recalculated alerts DERIVED FROM RECORDED PUBLIC CHAINS, with omitted optional live inputs listed. Keep source provenance unavailable exactly as actual inputs require. Expected outcome is unknown fresh direction, not positive fresh agreement.
3. Separately initialize an empty fixture store and run the real strict reader for a declared ticker/date window. Successful empty means only that controlled fixture query was empty. A missing table/query error must remain unavailable. Never describe either as verified production absence.
4. Positive fresh-alert behavior requires either an independently recorded alert source with verifiable underlying flow observation timestamp, or a separately labeled SYNTHETIC contract test. The inspected real sources do not provide that observation. Adding provenance to these fixtures is not a production defect fix and cannot count as real positive evidence.

## Inspected source and original capture SHA256

- backend/services/duckdb_engine.py: 257fa925b5a85a611f98b26239c5f0c0d40ef932907d42eed34e85b726d44a23
- backend/services/research_data_seam.py: 8848816575280ca122c772340e868d0c2beae4e1936427061c3c0b18ffaf7e6e
- backend/services/public_api_adapter.py: 5b5117b51b96c9551a12527ea033f14e022a7a89d8123376fb3d1793ebd7c085
- backend/services/public_scanner.py: 2512e6f65a6f07e731241cf7a6eb752227468bea9a968d36cab6c867652308e4
- backend/services/flow_alerts.py: e00cb1debdaf562020ee6b19302c54a45fc25fb18fef5cdb53d16ec6604807ac
- backend/services/agent/reads.py: 62f64457e3e53a3863b4800906eb6d1221fedf252f5cc6e6a7a23d4710847e60
- backend/routes/flowseeker.py: e54e92858dbbf33f8337bd4f395e768e1a56f6e565f901eae9297715314ef55b
- backend/server.py: 6999643ab995d03b20885dfdd3f35219d40eca2a7c6cf8cdc244705cc8e0422d
- backend/scripts/oauth_heldout_v2.py: 0aa977e3e9db2350e2acb6baaa48835eda8286f78be334e60beaf32b9c9597c4
- backend/scripts/oauth_heldout_eval.py: d16760abbc0bc163c46e95434b06a8b1084380c0b7fee0f20d326221ee7864eb
- .planning/eval/oauth-heldout-v2-sources.json: ad63bcfc86dbd515516382f61736e83e504fc39b5d6507cb4f9f1facbc518f3a
- .planning/eval/oauth-heldout-v2-aapl-source.json: 05d311d2b835445c0c954d42ea82b7c560595f0a1f6a6cb9edc07c8a9edc0f72
- .planning/eval/oauth-heldout-v2-inputs.json: 00eef687dd33d7bc325fb2e9bd34830445f9357fb8d51546a5ae88a6d28c98d2
- .planning/eval/oauth-heldout-v2-maps.json: a521aae276706242daa1c3906bd82b0b514adbdfca32a3586234af112df2acb4
- .planning/eval/oauth-heldout-v1-sources.json: e02d91ed159248f4cd7261718da03c4d2d6505573f1590ccbbdb79e8e898c5df
- .planning/eval/oauth-heldout-v1-independent-review.md: 0d7bd3a2473558ee12a5eceea39e98e978982ea8a344726ce1cf82bee08c7755
- .planning/eval/public-oauth-live-20260911-2030.json: 879409886e1720c1687285e8d0c2972a2921009daef947d01779c7de430898b8
- .planning/eval/public-solstice-real-20260911-2146.json: 9833e4dbc7a12fff34ce29449c23bb75e521aeb9f72ff0664b6bb29e6dda9f11
- .planning/eval/public-solstice-selected-real-20260911-2316.json: 81f73b81e4d98ae706cef3a6840d16a6ce329ce5ef7416e815316228a0442600
- .planning/eval/public-ui-real-20260911-2117.json: 395369744198454bd2a599eaf95ed5f39b8ce386ae226ad099ca6c9bd7178335
