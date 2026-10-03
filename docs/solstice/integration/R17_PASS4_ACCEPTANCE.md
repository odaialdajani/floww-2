# Historical R17 pass 4 — committed control disclosures; commissioning HOLD

Superseded by [R17_PASS5_ACCEPTANCE](R17_PASS5_ACCEPTANCE.md). The results and hashes below describe CODE98ab205a/receipt0d8452d7 only. Shared preview files and browser-receipt.json are now pass-5 evidence; retrieve their historical bytes from receipt0d8452d7. The strict approval repair closes the old missing-row/query-failure blocker for strict callers only; this historical record is not a current unresolved-defect list.

## Exact combined candidate

- Verified main/base: `6eaa3343655a30fd38c40abaa6a903e8d3814530`, including PR102's disarmed-supersede fix.
- Consumed committed Spark PR103: `1e43c00aa601d5736cec4abdaca4ac253eab64ab`; runtime fix `667993ffaeb9ee5f9da4df409267450b3c4e115a`. Includes policy ceilings, stored/revocable approvals, initial recovery admission, conservative protection reports and the listing projection, plus revocation/newest-policy/silent-handler/test-order repairs.
- Composition before owned source commit: `52e59a7c5536ab7c917f2aae4412d210af74e70f`.
- **Tested combined CODE: `98ab205a610938bdb44d2f298cc4c31c559117db`**, [PR104](https://github.com/odaialdajani/floww-2/pull/104), isolated `.worktrees/zed-r17-integration-20261003`, branch `solstice/zed-r17-integration-20261003`.
- Later receipt publication changes owned documentation/evidence only. `git diff --exit-code 98ab205a HEAD -- frontend backend scripts .github qc` must be empty; obtain the actual receipt SHA from git/PR, not this document's self-reference.
- Resume drift check: Spark's newer `7d151fca8065a37b411aa1016d95e0b15c919eba` adds only its §28 checkpoint. PR105 `daa31c7c7c1ab8d3f0dc459ddb968924f3ad14ef` contains the tested runtime tree; the same runtime-path diff against CODE98ab205a is empty. These PRs are **OPEN**, not main-merged. Spark's committed checkpoint and receipts remain untouched; no dirty other-lane files were consumed.

Contracts: `floww-integration.v1`, `coverage-read.v1`, additive `lifecycle-inventory.v1` and reported `account-policy.v1`; existing replay/metric/trace/non-executable draft/manual handoff versions remain unchanged. All eight workspace IDs are preserved. No producer/server/shared-schema/dependency/protected/frozen/watchdog edits by Zed this pass.

## Functioning disarmed consumers

### Public lifecycle inventory

`PublicLifecycleInventory.jsx` retains the **explicit on-demand authenticated GET** boundary. It now validates and discloses:

- Installed policy only for exact `account-policy.v1`, literal `set=true` and a valid update timestamp. Installation does not establish account binding, values or enforcement.
- Stored/revoked approval counts, not authenticated permission.
- Conservative native-protection support and concrete reasons. Unsupported/unverified support is not offered as protection.
- Recovery review when stored nonterminal rows exist with an empty local registry. This disclosure executes no recovery and does not prove reconciliation.
- Missing legacy fields as unavailable, never zero or verified. Malformed metadata refuses before rendering.

Account/connection/key/session/unmount changes still abort/reset, and obsolete responses cannot restore another account's review. Receipt time is a client clock. Process-local and stored counts are not actual account positions, open broker orders or a remote-native workflow census. The current account header does not bind an unattributed producer registry to that account. No policy, approval, recovery, cancellation, entry or activation mutation is exposed; FLOWW_BACKEND entry stays unavailable.

### Admitted expiry listing projection

`ExpiryCoverage.jsx` accepts optional `range_map` only as a **listing projection**: exact version/window, sorted admitted expiry/DTE pairing against returned rows, exact min/max bounds, literal completeness and reason. It explicitly says **“Producer reports complete listing; exhaustive coverage unverified”** and **“No analytical grid or owning display record.”**

A first-N count/edge heuristic is not exhaustive coverage. Dates/DTEs supply no analytical axes, metric grids, Greeks/population or owning persisted display envelope. The optional API DTE query remains ≤30; unfiltered count-based loading can return later expiries. Listing admission and analytical 14–60 range-map admission are different. Analytical range-map controls remain disabled; this read does not change selection or invoke a model and remains unavailable in historical replay.

Stored-session selection, owning-prefix versus NY attribution, persisted staleness/unknown freshness, Raw/Adjusted restoration, exact-pair comparison refusals and abort/late-response guards from prior passes remain intact.

## Checks run at CODE98ab205a

These are the full local pass-4 runs before the metadata-only receipt continuation, not extrapolated from Spark's focused suite. The resume rechecked runtime equivalence, retained frontend/story logs, browser source/screenshot/fixture hashes and protected git-object hashes. No new skip/xfail or masked command was introduced.

| Gate | Actual result |
|---|---|
| New regressions | **15 failed before the patch**, then passed; one extra unsupported-policy compatibility guard already passed. Focused PublicPanel + SkylitDashboard: **2 suites /99 passed**. |
| Full backend, unmasked, coverage-bound | **7099 passed /37 existing skips /68.97%**, 257.94s; coverage gate60%. Test credentials/flags isolated; no production worker or execution activation. |
| Full frontend | **126 suites /1153 passed**, 20.738s. |
| Storybook interactions + axe | **4 story files /28 passed**; no accessibility rule disabled. Three added states: stored-control reports, recovery review, listing-only projection. |
| Production + Storybook builds | **PASS**; recorded browser source/bundle hashes remain bound to tested code. |
| Ruff0.15.22 / configured Bandit | **PASS**, full backend, fail-fast. |
| Truth / silent-except / generated API docs | **227 passed /0 failed**; **353 files** scanned; **380 paths** current. Existing model-unverified SKIP/duplicate operation-ID warnings remain disclosed. |
| Protected TideHunter/Flowseeker | **71/71 unchanged**, both HEAD git objects and working files rechecked on resume. |
| Compiled full-app fixture browser | **PASS**:8 direct/refresh/active routes, history/query/hash, replay/date/pair guards and owning-contract/manual handoff. Two explicit inventory **GETs**, no execution mutations or page exceptions. |
| Viewports / real browser zoom | Six Solstice/Triad captures at1440/1280/390 with document width equal to viewport. Native Chrome `setZoom(2)` verified720 CSS px/DPR2, CSS zoom1/visual scale1. |
| Hosted CODE and receipt-head gates | Tracked separately in the [pass-4 exact-head closure](https://github.com/odaialdajani/floww-2/pull/104#issuecomment-5968011801). CODE98ab205a backend/Docker were pending at receipt preparation; lint/frontend succeeded. Final receipt results must be read from the closure after bounded verification, not substituted from an older head. |

Local Python3.14.6/Node24 differ from ship Python3.12/Node20. Local Docker is unavailable; require hosted exact-head image results. Existing React act/fake-timer/open-handle, bundle/deprecation/peer, provider-options/lifespan and model/operation-ID warnings remain disclosed.

## Evidence and review links

[Production preview/story index](README.md) · [Public inventory screenshot](evidence/public-inventory-1440.png) · [browser receipt](evidence/browser-receipt.json) · [commissioning policy packet](COMMISSIONING.md) · [TideHunter boundary](TIDEHUNTER_BOUNDARY.md) · [checkpoint](../ZED_STATE.md).

| Evidence | SHA256 |
|---|---|
| Protected manifest | `c5bea4270f1b6a79d60c22468db261644d43dcf2ee5aeb653cad4a3fff1e6e94` |
| Synthetic coverage fixture | `a066bc6bfa4e0fd38f78bf983b5aace077a66b5eff606241b2b30cb0aa942eb0` |
| Synthetic lifecycle fixture | `0c05695f69de74d42bf221172dc0269db8d381c958543b58788f428116153a7c` |
| Original backend-generated R14 fixture | `8fefacf5c52d58c0271fcabd535c7eea61d5fb0ab24b134ba89b75aa5c821f12` |
| Browser receipt | `4f6b370ae1f46fe27a417ff02d667f70b6228c3ae6cc624283bf292183b8e117` |
| Public inventory screenshot | `68f323f6a6009845754df515dda2e36ba289f1ed9e91245a548dcf5f6171b236` |
| Retained full frontend log, `.verification/pass4-frontend.log` | `6d44519064b8cdaf286f2e2a5c2d44d29766c56d351cca2bddb3705ab003a463` |
| Retained Storybook log, `.verification/pass4-storybook.log` | `f346b258202d30c77bfd11268f7e9af2634d2d251f07ded0e806f5dacfd88ce5` |

Browser receipt `sourceCommit` is CODE98ab205a; **666 source hashes** match. Market/account/model traffic is isolated synthetic data, not authenticated production account reads, paid dispatch or durable admitted live observations. Twenty console warnings and the first-use install overlay remain disclosed. Public screenshot was inspected for readable disclosures, **not Nav visual approval**. Installed local tools are not connected MCPs: no browser/Storybook/Sentry/Public/Codex-task connector is exposed in this chat; remote Sentry authentication/trace delivery remain unverified.

## Producer audit and exact remaining requirements

Spark's §25–27 controls are genuine service improvements and are **not repeated as absent**. They do not establish a commissioned executor:

- Resume probe at CODE98ab205a/runtime667993ff, source SHA256 `d7cf17c9a5bd377362cc11301e5dffa8b3c035b8bed02f5576f0979eafb6e87f`: a synthetic supplied approval returned **`accepted=true`, `authoritative_row=null`**. Only `create_approval`/`stored_approval`/`verify_approval` were called in an isolated process; no store, broker or authenticated route was invoked. Missing authoritative approval still does not refuse. Durable revocation repairs do not close this missing-row boundary.
- Policy/approval persistence and recovery-count lookup retain best-effort fallback. Documented silent-handler intent makes the audit gate pass; it is not fail-closed execution proof.
- No accepted account-bound daily loss/fees/aggregate exposure/actual-position/remote-native census or deployment-safe exclusive execution boundary is supplied. Native support remains conservative unsupported truth, not verified protective behavior.

[CI/semantics request](https://github.com/odaialdajani/floww-2/pull/103#issuecomment-5967881158) · [exact approval/persistence failure request](https://github.com/odaialdajani/floww-2/pull/103#issuecomment-5967906047).

| Owner | Requirement / exact next action |
|---|---|
| Spark/Cline engineering | Supply complete admitted14–60 analytical query/projection with owning axes, metric/basis/population/freshness and persisted display record/refusal fixtures. The sorted listing and reported completeness must stay separate. |
| Spark/Cline engineering | Refuse missing authoritative approval and required policy/approval/recovery store failures; then propose the exact authenticated/default-deny immutable-intent/preflight/approval, account-wide risk/ownership/protection/recovery and exclusive-dispatch boundary. Obtain acknowledgment before any broker-reachable mount. No new entry wiring is authorized by this read-only pass. |
| Authenticated owner | Save the actual catalog-supported `gpt-6.1-sol/xhigh`; separately authorize one substantive grounded turn and retain its effective model/effort/context trace. Actual catalog proves support, not saved settings or dispatch. No auth bypass or paid turn performed. |
| Operations | Supply admitted production manifest/record/price-path identities and process-restart proof under an explicitly approved capture policy. Fixture/throwaway restart/counts do not commission replay. |
| Nav/operator | Supply exact account/rights/entitlements and all concrete commissioning values; review native workflow/overlap in Public and approve the visual interface. Values remain **UNSET**, activation **OFF**. |

No main push/PR merge, deployment, existing-service restart, new executor wiring, activation, order or paid model turn occurred. Commissioning remains **HOLD**; underlying outcomes remain **INSUFFICIENT EVIDENCE** for options profitability.

## Bounded continuation

Publish the documentation/evidence-only receipt on PR104, verify its remote SHA/runtime equivalence and run bounded `gh pr checks 104 --watch --interval 30`. Update the linked closure with final exact-head backend/frontend/lint/Docker results without another receipt-commit loop. Fetch/check drift once more and notify Spark through the PR. The independent owned consumers are DONE; further implementation becomes READY only on a concrete admitted producer contract or separately authorized owner operation. No repeated unchanged proof resweep or background-work claim.
