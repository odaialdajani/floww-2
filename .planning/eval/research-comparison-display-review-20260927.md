# Research comparison display independent review - 2026-09-27

## Scope and result

PASS for the narrowly scoped offline display adapter, with the limits below. Reviewed and changed only frontend/scripts/render-comparison-packet.cjs, its .test.cjs, this report, and explicitly requested synthetic development output. No product source, model/provider call, frozen evaluation answer, commit, or trading activation was touched. All spawned commands used windowsHide:true.

Hard-tasks proof target: reject comparison display whenever the sealed identities differ from the actual compiled source closure or required supporting files, while preserving saved evidence and visibly incomplete outcomes. Root separately reviewed the identity gate and confirmed the installed-dependency limit.

## Reproduced findings and fixes

1. CLOSED: legacy ledger evidence was lost by masking. Original Evidence supports turn.ledger when answer.facts is absent; maskedTurn omitted it. An independent probe failed with missing 987.65 USD and coverage text. Ledger is now cloned and retained.

2. CLOSED: comparison packets did not require expected display identities, did not reject incomplete identity sets, and did not record binding. Three independent probes failed before correction. Comparison now requires expected_display.files, checks supported safe relative paths and SHA-256 values before loading, recompiles its source closure on each call rather than trusting an earlier require cache, compares exact identity keys/hashes before markup, then checks file bytes again after markup. Extra compiled-source expectations and missing source entries both fail. Development may omit expected_display.

3. Refusal fidelity: reviewed actual non-OK request path in useAgentStream, AgentProvider, AgentConversation. Actual visible message is Research request could not start, passed unchanged to a role=alert paragraph. These three source files are mandatory supporting identities, not compiled closure entries. Adapter refusal now also uses role=alert; root exporter is responsible for passing exactly the visible message instead of richer server-only detail. Final synthetic artifact uses the actual generic text.

## Checks run

Initial independent red run: 4 pass / 4 fail, proving ledger loss and the missing comparison binding. After repairs and expanded probes: 12 tests PASS, 0 fail, Node test runner exit 0. Command: node --test frontend/scripts/render-comparison-packet.test.cjs, launched through hidden spawnSync.

Coverage: actual answer component plus explanations; model/provider metadata omission and input immutability; escaped answer/question/refusal text and restrictive content policy; each unfinished outcome plus rejection of attached successful answers; 32-case cardinality and distinct masked arm labels; ledger fallback; missing or incorrect hash for every required identity; missing/surplus source closure and traversal; valid synthetic 32-case display producing 96 arms; a mocked file-byte change after answer preparation rejected by final identity check; stale evidence status/time/source/coverage/gaps/referenced facts; real development command creating HTML/receipt and refusing overwrite while existing bytes remain unchanged. The 32-case success fixture repeats synthetic development content; it is not any of the frozen evaluation answers.

## Inspectable development output

Final HTML: output/research-display-development-20260927-final/answers.html. Input: output/research-display-development-20260927-final.json. Receipt is alongside final HTML. Two synthetic cases show saved answer, stale/partial evidence, explanatory details, ledger fallback, failed, unknown, unrun and generic refused request. HTML SHA-256: b3e915d69322f8b9b0df4c17549e0d52032e5852a985e10c579009a20b575fb3. Root owns actual browser inspection; this reviewer inspected rendered HTML through jsdom and exercised the real command. Earlier output/research-display-development-20260927 is superseded and has an older renderer identity.

## Exact tested identities

Compiled closure is exactly the five answer-related source files recorded below. Required supporting files add refusal-path source, renderer, package manifest and lock. Paths below are relative to frontend.

- src/agent/AgentPanelAnswer.jsx = b6d551d2da629c18b8eae94f7c31935a24c06cbe6d6183c0c7a3140e8fdb47e4
- src/agent/Evidence.jsx = 2607afa45399216ff7d8f3df4f5da40669567edfcf74a8c11ab9a4143099e367
- src/agent/AgentModelSettings.jsx = 609949a63f34489d232cac5074945b2ca4acbc769f1ef773d88e9776f5eab7cf
- src/config/api.js = 228ead5144e070970d8ddab45b37d97b6973f77deb16885b0ebc45fb8e5f1836
- src/agent/chartReading.js = 823642f348f9a16ec0faac2c60ad2c6f01347cd9d5bc882bb8c2d090e488906f
- scripts/render-comparison-packet.cjs = 06dc19325d7889851e90e31fca6c8680af9f493f94f61df7f8cc6d1598eb5ea8
- package.json = 28e06db891b5850a36ec4e045899622be2796a30538478f9f5432f8e2e9bcf95
- package-lock.json = 52fde7e36a30985dbf7cd3127694a6c839492a9d7daaa2c9016eaadab994c3cc
- src/agent/useAgentStream.js = 69247fe1600e7327a4c90a60a3bbaaef216794784767707ef47ac93dc2f1d4e2
- src/agent/AgentProvider.jsx = 00a3f4489d386ba11dd5e8e04cab53656db5401baebbeaed841b3c089415c55f
- src/agent/AgentConversation.jsx = f5312c951cd47674b1bf1a16f691eb9854b634dc561e9ff572ea1099153166ba
- scripts/render-comparison-packet.test.cjs = 5d12ceed19a6ca2fd4a916b644d838fd67d8c12e6906888ae0d65e21915c4f0a

## Limits and handoff

Only model/provider metadata labels are masked. Answer text, evidence source, raw saved values and coverage are intentionally preserved and can themselves reveal a source or provider. This is not a guarantee that content is impossible to identify. Input packet remains PRIVATE; only rendered HTML should reach blind graders. Receipt hashes and local environment versions are provenance, not grades.

Manifest and lock hashes do not prove installed dependency bytes. Actual React and Node versions are recorded, but this review does not attest the full dependency tree. Source identities prevent accidental code drift relative to the seal, not a malicious actor rewriting both the seal and artifact. Root owns sealed exporter validation and result provenance.

Native details are inspectable in the artifact, but review styling is not the full application stylesheet. No first browser display time, physical browser paint, accessibility certification, usefulness grade, equal-arm performance comparison, release acceptance or live authorization is claimed. No remaining blocker found inside the reviewed adapter scope; generic refusal usefulness must be judged as actually shown, not improved for review.
