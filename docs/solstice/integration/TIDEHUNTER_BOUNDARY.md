# TideHunter boundary receipt — Zed-owned bridge

Boundary version: `tidehunter-public-review.v1`; protected manifest `docs/solstice/r11/PROTECTED_MANIFEST.txt`. Manifest SHA256: `c5bea4270f1b6a79d60c22468db261644d43dcf2ee5aeb653cad4a3fff1e6e94`. Before and after the integration changes, the batch `git hash-object --stdin-paths` check found **71/71 identical git-object hashes**, zero protected-file changes. No friend component, CSS, tests, domain calculations, watchdog, frozen ML artifact or source adapter was edited.

## Supported integration, not an unused prop

`FlowseekerProBlademap` accepts `active` and publishes screen context. App's old `onTrade` prop is not consumed by that component and is not claimed to be a working trade bridge.

Owned files: `frontend/src/components/public/TidehunterPublicBridge.jsx`, its tests/styles, surgical `App.js` mount/active wiring, and the owned agent v2 context admission guard. Pro remains the single writer of its proprietary focus/calculations and feed subscriptions; the bridge consumes the published selection, not private implementation state.

1. No bridge network work occurs on mount or every tick. Resolution is an explicit user action.
2. Pro ckey, estimated premium and conviction remain display inputs. A string resembling an OSI still must resolve against the backend's recorded contract population. Public option-chain OI/volume is not a trade-print/aggressor feed.
3. Pro does not publish an owning record ID. The bridge therefore explicitly loads a NEW bounded owning observation, rather than calling it the old Pro observation. Both original Pro source time and new record/time/source are shown.
4. Exact strike/expiry/type or listed OSI is resolved by the existing read-only contract endpoint. Symbol, record identity, actual listed axes and matched contract must agree before the separate review opens. No closest contract, midpoint, inferred series or quote is substituted.
5. While that review is active, the owned shell passes `active=false` to Pro, retaining the friend component/mode while releasing its feed. The bridge publishes its own versioned exact selection through the existing owner-token context store. Older Pro cleanup cannot clear the newer selection. Close/Escape releases the bridge context, restores focus and resumes Pro through `active=true`.
6. Changed symbols/selection and unmount abort/invalidate pending resolution. No owned bridge polling/SSE loop duplicates Pro. The ordinary Pro UI clock is not an additional feed or broker connection.
7. Lodestar uses the same provider/context/auth/history machinery; Public handoff remains non-executable, separately reviewed, and never calls an order route from this bridge.

## R16 continuation — current recheck

At tested combined CODE `e5ee1404b5461a994befd2703e57627f5dca7ff5`, protected71/71 hashes remain identical; full frontend126 suites/1096 tests and compiled8-route browser passed, including Pro entry/refresh and unchanged active lifecycle tests. No protected/friend code or source/bridge implementation changed this pass. The synthetic/browser versus live-feed distinction below still applies. Current combined proof/remaining commissioning HOLDs: [R16_ACCEPTANCE](R16_ACCEPTANCE.md).

## Historical implementation evidence and limits

- New bridge tests passed: ckey exclusion/exact-contract-before-review, conflicting identity refusal, late-response abort on symbol change, and restoration of published Pro context on close.
- Existing protected `BlademapActiveMount` and the full frontend suite passed unchanged, including active feed ownership/cleanup and existing no-feed states. The wider suite still emits pre-existing React act/fake-timer/open-handle warnings; they were not suppressed by changing protected tests.
- Compiled full-app browser smoke visited/refreshed `flowseeker-pro` and every other route with zero uncaught page errors; feed/network traffic was fixture-only and no broker/model provider was invoked. This is not live SSE/feed entitlement or live Public connection proof.
- Source inspection verified active-gated polling, SSE ownership/close, scan/history/regime/quality and existing reconnect/no-feed behavior. Real feed reconnect and final Nav visual review remain separate operational checks; protected implementation is not rewritten to manufacture a green receipt.

The bridge establishes an owned reversible UI seam. It does not commission Pro for real-money execution, calibrate conviction, verify native workflow ownership, activate capture or establish profitability.
