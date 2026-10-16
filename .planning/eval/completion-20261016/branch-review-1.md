# Branch semantic review — assignment 1

Candidate: `0bbdd711859e9a2fea043c8b79bf25e9728319bc`. **67/67 assigned SHAs, exactly one row each.**

This is historical patch reconciliation, **not acceptance of the original obligations**, live commissioning, hosted CI, reviewer signatures or a served build. All source/test excerpts and pure probes are committed blobs at the candidate. The shared HEAD advanced to `f7108e7870894cee37a2f8b959d2ee02094bcf5d` during review; findings below must be rechecked against the parent’s newer implementation head before acting.

## Results

| Disposition | Rows |
|---|---:|
| conflicting-owner-protected | 2 |
| missing-actionable | 7 |
| retained | 25 |
| superseded | 23 |
| unverifiable | 10 |

## Missing behavior / corrections for parent

These are candidate findings, not instructions to resurrect entire old branches. Original retain/defer decisions and acceptance criteria remain with the parent/owners.

### BR1-GRID — Unsigned OI and DUO/DVO grid producers/display/hash/replay integration are not present; registry/oracle definitions are not producers.
- Evidence: Production symbol search finds second_order functions only at definitions; _display_surfaces attaches only Charm/VEX; _canon_grids omits oi_grid/duo_grid/dvo_grid. Executed candidate digest probe: changing only oi_grid leaves digest unchanged.
- Paths: `backend/services/gex_core.py`, `backend/server.py`, `backend/services/heatmap_snapshot.py`, `backend/services/heatmap_history.py`, `backend/tests/services/test_oi_duo_dvo_surfaces.py`.
- Required guard: Retain/defer needs explicit owner disposition. Use product-rule math and existing multiplier/coverage rules; do not restore old single-factor DUO or eight-tab UI.

### BR1-CURVE — Recorded 1m/5m/15m/1h exposure time-series, including adjusted/activity surfaces, remains a spec rather than an implementation.
- Evidence: No get_gex_series/gex_series/_augment_strikes_with_surfaces consumer; current build_history emits nodes/price/centre/CVD, not curve buckets. docs/unified/RECORDED-CURVE-SPEC.md explicitly says SPECIFIED.
- Paths: `backend/services/heatmap_history.py`, `backend/routes/data_providers.py`, `backend/server.py`, `frontend/src/components/heatseeker/RangeAnalyticsWorkspace.jsx`.
- Required guard: Implement approved bounded aggregate-only/default-OFF contract with exact scope/known-at/TTL/cap. Do not activate recording/providers or copy old ticker-only mixing SQL.

### BR1-NAKED — Prior-session naked profile/TPO level start-to-first-revisit lifecycle has no successor implementation.
- Evidence: Current TPO is bar occupancy/single prints/composites; current profiles compute POC/VA. No naked/visible_until/revisit lifecycle in those production sources.
- Paths: `backend/services/chart_tpo.py`, `frontend/src/components/heatseeker/chart/indicators/profile.js`, `backend/tests/services/test_chart_tpo.py`.
- Required guard: Original helper was unmounted and insufficient for gaps/chronology. Retain/defer original B23 acceptance explicitly; if retained build sorted session-bound observed lifecycle and unknown gaps, not naive resurrection.

### BR1-DOCS — Two audit notes currently contradict source: claimed shipped OI/DUO/DVO grids and wrong-directory model discovery.
- Evidence: heatmap_snapshot does not emit/canonicalize second-order grids; truth_audit.sh already scans models and backend/models including *_manifest.json.
- Paths: `docs/audit/CLAIMS-VERIFIED.md`, `docs/audit/MODEL-AUDIT-2026-09-27.md`.
- Required guard: Repair prose only; do not use historical descriptor counts as current, alter model artifacts, or convert these corrections into acceptance.

### BR1-OPPORTUNITY — Opportunity scorer empty-dict absence still returns (0.0,ok), unlike changed flow/confluence/ML boundaries.
- Evidence: Executed exact candidate committed pure module: _norm_opp({}) -> (0.0,ok). Historical all-four subject overstates actual three-normalizer patch/tests.
- Paths: `backend/services/conviction_rank.py`, `backend/tests/services/test_conviction_missing_inputs.py`.
- Required guard: Current owner should add failing absent/None/malformed/measured-zero opportunity tests and repair availability, without changing weights/tiers or pretending original three hunks were lost.

