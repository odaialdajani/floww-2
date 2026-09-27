# Independent research read-budget review

**Finding: the current production-shaped service can exceed the plan's eight capability/ticker allowance before any model call. No enforcement of that shared allowance was found on the active path.** An offline run through the actual ResearchService completed a three-ticker history question after 9 observed read/history entries; selecting one chart raised this to 10. Both saved an answer without any read-count or read-budget record.

This is a read-only audit. No production source or existing tests were edited. The concurrent full backend run was not touched. Only this report and scratch probes/results under output were written; all processes used hidden Node execFile with windowsHide:true.

## Exact requirement and active path

The authoritative plan at .planning/unknowns/lodestar-plan-v4-review-draft.md:189-191 requires eight capability/ticker invocations per turn, including context; one grouped structure capability computes its related outputs once; three tickers normally allocate context plus requested metric per ticker, leaving two focused follow-up slots. Model requests and actual provider snapshot-acquisition requests are separate counts. It also requires per-tool deadlines inside the shared turn deadline (:125, :189).

Production composition is backend/server.py:3639-3674: it constructs ResearchReads with cache-only chain, selected-map and stored-alert callbacks, then injects that directly into ResearchService with CodexModel. It does NOT attach read_daily_bars.

The real route uses ResearchService.ask, then _work: request_spec enforces three tickers (contracts.py:128-132); service runs each ticker's snapshot (research.py:95-115), and history intent separately calls history_facts for every snapshot (:121-148). The reads snapshot invokes optional daily bars, chain, optional selected map, and alerts (reads.py:31-60). One selected screen can match at most one ticker, so this audit does not falsely multiply selected-map reads across all three tickers.

ResearchService capacity/concurrent/queued values restrict concurrent jobs, not capability invocations. Its overall asyncio timeout is not an eight-call counter. Neither repository admission, route validation, nor the configured read callbacks adds that counter. Model quota and monetary reservation checks do not constrain these local reads. Searches covered all active agent modules and server/route wiring plus registry callers across backend source.

The legacy registry is not the active dispatch path. tools/__init__.py registers four names, but each registered wrapper itself calls the full snapshot and then filters facts; registration metadata does not enforce a per-turn count. Current routes do not dispatch through get_tool/list_tools. loop.run_turn is a compatibility preview and also calls snapshots directly; production work is owned by ResearchService. Counting registered names is not evidence that live invocation limits are enforced.

## Observed offline reproduction

Scratch source: output/research-read-budget-probes.py. Full ordered entries, internal history-query trace, source hashes and saved outcomes: output/research-read-budget-probes-result.json. Process output: output/research-read-budget-execution.json.

The probe used the actual request_spec, ResearchReads, ResearchService, AgentRepository and history_facts. Injected callbacks returned controlled synthetic XLK/XLF/XLE data. The history wrapper recorded entry then called the real function. The store was in-memory. Model was disabled so the same pre-model work could be tested without any actual model call. A socket guard blocked outbound connections after the Windows event loop created its internal self-pipe; the successful run recorded zero network attempts.

| Scenario | Chain/context | Alerts | Selected map | Daily bars | History | Total entries | Saved status |
|---|---:|---:|---:|---:|---:|---:|---|
| Three tickers, no history | 3 | 3 | 0 | 0 | 0 | 6 | completed |
| Three tickers with history | 3 | 3 | 0 | 0 | 3 | 9 | completed |
| Three tickers, history, selected chart | 3 | 3 | 1 | 0 | 3 | 10 | completed |
| Same with optional daily reader | 3 | 3 | 1 | 3 | 3 | 13 | completed |
| Price-only with selected screen | 1 | 0 | 0 | 0 | 0 | 1 | completed |
| Three tickers/history with alert failures | 3 | 3 | 0 | 0 | 3 | 9 | completed |

All cases used zero real model calls and zero provider requests. The optional daily case proves the supported injected-reader path, not today's production wiring. Cache misses and failed alerts were actual entered calls and were counted; a missing result is not a free call.

These are a conservative lower bound on distinct capability reads: one chain/context acquisition, one alert capability, one map capability, one daily-history capability and one owned-history capability per relevant ticker. A history capability internally queried both saved turns and saved anchors: 3 history entries produced 6 store queries. Those two internal queries were not falsely doubled into two capability calls. Repository state checks, save/watch writes, individual facts and scalar arithmetic were not counted as research capabilities.

Pure structure/volatility calculations were not added to this lower-bound read total. The final implementation must still define the plan's grouped metric capability boundary explicitly. In particular, an eight-callback counter alone is not proof of full plan conformance if a separate requested metric capability remains outside it; nor may all of a snapshot's unrelated context/alerts/map/history work be relabeled one capability. The plan allows grouping related structure outputs once, not hiding unrelated reads inside a broad report.

## Follow-up reachability

The generic ResearchService._interpret path can request history once (:205-233), and does not charge a shared read budget or reuse initial history automatically. A history question followed by an inspect_history request can therefore repeat the same ticker's history read. Under that generic path it would add one capability entry, not one per returned fact. This was established from source; no real model was called for the audit.

Today's production CodexModel is single_attempt=True and always returns name=research_answer (codex_model.py:117, :187-201); its bridge output schema is the answer schema and tools are disabled. Therefore model-requested inspect_history is NOT currently reachable from the production Codex output. It remains reachable through the older OpenRouter/generic model integration. Do not inflate the demonstrated production 9/10 counts with a hypothetical current Codex follow-up. The current failure already exists before interpretation.

## Deadline and cancellation evidence

