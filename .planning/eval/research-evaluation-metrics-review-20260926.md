# Independent research evaluation measurement review

Date: 2026-09-26. Last bounded independent check: 22:18:53 UTC. Source identities rechecked unchanged at 22:19:09 UTC.

## Verdict

Two concrete issues were found in the first helper version and corrected by the owning agent. Both corrections and adjacent completeness/cleanup cases pass independent reproduction. No unresolved blocker was found within this bounded development review. This does not provide fresh held-out model acceptance, a browser-display measurement, an upstream request count or a dollar-cost invoice.

Scope: backend/scripts/research_eval_metrics.py, backend/scripts/verify_research_eval_metrics.py and their new test file. The reviewer edited no production helper or existing test, only this report and output/eval-metrics-review-* probes/results. All Python children used hidden Node execFile with windowsHide:true. Tests used synthetic methods, in-memory data and an owned loopback listener. No actual model/provider request, managed Codex process or external network connection was used. Previously exposed comparison artifacts were neither edited nor rerun.

## Findings closed by independent recheck

1. **Medium: an unfinished durable model record claimed exact zero entries.** The initial wrapper saved a reserved state with model_invocations=0, then entered the actual method without another saved update until it returned. Holding that method proved actual entry while the latest durable record still said zero. Forcing the terminal measurement save to fail reproduced the same durable zero after one completed method call. The correction returns null for unresolved model entry counts, provides a lower bound and completeness flag, and treats every saved counter as a lower bound until explicit successful finalization. The corrected durable reserved record is unknown/incomplete; final-save failure remains latched and cannot later be labeled complete.

2. **Low: the local proof left process settings changed and could leak its listener.** On normal return, both deployment/origin environment variables remained set to the fixture. When repository initialization failed before the original try/finally, its owned listening socket also remained open. The correction wraps resource creation in synchronous/asynchronous cleanup stacks and restores prior environment values. Independent success, setup-failure and service-close-failure probes now restore the environment and socket guards and close the listener. The original failing probe explicitly cleaned its own leaked resources after recording evidence.

Before-fix evidence is preserved in output/eval-metrics-review-first-result.json and output/eval-metrics-review-cleanup-result.json. Fixed evidence uses separate files: output/eval-metrics-review-fixed-result.json, output/eval-metrics-review-cleanup-fixed-result.json and output/eval-metrics-review-cleanup-finalization-result.json.

## Other independent checks

- Model and managed-request work still in progress cannot be finalized. Completed work needs explicit finalization. A new timing mark or counter update invalidates prior completeness. Failure to save final completeness remains latched. Seven adjacent assertions pass in output/eval-metrics-review-completeness-result.json.
- Actual CodexBridge send/request code was exercised against controlled in-memory pipe objects. A failed write records attempt/write/ack counts of 1/0/0; a drain failure after a synthetic write also records 1/0/0; a completed write with lost acknowledgment records 1/1/0; an accepted response records 1/1/1. Request bodies are unchanged. Upstream request count and dollar cost remain null. These are observed local boundaries, not proof of generation completion. Evidence: output/eval-metrics-review-bridge-result.json.
- Replaying the completed owned HTTP stream preserves its original first-receipt and terminal timing marks. A different valid owner receives 404 with no timing events added. Buffered ASGI transport is rejected. Legacy turns with no read record stay unmeasured.
- Owned durable usage is read independently of answer success. An owned completed reservation is returned, while another owner receives no-owned-record with unknown count/cost. No other owner's entry is returned. Evidence: output/eval-metrics-review-behavior-result.json.
- The final controlled local HTTP proof passed with first progress receipt about 0.0067 seconds and terminal receipt about 0.5168 seconds from case start, for a deliberately delayed synthetic cached-price read. The counter records one capability read and zero model entries. Those timings describe this fixture only. The final high-resolution monotonic clock reports its resolution; browser display/first paint remains unknown. Saved progress timestamps retain their separate server pre-write meaning.

Each evidence result has a matching scratch .py companion (the fixed and cleanup variants are explicitly named). No replay or saved timestamp was relabeled browser visibility or fresh model acceptance. The root agent owns the full test run and subsequent evaluation integration.

## Final reviewed source identity

- backend/scripts/research_eval_metrics.py: a92555451f6cebc915d94eb18d29fe1ae34a5de27b8d781663d5b7f0f4de9ff4
- backend/scripts/verify_research_eval_metrics.py: ee924f8f40688c673f65a7611524679924733cc95d7d5edcd3cc4fd59ded5f6d
- backend/tests/agent/test_evaluation_metrics.py: 198e4ff63ea620f98fc63e2faab4405d649b1da759ee901822fc3511759335b5