## Owner and evidence limits
- Keep the successor UI: eight permanent tabs and old behavior chips are not silently authorized. Blanket Greek-return normalization must not overwrite numerical/ML ownership or frozen scales.
- Missing Bxx chart helper files are **not automatically missing mounted behavior**: historical consumer search found no server/route/frontend users. Bxx source prototypes and isolated tests cannot close Bxx acceptance.
- Ten unverifiable rows are missing historical external/runtime/signature checkpoints, not ten proven product defects. Preserve their original Git blobs; do not invent peer bindings, restart services or reuse dated counts.
- No pytest, browser, provider, store, model-artifact or service execution. No source/branch/worktree/index/remote changes. Only the two assigned scratch reports are authored.

## Verification actually executed
- Coverage check: assigned/reviewed/unique = 67/67/67; missing/extra/duplicates = empty.
- `ast.parse` on 51 candidate committed Python blobs in changed scope: no syntax errors. This is parsing, not a pytest result.
- Candidate pure-module probes: missing rank 0.0; mirrored confluence +40/-40 gives 8.0 each; fused-marker rank 0.0; missing/bool/nonfinite scalar inputs remain null; strongest equal-magnitude wall chooses first stable ID.
- Counterexamples: `_norm_opp({}) -> (0.0,"ok")`; changing only hypothetical `oi_grid` content yields the same canonical snapshot digest because the grid is omitted.

## Every assigned commit

Zero-based row numbers match the assignment. JSON contains full semantic reasoning, exact source excerpts/lines/blob IDs, original patch hashes/hunks, tests/consumer evidence and actionable paths.

