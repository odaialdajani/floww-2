# Independent bounded chart/catalog backend review - 2026-09-26

Reviewed applied ROOT sources and latest20:29 integration checkpoint/report before authorized integration commits. Scope limited to catalog, historical price/nodes, provider pacing, scanner integration, documentation watcher and immediate route/server wiring. Existing report's live provider/browser outcomes were read as prior-thread claims, not independently repeated. No model/provider/account calls, server startup, order calls, held-out data or production storage access. No source edits. Owned files are this report and output/chart-catalog-review-Wwc77X/test_review.py.

## Confirmed findings

### Medium: shared cooldown does not learn from bars or catalog throttling

public_api_adapter.py:1120 fetch_bars_by_interval catches provider errors and returns None without _note_public_429; market_catalog.py:52 _fetch_instruments/get_catalog likewise propagate/catch errors without recording throttle feedback. The new request hook respects already-recorded cooldown but does not observe responses. Independent fake429 tests for BOTH bar and catalog paths returned unavailable/stale locally while immediate budget.check_request_allowed('api.public.com') still succeeded. A failed chart/catalog request therefore does not cool the shared account lane; other requests may continue hitting the limit.

Narrow fix: consistently record provider429 (including Retry-After where supported) at the shared real client response boundary, or at every new catch boundary; avoid counting the same response twice through existing adapter hooks. Add fake429 -> next unrelated request refusal test. Process-global pacing itself is shared: two default PublicBroker clients install the same pace_request function backed by one module pacer. Across-process/account-global enforcement is not proven and is already disclosed as a limit.

### Medium: scanner converts missing readings to zero and promotes incomplete evidence

public_scanner.py:279 unusual_rows_from_chain uses missing OI as0, missing IV as0, missing underlying spot as0; absent OI turns volume/OI into the volume itself. A synthetic returned contract with volume250, oi=None, iv=None and spot=None emitted one unusual row with OI0/IV0/spot0. Since250 is below BIG_VOL2500, the missing OI itself is what admits the apparent unusual ratio. Current adapter intentionally preserves absent OI/IV as None, so this downstream conversion defeats that truth.

Verified the same zeroing and ratio lines exist in HEAD: inherited defect exposed by the now broader scan, not newly introduced by catalog rotation. Narrow fix: preserve unknown fields, require observed valid OI for the ratio branch (known zero OI needs an explicit policy), allow independent absolute-volume admission only when its own condition is met, and ensure downstream row/alert conversion does not recreate zeros. Preserve unknown price/IV instead of drawing a fictitious0. Tests should cover missing OI below/above absolute-volume criterion separately.

### Low/medium: history declares prices available with zero valid candles

price_history.py:64 sets price_status available based on timestamps before build_history validates OHLC. A fake candle with valid14:00timestamp but high90/open100/low99/close101 yields frames=[], candles0, price_status available and a last_candle_at for that discarded candle. This is false success for malformed upstream price data. Narrow fix: derive availability and last_candle_at from validated frames, keep unavailable if none survive; do not report rejected candle timestamps as the last displayed candle.

## Verified bounded behavior

31 supplied root standalone tests passed independently. Four initial independent probes ran alongside them:35pass total (three defect reproductions plus a future/ticker/scope/age/no-mutation invariant). Added catalog429 and two-client shared-hook probes: all six independent probes passed. Passing defect probes confirm the defects, not readiness. Initial collection failed only because root and backend both define tests packages; --import-mode=importlib resolved that isolation issue.

Commands used backend .venv Python with --noconftest --import-mode=importlib, tests.offline_network, -o addopts=, DUCKDB_PATH=:memory:, and explicit PYTHONPATH backend. Root supplied tests: test_market_catalog, test_market_history_routes, test_market_integration, test_price_node_history, test_public_release_watch. Final standalone combined run35pass2existing on_event deprecation warnings2.02s; added independent-only run6pass1.56s. No live app lifecycle started: route TestClients were not entered as startup contexts.

- Catalog filtering/paging retains provider symbols, distinguishes stale/unavailable and option-enabled list; no silent featured-universe fallback. Completeness is explicitly provider catalog, not exchange completeness. Full real universe traversal was not repeated.
- History queries use bound ticker/time values; join requires matching ticker, chosen saved scope, valid observation/receipt time, available_at=max(observation,receipt), and <=900second observation age. Independent synthetic late/future/other-ticker input yielded [no nodes, correct saved node, age-expired gap], ignored unavailable future scope and left inputs unchanged. Stored market nodes are shared market history, not owner-specific research; no personal/account content was seen in these rows. This is not proof of any private-history authorization.
- Rotation distinguishes attempted/failed/never-scanned/fresh and clears expired payloads; failed scans retain prior timestamps, and existing tests cover cooldown cursor preservation and queued sweeps not holding outer request slots. Sixty-second freshness describes saved/request slices, not guaranteed source quote recency or whole-universe freshness. Two-expiry/60row limits remain explicit.
- Pacing is one in-process default-client request hook,8/sec, with cooldown checks before and after waiting. Custom injected clients can omit it (tests deliberately inject clients). Multi-process coordination is absent; external account consumers remain out of scope.
- Documentation watcher fetches only public.com documentation under validated/api/docs paths, follows no redirects, reads text without running scripts, compares a reviewed baseline and sets automatic_activation false. Its startup/shutdown handlers are attached via the mounted router; current server uses on_event handlers without custom lifespan. No new release can activate orders or arbitrary capabilities from this code. Live scheduler timing was not executed.

