# Blind export control review - 2026-09-27

Status: REVIEWED_FINDINGS_CLOSED_DEVELOPMENT_PROOF_PASS. No remaining concrete export control defect was established in this bounded review. This is not frozen-comparison, usefulness, browser-display or release acceptance.

Scope: `backend/scripts/research_comparison_export.py`, its development tests, and prospective display-source binding changes in `research_comparison_run.py` and its tests. Renderer behavior has a separate reviewer. This review owns only this report and its output proofs; source edits remain with root. No frozen functional research answer, model or upstream provider was executed. A later authorized proof saved one development-only price answer in a new isolated local Mongo store, as recorded below.

## Reproduced findings

### Completed bytes were not bound to their actual request and turn

The original exporter checked the outer result ID, final result hash and success booleans, but did not bind the embedded saved turn to the frozen question/request or admitted turn identity. The reviewer created an invented development result with the correct outer case ID/hash, a different saved question and ticker/spec, a foreign turn ID, and foreign stronger-model settings. Existing before-request/admitted sidecars still named the original request/turn. Export succeeded and put the unrelated saved answer under the original frozen question and deterministic arm label.

Evidence: `output/research-export-review-20260927/probe.py` and its `probe-results.json`, variant `foreign_question_and_turn`. This does not rely on model execution or modifying the frozen question set. Root repaired prospective request-spec freezing and export binding to the exact saved specification, question/ticker/horizon, candidate settings, and consistent before-request/admitted owner/request/turn records. The independent recheck separately substitutes a foreign question, turn ID and selected model; each is refused at the intended identity check.

### Exported refusal detail was not actual visible refusal text

The original exporter displayed the backend's 422 `detail`. The actual UI's `useAgentStream` throws the fixed message `Research request could not start` without reading response detail; `AgentProvider` carries that text to `AgentConversation`'s visible alert. An invented refusal exported `Detailed backend-only refusal`, proving the exported text differed from this current user-visible path. The initial display-source list also omitted that refusal path.

Evidence: the same probe output, variant `refusal_backend_text`, plus source inspection of `useAgentStream.js`, `AgentProvider.jsx` and `AgentConversation.jsx`. Root repaired export to preserve the current generic visible message while retaining raw backend detail privately; the three supporting refusal-display sources are now included in the prospective display identity. An independent recheck verifies the exact generic text and absence of the richer backend detail from the render packet. This does not claim the generic refusal earns the proposal's requested usefulness; grading must assess the actual text. Product UI behavior was not changed for this repair.

## Checks already performed

The reviewer independently ran `.venv/Scripts/python.exe -X utf8 -m pytest tests/agent/test_comparison_export.py tests/agent/test_comparison_run.py --noconftest -o addopts= -q` from `backend` on Python 3.11.15: 27 passed, 0 failed/skipped, one existing Hypothesis warning, in 2.76 seconds. This initial run does not close the counterexamples absent focused repair rechecks.

The reviewer inspected the complete export path and existing assertions for ordered 32-case preservation, 96 answer slots, one-to-one frozen blind assignment, same-directory reuse refusal, changed result hash rejection, final completion consistency, wrong-arm refusal, started-versus-not-run handling, failed-answer withholding, and conservative absence of a final manifest. Missing arms remain represented in all slots. The private packet/receipt carry unmasked evidence and identities; only the renderer's masked HTML is intended for blind graders.

A third probe used a malformed started marker with no final manifest. Export retained `started_outcome_unknown` and withheld the existing answer. That is conservative uncertainty, not a demonstrated success-labeling defect; no new gate was requested from it. Missing-final snapshots neither prove a process stopped nor authorize a retry.

## Final independent recheck

The same development suite was rerun after repair: **35 passed, 0 failed/skipped, one existing Hypothesis warning in 2.96 seconds**. The reviewer read all output and the added assertion bodies. Four independent counterexample rechecks also passed; see `output/research-export-review-20260927/recheck.py` and `recheck-results.json`. They verify foreign-question refusal, foreign-turn refusal, foreign-model refusal, and the actual generic visible refusal while retaining all 96 slots. These are distinct from merely repeating root's tests.

The updated preparation binds the actual request specification for every admitted case and `None` for expected pre-admission refusals. It rejects unexpected admission/refusal during binding. Display identities are compared again at preparation completion and seal verification. Export does not recalculate historical answers using changed production logic; it compares their saved specification to the prospective frozen specification.

## Actual saved-answer command proof

An initial CLI check used invented saved-result JSON only; it is weaker evidence and is not substituted for the following proof.

The reviewer then ran `output/research-export-review-20260927/real_prepare.py`. It created a clearly labeled development-control seal before work, one development SPY price question, and 31 unrun placeholder questions. This is not the frozen comparison or an authorization seal. The script used production `transport.exercise`, actual loopback HTTP, actual session/request admission, production saved-turn storage, and a new isolated Mongo store on 127.0.0.1:27017 (server 8.0.32). It saved the real before-request/admitted sidecars, verified exact saved request specification and price 123.45, reopened the result, and observed one source read with zero model entries. External socket entry points were guarded to loopback only.

Using the recorded development arguments, the reviewer executed the actual `python -m scripts.research_comparison_export` command, then the actual `node scripts/render-comparison-packet.cjs` command. Both succeeded. Artifacts are under `output/research-export-review-20260927/real-development/`:

- `deterministic/`: actual saved result, admission sidecars, initial and final denominator records.
- `export/`: private render input and export receipt.
- `rendered/`: produced `answers.html` and renderer receipt.
- `verification.json`: independently checked artifact counts and hashes.

Verified result: **32 case rows, 96 arm slots, exactly one executed development answer, and 95 explicit unrun slots**. HTML contains 32 case elements, 96 arm elements, 95 explicit “No completed answer: not run” messages, and the actual saved price. Renderer input-file and HTML hashes match their receipts. Browser first display remains null; no browser-paint or usefulness grade is claimed. The actual isolated store and output artifacts are retained, with no existing store/process removed or restarted.

| Reviewed file or proof | SHA-256 |
| --- | --- |
| `backend/scripts/research_comparison_export.py` | `3070bc42fbff866c0732d731aa199ae80ef59717ac08b16809707807d4f49e1b` |
| `backend/tests/agent/test_comparison_export.py` | `1d3fb35f0171f1042373a1b7966a74a6ef010071239fb92012d60b22b2e88bba` |
| `backend/scripts/research_comparison_run.py` | `1c1cf334796466cb98ee9cb65fd73c4db1d3fb8ffe42d8e49464c9d0bb23baf2` |
| `backend/tests/agent/test_comparison_run.py` | `04f7ae5e91c145e3370164f325298184df118bfffbdf59b9b59950e33e1c4f45` |
| `real-development/export/private-render-input.json` | `b73c5ab9b498ec45c5ee65b2b545d3524e492d97c734b95a332537e5f234d00a` |
| `real-development/rendered/answers.html` | `4fd6c3fa9d3b36fcbf0faa4a5acec3f62df499d960852dc4007acaceb781b215` |

The last two paths are relative to this review's output directory. Actual renderer and supporting display hashes are preserved in the development seal and renderer receipt; the independent renderer review remains separately authoritative for masking/rendering behavior. No new release gate was introduced, and existing raw-evidence, critical-proof, user-choice and comparison requirements remain unchanged.