| Row | SHA | Disposition | Semantic verdict |
|---:|---|---|---|
| 0 | `de9b13657588a26b1b7663f920cb449f2bca4c05` | retained | Honesty, GET boundaries, null OI dates and PNG background retained; Uxx notes are not acceptance. |
| 1 | `744fa5262b70e216b2bb7c205cf29152dcdd8df4` | unverifiable | Shutdown joins retained. Unmounted Bxx helper prototypes absent; unit-only history cannot establish Bxx acceptance. |
| 2 | `161384ccb235c5522f6b911d7b405f032e8e1d78` | missing-actionable | VWAP/PNG/profile supersede old panels; recorded exposure-over-time chart remains missing. |
| 3 | `29a53e0afc18581a8386a1c3715c79bd6ada0c54` | missing-actionable | Registry/oracle exists, but no OI/DUO/DVO producer/display/hash/replay integration. |
| 4 | `22e8fb164b020b19556cf74a24b1bc410fd6ea83` | conflicting-owner-protected | Eight-tab port conflicts with binding quiet GEX/VEX/Charm + Triad comparison decision. |
| 5 | `9e65b053701d59f574f09a7106215987095cf2a3` | superseded | Parser/UI aliases retained; broadcaster corrected into separate sync and async APIs. |
| 6 | `f39f839ae826c3e25b96963a3ccd0f1569d3eaf1` | superseded | Charm v2 applies units/weights; inspector reads actual displayGrid.vex_grid. |
| 7 | `d9f3ddcf3c212f48ee3da3832e59be1b2fb595b2` | retained | Canonical data imports, explicit unavailable values, broker refusal and AST dead-import gate retained. |
| 8 | `3b1b39388f06fc728e75e6ca9905522ef9671510` | superseded | Only import ordering; obsolete deleted-symbol import list must not return. |
| 9 | `88b98fc7683d28b54ae62997e7b3ab0e140b00f5` | superseded | Same formatting-only import swaps; no behavior to port. |
| 10 | `f53161745fde5612655173fae9b8c2de78b1cf5e` | superseded | Current raw/adjusted panes + conditional watches replace old PlayWalls behavior chips. |
| 11 | `5cba1d9dc066dc5b8dd41e30802df1721f29b9f5` | retained | Missing=zero/missing, directional symmetry and fused-blob guards retained; pure probes executed. |
| 12 | `78143ef867e5a858f64294b0ac0c0545ced89240` | retained | Both merge-parent deltas inspected: budget reset, network guard and calendar fixture retained. |
| 13 | `b0de55c69e0fbd4ee0165d022388cfe4d54805e8` | missing-actionable | Snapshot/node/centre replay is not 1m/5m/15m/1h exposure curve; approved spec remains unbuilt. |
| 14 | `d70a7ee5fe847d9458b01fd478245e8c5e69ada8` | retained | Sync broadcast, normalized frames, eviction and real no-loop delivery retained. |
| 15 | `04dcf539bf29bceb4ec8269c87fc858a888e40e8` | superseded | Projection hardens canonical multiplier/strike/coverage and is wired to route consumers. |
| 16 | `0ea45dc9102beb22d57f73a12a15d584bacc9caa` | retained | Pure scalar/array missing-preserving boundary retained; broad production adoption not claimed. |
| 17 | `2e3c95414de8b2c63a9605f0f1f05e1b6eb4f0ae` | retained | Deterministic pure tie policy retained; mounted strongest-wall integration not claimed. |
| 18 | `3b2f3d422a8581e3239f89553c445ec3ef987b24` | superseded | Signed zero-axis renderers supersede unsigned ladder magnitude widths. |
| 19 | `50119c10ccf21b40a2069a544d5928f167417a0e` | superseded | Variable rename obsolete; current session VWAP uses explicit high/low/close. |
| 20 | `57b7342da673519e35426f1604cf74335ede003e` | superseded | Ledger retained with newer H2 route-cursor corrections; old receipt is historical. |
| 21 | `62b571f196fad072b8b017896b6174b165c08d5c` | retained | Governor exception returns budget_unavailable before fetch task; exhaustion stays distinct. |
| 22 | `68f3f21632d39386a1b6c3429b12840fe3476630` | retained | America/New_York entry window and DST tests retained. |
| 23 | `7a783dfdbe4b41128ce318e9bbd65a52ae63ad91` | missing-actionable | Naked profile/TPO prior-session level lifetime/revisit helper has no successor; old prototype is inadequate. |
| 24 | `958bfc68e59babdf5c8924b2ff7ccc7864530139` | superseded | Product-rule DUO/DVO and VEX non-equivalence live in separate canonical oracle module. |
| 25 | `9ebf03f9b20acd05c8dafa3e6f1f5b86f294a8f0` | superseded | Active ProfileBars/TriadExposure handle signed geometry; standalone CSS-plan helper obsolete. |
| 26 | `a40b29580d31c7061749ab2679b50abf44564843` | missing-actionable | Adjusted/activity recording augmentation absent; full-grid replay is not requested exposure curves. |
| 27 | `b51ee58123230a43fa18fe11a6ceecba2221dc84` | retained | Three changed normalizers retained; empty opportunity still incorrectly reports ok (adjacent finding). |
| 28 | `c3bdf4c1b0ae0c5c38c4bb6ad245312a52582645` | conflicting-owner-protected | Blanket Greek _pyfloat return policy not retained; owner decision needed, no frozen-kernel/ML rescaling. |
| 29 | `df3ddc109dbb8a668ef2162df919172473b9e5bc` | retained | Absent alert feed passes None; no seeded measured-zero flow. |
| 30 | `ef4946bf3f6cec8053f4091d3dd4b78e5c39a489` | retained | Distinct versioned VEX/DUO/DVO registry rows and tests retained, not producers. |
| 31 | `f90aa2ed6ef84b4e3596645db0df54073d5a51c1` | retained | Profile exception boundary and real adapter mocks retained, including uppercase test. |
| 32 | `155edeac74b31f934978c65b578d6f067f3ed6ab` | superseded | Rebuilt canonical ADJ oracle/boundary tests supersede old test matrix. |
| 33 | `15fae25ab58ac9a5a1480743922cb0160b60f5f6` | superseded | Historical header corrections retained; pinned SHA and totals superseded, not candidate CI. |
| 34 | `1a7d5b018839349877e98f674999f14d1f8db9d7` | unverifiable | S17c source remains; absent external checkpoint cannot authenticate counts/peer signatures. |
| 35 | `1e24f0c03e4ac1ce8f3891f1c101f676335bd055` | superseded | Newer fixture-delivery and H2 corrections supersede stale handover/action state. |
| 36 | `244a6b95d11fed747578387057bf07f0b5b7b7f8` | superseded | Old green-run receipt superseded by later historical evidence; no fresh CI result. |
| 37 | `26307bc61e9f0d80fcd2ce287f2cf24eb9b634fb` | superseded | Updated old counts/mutation explanation retained; old pinned SHA removed. |
| 38 | `3073aa7e5187fec1ff1641232cc8c480f29bd7ea` | unverifiable | Absent architecture/screenshot checkpoint cannot prove full-plan promotion or visual acceptance. |
| 39 | `37c4b32a7ceeb461d97fb98e04fe8081a03da12a` | superseded | Duplicated speculative 43-row inventory superseded; original blob remains history. |
| 40 | `3ed61b5dd250fdf9b286b898f7bdd5f9c5aed751` | missing-actionable | Successor audit falsely says second-order grids ship; source contradicts it. Correct prose and keep gap open. |
| 41 | `434409b326cbf25e07f80f6209cd5f4cf38da446` | unverifiable | Old build/Chrome/PID receipt cannot establish candidate served identity. |
| 42 | `4656c92ba833171c8a1e4b47dc59fcf04c87507d` | retained | Unused dollar_gamma_unit import stays removed; singleton canonical aggregate computes values. |
| 43 | `4dba147e269e0240d707fc905972c444dc525e80` | superseded | Wording-only ownership translation obsolete with removed historical runtime note. |
| 44 | `6046be86ed40d22711efe5237619782cef40600b` | unverifiable | Replay precedence/abort guards remain; missing external analysis/signoff not authenticated. |
| 45 | `6266f89e4582c81b213cbc8926dc0f892a345b9b` | retained | Bool momentum rejection + dead-band sentinel preserved in code/tests and ledger. |
| 46 | `7294c8a15a202278bed99f743c0c6e588723cd39` | unverifiable | Fingerprint claim/completion code remains; absent S17d checkpoint cannot authenticate acceptance. |
| 47 | `84b11e5effff4832213c5124999d27bdd88efb51` | superseded | Receipt blob retained but later route-cursor correction supersedes broad H2 refutation. |
| 48 | `8b291d4445b8c898e5b84ff7461a807f7b89aa75` | retained | Availability explanation retained for actual three changed scorers; not all-four acceptance. |
| 49 | `96745f894e2940b1917b8f4d9987237721606971` | unverifiable | C16/S15/PR108 external ledger bindings are not authenticated by source review. |
| 50 | `9a6701b8ecf9d4de3c1d9b30513d7e94a69696d0` | superseded | Dependency-install timeout explanation preserved within later status; no fresh hosted CI. |
| 51 | `9ec71faf3510b3bc788c11f9e7feb5c5efc45946` | unverifiable | External full-packet/read/signature record absent; no original obligation self-accepted. |
| 52 | `a3d37619c539a59cfd69bc9526adacd241e6a0d5` | retained | Index entitlement versus non-optionable taxonomy retained; no new entitlement claim. |
| 53 | `a56059b6a13cdfa86445a9f0175f981513b375d6` | retained | torch.manual_seed precedes data/model draw; assertion unchanged. |
| 54 | `a7b3ebebc485ac511bfb99251ba4f82954e53798` | missing-actionable | Actual guard includes manifests; audit doc reverted to inaccurate directory claim. Fix prose only. |
| 55 | `b0178e6d6971d60f07f5d027fd345e5c1c5e3a88` | retained | Second fail-open-site finding and fail-closed code/tests retained. |
| 56 | `bacc9fabb68c464ab1b7a037af5f6d3945b82ec9` | superseded | Eight-tab CSS obsolete under successor controls; readability needs real browser, not old pixel claims. |
| 57 | `c4bdc5fb0dfab80633f771e1864a487e395eb92d` | retained | Provider call is inside date-pair guard with cleanup; matching-date network branch remains caveat. |
| 58 | `d436cc5c67fc9fd02e0df096e77cfe77abe0b001` | unverifiable | 39/39 external evidence-hash/CI checkpoint cannot be verified from source alone. |
| 59 | `d85d68f2378cecab34913d9ed105b6cb55b828b6` | unverifiable | Review-stack refresh/PID/build screenshot record is runtime-unverifiable in read-only source scope. |
| 60 | `dbbd3d3c89ebeb4b5d0b4e75556315b5f36afa48` | retained | Completed-session-pair fixture retained; no live provider/test execution. |
| 61 | `decee176bdba05f2e3a2d479d06cef0be287cfda` | retained | Exported scope allowlist retained; Muse connection remains unclaimed. |
| 62 | `e9410de5705a6dfbdee8ccdd486b7e816bb4815f` | superseded | Recency/taxonomy/DTE slices retained; old open-item list superseded by later code/ledger. |
| 63 | `ec456dc2042fe89e59dc462bcb952b43139a46ab` | retained | Global conviction ordering/rank and batch_rank retained; freshness not independently proven. |
| 64 | `f3d916252a7c65fead7b6daf66429fd1fc023b42` | retained | Actual file backing + tables required for durable; no current store/restart claim. |
| 65 | `f9f73862d1857d232450c949f4517741a94e46a4` | superseded | Old local-count checkpoint superseded by later historical status; not current acceptance. |
| 66 | `8fada0d60d0b6bafd38391deda479b628ef82302` | retained | Both merge parents inspected: never-succeeded JSON null and fit-status safety retained. |
