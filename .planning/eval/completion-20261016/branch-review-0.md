# Branch review 0 — semantic historical reconciliation

Candidate: `0bbdd711859e9a2fea043c8b79bf25e9728319bc` · tree `bb74fd8a340b9b7771513d5364b852c802d4b912`.

**66/66 assigned SHA rows reviewed exactly once.** Source/history-only findings; no source files, branches, worktrees, stores or services changed. No test suite or live endpoint was executed. This is not original-obligation acceptance.

## Outcome

| Disposition | Rows |
|---|---:|
| superseded | 20 |
| retained | 31 |
| missing-actionable | 6 |
| conflicting-owner-protected | 2 |
| unverifiable | 7 |

## Real missing behavior — parent implementation handoff

1. **BR0-MONITOR — incorrect per-provider age gauges.** `backend/services/meta_observability.py:481-494` updates success-rate gauges in the loop but age only after the loop. AST confirms `.set` at line 492 is a sibling, not a child, of `For@481`. Only the last provider age updates; empty monitor hits a swallowed unbound local. Scheduler and `routes/data_providers.py` invoke it. Move the age update into the loop; test two providers and empty state. Keep JSON `None` and Prometheus `+inf` distinct. Existing test at `test_provider_monitoring.py:356` checks only one success-rate series. Health JSON fix itself survives.

2. **BR0-SURFACES — OI/DUO/DVO are not shipped.** No corresponding producer functions or matrix keys exist anywhere under candidate `backend`/`frontend/src`. `_display_surfaces`, snapshot digest canonicalization, `_full_grids` recording, Skylit `GRID_BY_VIEW` and current Triad raw/adjusted panes omit them. The surface-named backend test was rewritten to ADJ tests. `CLAIMS-VERIFIED.md:211-214` and `U16/RECONCILIATION.md:98` incorrectly claim retention. Decide presentation against current O4 ownership, then implement approved source→digest/store→consumer behavior and real tests, or explicitly decline it and correct the false docs. Do not cherry-pick naive old DUO math or restore the retired desk wholesale.

## Separate holds / non-restorations

- Wall-response dealer-intent/front-running doctrine is explicitly declined by the committed successor decision. Keep it absent; any safe redesign needs a fresh review.
- Recorded multi-resolution GEX curve remains specified, not implemented/activated, under H-CAPTURE. Domain math and existing candle/node charts do not prove it exists.
- Backend session-reference helpers are module capabilities without production callers found; bar-VWAP on the price chart is separate. Confluence/ML remains deliberately unavailable, not fabricated.
- Seven historical CI/browser/native-runtime records remain unverifiable here. No historical acceptance signature, old suite count, or file identity was promoted to current acceptance.
- All original owner/model/account/native/capture/visual/release/paper-exemption holds and optional C17 ownership remain separate.

## Checks actually performed

- Compared every assigned parent→commit patch and candidate committed source/tests; JSON includes exact Git blobs and line excerpts for replayable citations.
- Candidate-wide committed frontend relative-import scan: zero references into the removed modules.
- Transport comparison: exact semantic equality to later historical transport after removing only four `recorded_at` leaves; both envelopes and digests match committed sealed complete/partial fixtures. Fixtures remain synthetic and qualification=pending.
- Exact assignment SHA set/order/count checked programmatically. Tests inspected, not rerun.

## Per-commit dispositions

