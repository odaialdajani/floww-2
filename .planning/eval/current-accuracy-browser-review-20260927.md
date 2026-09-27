# Current source browser review - 2026-09-27

Result: PASS for the three scoped rendered behaviors. Performed in actual Chrome with current source components bundled in a separate local fixture. No production source edits by this reviewer.

## Evidence

Artifacts: `output/playwright/current-accuracy-20260927/`.

- `01-unknown.png` and `.txt`: actual SolsticeStatusStrip displays `UNKNOWN` with `incomplete options data`, including when provider quality says `Data usable`. Expanded actual WallInspector displays `Options data is incomplete; no reliable sign or zero-gamma level is available.`
- `02-expiry.txt`: actual OptionsChainTable changes from three strikes 90/100/110 to two strikes 100/110 after selecting 2026-10-02.
- `03-filter-sort.png` and `.txt`: descending strike button changes those two filtered rows to 110/100. This verifies visible row changes, not only filter control state.
- `04-chain-refused.png` and `.txt`, `05-refusal-zero-requests.txt`: actual AppShell/AgentProvider retained across actual SkylitDashboard SPY unmount and actual OptionsChainTable QQQ mount. Generic question gets `Open the Solstice grid or Tidehunter to ask about the current selection.` Local request counter remains zero.
- `06-qqq-grid-accepted.png` and `.txt`, `07-accepted-request.txt`: reentering actual SkylitDashboard for QQQ shows `Selected: QQQ · days:7`; submitting a new question captures one request with ticker QQQ and horizon days:7, then displays the synthetic saved QQQ answer.

## Scope and limits

Fixture imports real AppShell, AgentProvider, screen context hooks, SkylitDashboard, OptionsChainTable, SolsticeStatusStrip and WallInspector, plus real research panel/stream components. Unrelated heavy visual children and sidebar/settings were replaced with empty components. Public-chain data, axios calls and fetch responses were replaced locally with synthetic responses; no provider, model, backend service, or live store was called. Source CSS is used with a small fixture header/layout override; screenshots are evidence of these behaviors, not a full production layout audit.

This browser check does not independently verify backend missing-IV calculation, exhaustive chain filters, or the worker's later expiry reset change. Those are covered separately. The refusal message remains visible after reentering a supported grid until asking again; the selected ticker is correct, and asking clears the old message. This is minor retained error feedback, not a stale ticker submission.

Fixture build started at approximately 02:19 UTC; final source hashes are in `source-hashes.json`. Fixture server listened only on 127.0.0.1:43187 and was stopped after screenshots; the created browser tab was closed. User application windows and services were untouched.

## Follow-up chart accuracy proof - 02:25 UTC

Result: PASS. Additional isolated browser entry `charts.jsx` imports real current BarHeatmap and VolumeProfileGrid directly. Build was run after both source owners confirmed final edits, including the BarHeatmap extra-selected-expiry correction. Exact prebuild SHA-256 hashes are saved in `charts-source-hashes.json`. No source components were mocked for this check; fixture layout supplies the bar flex utilities and surrounding cards. No network-dependent data sources are used.

`08-charts.png` and `08-charts.txt` visibly confirm:

- VEX zero alongside GEX 900000 displays 0 and no colored bar.
- Missing charm alongside GEX 900000 displays Unavailable and no colored bar.
- Selected VEX grid -50 plus -25 produces the left/negative bar; accessible value is -75 despite old row +123.
- Selected VEX 50 plus missing expiry displays Unavailable and no surviving partial bar.
- GEX zero has no colored bar; missing GEX displays Unavailable.
- Selected VEX expiry absent from the raw axes remains included: +50 and -200 produce the left/negative bar and accessible -150 value.

`09-profile.png` and the profile section of `08-charts.txt` confirm real zero/zero strike 102 stays 0/0 and is the only AIR row. Null/zero strike 101, absent/zero strike 100 and 1/null strike 99 show unavailable dashes at the missing cell and have no AIR labels. The explanatory status says incomplete rows are not marked AIR; total air count is exactly one. Complete strike 103 remains 1.0K/1.0K.

Temporary server and browser tab were closed after capture. This is a display-correctness check against synthetic values, not independent validation of any financial exposure formula.
