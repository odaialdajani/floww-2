# Independent frozen replay runner review

Reviewed 2026-09-11 23:02 UTC by review_backend_merge. Read-only review of backend/scripts/oauth_heldout_v2.py, its actual research/read/history/model callers, frozen proposal/input/derived/source files and route-check-2301.json. This reviewer made no model, provider, broker or production-storage calls and edited no production source. No full test suite was run.

## Independently verified

- Recomputed the proposal/reference and all 29 research-code hashes. All match. All 30 bound case IDs and request bodies equal the original proposal. No case was removed from the denominator.
- Recomputed history derivation directly from recorded inputs: current retains all 442 original contracts; prior retains exactly the 166 September 14 contracts. Current changes only spot, spot_event_time and spot_fetched_at; spot_source is copied but already equal. These are explicitly synthetic assembled conditions using actual recorded values, not fabricated historical captures.
- The runner assigns each case a new owned session in a unique local evaluation database, asserts empty initial turn history, seeds only the designated prior case, saves/reopens through actual production research routes and checks a distinct owner receives 404. Recorded market clocks are passed explicitly to snapshot calculation. Application session timestamps remain actual execution time; market timestamps remain the recorded clock.
- Replay chain/map callbacks resolve frozen copies; alerts explicitly raise unavailable rather than pretending an empty successful history. The full server and its background market readers are not mounted. Baseline exercise receives model=None. The recorded baseline before/after shared counter is 33/33, with zero saved dispatch reservations.
- Independently counted 26 candidate-eligible cases from actual baseline route outputs: 30 total less three factual price-only routes and one rejected request. The runner requires 26 remaining against the existing shared 40/day counter before validating candidate settings or admitting work. No reset, allowance increase or alternate usage database is present.
- Candidate and baseline reuse the same frozen inputs, clock, owned-history setup and actual routes; candidate fact hashes must equal baseline hashes. Candidate output stays explicitly ungraded and cannot claim usefulness acceptance from input checks.

## Current result and review limits

At reviewed route-check-2301.json, all 30 cases ran but one input check remains failed: map_16 reports displayed bar coverage. Parent is investigating this mismatch. Candidate execution must not use that failed report as a passed baseline. Earlier selected-cell checker mistakes and the omitted history explanation are not grounds to change frozen product answers: the latter remains an independent usefulness grading issue.

The context event case changes a client-side Python request dictionary after the HTTP body has already been serialized. It verifies retained admission context and saved-answer reopening at the route boundary. It does not exercise a real browser changing selected cells; describe it as a controlled request-context test and retain separate desktop evidence for actual screen transitions.

The daily allowance preflight reads available budget; it does not atomically reserve all 26 calls as a group. Concurrent use can consume allowance between preflight and later cases. The existing per-dispatch limiter still prevents exceeding 40. A resulting partial/fallback candidate must remain incomplete or lose its relevant cases under the unchanged grading denominator, never be promoted as 26 successful model calls.

provider_requests is currently a declared zero, not an independently incremented transport counter. Source inspection supports zero market-provider callbacks in this frozen replay; the runner blocks asynchronous HTTP transport but is not a universal process/socket network guard. This field should not be described as comprehensive measured network telemetry.

No candidate was run by this review. Seven remaining calls cannot satisfy the required 26. The wider acceptance gate remains pending actual permitted candidate execution and independent frozen-rubric grading.

## Follow-up refutation and exact remaining work - 23:04 UTC

Read route-check-2302.json directly: 30 cases, zero errors, zero calls, unchanged shared usage. Parent corrected the map_16 checker to respect the existing Solstice cell-only display contract; no production answers or frozen expectations changed. This supersedes the failed input-check status above.

Independently checked supplemental AAPL from raw saved fields: 332.53499999999997 USD, public-mid, source event22:35:56UTC, received22:51:05.099053UTC, capture/evaluation22:51:06.037159UTC. Event <= receipt <= capture; age910.037159 seconds exceeds900 and actual route marks it stale. The single-case later clock is declared, not represented as contemporaneous with the earlier other-symbol captures. This proves faithful replay of the saved source, not an independent new venue verification.

Confirmed a remaining freeze gap: the 29 research-module hashes omit directly used external calculations/configuration. Add an immutable supplemental seal for backend/services/heatseeker.py, market_provenance.py, gex_core.py, realized_volatility.py, backend/bs_greeks.py, backend/auth.py, root config/agent_weights_v1.json and the final runner. Record relevant installed calculation/calendar and managed-model-client versions. The weights path was resolved on disk and is root config, not backend/config. A final deterministic check under that seal establishes a common final baseline; do not modify existing frozen inputs to conceal a change. Existing candidate fact-hash equality detects changed facts but does not by itself prove unchanged code or scoring behavior outside the facts list.

Source review confirms model-assisted mode is set only after validate_model_answer accepts the returned content against the saved fact ledger. Reservations alone prove a counted possible dispatch, not a successful checked answer. Parent is adding explicit per-case candidate failure for an interpretation case lacking both a saved dispatch reservation and model-assisted result. Retain all30 cases, require actual saved settings equal the frozen candidate, and do not retry or replace failures. Three factual lookups and the rejected request must not gain model calls. Completion of those runner checks and the supplemental seal needs final readback before candidate execution.

Exact remaining steps: finish/freeze runner guard changes and external-dependency seal; pass all30 deterministic routes under the final seal without model calls; obtain enough authorized remaining daily allowance without resetting/bypassing40; run the one frozen candidate once; independently grade all30 cases using the original rubric, recording factual-only/rejection cases as such and every candidate failure. No current usefulness or wider AI acceptance is claimed.

## Final sealed readback and refusal probe - 23:08 UTC

Independently executed execution_seal() and compared its full result to oauth-heldout-v2-execution-seal.json: exact match for frozen input hash, final runner and eight listed external/config files total, Python3.11.15, ten package versions and actual managed Codex executable SHA256. The previously reported external freeze gap is closed for this bounded dependency set.

Read oauth-heldout-v2-route-check-sealed-2307.json and independently checked both input and seal hashes:30 cases, zero errors, zero model calls. Read final candidate guards: each interpretation needs model-assisted plus a dispatch reservation; every saved usage setting must match the frozen candidate; bypass/rejection/baseline cannot contain a reservation. Failures remain in the denominator and no retry is added.

Ran actual execute('run',...) preflight against that final baseline and live local shared counter, while replacing settings validation, model once and case exercise with tripwires that would fail if reached. Actual refusal was exactly 'Insufficient existing daily allowance for the complete candidate; no calls made'. No tripwire was reached and no output file was created. This proves the insufficient-budget path without opening a managed model client or admitting any candidate work.

No further setup blocker found in this bounded review. Remaining steps are adequate authorized remaining allowance under the unchanged daily cap, one actual frozen candidate run, and independent all-case grading. The preflight concurrency, controlled-context and unmeasured provider-counter limitations above still apply.