| # | SHA | Disposition | Semantic finding |
|---:|---|---|---|
| 1 | `f95aeb7b67c9b026140b69d8feb67e80ed23d897` | superseded | Composition patch retained its actual product fixes: null OI date admission/rendering, neutral CSS/Storybook/main imports, computed-background PNG, and brace cleanup. |
| 2 | `0acb3799cf0367f089c1ab1d3d96e3b6b99aedfe` | retained | Patch removed unused UI/helpers and their tests, leaving sectorMap coverage. |
| 3 | `85c32d71d26c445dd586e52bfa72ae776bdbf982` | superseded | DUO product-rule correction survives in domain.second_order_exposure.dollar_duo_second_derivative, not the retired bs_greeks wrapper. |
| 4 | `d5fea0fbcea620cb14a43c825d7e33a950920e0c` | missing-actionable | Actual patch added OI/DUO/DVO producers, display attachment, persisted grid keys and oracles. |
| 5 | `de3a3208e5a98463e65145ed96c0d30b8df45b94` | missing-actionable | Patch supplied eight-surface registry/tabs, unit-aware unsigned OI, null-safe float/object cells and actual Triad rendering tests. |
| 6 | `1a7ff033b1be1ca4135a2a877c2860f302cd4930` | retained | C17 exposure-by-strike route and explicit n_measured/n_total/partial remain, with stronger successor admission: route projects raw source before table-only filtering, unknown-side rows remain in denominator, exact fractional strike IDs, reasons/basis and source clocks propagate. |
| 7 | `8300af1645e124cf11918812985d4afa9f294d19` | missing-actionable | Health outage serialization fix is retained: never-succeeded age and SABR/SVI no-fit rmse are None; check_alerts still reports provider_down. |
| 8 | `19607915ff33c2be022b3d79393cc3fdf4c432ea` | superseded | Patch only changed channel coverage shape and added week_start (no resample call to week_start even in historical blob). |
| 9 | `4cc19c45ac1ad8da5bbfe5d7a98a8ee126ed9995` | retained | Docs gate behavior remains: internal link existence plus contract token checks; later candidate fixes exclude installed venv/node_modules sources, preventing dependency packages from backing project claims. |
| 10 | `91881cc29cebcb82a0afd1e485d013d797ec8fa4` | retained | Route still accepts independent dte and forwards it to scan_batch; scan_batch forwards dte alongside max_expiries to build_heatmap. |
| 11 | `2750548046c53075b9f31c787062aaeb9623d452` | missing-actionable | Actual grid patch maps oi/duo/dvo to their own payload matrices, formats unsigned OI as contracts without $, uses 0..max scale, and refuses unavailable named surfaces. |
| 12 | `5e0420190ec8d323c5488eaceba7f73242640481` | missing-actionable | Actual grid patch maps oi/duo/dvo to their own payload matrices, formats unsigned OI as contracts without $, uses 0..max scale, and refuses unavailable named surfaces. |
| 13 | `790257f11c4194e0e382ce18725db82808d5d899` | superseded | Call/put summation and no invented expiry/VEX/VIX goals survive through backend canonical annotate_contract_exposure/project_triad_from_chain and direct heatmap snapshot consumer. |
| 14 | `c33e635f5aa6e7393c5ca113a4608c80f1f546b4` | conflicting-owner-protected | Historical wall_response maps adjusted sign to reject/squeeze/flush and mechanical front-running instructions; ranking follow-up makes exactly one strong wall. |
| 15 | `f965064c6507a8b507a1f8c23a98dfa2459b026a` | superseded | Fixture-first packet/window tests remain, but candidate repairs production module importing tests and fabricating SPOT/K100. |
| 16 | `13b952bc8650809dba5c84450a221ac329a73059` | retained | Split optionability fact from deployment entitlement remains: BTC/ETH NON_OPTIONABLE, ^VIX/^SPX ENTITLEMENT_UNVERIFIED, separate exclusion reasons. |
| 17 | `336a69a90bcecffb53ecda6118a4e52b6497ea0d` | superseded | Generator import-scope NameError fix remains: record_id_for_digest is used from module imports when resealing distinct received_at. |
| 18 | `4f5fd4225e7b363d0d80cd2673c48a20b8efd60a` | conflicting-owner-protected | Historical wall_response maps adjusted sign to reject/squeeze/flush and mechanical front-running instructions; ranking follow-up makes exactly one strong wall. |
| 19 | `53ea53b66a003085cfbd4840d1c29577674b5342` | retained | Actual oracle math and registry remain: product-rule D second derivative, vomma*OI*multiplier, separate Taylor half-factor. |
| 20 | `58ac742cef45b8b742832d085da380d0c1671835` | retained | research_default_features validates zone shape before unpacking; invalid/missing/non-numeric/nonfinite/inverted inputs return policy_unavailable. |
| 21 | `6487b85be30fceff33f1c1a72b18e394ec667630` | retained | market_bars._reset_state still clears local cache/quarantine/error and shared budget singleton, preventing stale cooldown from bypassing the broker seam in later tests. |
| 22 | `6dbe0bf3534fe8e005865611a5378776f9f7bc03` | retained | Export envelope scope uses explicit allowlist rather than verbatim snapshot scope. |
| 23 | `954604f0e751562020bf997cb6c888092346d407` | retained | Pure reducer retains same session-date/session filtering, finite nonbool OHLCV, positive volume, Σtypical*volume/Σvolume and unavailable no-bars/no-volume responses. |
| 24 | `9c5734c08ddd67d0878c5f6af88f75d1d0309333` | superseded | Historical #57 signal-channel conflict narrative is summarized in a labeled appendix, not retained as current suite acceptance. |
| 25 | `a134820ebc0cfa136e2d42a30c438cf6972ec1e5` | retained | databento_usage still delegates window decision to server._in_window_now_et rather than fixed UTC-5, and exposes that result. |
| 26 | `a7a6e94a2cd357e4a78272829506483aa7cc8a36` | superseded | Real async adapter binding/await and no nested-loop composition remain. |
| 27 | `c34824bf27c28fe1970f51c30b0c5960acb93c5a` | retained | latest_leaderboard orders stored population by conviction DESC/updated_at ASC, recomputes rank across all stored rows and preserves batch_rank. |
| 28 | `dca82a7bc467194d815a2108ab41a92c434b0200` | retained | Per-contract values still derive from canonical compute_raw_oi([row], spot). |
| 29 | `ed58eb7c5534b6c91bb85e194b69d59f533776df` | retained | Budget read exception/None stays fail-closed BUDGET_UNAVAILABLE and skips the fetch; measured exhaustion remains BUDGET_UNAFFORDABLE. |
| 30 | `f76a5cee91ea77b6de4690c8a925ab852ae0483c` | retained | _recency and seven-day threshold remain diagnostic-only, ev.update(_recency(asof)) does not rescale conviction. |
| 31 | `0c7691a35e6757252a4ed0fbb6bede16dc2af57d` | retained | Thursday negative-case and backtest fixture now construct the actual 15:35 America/New_York instant rather than mislabeled 20:35 UTC; candidate keeps exact final fixture bytes. |
| 32 | `111d177d0efd1d918836f70a18f0b9c858a1cbfe` | unverifiable | Patch appends bdb6a8d8 CI/main-wave, budget battery, native review-stack refresh and S03 no-new-placement census claims. |
| 33 | `15845fc09125295cb0fe4994121de3f6572fcfd6` | superseded | S17e historical five-thread consume-once proof is represented by committed mounted-entry concurrency tests and execution_admission atomic fingerprint claim; no need to replay journal/CI counters into current ledger. |
| 34 | `1814461dc594c9a9f4d61dc810a2fbc945b7ccdb` | retained | Historical H4 note remains in current integration ledger and correctly identifies nullable-zone fix. |
| 35 | `1d79a248fb86bc8af22ae36c865bc6473bd5fb40` | retained | Ledger still retains exact historical CI row corrected to 0c7691a3 and its install-time infrastructure failure distinction. |
| 36 | `223c6fc87048c864df483914c1a6ad9742e8f0c9` | superseded | C0 recovery ledger file is absent at candidate, but its concrete module work is in stricter successor source. |
| 37 | `258b81693ce1696910ab3b07e9a106655864be92` | retained | H2 budget uncertainty note remains and matches retained scan_batch exception/None fail-closed branch and distinct unaffordable reason. |
| 38 | `2c19dbf3214c7bf03da36d3b468f4ae604b686a5` | superseded | Patch mixes external model-identity/peer-PR claims with S17b ambiguous-ACK journal repair. |
| 39 | `32d1d6a3cd82df84fc232a83e27845ead3174441` | retained | H3 live-data receipt is preserved verbatim as historical observation. |
| 40 | `38d8a9d1afeb0a3f991a181e19eb635827df7c2e` | retained | Detailed deliberate confluence/ML no-wiring decision remains and route still honestly passes None rather than fake neutral evidence. |
| 41 | `4084b94b8eb9a0cff2111e3d98192aaa0dd279bd` | superseded | One-word prose correction replaces foreign-language qualifier with third-party in a historical service-retirement sentence; no executable behavior changed. |
| 42 | `45c5259227e53fe6eec960cc96bf263cb992bcf0` | unverifiable | Patch records a three-parent composition, 7410/backend coverage pass, three frontend ordering failures, peer acceptances and future merge steps. |
| 43 | `481a20539bcefeb8c376d96138d836698085facf` | unverifiable | Six-gate measured manifest belongs to historical 223c6fc8 and absent C0 ledger; its commands/results were inspected but not rerun. |
| 44 | `55871cc09e8ef09e0f645a6e4ce9e0443fdba3d4` | retained | I18 transport regeneration retains complete/partial content digests, record IDs, synthetic, qualification=pending fixture envelopes, corruption/refusal cases and distinct received_at clocks. |
| 45 | `615cd9a77fda0284b5df20b3ec3cf8534f9bcd20` | unverifiable | Historical bdb6a8d8 main-wave battery, PR115 mergeability and CI state are not reproduced by committed blobs. |
| 46 | `720bfec6858afa5a766b4e86570bcb8c45260c15` | unverifiable | Patch is a historical UI/model-owner/process-protection account of a same-app Screener view and paper-only path at bdb6a8d8. |
| 47 | `7bdb74e2b679c51478132c008fe81d1e4c885b4c` | missing-actionable | Round-2 audit prose was replaced by successor appendix, but successor now falsely says OI/DUO/DVO surfaces ship via heatmap_snapshot and are covered by surface tests. |
| 48 | `89074181796f0d6b3ff087877df3d1b1ee3176b2` | retained | Actual patch is only a blank line separating stdlib datetime import from services.movers.completed_session_pair in _bars_for; candidate retains same ordering and test fixture uses completed_session_pair to avoid fixed-date windows. |
| 49 | `8db792c267d51fc666ab139d5d0b54f6626f66f7` | superseded | Historical fast-lane merge/51-accept ledger update and duplicate PR113 closure are not current closure proof. |
| 50 | `99ba5cd8aa68970baa882fe1eb13d9bffd523405` | superseded | Single-use repair and ambiguous replay doctrine are retained in consume_order_approval and the mounted route before broker placement, with tests for used-approval refusal and unresolved outcome. |
| 51 | `9bb7307a3a5a6a257b804e1dba06b082f78eb6c0` | retained | Historical sibling-pattern sweep narrative remains, with candidate budget fail-closed and DST-aware admin/Friday-pin implementations matching the narrow code conclusions. |
| 52 | `9faf629dda6390c30072cb51185f1a1bd91bca6e` | superseded | Historical controller queue T02/T03 collision, I18 acceptance and 72-hour idle waiter setup are absent from successor continuation. |
| 53 | `a540178447fe89fe876c37ea23825ca525245dba` | unverifiable | Peer review/14 C-obligation acceptance claimed at 6342afdf is historical and its model/native/CI receipts are not authenticated by this static task. |
| 54 | `a7802f2a547a2a7d9664a5e048139a10c3a5c8e0` | retained | requirements explicitly declares pytest-rerunfailures>=14.0 and marked flaky tests remain consumers, including anomaly training reruns=2. |
| 55 | `ad56e9049306e2638b55461ce056b30f918309bf` | retained | WallDeskSnapshot history roundtrip assertions survive: snapshot packet, missing-delta and stale identities/reasons, and stored OSIs are restored through real record/replay helpers in test. |
| 56 | `b3874cc9989950b1018d60bddc8bd90c9e302256` | superseded | Absent-flow fix remains (route starts flow=None), but old H2 cursor refutation does not settle the complete route: candidate explicitly removes prefilter limit truncation before rotating over len(ranked). |
| 57 | `c245fa96891744306e60d689c4c48426b177e0f7` | superseded | Historical skill audit, PR112/114 watch and Triad feasibility note are not current CI proof. |
| 58 | `d2c87b1e8b1d45da00561f6e76cf841f9f4d0598` | superseded | Original H3 receipt and its open-work list remain as historical entry but candidate appends follow-up results. |
| 59 | `d5b13041a1d99112ea471e148591b535dd4a0bec` | retained | Friday 15:35 ET factory correctly uses ZoneInfo America/New_York then UTC. |
| 60 | `db43da88c63e3ff5e34023e273e158c4d5080d07` | unverifiable | Ledger refresh claims exact historical fresh runs and an opened /private/tmp review worktree; no statuses were changed in its patch. |
| 61 | `dc36ab7725ebe9fb72edc37522286980fe80e79b` | superseded | STATUS header no longer pins b46e9af0 because successor explicitly explains self-referential SHA staleness. |
| 62 | `e32fed484d2baefd6b3ff2eeecc511130e868802` | retained | Recency no-decay decision and explicit unknown/unparseable states remain documented and implemented in _recency; test keeps same conviction across observation ages with clock-relative samples. |
| 63 | `e9d71a250fa1a3bb34ef2c58cb1c6edf77bae59e` | retained | DST sweep historical rationale remains and both production sites still use the same named timezone/helper normal path; Friday tests now use zone-built instants. |
| 64 | `ed278d04460bfdb6303f8d42d77dd7dec98ccc16` | retained | Actual cross-instrument tests remain for SPY/QQQ/^SPX/AAPL: parity against canonical exposure, shared formula/metric IDs, empty coverage unknown, and no instrument branch in annotation. |
| 65 | `f7ded485296dba603fda5d90b8cbcb730495671d` | retained | Historical correction of SPX optionability and independent dte/count axes is retained, with no source entitlement activation. |
| 66 | `fd3d55a761ab3c3f31e532af27418eb50d7ef4bd` | superseded | Historical idle-waiter/peer-dependency fix changes no product source and is absent from candidate continuation. |

Full patch provenance, candidate symbols/line excerpts, actionable paths and limits are in `branch-review-0.json`.
