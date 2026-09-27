# Independent transport review - 2026-09-26

Final verdict: PASS for this isolated transport building block after the cleanup fixes below. All seven focused transport tests passed independently against the final reviewed source. Real socket streaming, source-clock separation and development price/refusal paths are demonstrated. The earlier cleanup defects are resolved by the final bounded, shielded cleanup path. This is not a comparison run, model authorization, browser evidence, durable recovery result or release approval.

## Scope

Reviewed `backend/scripts/research_comparison_transport.py` and `backend/tests/agent/test_comparison_transport.py`, with read-only inspection of their measurement, route, research-close and alert-fixture dependencies. No application/proposal edits. Additional probes use development-only SPY price 127.25; none of the frozen 32 questions or candidate answers were run/read. Zero model/provider calls. The probes own their local server, in-memory repository and alert store. Only this report and `output/research-transport-review-*` artifacts were written.

## Blocking finding: exceptional service cleanup leaves the server task alive

In `local_server`, `await service.close()` executes before `server.should_exit = True` and before the bounded worker wait. If service close raises or is cancelled, shutdown signaling is skipped and the outer cleanup only closes the raw socket. Reproduction with an owned development service whose close raises leaves one unfinished `Server.serve` task after context exit. The review probe explicitly cancelled and awaited that task afterward; a Windows aborted-accept warning also occurred.

Evidence: `output/research-transport-review-close-failure.json`: `owned_tasks_remaining_after_context=1`, `probe_cleanup_complete=true` after the probe's explicit recovery.

The same ordering means a noncooperative service task can block `service.close()` indefinitely before the existing five-second server deadline begins. The timeout branch also relies on `wait_for` cancellation of the server before merely setting `force_exit`; it should explicitly account for owned server and connection tasks. Require bounded service cleanup plus an unconditional server-stop/await path even when service cleanup raises, cancellation occurs, or startup fails. Preserve the original failure and record any cleanup failure; close only resources owned by this helper. Add focused cleanup-failure/cancellation tests before accepting the fix.

## Demonstrated behavior

A delayed development snapshot over real loopback HTTP produced first progress receipt at about 0.005 seconds and terminal receipt at about 1.509 seconds. This shows progress was observed before completion rather than buffered until the answer finished. The observer requires actual HTTP transport and reads the stream incrementally. These are client receipt times from shortly before actual ask; they are not browser paint, provider latency or source observation timestamps.

The same probe saved admission at real wall time `2026-09-26T23:34:39.395000+00:00` while the fixture read clock remained `2026-09-28T14:30:00Z`. The snapshot seam injects only the evidence clock; request identity/admission remain real. The source being a declared future synthetic clock does not claim real market freshness. Alert clock changes are confined to fixture operations; deployment environment mutation assumes an isolated serial process and must not be used concurrently with unrelated servers in the same process.

The development price path entered one snapshot, saved one read entry, reopened identically, appeared in its owner's history and returned 404 to a second owner. The development invalid activity overlay returned 422, saved zero turns, entered zero snapshot callbacks and zero model calls. Neither path queried alerts. Evidence: `output/research-transport-review-stream-refusal.json`.

## Measurement and coverage boundaries to preserve

- The existing refusal test name says no reads, but it only checks zero saved turns and alert receipts. Those observations alone do not prove zero chain/map reads. This review's independent snapshot spy demonstrates zero snapshot reads for the development refusal; add direct read-entry evidence to the eventual per-case refusal record/test instead of generalizing alert-only receipts.
- `exercise` returns read metrics only for admitted work. The future runner must record refusal zero-read proof separately and must check read-count completeness/unresolved workers, not just whether `errors` is empty.
- Trace completion means the trace's own pending model entries have settled. It does not mean all acceptance evidence is complete. Browser display, upstream provider request counts and actual dollars correctly remain unavailable. No model wrapper was entered by these probes; live model counting is not proven here.
- A factory is an injection point, not approval. A future caller must supply only the approved candidate and shared allowance, bind its transport observer if managed counts are claimed, and retain failure/lower-bound records. When exceptions prevent a return, a durable trace sink and caller-owned failure record are required; a successful result must not be fabricated.
- Identical immediate reopen plus owner history/privacy demonstrates ordinary persisted-route behavior only. These in-memory probes do not establish process crash/restart recovery, retention or real database durability. Root's separate real-store work is outside this review's evidence.
- A delayed stream probe confirms receipt timing only for the observed development path. A very fast case can finish before subscription; its received progress remains a valid receipt measurement, not proof the user saw progress while work was running.