## Exact reviewed SHA-256 scope

- backend/routes/market_catalog.py: 7da6fcec76de1174706d3fbaa01f0a356c16f5dc72e8a278d49ded8dbb748aa6
- backend/routes/price_history.py: 87849f517889da72ab930a6574b61a26939f26cb920a068291504b9228dd3e8e
- backend/routes/flowseeker.py: 7a2749b7b59304b0fe98d5f0572cfeeb05b0a187130c8bc8351a9c107fea41fe
- backend/routes/market_data.py: 4dff6c4549e12ad040580dce4d55eaa740da2d16d7664d233d5436e4a520bd5e
- backend/server.py: 6999643ab995d03b20885dfdd3f35219d40eca2a7c6cf8cdc244705cc8e0422d
- backend/services/market_catalog.py: 3723f7c8d87dd8c0e249486ccf6d7b506eb721e0a3a71f4b3666f7598e99d055
- backend/services/price_node_history.py: d46a881f5a7967e1662a658ba9789a67c72c4d1108ad7308bc57f1c5def317ac
- backend/services/public_release_watch.py: fd9ca1484f7914e7c00addf69cc6049028551beb390e174b274444ebb77013c8
- backend/services/public_request_pacer.py: 0347e2a0832ecd1521b4c75668a5f1ad3fc9172220e5e30be5e57188081e7342
- backend/services/public_api.py: 2266ea6aef6a5b34471186e0efa9972a93f39a1f33962d83036192b48732265f
- backend/services/public_api_adapter.py: eaf81c1020d0b8ab84fb5a691e8728247553c9fcac739830df1cc1de6ae6d351
- backend/services/public_budget.py: a61880764b373126ca94ddf2ff0ad49e2c23841fdc2a48add5f23f6c41f0f147
- backend/services/public_scanner.py: d20d6b97dbd00bab76e82f95ed517f1965990e6d392b4b9b4310157dd48ac800

Limits: this is a bounded backend review, not a full application/frontend audit, provider entitlement check, financial-model certification or live full-market pass. No broader78-backend claim is independently repeated here. Three findings above remain open at these hashes; integration should retain them as explicit work rather than declare all functionality complete.

## Independent repair closure - 21:22 UTC

Parent repaired the three findings and connected null-handling family. No reviewer production edits. New owned scratch test_closure.py has16 direct offline cases; combined with current supplied root tests yields **48passed,2existing on_event deprecation warnings,2.13s**, exit0. Same hidden backend Python/--noconftest/--import-mode=importlib/tests.offline_network/:memory: execution constraints as above.

- Actual PublicBroker with real httpx.MockTransport exercised bars, catalog, accounts and auth429s (fake credentials only). Each retained caller response hook, recorded cooldown exactly once even after adapter/helper fallback, and blocked subsequent shared-lane admission. Malformed/missing-zone/past-date/numeric/NaN/infinite Retry-After variants were handled without dropping the cooldown. NonPublichost was ignored, and a second shorter wait did not shorten an active long wait. The response hook covers supplied clients; supplied clients still own their request-hook policy, whereas default clients install shared pacing.
- Actual _record_scan_baseline with an isolated in-memory update sink persisted knownOI0 and500 but never created the absent-OI entry. This validates emitted save operations without a production Mongo connection.
- Actual journal_store init/bookmark/update functions ran against an independent native DuckDB memory connection. Missing entry/current OI and spot persisted as SQLNULL; state wasUNKNOWN and profit wasNone. Known priorOI followed by missing currentOI stayedUNKNOWN; known priorOI followed by observed0 correctly reachedEXITED. These cases distinguish missing from measured zero.
- Actual scanner -> flow_alerts.norm_rows preserved OI/IV/spotNone and ratioNone for an independently eligible3000volume row, with no inferredBUY side;250volume with missingOI was excluded. Parent separately owns the frontend and broader alert-format tests; this pass did not start the full app or a browser.
- Actual price-history route with mocked bar source returned unavailable for invalid-only candles and did not query saved nodes. In mixed valid/invalid input, only the valid candle determined last_candle_at and storage query end.

Exact closure SHA256 values (checked unchanged before/after final run):

