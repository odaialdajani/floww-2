# R17 pass 5 — strict approval and recovery-surplus review; commissioning HOLD

## Exact combined candidate

- Verified main/base: `6eaa3343655a30fd38c40abaa6a903e8d3814530`, including PR102's disarmed-supersede fix.
- Consumed Spark PR103: `d8ba5b7b533667520274a6396b7b73da4db9bad2`, including strict stored-approval repair `35939a6e` and recovery-surplus/approval-count-dedup repair `a9e794ca`. Spark's service/routes/tests/checkpoint are preserved verbatim.
- Initial strict composition: `f14e735ae20436630373f9eb069685b27c2d5204`; later producer composition: `9b6573f52a8d7e2794920ad088335f961539bb19`.
- **Tested combined CODE: `aadea4ac833e35b14375f9f36243c7da1f526d7f`**, isolated `.worktrees/zed-r17-integration-20261003`, branch `solstice/zed-r17-integration-20261003`, [PR104](https://github.com/odaialdajani/floww-2/pull/104).
- Final publication adds owned documentation/evidence only. Verify `git diff --exit-code aadea4ac HEAD -- frontend backend scripts .github qc`; the receipt's runtime must match this CODE. Actual final receipt SHA and hosted workflow `headSha` are maintained in the [pass-5 exact-head closure](https://github.com/odaialdajani/floww-2/pull/104#issuecomment-5971763877), without a self-referential receipt-commit loop.
- PR103/104/105 were **OPEN**, `mergedAt=null`, at pre-publication. Observed Spark PR105 head `d5a8b469d6c0cd5abe7e42a47e7fe8480b479311` is branch composition, not a main merge; its older frontend does not contain this new disclosure fix.

Contracts remain `floww-integration.v1`, `coverage-read.v1`, `lifecycle-inventory.v1`, reported `account-policy.v1`, and existing replay/trace/draft/manual-handoff versions. `require_stored_approval` is a service parameter, not a new route or authenticated permission contract. All eight workspace IDs remain intact; display-GEX S²/feature-GEX S¹ stay distinct.

## Delivered boundaries

### Strict approval repair — credited to Spark

Explicit `require_stored_approval=True` on injected submit/supersede requires the durable unrevoked approval row binding the presented immutable intent:

| Condition | Refusal |
|---|---|
| Storeless or authoritative row absent | `APPROVAL_NOT_STORED` |
| Intent/account/scope mismatch, expired or revoked | `APPROVAL_INVALID` |
| Required approval query fails | `APPROVAL_STORE_UNAVAILABLE` |

Supersede pre-validates before cancellation and forwards strict mode to submit. Spark's hardening suite passes **21 tests**, including no cancellation on strict refusal and durable surplus with settled local history.

The [independent probe](evidence/strict-approval-r17.json) passed **ten cases** at composition9b6573f5, using only isolated DuckDB `:memory:` and the approval functions; lifecycle source SHA256 `18ca1f7cf8864012c5ac9a5f93482a754f363c295b2b8c1ec5356576f2d404d1` still matches tested CODEaadea4ac. It includes expected legacy-copy acceptance, strict absent/storeless/query-failure refusals, accepted authoritative row and intent/account/scope/expiry/revocation refusals. Minimal synthetic identity tests approval binding only, **not validate_intent, broker transport, authenticated approval or trading admission**. Broker calls, route invocations and model turns: zero.

**Pass-4's missing-authoritative-row/query-failure issue is closed for strict callers.** Legacy `verify_approval`, `require_approval=False`, `require_fresh_preflight=False` and `require_stored_approval=False` defaults are intentionally unchanged. No mounted authenticated approval-write/approved executor boundary is introduced.

### Owned read-only recovery disclosure

`frontend/src/components/public/PublicLifecycleInventory.jsx` previously warned only when the entire local registry was empty. That hid recovery surplus when settled history or partially recovered local records existed. It now compares stored nonterminal rows against **local open plus unknown records**, matching the new producer admission condition.

Two new regressions failed before the fix and pass after it. They also prove equal/unavailable counts do not become permission and all reads remain GET-only. `PublicPanel.stories.jsx` adds a settled-history surplus interaction/accessibility state; the compiled browser checks partial recovery plus the existing empty-registry case. The warning requests review through an approved server boundary and executes no recovery, reconciliation, cancellation or entry.

Producer files, MUSE_STATE, server.py, shared schemas, App.js, dependencies, protected implementation, frozen artifacts and watchdog were not edited by Zed. The only new runtime edits are the disclosure, its tests/story and existing owned browser assertion. Account attribution and remote native census remain explicitly unavailable.

### Preserved full application

Solstice Matrix+Profile/signed maps, Triad owning Raw/Adjusted pair, guarded dated replay/session enumeration/comparable-pair refusal, catalog-bound Lodestar traces/non-executable drafts, manual Public handoff/history, actual venue disclosures and owned TideHunter bridge remain intact. Zenith and Steal Three retain their calculations. The sorted14–60 expiry/DTE listing remains explicitly **not an analytical grid or persisted display envelope**; optional analytical DTE queries still enforce≤30 while count-based unfiltered listings can return later dates.

## Final local validation at CODEaadea4ac

Final commands ran sequentially, without masks or weakened tests. Earlier successful runs at f14e735a/9b6573f5 are not substituted for these final CODE results.

| Gate | Actual result |
|---|---|
| Owned regression red/green | Two surplus cases failed before fix; PublicPanel module **28 passed** afterward. Filtered26 tests in the red command were not skip decorators. |
| Full backend, unmasked, coverage-bound | **7105 passed /37 existing skips /68.99%**, 445.64s; gate60%. Test-only database/credentials, model fakes and execution/capture/price flags OFF. |
| Full frontend | **126 suites /1155 passed**, 31.369s. |
| Storybook interactions + axe | **4 files /29 passed**, 7.43s; no accessibility rule disabled. |
| Production + Storybook builds | **PASS**, compiled browser serves the hashed production bundle. |
| Ruff0.15.22 / configured Bandit | **PASS**, full backend, fail-fast. |
| Truth / silent-except / generated API | **227 passed /0 failed**, **353 files**, **380 paths** current. Existing unverified-model SKIP and operation-ID warnings remain disclosed. |
| Protected HEAD/working hashes | **71/71 unchanged**, manifest SHA256 `c5bea4270f1b6a79d60c22468db261644d43dcf2ee5aeb653cad4a3fff1e6e94`. |
| Compiled full-app fixture browser | **8 direct/refresh/active routes**, back/forward/query/hash, replay/date/pair/contract/draft/manual-handoff guards; **0 page exceptions /0 execution mutations**. Two on-demand inventory **GETs**, including recovery surplus. |
| Viewports / native zoom | Six Solstice/Triad captures at1440/1280/390; document widths equal viewports. Chrome native `setZoom(2)`:720 CSS px/DPR2, CSS zoom1/visual scale1. |
| Hosted final receipt | **Pending at document preparation**; actual receipt SHA and four exact-head gates, including Docker, are updated in the linked closure after bounded verification. Older green heads do not satisfy this gate. |

[Validation manifest](evidence/validation-r17-pass5.json) records actual counts and SHA256s of retained local logs/evidence. Raw `.verification/` logs remain local; a hash does not claim their remote availability. Browser receipt SHA256: `af6a6f836fa1aeb79ed01a0f66e03459ed128d8504734d61c465f1f9b1aae18f`; independent probe SHA256: `364daa3a333f1af9063236cce6e739ade6c953d3b271a3500d3e3354cec8c919`. **666 browser source hashes** match tested CODE. Shared screenshots/receipt now describe pass5; pass4's historical bytes remain retrievable at receipt0d8452d7.

Local Python3.14.6/Node24 differ from ship/CI Python3.12/Node20. Docker is unavailable locally; hosted exact-head image results remain mandatory. Existing React act/fake-timer/open-handle, bundle/deprecation/provider/lifespan/operation-ID warnings remain disclosed. Browser traffic is synthetic: **20 resource warnings** and the first-use install overlay are retained. Screenshot inspection is not Nav's visual approval, authenticated account/model dispatch or production replay readiness.

## Failure receipts — retained, not hidden

- Initial orchestration set `FLOWW_AGENT_DISABLED=1`, causing **16 backend failures**, including the correctly refused503 research route. Correcting only the test-subprocess flag to0 yielded42 affected-module passes, then7103 full passes at initial f14e735a. No source or production flag was changed.
- Concurrent heavy validations hit limits: initial frontend wrapper150s timed out; its completed log showed125 passed suites/one existing5s Skylit replay test failure under contention. Focused replay rerun passed four tests; final sequential full run passes1155. Browser build180s and truth-chain90s also timed out before later sequential successes. Existing services/other writers were not stopped.
- Unsupported merge-message stdin failed before merge started; a local HEREDOC message file corrected it without abort/reset/revert. No user work was discarded.
- Initial metadata extraction asserted the earlier226 truth count; final CODE logs actually show227 and68.99% coverage. Extraction refused before writing and was corrected to actual results, without changing tests or source.

## Remaining acceptance / commissioning requirements

| Owner | Exact next action |
|---|---|
| Spark engineering | Propose accepted authenticated/default-deny approval-write/immutable-intent/preflight/executor boundary requiring strict approval and fresh preflight; required policy/approval write and recovery-query failures must refuse. Obtain writer/boundary acknowledgment before any new broker-reachable mount. No entry wiring is authorized by this receipt. |
| Spark engineering | Supply account-bound real fills/fees/daily loss/aggregate exposure/actual positions/remote-native census, deployment-safe exclusive execution and verified protection/recovery. Installed ceilings, deduped registry counts and conservative native support are implemented, not proof of these remaining controls. |
| Spark engineering | Supply admitted14–60 analytical axes/grid/metric/basis/population/freshness and owning persisted display record, with refusal fixtures. Listing projection and completeness heuristic remain separate. |
| Authenticated owner | Save actual catalog-supported `gpt-6.1-sol/xhigh`; separately authorize a substantive grounded turn and retain effective settings/context/observation/usage trace. Catalog support is verified; owner settings/effective dispatch are not. No auth bypass or paid turn occurred. |
| Operations | Supply admitted production manifest/record/price-path IDs and process-restart proof under explicitly approved capture policy. Fixtures/throwaway stores/counts do not commission replay. |
| Nav/operator | Supply exact account/rights/entitlements and every concrete policy value in [COMMISSIONING](COMMISSIONING.md); review native workflow/overlap in Public and visually approve the production interface. Values remain **UNSET**. |

No main push/PR merge, deployment, existing-service restart, new executor mount, activation, order or paid model turn occurred. **Commissioning HOLD; activation OFF; outcomes INSUFFICIENT EVIDENCE.** Underlying labels/fixtures and engineering gates do not establish profitable options trading.

## Bounded continuation

Publish explicit owned receipt files to the lane only, verify remote SHA/runtime equivalence, then bounded `gh pr checks 104 --watch --interval 30`. Update the linked exact-head closure without another receipt-commit loop. Notify Spark through PR103, credit the strict/surplus repair and identify the remaining contract boundaries. Fetch/drift-check once more. Independent owned READY consumers are exhausted; further implementation requires an admitted producer contract or separately authorized owner operation. No unchanged R14 resweep or invented background work.
