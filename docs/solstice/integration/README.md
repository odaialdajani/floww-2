# FLOWW integration review

Current continuation: `.worktrees/zed-main-acceptance-20261003`, branch `solstice/zed-main-acceptance-20261003`, base `08f3793c242d943ab3b61b84e5394ce4602daa0a`. Earlier Zed/Spark runtime code is merged through PR96/97/98; main's exact-head CI/CD and lint are green. Fresh local main backend7063/37 existing skips/68.83% and patched frontend126 suites/1096 tests passed. New Spark [PR99](https://github.com/odaialdajani/floww-2/pull/99) at frozen review head `c16e7f688ffd3f3150e2be67504c70c77702b2aa` remains separate from main. No automatic merge, deployment or activation. Exact current publication/combined receipts are maintained in [ZED_STATE](../ZED_STATE.md); [COMBINED_ACCEPTANCE](COMBINED_ACCEPTANCE.md) retains the old047153ec receipt as historical.

## Reviewable production behavior

- All eight current workspace IDs are registry-backed, URL-authoritative and browser-history aware. Zenith and Steal Three mounts/calculations remain intact.
- Solstice defaults to Matrix + Profile; left Profile changes geometry without discarding selection. Legacy Volume Profile remains accessible separately. GEX+VEX, Raw+adjusted, Multi-map, Calendar, Follow and Expand remain working. Next listed uses the admitted day-only server query; polling avoids the legacy loaded-only data alias. Four columns are not four DTE. The unsupported 14–60DTE range is visibly unavailable.
- Triad requests same-session scope and session Volume × |delta|, distinguishes the actually admitted scope, shares raw/adjusted strike/expiry rails and display range, and publishes exact contract selection. Unknown volume/window/Greeks stay unavailable; no copied OI. Shared symbol changes clear impossible selections without navigating away from Triad.
- Replay uses actual manifest and owning-record routes, a selected date, generation/abort/record-identity guards and persisted display projection. The displayed Raw/Adjusted pair is restored without today's Greeks. Current producer does not enumerate stored session dates or establish durable live recorder readiness. Owning identity and recorded staleness are now guarded in projection. Coarse last-two comparison currently lacks matching source/scope/model/population admission; producer follow-up is required, rather than claiming its `status=ok` establishes comparability.
- Lodestar retains bounded authenticated research, usage reservation and cancellation. Catalog-bound Sol/xhigh preset requires explicit owner save; requested/effective trace fields are distinct. Typed drafts use backend-owned contract/wall facts, never model-generated prices, quantities or permission.
- Public handoff is editable, dated, context-bound and manual. Operator reports are privately saved, not broker verification or activation. Actual Public account reads/partial fills stay separate from Alpaca PAPER, local portfolio estimates and journal outcomes. Backend entry is unavailable pending accepted producers.
- TideHunter files remain untouched. An owned bridge consumes published selectors, treats ckey/premium/conviction as display-only, resolves a separate exact current record before opening review, suspends Pro through its supported `active` prop, and resumes it on close. No duplicate automatic feed or new order path is added.

## Preview evidence — synthetic, not live readiness

These screenshots are the compiled complete React app with API/WebSocket traffic isolated to the existing committed R14 backend-generated synthetic fixture (SHA256 `8fefacf5c52d58c0271fcabd535c7eea61d5fb0ab24b134ba89b75aa5c821f12`). Storybook imports an exact compact display-only projection with that source hash rather than duplicating the entire replay/research packet. They are not the packet HTML prototype, live market observations, verified account reads, paid model results or a durable recorder commissioning receipt.

- [Solstice 1440](evidence/solstice-1440.png) · [1280](evidence/solstice-1280.png) · [narrow](evidence/solstice-390.png)
- [Triad 1440](evidence/triad-1440.png) · [1280](evidence/triad-1280.png) · [narrow](evidence/triad-390.png)
- [Native 200% zoom](evidence/solstice-native200.png) · [Lodestar](evidence/lodestar-1440.png) · [Manual Public handoff](evidence/public-handoff-1440.png)
- [Browser source/bundle/fixture receipt](evidence/browser-receipt.json): eight direct links/refreshes, back/forward, query/hash preservation, Expand/selection, replay steps/Live exit, contract/draft/handoff and six viewport captures. Native zoom is `chrome.tabs.setZoom(2)`, verified by 720 CSS pixels, DPR2, CSS zoom1 and visual scale1; not pinch/CSS emulation.

Local Storybook can be opened with `npm run storybook` from the lane `frontend`. This receipt does not claim that a server remains running after the finite checks. Useful story IDs:

- `solstice-production-desk--matrix-and-profile`
- `solstice-production-desk--missing-same-day-expiry`
- `solstice-production-desk--missing-activity`
- `solstice-production-desk--replay-gap`
- `public-manual-reviewed-handoff--native-brief`
- `public-manual-reviewed-handoff--backend-blocked`
- `public-account-reads--partial-fill`
- `public-account-reads--account-connection-failure`

Storybook uses the already inspected 10.6.1/React-Vite setup, with locally pinned Vitest/Playwright and no MCP addon/second app provider. State interactions and axe checks passed16/16. Installed is not connected: this Zed chat exposes no Storybook/browser/Sentry/Public MCP connector. Finite local Chrome-for-Testing acceptance is available; Sentry authentication/remote trace delivery remain unverified.

## Historical lane validation and known limits

The receipts in this section describe the original pre-merge lane, not the current continuation or PR99 combined candidate. Current checks are recorded in ZED_STATE.

Working-tree milestone: frontend126 suites/1091 tests passed; owned backend agent+Solstice1052 passed; Ruff/Bandit clean; production and Storybook builds passed; truth audit226/0; protected71/71 unchanged. An earlier full backend run logged6996 passed,37 pre-existing skips,68.66% coverage. Its shell command accidentally masked the pytest exit code; the log was explicitly checked, and the required full command must be rerun UNMASKED at the exact combined candidate. No skip/xfail was added. Counts/head-specific receipts must not be promoted to new heads without verification.

Local Node24.14.1/Python3.14.6 differ from CI Node20/Python3.12. Docker daemon is unavailable locally; hosted exact-head image checks are required. Existing React `act`, fake-timer/open-handle and bundle-size warnings were observed; no unrelated tests were weakened to silence them. Initial browser harness failures concerned deliberate dismissed-inspector behavior and benign theme preference POST classification, not broker dispatch; the harness was corrected without changing those product behaviors.

Dependency delta: existing shared Storybook/package/MCP dirty files were inspected read-only. This lane owns its own pinned dev dependencies and lockfiles. Npm retained lockfile version3, added optional/tooling package nodes, and changed one existing transitive version (`@jridgewell/sourcemap-codec`1.5.5→1.6.0); the large lock diff also includes metadata/layout churn. CRA/CRACO/Tailwind and application dependencies were not replaced. Existing react-day-picker peer skew remains disclosed, not repaired out of scope.

## Acceptance is held

See [disarmed commissioning packet](COMMISSIONING.md) and `../ZED_STATE.md` for producer review gaps, actual model preference/dispatch blocker and operational replay status. Green fixtures/CI cannot establish server-authorized trading, remote native ownership, durable live records, option P&L or profitable options trading. Final Nav visual review, actual authenticated owner/model receipt and accepted Spark producers remain separate gates.