Alerts and optional daily bars have a five-second wait_for around asyncio.to_thread. Chain and map callbacks are called synchronously on the event loop with no individual timeout; history has no separate per-capability timeout. The service's outer 120-second deadline is cooperative. It cannot interrupt a synchronous callback that blocks that loop.

A separate scaled synthetic service probe, output/research-read-budget-timeout.py, used a 0.2-second overall deadline and a 0.5-second blocking chain callback. It recorded 0.5 seconds before the failed saved result; both chain entry and exit occurred. This demonstrates the interruption limitation, not actual production callback latency. Its result is in output/research-read-budget-timeout-result.json. The initial 20ms experiment had too little startup margin to reliably reach the callback; the final 200ms/500ms probe explicitly asserts callback entry and elapsed work.

The cancellation probe held an alert callback in a thread, cancelled the real service turn, then released the callback. The turn was already saved cancelled while the worker was still running. The worker later completed, and the terminal answer stayed cancelled with no answer published. Thus existing terminal-state protection held, but cancellation does not prove a threaded read stopped or never ran. Its attempted read must remain charged and its late result must remain unusable for the terminal answer.

## Minimal enforceable repair proposal

1. Create one turn-owned budget before the first research capability starts. Share it through snapshot, initial history and any allowed model follow-up. Keep model requests and provider acquisitions in separate ledgers. Do not use the service's queue size or model daily quota as this budget.
2. Define/version a small explicit capability policy matching the plan: context; requested grouped structure/volatility/flow/chart/history reads; ticker and frozen scope on every attempt. Charge once for a grouped operation, not once per returned metric or internal store query. Reuse the already-frozen chain for related calculations. Stop unrequested alert/daily/map work when the question does not require it. A three-ticker history question can use three context reads and three requested history capabilities; it need not spend three extra alert reads first. A request genuinely needing more than eight operations must receive explicit partial coverage, not hidden expansion or silent ticker omission.
3. Reserve and record an attempt before invoking a callback, starting a thread, or awaiting a history operation. Refuse the ninth before any side effect. A cache miss, read exception, timeout or cancellation does not refund an entered/reserved attempt. Record denied work separately so the saved answer says which requested evidence was not attempted. If durable reservation cannot be saved, fail closed before starting that read.
4. Route synchronous callbacks through a bounded executor where needed, with each attempt bounded by min(per-capability limit, remaining monotonic turn time). The plan's six-second limit is a maximum; the existing five-second read limit can remain stricter. Do not wait six fresh seconds after the overall deadline is nearly exhausted. Bound actual workers separately: wait_for/to_thread cancellation cannot kill an already-running thread. Mark such work timed_out/cancelled-unresolved, retain its charge, and never start hidden retries or publish late results.
5. Memoize initial history by ticker plus exact frozen scope, comparison mode and snapshot identity if a follow-up requests the same read. Reusing a saved result is not another invocation; performing the read again is. Check the same remaining budget before accepting any genuinely new follow-up. Current Codex does not request one, but the generic path must not bypass enforcement.
6. Save a bounded per-turn attempt record usable even when answer is absent: policy version, limit, reserved/started count, capability, ticker/scope identity, attempt ID, start/end timestamps, outcome, denied operations and unresolved worker status. Persist for completed, failed, cancelled and interrupted turns, not only successful answer objects. Do not relabel a reservation as proven completed work; expose unknown states honestly. No raw callback exception text or private data needs to be included.
7. Prove the repair with observed ninth-attempt refusal, mixed initial/follow-up attempts, three-ticker allocation, optional daily input, misses/exceptions/timeouts/cancellation, two simultaneous turns with independent budgets, and saved/reloaded counts. Assert callback entry counts, not only configured limits. Preserve price-only one-read behavior. Existing frozen comparison rows remain unchanged and cannot become fresh acceptance after this repair.

## Review boundary and source identity

No source changes were made by this reviewer. The source hashes used for the successful reproduction still matched at report time. These checks demonstrate a development defect and suggest a repair; they do not authorize any new provider/model call, raise an allowance, prove trading performance or close the existing research acceptance gates.

- backend/services/agent/research.py: e42a107ba407c08d841144efd0e2b6114311e73e1fbd62102aac11b5974b862f
- backend/services/agent/reads.py: 17231a1207c0d79142f639a24dead37d38c77cfc2113c201d8c2fba0cd7eb6f8
- backend/services/agent/saved_history.py: 283b820a4a31a5fe08d2f129d54d74462a3e6625053d1155d84ff1f96ed44903
- backend/services/agent/repository.py: 9ee5abff535f41e009256fb41d6279b1cd0d47a8311452fa21eaed98ac21d26f
- backend/server.py: 6999643ab995d03b20885dfdd3f35219d40eca2a7c6cf8cdc244705cc8e0422d
- backend/services/agent/tools/__init__.py: 76a6d6eb35561807d203ce6a0b15fda9d0a4bd309d10f346611b767bc4050ac5
- backend/services/agent/codex_model.py: e9d1d7c909c57c9d7c206a3d11cb833f0223252d1e5c391b473e9448a9fdf7d3
- .planning/unknowns/lodestar-plan-v4-review-draft.md: 0702aa38984e636e1665af4814652d0d5ce13ffee01867731f145a6459a04253
- backend/services/agent/loop.py: 96714af748a514b126703f396a39cfd3dc0dc042c31350b4c5955e425d77213e
- backend/services/agent/registry.py: fd985f131e9b4ca0f17b906993a6e127053061c16f2440697b1f70bf77220cca
- backend/services/agent/contracts.py: 6ac9434175ae6b02101a628271710515dc0d08d2ba688d113f7ec7dd66402273
- backend/routes/agent.py: 40f54240ba5ec47fd601255e73760ca91291f7df92c9300263ac3125fe4930df
