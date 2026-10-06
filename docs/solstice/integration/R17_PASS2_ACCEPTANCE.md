# R17 pass 2 — historical combined engineering receipt

Current combined runtime is recorded in [R17_PASS3_ACCEPTANCE](R17_PASS3_ACCEPTANCE.md), CODEef911f37 including Spark044ca009. Pass-2 hosted gates all passed at03a1db39; the linked closure records them. Shared screenshot/browser paths now contain pass-3 evidence; retrieve pass-2 evidence from03a1db39. Counts/hashes below remain historical.

## Fixed candidate and ownership

- Verified main/base: `6eaa3343655a30fd38c40abaa6a903e8d3814530`, including PR102's disarmed-supersede fix.
- Tested combined **CODE `90c58939f14f734c83844b80b82c6f8bd9d70090`**: prior PR101 plus committed Spark PR103 `93dc0ef018e444e45e82b5335394590545134a16`, composed at `0b960b4f50b4cc98d99421803e056c5365194126`, then Zed's consumer patch.
- Review: [PR104](https://github.com/odaialdajani/floww-2/pull/104), isolated branch `solstice/zed-r17-integration-20261003`. The later receipt commit changes documentation/screenshots only; `git diff 90c58939 HEAD -- frontend backend scripts .github qc` must remain empty. Obtain the receipt SHA from git/PR rather than substituting it for the tested code.
- Producer acknowledgment: Spark's own `MUSE_STATE` §23. [Zed acknowledgment](https://github.com/odaialdajani/floww-2/pull/103#issuecomment-5966810840) records exact additive semantics and ownership. Spark's active dirty lifecycle/route/test work remains untouched and **not included** in this acceptance.
- Contract versions: `floww-integration.v1` consuming additive `coverage-read.v1`; existing trace/draft/handoff/metric/replay boundaries unchanged.

No PR merge, main push, deployment, existing-service restart, new broker wiring, activation, order, paid model turn or policy change occurred. Workers/execution stay OFF; commissioning values remain UNSET.

## Completed consumers

1. **Owning stored day:** enumeration uses the stored timestamp-prefix date consumed by manifest/attribute. Selected NY date and overnight/mixed attribution are disclosed separately. Missing legacy metadata remains unknown. Selecting a NY date never silently changes the owning manifest key. Existing reset/abort/generation guards remain intact.
2. **Expiry meaning:** exact version/ticker/window/freshness/observation checks remain. Coverage validates requested/returned/filter counts and literal cap/edge flags. The optional `≤30 DTE filter` is separate from 14–60 admission; `display_envelope` is a boolean eligibility flag, **not** a persisted analytical display envelope. Missing metadata stays unknown; caps and observed edges never establish exhaustive intermediate coverage. The range-map control remains unavailable.
3. **Refusals:** top-level `chain_unavailable` (502) and `REVERSED_WINDOW` (422) are retained. No arithmetic/table replaces a refused read. Current expiry reads stay disabled during historical replay.
4. **Representative states:** committed synthetic fixture includes 0/28/45DTE and an overnight stored-prefix example. New production Storybook states: OvernightStoredDay, CappedExpiryListing, ChainReadRefused. Browser verifies the overnight manifest request against its stored prefix using an index-only fixture; it does not claim overnight analytical playback or production durability.

Owned source changes are limited to ReplayStrip/ExpiryCoverage, associated tests/stories, synthetic coverage fixture and finite browser harness. No new App.js, package, protected, frozen, server/shared-schema or producer edit by Zed.

## Checks actually run at CODE90c58939

| Gate | Actual result |
|---|---|
| RED → GREEN | **11 new regressions failed before the patch**, then **87 passed** across the two focused suites. |
| Full backend, unmasked, coverage-bound | **7079 passed /37 existing skips /68.91% coverage**, 283.77s; required floor60%. Test Mongo, blank vendor credentials, execution/capture/price/outcome flags OFF. No new skip/xfail. |
| Full frontend | **126 suites /1126 passed**; latest repeat16.96s. |
| Storybook interactions + axe | **4 files /23 passed**, latest repeat3.78s; no accessibility rule disabled. |
| Production + Storybook build | **PASS**; browser harness recompiles and verifies unchanged source/bundle hashes. |
| Ruff0.15.22 | **PASS**, full backend. |
| Configured Bandit medium gate | **PASS**, fail-fast run. |
| Truth audit | **227 passed /0 failed**; existing unverified-model SKIP messages remain disclosed. |
| Silent-except audit | **PASS**,353 files. |
| API-doc gate | **PASS**,379 paths. Generated producer docs untouched by Zed. Existing duplicate root-head operation-ID warning retained. |
| Protected TideHunter/Flowseeker | **71/71 git-object hashes unchanged**. |
| Complete-app fixture browser | **PASS**:8 route IDs/direct/refresh/active checks, browser history/query/hash, Expand/selection, dated replay/play/pause/scrub/both steps/Live exit, exact-pair admission/refusal, expiry/filter/count disclosure, overnight key, contract/draft/manual handoff; **0 page exceptions /0 execution mutations**. |
| Desktop/narrow/zoom | Six captures at1440/1280/390; document width equals requested viewport at each. Real Chrome tabs zoom2:1440→720 CSS pixels, DPR2, CSS zoom1/visual scale1. |
| Hosted ship-runtime + Docker | Read the [exact-head closure](https://github.com/odaialdajani/floww-2/pull/104#issuecomment-5966858390). At receipt preparation CODE90c58939 Ruff/frontend passed, backend was running; new receipt-head checks require independent verification. Neither local success nor Spark's green lane substitutes for combined checks. |

Local Python3.14.6/Node24 differ from shipped Python3.12/Node20. Local Docker is not claimed. Hosted checks must bind their actual SHA. The linked closure is updated after verification without another runtime mutation.

## Evidence and limitations

[Preview/story index](README.md) · [browser receipt](evidence/browser-receipt.json) · [commissioning packet](COMMISSIONING.md).

- Protected manifest SHA256: `c5bea4270f1b6a79d60c22468db261644d43dcf2ee5aeb653cad4a3fff1e6e94`.
- Synthetic coverage fixture SHA256: `3b47655a3a7fbbf3a4dbdd0d305fb17b0a4a84addef8cdf395320a48ba479c49`.
- Original backend-generated R14 fixture SHA256: `8fefacf5c52d58c0271fcabd535c7eea61d5fb0ab24b134ba89b75aa5c821f12`.
- Browser receipt SHA256: `fa1ac2d26e351f68ef9ab3e3e1e64705b642135a1607332d7cb4fca27c924382`; sourceCommit binds90c58939, source/bundle hashes and coverage fixture.

Browser account/model/market traffic is isolated synthetic data. Twenty retained console warnings and the first-use install overlay are disclosed; no zero-warning or Nav visual approval claim. Existing React act/fake-timer, package peer/deprecation, provider-options, FastAPI lifespan and bundle-size warnings remain. No exposed browser/Storybook/Sentry/Public/Codex-task MCP; CLI checks do not establish connector authentication, remote trace delivery or live entitlements.

## Remaining queue, owners and exact next actions

| Owner | Remaining requirement | Next action |
|---|---|---|
| Spark/Cline engineering | Complete admitted14–60 analytical range-map query/projection | Publish versioned owning observation/basis/freshness/axes/population/refusal fixtures, not only listing or optional-filter flags. Zed then writes a consumer with RED → GREEN guards. |
| Spark/Cline engineering | Authenticated/default-deny approval/preflight and account-wide execution ownership/risk/protection/recovery | Finish committed proposal and exact mount boundary in MUSE_STATE. Inventory/review surfaces do not establish an executor. Zed acknowledges the precise read/review boundary; no new broker-entry wiring is authorized. |
| Authenticated owner | Effective Lodestar Sol/xhigh | Save supported catalog preference through existing owner UI; separately authorize a grounded turn and inspect effective dispatch/context trace. Fresh prior catalog proves `gpt-6.1-sol/xhigh` support, not saved settings or dispatch. No DB auth bypass or silent fallback. |
| Operations | Durable admitted production replay | Supply actual record/manifest/price-path identities and restart receipt under an explicitly approved capture policy. Synthetic/throwaway restart fixtures are not production records. |
| Nav/operator | Public account, rights/entitlements and all policy fields; remote native review; visual approval | Review the concrete commissioning table and production screenshots; keep values UNSET until supplied and server-enforceable. Native report is not activation. |

Session-prefix normalization and reversed-window refusal are resolved at93dc0ef0, not repeated as missing work. Optional DTE queries still enforce≤30; unfiltered expiry-count loading can include later dates. Range projection remains a genuine engineering gap. Green gates are not trading approval, realized option P&L or profitability evidence.

## Bounded continuation

Fetch main and PR103; inspect Spark's checkpoint and clean/dirty ownership before composing **committed** inputs. Re-run full combined gates if runtime changes. Verify the receipt-head checks with bounded `gh pr checks 104 --watch --interval 20`, then update the linked hosted closure with actual SHA/job results. Do not re-audit unchanged R14 proofs, consume dirty Spark files, auto-merge or claim background work after this session.