No frozen evaluation evidence has been exposed by this review. The following intermediate findings are retained as history; the final recheck supersedes their unresolved status.

## First cleanup revision recheck

The revised helper signals listener exit before service close and uses separate bounded waits, addressing the initial failure ordering and unbounded initial wait. A further cancellation probe found one remaining failure: cancellation of the context-owning task while it awaits `asyncio.wait({closing})` skips cancellation/collection of the owned `closing` task. The listener stops but a cooperative close coroutine remains alive after context exit. Evidence: `output/research-transport-review-close-cancellation.json`, `remaining_count=1`. The probe released and awaited its remaining task afterward. Catch cancellation at that boundary, cancel and boundedly collect the close task, retain unconditional server cleanup, and explicitly report/discard the process if either owned task cannot stop. Verdict remains CHANGES REQUIRED pending that cancellation fix.

## Second cleanup revision recheck

Cancellation during the service-close wait is now handled, and direct snapshot/source-callback evidence has been added for refusals. One adjacent cancellation boundary remains: the first external cancellation can arrive while the context owner is awaiting the listener worker, after service close has already completed. The unguarded worker wait then exits without collecting the listener. A real listener/quick-close probe cancelled the context owner five milliseconds after close completed and observed one live `Server.serve` task at context exit plus a Windows aborted-accept warning. Evidence: `output/research-transport-review-listener-cancellation.json`. The probe separately awaited its remaining worker. Protect the entire bounded cleanup sequence against caller cancellation, not only the first service wait. Verdict remains CHANGES REQUIRED until this final boundary is handled.

## Final cleanup and refusal recheck - 23:39 UTC

The final helper signals listener exit, starts one owned cleanup task covering both service and listener waits, shields that complete task, and keeps awaiting it across caller cancellations. Both cancellation boundaries now have focused regression tests that require no leftover cooperative tasks. Noncooperative cleanup is bounded and fails explicitly with a requirement to discard the isolated evaluation process; the helper does not falsely claim a forced Python task can always be terminated. Close exceptions are collected rather than abandoned. No remaining blocking finding was identified in this reviewed scope.

Direct `snapshot_entries` and `source_callbacks` are now returned separately from the saved capability accounting. The refusal branch checks those entries and saved/service work, and the focused refusal test verifies both callback lists are empty. This closes the earlier refusal measurement gap without mislabeling raw callback counts as capability calculations.

Independent final execution: `backend/.venv/Scripts/python.exe -m pytest tests/agent/test_comparison_transport.py -q -o addopts= --junitxml=../output/research-transport-review-final-tests.xml`, from backend: **7 passed**, 29 existing import/deprecation warnings, zero failures. The tests restrict outgoing socket connections to loopback and use development-only inputs. No frozen comparison question or model was run. This includes ordinary price and owned-history routes, pre-admission refusal, close exception, noncooperative timeout, cancellation during close, and cancellation during listener shutdown.

Final reviewed SHA256 identities:

- `backend/scripts/research_comparison_transport.py`: `c0ffd51bbb7afa3c3a28e99ca4053d0e0fae4e4ac3236624c6ab20d90cbbb4f2`
- `backend/tests/agent/test_comparison_transport.py`: `da7062018b5e1ff45349d2953a8e225e041753b455c6c736228155ccf4730ce1`
- `output/research-transport-review-final-tests.xml`: `6c15c967b8fbf23fc084b6af3007e506266e36de18d138f98356484ac9af5a04`

The measurement boundaries above remain: future comparison execution still needs exact fixture/source binding, approved settings and shared allowance, durable failure/lower-bound recording, actual browser display evidence and separate crash/recovery proof. PASS here grants none of those and does not convert fixture or development success into held-out acceptance.
