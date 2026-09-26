# Independent saved-progress timestamp review

Verdict: no new blocking defect found in the narrow timestamp change. This supports recording and replaying timestamps on newly saved progress/final events; it does not establish browser paint timing, network latency or market observation time.

## Observed verification

- Independently reran test_owned_research.py with isolated collection: 11 passed in 1.97 seconds.
- Ran 15 new offline adversarial checks in output/progress-timestamps-probes.py; all passed. Exact results are in output/progress-timestamps-probes-result.json, with the existing-test output in output/progress-timestamps-existing-tests.json.
- All child execution used Node execFile with windowsHide:true. Tests used an in-memory store and local in-process HTTP transport. No provider/model calls, live storage edits or visible windows were used.

## Refutation checks

A forced version conflict rejected a progress update without leaving a phantom event or timestamp. A later successful progress update stored its new UTC sample alongside updated_at. A forced finalization conflict retried, stored only one successful final event, and used the later attempt's timestamp. Late progress and repeat finalization could not rewrite existing event times.

Wrong-owner progress and finalization were refused. A valid session belonging to another owner received a 404 from the real stream route and no timestamp data. Owner replay using Last-Event-ID returned only the remaining saved event with its original timestamp, despite advancing the wall clock. Replay did not change stored events. Legacy events without timestamps stayed readable and no time was invented for them. The stored market-fact observation time remained byte-for-byte unchanged.

Source review confirms status/version/owner conditions and timestamp insertion remain in the same conditional store update. The stream reads the existing event fields; the new field does not add a separate unguarded route.

## Exact scope and limits

recorded_at is the UTC wall-clock sample taken immediately before the successful conditional persistence attempt. It is stored atomically with that event, but it is not an acknowledgement timestamp taken after the store confirms durability. Report this as the timestamp of the first saved progress event, not the exact first durable-write completion time. It is also not actual first browser display or transport arrival latency.

Wall-clock changes can make timestamp differences non-monotonic; this change does not introduce a monotonic duration clock. The event string preserves Python microseconds while store datetime fields commonly retain milliseconds, so downstream comparisons with created_at/updated_at should allow that precision difference. This is a measurement limitation, not a failed event-order invariant; event IDs remain the replay order.

Historical runs still have missing progress times. This change cannot supply them retrospectively. No read/capability counts were added or claimed in this review. Existing acceptance grades and stronger-candidate/cost/coverage gates remain unchanged.

Only this report and temporary output probes/results were written by this reviewer. No production source was edited.

## Exact reviewed source hashes

- backend/services/agent/repository.py: 9ee5abff535f41e009256fb41d6279b1cd0d47a8311452fa21eaed98ac21d26f
- backend/routes/agent.py: 40f54240ba5ec47fd601255e73760ca91291f7df92c9300263ac3125fe4930df
- backend/tests/agent/test_owned_research.py: aefad50c78a9c8c3e9824d84e7cbf7c85563876bd18c2bd915a424f7257f69f5
