# Independent screen-context ownership review - 2026-09-27

Verdict: PASS for the scoped stale-screen request identity correction. No production edits by reviewer.

## Independently executed checks

Four fresh adversarial React tests passed using the actual context hook and provider (only transport mocked):

- A new owner publishing exactly the same value survives the old owner's unmount. Transfer occurs even when no value-change notification is needed.
- StrictMode mount/effect replay, ticker update and unmount leave the correct context and ultimately unknown.
- An older publisher turning inactive cannot clear a newer active screen's context.
- An in-flight submitted request and saved answer remain SPY after current context switches to QQQ and then unmounts. A later generic ask without a supported screen is blocked and no extra request is sent.

Evidence: `output/screen-context-independent-20260927.json` (4/4) and `output/screen-context-independent-20260927.test.jsx`. The scratch test was moved out of frontend source after its run; no reviewer file remains in the normal source tree. An initial command used the wrong working-directory-relative path and ran zero tests; the corrected run above is the passing evidence.

The actual mounted grid -> chain -> grid regression, existing context tests and provider test also passed independently: `output/screen-context-mounted-independent-20260927.json`, 7/7 across three suites. The mounted regression blocks a generic ask after SPY grid is replaced by QQQ OptionsChainTable and restores a QQQ/days:7 request after returning to the supported grid.

## Source refutation

The stable per-hook token survives renders and StrictMode replay. Publishing updates currentOwner even for an equal-value handoff. Unmount/inactive cleanup releases only the current matching token; a departing older owner cannot erase the new view. Layout effect publishes before ordinary user interaction with a newly committed view. Tidehunter explicitly passes null while inactive. AgentProvider deep-copies the context before submission; saved turns and the active saved answer are not relabeled from live selection. Unsupported views honestly refuse a new generic ask instead of reusing the previous ticker.

No scoped blocker was found. Tests validate React-mounted behavior with local mocks, not browser rendering or real external model execution. This does not add chain-page research support or establish arbitrary multiple simultaneous active publishers as a supported product state.

## Source SHA-256

- `frontend/src/agent/useScreenContext.js`: `03e598fddf500b62ef1adef6a9f0d1cae1b419bf6ca8b22e37e41723bfaa650e`
- `frontend/src/agent/AgentProvider.jsx`: `2e0e10e978f7a05e86429f04a09b6ade092cfbbbfc6e711f4f4b770e493e92d9`
- `frontend/src/components/heatseeker/SkylitDashboard.jsx`: `b5e21622641b319f57077dab20fc9bd1d648c3f54fff53151ab5d9fe7296994e`
- `frontend/src/components/flowseeker/FlowseekerProBlademap.jsx`: `46c6a83f79114a8ab15f6b18b6b92c3165ee47d78f03eb56278680a367cc92f5`
- `frontend/src/agent/ScreenContextLifecycle.test.jsx`: `8a181fc0004df78694f88e41294721f6cef413bbbb3e44f559f1d8976a33d6d0`
