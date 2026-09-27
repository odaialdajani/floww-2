# Independent research request refusal review - 2026-09-27

## Bounded verdict

PASS for the current bounded response-read correction and saved-result display parity, rechecked at 2026-09-27 00:54 UTC. No concrete new defect found in the inspected response-message change. Source remained read-only; reviewer added only this report and output/research-refusal-review-20260927 proofs. No model/provider calls, new comparison answers, changed frozen answers, commits, browser-policy workarounds, or trading actions.

This review follows hard-tasks: inspected the actual helper, request hook, provider, conversation and renderer; attempted to refute timing, escaping, private-error protection and live/offline parity with independent mounted probes. Parent owns broader build and frontend tests.

## What was verified

The live request path and offline refusal adapter call the same helper. It exposes only a nonblank string detail from HTTP 422 when its untrimmed length is at most 500, and trims visible whitespace. Other statuses, malformed/empty details and unreadable JSON retain the generic message. Internal non-422 response JSON is not read by the live hook. Both actual conversation and offline adapter render alert text as escaped React text.

Independent live/offline parity checks use actual AgentProvider and AgentConversation with mocked request responses and model settings disabled. Offline comparison text is derived from actual rendered HTML, then compared to the live mounted alert for ten inputs: padded text, hostile-looking markup, whitespace, validation array, null body, 500-character string, 501-character string, HTTP 500 private detail, HTTP 401 private detail, and unreadable 422 JSON. All match; no script/image element, new research answer or saved-answer fetch appears. This proves the tested local code paths, not a live server connection.

Delayed 422 body resolution after disconnect, unmount or a newer completed request produces no stale error event and cannot overwrite the newer saved answer. Cancel during known rejected 422 body parsing now finishes immediately as cancelled, releases the pending read and aborts that rejected request; it never fetches an answer or cancels a nonexistent turn. A rejection is not converted to a completed answer.

Renderer binds six actually compiled source files including requestFailure.js, plus three supporting live-refusal-path files, renderer, package manifest and lock: twelve identities. Existing renderer tests reject missing/mismatched identities and old free-text refusal input. Its refusal input is now the actual response structure {status, body}. Previous display-review conclusions about a permanently generic 422 message are superseded for these new hashes; older result files remain historical and were not rewritten.

## Executed checks

- Current independent probes: 21/21 PASS, one suite, exit 0; output/research-refusal-review-20260927/independent-bounded-body.log.
- Current existing request hook, provider and conversation suites: 20/20 PASS, three suites, exit 0; existing-bounded-body.log.
- Current offline renderer checks: 13/13 PASS, exit 0; renderer-bounded-body.log.
- Current total: 54 passing checks. All subprocesses used windowsHide:true.
- Independent deadline probes confirm no result at 2999 ms, exactly one generic rejection at 3000 ms, aborted response read, explicit clearing of the specific three-second timer, and ignored late detail. Detail resolving at 2999 ms instead clears the timer, preserves its useful message and is never aborted later.
- Disconnect, unmount and supersession settle a stuck rejected read immediately and clear its timer. Cancellation before headers does not abort unknown admission: a later rejected response aborts safely without parsing; a later accepted response cancels its actual turn.
- Earlier scratch setup had classic/automatic JSX mismatch, fixed only in scratch configuration. A new initial timer-count assertion included React bookkeeping; the corrected probe tracks the actual 3000 ms timer and proves its clearTimeout call. Neither was a product failure.

## Exact reviewed hashes

- frontend/src/agent/requestFailure.js = 9ea2d199048dec651ad24c9ac2e3c91190499d82c45dab2dd99aa62bb08ae10e
- frontend/src/agent/useAgentStream.js = 19583af4aa4f506712629a69ce957bde579429181973434815c6b43f15dda85a
- frontend/src/agent/AgentProvider.jsx = 00a3f4489d386ba11dd5e8e04cab53656db5401baebbeaed841b3c089415c55f
- frontend/src/agent/AgentConversation.jsx = f5312c951cd47674b1bf1a16f691eb9854b634dc561e9ff572ea1099153166ba
- frontend/src/agent/useAgentStream.test.js = 3c5bed356de3c13e21ff81dd320d1ee10e1ae4a18e25930015666856e54bdafd
- frontend/src/agent/AgentConversation.test.jsx = 0fd16e4a6acd5dad4b687c39e2fae2ac24da74959a0ec9a41fbc36ab6ae00c34
- frontend/src/agent/AgentProvider.test.jsx = eabb7a56866f990625b96d139c4cf05ec979895771ef93a1bafd192c2df8a55d
- frontend/scripts/render-comparison-packet.cjs = ef4d5b3debbeecb1195526e8cacb1bb75ea7aa666f25bc17d3ec59769ac819c7
- frontend/scripts/render-comparison-packet.test.cjs = 5cd9177d3f528196685acb9c12debfa7bee4004a0d2b9c6e97ab0d7bdbd759df
- frontend/src/agent/AgentPanelAnswer.jsx = b6d551d2da629c18b8eae94f7c31935a24c06cbe6d6183c0c7a3140e8fdb47e4
- frontend/src/agent/Evidence.jsx = 2607afa45399216ff7d8f3df4f5da40669567edfcf74a8c11ab9a4143099e367
- frontend/src/agent/AgentModelSettings.jsx = 609949a63f34489d232cac5074945b2ca4acbc769f1ef773d88e9776f5eab7cf
- frontend/src/agent/chartReading.js = 823642f348f9a16ec0faac2c60ad2c6f01347cd9d5bc882bb8c2d090e488906f
- frontend/src/config/api.js = 228ead5144e070970d8ddab45b37d97b6973f77deb16885b0ebc45fb8e5f1836
- frontend/package.json = 28e06db891b5850a36ec4e045899622be2796a30538478f9f5432f8e2e9bcf95
- frontend/package-lock.json = 52fde7e36a30985dbf7cd3127694a6c839492a9d7daaa2c9016eaadab994c3cc

## Limits

The earlier known-422 body liveness limitation is CLOSED at the current hook hash. A three-second bound and explicit release on cancel/stop are independently verified with a body promise that never resolves until after the action. Unknown admission before headers and successful-response body reads retain prior behavior; this review does not claim a universal request timeout. Timer cleanup is checked for this new rejected-body timer, not every timer or browser transport resource.

Browser paint and physical interaction remain unverified: parent reported that the in-app browser was unavailable and Chrome file navigation was denied by browser URL security policy. No workaround was attempted. Mounted React/DOM tests and offline HTML inspection are not browser-paint evidence.

Manifest and lock identities do not attest installed dependency bytes. Model/provider metadata is masked in review output, but preserved answer/evidence text may still identify sources. No new usefulness grade, complete comparison acceptance, timing result, activation permission or release approval follows from these tests.
