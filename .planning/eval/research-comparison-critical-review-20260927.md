# Deterministic critical proof review - 2026-09-27

Verdict: **14 declared critical cases pass in the final independently executed synthetic/local proof; 17 test variants pass.** The review found no remaining concrete control defect in the inspected recipe assertions. This does not approve the 32 functional comparison answers, candidate usefulness, browser paint, database crash recovery or production backup. No new gates were added.

## Independent execution and identity

The reviewer inspected `backend/tests/agent/test_comparison_critical.py`, `backend/scripts/verify_research_comparison_critical.py`, all 14 declared recipes in the revision 3 proposal, and the earlier critical-binding inventory. The reviewer independently executed the verifier twice on new output directories using `backend/.venv/Scripts/python.exe` (Python 3.11.15), owned loopback listeners and new isolated stores. No frozen functional question, real model, upstream provider, shared allowance modification or existing process interruption was performed.

The initial independent run passed 17 checks in 8.96 seconds. Review found that the local-only socket guard covered `connect` but omitted `connect_ex`. Root repaired both entry points; no actual external request was demonstrated. Because that changed the source identity, the final verifier was rerun rather than relabeling the older receipt.

Final command, from `backend`: `.venv/Scripts/python.exe -X utf8 -m scripts.verify_research_comparison_critical --output ../output/research-critical-review-20260927-0010-final`.

Final result: **17 passed, 0 failed, 0 skipped, 29 warnings in 9.01 seconds**. The receipt has 14 ordered case IDs, all passed, expected cancellation variants 4, exactly 3 measured fixture-model entries, zero real model/provider calls, and `source_unchanged: true`. Existing warnings do not count as skipped tests. All captured pytest output was read. Mongo reported version 8.0.32. Both deliberately terminated owned child processes returned exit code 73.

| Artifact | SHA-256 |
| --- | --- |
| `backend/tests/agent/test_comparison_critical.py` | `769e2819ac970591b7b9126d98ef33fde081c581b4da8576364a46a71b3db93f` |
| `backend/scripts/verify_research_comparison_critical.py` | `52106cb83f6fae67a9c3cb5c0456936bad72b53bc54b85092ede4c521778d199` |
| `.planning/eval/research-fresh-comparison-proposal-20260926-v3.json` | `305a42af3a8d86ed8e39ad314a99c592ad2fb57ccab53faf575e507e3aa71c2b` |
| `output/research-critical-review-20260927-0010-final/receipt.json` | `de2795b946ee991e4588e035228f8aa03e468d7b7b4d0ddc60d52b79ca8a172e` |

The final receipt also records the complete backend source inventory, exact test source, Python executable identity, pytest outcomes and per-test stored properties. The earlier root receipt and initial independent receipt predate the socket-guard repair and are not the final source binding.

## Assertions mapped to the declared recipes

| Declared critical case | Actual checked path and limits |
| --- | --- |
| `critical_missing_price` | Exact TLT request over real HTTP; absent context returns no price fact, an unavailable summary, one entered context callback, zero model entries and identical saved reopen. |
| `critical_four_tickers` | Exact four-symbol request receives 422 before any owned turn, snapshot/source callback or fixture-model entry. |
| `critical_conflicting_expiries` | Exact incompatible QQQ expiry request receives the same measured pre-admission refusal. |
| `critical_exclusion_only` | Exact exclusion-only request receives refusal; no fallback SPY work is admitted. |
| `critical_nonfinite_input` | A NaN raw IWM spot reaches the actual read/snapshot path. The saved turn is failed with no answer, reopens identically, retains two charged reads (context and requested flow), and enters no model. This is not merely input-JSON rejection. |
| `critical_unknown_reference` | One measured single-attempt fixture model supplies a nonexistent fact ID. Actual service validation retains the deterministic facts, records unsupported interpretation, publishes no model sections/relationships and makes zero managed dispatch attempts. A separate assertion confirms the exact unknown-evidence rejection branch. |
| `critical_wrong_comparison` | One fixture-model call supplies individually valid fact IDs with incompatible units. The actual comparison validator rejects `Incompatible comparison scope`, not an earlier malformed/stale-section branch. This binds the incompatible-unit variant; it does not claim three separate unit/ticker/horizon mutation tests. |
| `critical_free_text_claim` | One fixture-model call adds unrestricted numeric/directional script text to an otherwise valid section. The actual validator rejects that field; the saved answer retains deterministic facts and omits the injected text/model sections. No browser script execution is claimed. |
| `critical_other_owner_stop` | While an owned context thread is held, another actual session receives 404 for cancel, turn and stream requests with no answer/activity fields. Original budget remains open; releasing the callback lets the original owner complete. |
| `critical_last_allowance_race` | Two differently owned reservations race the production managed-usage ledger against a new real Mongo store with one synthetic slot. Exactly one wins, an uncertain result stays charged with unknown dollars, and duplicate reservations cannot spend again. This directly exercises usage admission, not an HTTP model dispatch or the shared production allowance. |
| `critical_same_identity_replay` | Exact owner/request/body is resubmitted over real HTTP. It returns the same turn and identical saved answer/activity without extra context reads or tracked work. Changed body gets 409; another owner gets 404. This fixture has no installed real model. |
| `critical_cancel_late_worker` | Four variants exercise held-read cancellation, deadline, immediate prestart cancellation and queued expiry. Entered context/flow reads remain charged and unresolved at termination; late callback return leaves saved terminal state unchanged. Prestart/queued expiry retain complete zero counts. Every variant leaves no tracked tasks or budgets and zero measured fixture-model entries. |
| `critical_crash_unknown_dispatch` | Two new child processes use production repository/usage reservation against distinct real Mongo stores, save acknowledged uncertainty, and exit abruptly with `os._exit(73)` before Python/service cleanup. Parent reopening retains interrupted/no-answer state and charged uncertain usage. Same identity cannot reserve again or schedule reads/model work. One boundary is before dispatch; the other adds an explicitly local durable signal. **Neither boundary invokes an actual model or establishes upstream dispatch.** The Mongo process itself is not crashed. |
| `critical_stream_display_boundary` | Exact DIA price body uses a delayed synthetic read over real HTTP. First received progress precedes terminal receipt; replay on the same actual trace does not reset marks. Reopened saved result is identical, one context read occurred, buffered transport is refused, and browser display remains null. This proves the receipt/display distinction, not rendered visibility. |

## Remaining limits

Most cases use in-memory research storage; only the allowance race and controlled process-interruption cases require actual isolated Mongo. The proof does not merge those levels of evidence. Local dispatch signals and fixture-model entries remain separate from real provider/model calls. The zero-real-call claim follows the inspected deterministic implementations and guarded execution, not inferred billing records.

The final receipt can support the existing critical-preparation binding when its full source inventory still matches. It cannot silently close separate raw-oracle review, stronger-model/cost choices, 32-case execution, blind usefulness grading, browser observation or broader AI/UI work. New isolated test stores and proof outputs are retained; no existing store or running user process was removed or restarted.
