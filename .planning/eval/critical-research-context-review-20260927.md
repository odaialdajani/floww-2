# Critical research context review - 2026-09-27

## Verdict: one reproduced high-impact wrong-context defect

CORRECTED; see screen-context-ownership-review-20260927.md and the final accuracy verification. Original finding: leaving the Solstice grid can retain its previous ticker, expiry horizon, selected-map axes and observation time as the context for a new research request from a different visible view. This is a new request built from stale view state, not the intentional retention of an already saved answer. The backend sees the stale fields as internally consistent and does not detect the mismatch.

## Exact reproduction

1. Open the normal Solstice grid for SPY with 0DTE. The actual SkylitDashboard publishes screen ticker SPY, horizon 0dte, current raw-map identity and its expiry/strike axes.
2. Switch the main Solstice view to Chain. App.js removes SkylitDashboard and mounts OptionsChainTable, while retaining AppShell and its AgentProvider, research panel and Ask button.
3. Change the visible ticker to QQQ and choose chain expiry 2026-10-02. The chain fetch uses QQQ and its expiry control shows the selected date.
4. Open Lodestar and ask What changed? with no explicit symbol in the question.
5. The request sends ticker SPY and horizon 0dte, with the old SPY map version/axes/time. The desired assertion submitted.ticker === QQQ fails; received SPY. A synthetic completed response is displayed as SPY / 0dte, even though the surrounding mounted chain is QQQ.

Mounted reproduction used the actual AppShell, AgentProvider, AgentPanel, AgentConversation, useAgentStream, SkylitDashboard publisher, OptionsChainTable and context store. The test reproduces the conditional child lifecycle verified in App.js; it does not mount the entire App entry. Unrelated grid children/model settings and all transports were mocked. No backend/provider/model research execution was performed. Temporary proof: C:/Users/DARK HERO/AppData/Local/Temp/floww-context-review-hZbnnz/context.test.jsx, with jest.config.json alongside. Node/Jest was launched via spawnSync with windowsHide:true. One test FAIL, exit1, at the intended wrong-ticker assertion.

Captured submitted fields:

- Visible chain: ticker QQQ, selected expiry 2026-10-02.
- Request: question What changed?, ticker SPY, horizon 0dte.
- Frozen screen: page heatseeker, ticker SPY, dte 0dte, displayMode live, overlayMetric raw, mode 5m, expiries 4.
- Old mapQuery: expiries 4, mode day, dte 0.
- Old mapVersion: 2026-09-27T14:00:00Z.
- Old observedAt: 2026-09-27T13:59:50Z.
- Old mapStrikes: [650]; mapExpiries: [2026-09-28].

Independent backend pure-function check invoked request_spec with the reproduced stale symbol/horizon/map fields, without repository/HTTP/model calls. It succeeds with {ticker:SPY, tickers:[SPY], horizon:0dte, context_conflict:false}; Python exit0. This is admission-shape validation, not proof that any real research result was produced.

## Cause and scope

- useScreenContext.js lines2-8 holds a module-global current value. Publishers replace it, but there is no ownership/lifetime release.
- SkylitDashboard.jsx lines372-379 publishes in an effect without an unmount cleanup.
- App.js lines974-975 mounts OptionsChainTable instead of the publishing grid when Chain is chosen. Only the grid and Tidehunter currently publish research screen context; Chain, Bars, Multi and other shell routes do not.
- AppShell.jsx lines38-54 keeps the research provider/panel/button mounted independently of the active page/view.
- AgentProvider.jsx lines29-35 checks only that context.ticker exists, then freezes and submits the orphaned old context.
- backend/services/agent/contracts.py accepts that self-consistent old context; it cannot know which view is currently on screen.

Sibling exposure: leaving the grid for Bars/Multi/Profile or leaving either publishing page for a nonpublishing route can retain the old source. Those siblings are source-backed, not separately mounted reproductions in this review. Price-history-open and replay refusal protections do not solve publisher unmount lifetime.

## Minimal safe correction

Fail closed when a view that owns the research selection leaves. Give each publisher an ownership token/lifetime and clear or mark its context unavailable on cleanup only if that publisher still owns the current value. Scope current research eligibility to the active page/view, and have AgentProvider refuse new work when that selection is unavailable. This prevents an older publisher cleanup from erasing a newer publisher selection. For Chain/Bars/Multi support, separately publish their real selected ticker/expiry/time with an explicitly supported data basis; do not copy the old grid map identity into them. The smallest safe fix is to block asking from unsupported views after clearing the orphaned context.

Required regression: mount actual grid SPY/0DTE, switch to actual chain QQQ/different expiry while shell survives, then attempt a generic question. Either send the current supported chain identity or send no request with an explicit unavailable-view message. Also verify reentering a supported grid restores asking and old cleanup cannot wipe the new publisher. No source changes made by this reviewer.

## Exact inspected source hashes

- frontend/src/agent/useScreenContext.js = cf13ac826a05a552022ed22602eedebf9eff080fbdbef77cda4b0971284313f2
- frontend/src/agent/AgentProvider.jsx = 00a3f4489d386ba11dd5e8e04cab53656db5401baebbeaed841b3c089415c55f
- frontend/src/shell/AppShell.jsx = 08fa6bb12e299e1e3c61e062c29aa25683fc1078786bdb0cee2991205e06d164
- frontend/src/components/heatseeker/SkylitDashboard.jsx = b5c50ff5f6b05105f73b39313cc13d56f96d3c08b855a9b5e5b0f40f54fcd207
- frontend/src/components/OptionsChainTable.jsx = b9c5e11d3391891822fce40f4349375f32aab94e12ac779f18f3f0416e4f40a4
- frontend/src/App.js = cd6831b6f427fbfc414c622b55ac057c5355af8cc9045157702b3c17bb6e6755
- backend/services/agent/contracts.py = 6ac9434175ae6b02101a628271710515dc0d08d2ba688d113f7ec7dd66402273

## Limits

This is a bounded functional/context finding, not CSS polish, process cleanup, broad provider validation, all-route certification, or browser-paint acceptance. No user app was restarted and no providers/models were called. Existing saved answers and frozen comparison results were not changed.