- backend/routes/market_catalog.py: 7da6fcec76de1174706d3fbaa01f0a356c16f5dc72e8a278d49ded8dbb748aa6
- backend/routes/price_history.py: d34bd9ba7a09656b845cf8f5d05032303e6ae2af7ea10c0764ce88103c2d7921
- backend/routes/flowseeker.py: e54e92858dbbf33f8337bd4f395e768e1a56f6e565f901eae9297715314ef55b
- backend/routes/market_data.py: 4dff6c4549e12ad040580dce4d55eaa740da2d16d7664d233d5436e4a520bd5e
- backend/server.py: 6999643ab995d03b20885dfdd3f35219d40eca2a7c6cf8cdc244705cc8e0422d
- backend/services/market_catalog.py: 85b84ad07697a53d35b7aa564dbd60df35d8d83045c4335b1c75feb8fbfe3fed
- backend/services/price_node_history.py: d46a881f5a7967e1662a658ba9789a67c72c4d1108ad7308bc57f1c5def317ac
- backend/services/public_release_watch.py: fd9ca1484f7914e7c00addf69cc6049028551beb390e174b274444ebb77013c8
- backend/services/public_request_pacer.py: 0170c49660a81c02b1e902a35de155f9e101eb7ddbda353f2f6271ef1cfe6aff
- backend/services/public_api.py: e470110e6cb4b6ab5b78230708d5f38b1e89f63297a522fc9e1633e582b7523c
- backend/services/public_api_adapter.py: 5b5117b51b96c9551a12527ea033f14e022a7a89d8123376fb3d1793ebd7c085
- backend/services/public_budget.py: a9973850c78cec0ee462bf48a06549d73ff36c88d10856de8582cc66d716575f
- backend/services/public_scanner.py: 2512e6f65a6f07e731241cf7a6eb752227468bea9a968d36cab6c867652308e4
- backend/services/flow_alerts.py: e9012771ea2b1129952d0eb9d0b3367877006df4bbfaea539c1481d1b6fcf2fe
- backend/services/journal_store.py: 2914ab606fb44122cecc1341f578ab5358e4c08949e3ee867b3a6c2429880efd

Bounded closure verdict: the three originally reproduced backend defects are closed at these hashes for the tested paths. No new blocking finding in the requested repair scope. Earlier evidence remains in this report as the before-state; this does not certify broader model correctness, live account-wide throughput, exhaustive market coverage, all frontend displays, or the full backend suite.

## Narrow measured-zero wording follow-up - 21:31 UTC

Read-only review requested by parent; no production edits. Direct isolated calls confirmed build_context with observed oi=0 and volume=3000 says "open interest unavailable". Parent's proposed "0 open interest (volume/OI unavailable)" is accurate: the observed reading remains known while division by zero is unavailable.

One matching wording defect remains in repaired journal_store.whale_state: entry_oi=0 with observed current oi=0 or50 and positive dte returns UNKNOWN with "Open interest unavailable; position change unknown". UNKNOWN is appropriate without a positive baseline for the relative change, but the reason should say the initial observed reading was zero rather than missing. Direct calls reproduced both cases. Recommend separate missing-reading and zero-baseline reason branches; no state logic change required.

No further actual-OI-zero collapse found in the bounded repaired paths: scanner row, norm_rows, daily baseline save and whale stored entry/current readings preserve observed0. The positive-denominator ratio guard is intentional. The OI-addition alert skips current0, which cannot meet its positive-addition condition; this is not lost valid positive-addition evidence. Price and IV zero handling are separate validity rules, not additional findings in this narrow OI-wording review. Broader unrelated routes were not reopened.

## Measured-zero wording closure - 21:34 UTC

Independent direct assertions pass for observed0 alert summary, zero initial/current0 whale state, zero initial/current50, zero initial/missing current, missing initial/current0, and positive initial/current0. Summary now says "0 open interest (volume/OI unavailable)". Zero initial observation returns UNKNOWN with the explicit zero-initial reason; missing readings retain unavailable reason; observed positive-to-zero remains EXITED. No production edits by reviewer.

Read new test_measured_zero_is_not_described_as_missing and adjusted zero-basis test: both assert the intended wording and UNKNOWN behavior. Read repaired adapter regression: status-only fake response is explicitly ignored because host cannot be established, followed by real httpx.Request/Response against api.public.com proving429 recorded. This fixture correction matches the real response-boundary contract; it does not loosen production host gating.

Exact final narrow-review SHA256:
- backend/services/flow_alerts.py: e00cb1debdaf562020ee6b19302c54a45fc25fb18fef5cdb53d16ec6604807ac
- backend/services/journal_store.py: 116c0346a712580f244d5655cd553d629aeaec704c8eacfb2d5dae1a524b841e
- backend/tests/services/test_scan_missing_readings.py: 1bb7cedfdc2087738e13d887742a70dfa2ab0d216de1b2a4789a35ff9e373313
- backend/tests/services/test_whale_tracker.py: ac79b089604d4ad02b9780467a609ff9719429c484a2731a2758a3b00e4c1167
- backend/tests/services/test_public_api_adapter_regressions.py: 81e955a088f21bc410ea548fe9457554b6dd2e28dd28d7e42bc038e8533ee676

Both21:31 wording findings closed. Parent reports69affected tests and Ruff passing; these were not independently repeated in this narrow follow-up. Parent's full backend rerun is pending and remains outside this independent bounded evidence.
