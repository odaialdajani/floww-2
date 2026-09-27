# Research request rejection verification - 2026-09-27

## Change and reproduced failure

The app previously discarded useful HTTP422 validation reasons. Reproduction covered too many tickers, conflicting explicit expiries and unsupported chart context. The first repair exposed two additional failures: a never-ending response body left the app asking forever, and cancelling that known rejection left it cancelling. Both failures were reproduced before the bounded-read repair; original red logs are preserved in output/research-refusal-red-20260927.json and output/research-refusal-body-red-20260927.json.

Live research and saved-result review now share requestFailureText. Only a nonblank string HTTP422 detail of at most500untrimmed characters becomes visible, with surrounding whitespace removed. Malformed, unreadable, too-long and non422 errors use the plain fallback. React escapes the text in the actual conversation and review display.

Once HTTP422 has proved rejection, message reading has a three-second bound. Timeout aborts the body and shows the fallback. Cancel settles cancelled immediately; disconnect, supersession and unmount release the read and clear its timer. A late body cannot change newer state. Cancellation before admission is known preserves the existing request until its actual outcome is known; accepted turns keep their existing turn-specific cancellation. This repair does not claim all successful-response or session fetches are time-bounded.

## Evidence

-20focused hook/provider/conversation checks passed, including the two reproduced stalled-body cases.
-99frontend suites /861tests passed; process exited0. A transient one-second open-handle warning appeared before normal process exit; no force-exit was used.
-Isolated production build exited0 and compiled successfully, without replacing the running build. Existing large-bundle and Node deprecation warnings remain.
-13offline display tests and35backend export/control tests passed. Ruff and git diff whitespace checks passed.
-Three actual HTTP requests through the real local route and fresh isolated Mongo store returned422: too many tickers, conflicting dates and unsupported chart mode. They created0turns, performed0snapshot/source reads,0model calls and0provider calls. Their returned reasons were passed through the actual renderer command:3visible alerts and9retained slots; all three returned messages appeared. These are development-only questions, not frozen acceptance questions.
-The source hashes, proof and rendered receipt are in [proof](research-request-refusal-proof-20260927.json). Actual request evidence is output/research-refusal-http-development-final-20260927; rendered artifact is output/research-refusal-rendered-final-20260927/answers.html. Full test/build logs use research-refusal-full-ui-final-20260927.log and research-refusal-build-final-20260927.log under output.
-The [independent review](research-request-refusal-review-20260927.md) tested parity and timing boundaries on the current source. Its updated bounded-body probe covers cancellation before headers with later rejection or acceptance, exact timeout, disconnect/unmount/supersession cleanup and ignored late bodies.

## Limits and next work

No frozen comparison answers, new model calls, provider calls, app restart, deployment, trading activation or browser-policy workaround occurred. Browser visual inspection remains unverified because the earlier attempt was denied by browser URL policy; mounted DOM checks and offline HTML are not paint evidence.

The previous critical receipt is now stale because backend sources changed. Current actual prepare returned blocked with the stale-source reason and the existing unanswered stronger-model/cost choices;0model calls. Original evidence remains unchanged. Refresh the critical proof only after selecting a stable intended source before execution. There is no new acceptance seal or comparison grade.

The wider AI/UI plans remain incomplete. See [remaining work](../../REMAINING_WORK.md) for paper setup, watches/briefs, outcomes, historic coverage and unverified prerequisites. Paper preparation is concurrent, separately owned and remains unmounted/default-denied.
