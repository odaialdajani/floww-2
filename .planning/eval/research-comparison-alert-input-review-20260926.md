# Research comparison alert-input review - 2026-09-26

**PASS for isolated alert input preparation and explicit synthetic chain/map preparation.** All reproduced findings are fixed and independently retested against the final source hashes below. This is not a research answer run, release acceptance, or proof of live-market alert contents.

## Scope and method

The reviewer owns this report and `output/research-alert-review-*` scratch only. The production helpers, tests and both comparison proposals were read-only for this reviewer. Root-owned fixes are independently retested. The review follows the hard-tasks requirement to reproduce faults, refute the happy path, and check the actual operation rather than infer capability from a green envelope.

Reviewed code: `backend/scripts/research_comparison_alerts.py`, its focused tests, and the explicit synthetic chain/map additions to `backend/scripts/research_comparison_inputs.py` and its tests. The reviewer also read the actual table initializer, persistence function, strict stored-alert reader and raw-chain scanner. All fixture storage is an owned `:memory:` connection. No research/model/provider answer function was called. A process audit hook refused network/process launches and recorded zero attempted external activity during the independent probes.

Initial focused verification: 6 alert tests plus 17 raw-input tests passed together (23 passed, 27 warnings). Independent reproduction evidence is retained in `output/research-alert-review-first/results.json` and `output/research-alert-review-third/results.json`; the reproducible probe is `output/research-alert-review-probe.py`.

Final independent verification at 23:14 UTC: `.venv/Scripts/python.exe -m pytest tests/agent/test_comparison_alerts.py tests/agent/test_comparison_inputs.py -q --disable-warnings`, run from `backend`, passed **35 tests** with 27 existing warnings. The independent actual-store probe completed with all normal-path assertions and all 15 malformed-input checks; every malformed case raised. Final evidence is `output/research-alert-review-final/results.json`. All six reviewed files were unchanged during that probe, the original proposal was unchanged, and no external activity was attempted.

| Reviewed file | Final SHA256 |
| --- | --- |
| backend/scripts/research_comparison_alerts.py | 83b8bdf056039613c3eece92c2db813cc5ba48ae138ef0cfbfabc3db7e3e1aad |
| backend/scripts/research_comparison_inputs.py | bc0e456421ff9d29fac136eee7060b231936d7cdf62898c46487aefcd71b3a8d |
| backend/tests/agent/test_comparison_alerts.py | 87e6da17c39b98d3c50059a7983330055183b8f9cb9c284db7bd37dc7e52fcee |
| backend/tests/agent/test_comparison_inputs.py | bcbe31fca921b75c46d2026fdc878d989c50640ae9bd9605fe45de2f749e26af |
| .planning/eval/research-fresh-comparison-proposal-20260926.json | 0a163764f83fcac3e4d411125e5888c0a37926b298daed72ca8ece6be21ff2f8 |
| .planning/eval/research-fresh-comparison-proposal-20260926-v3.json | 85ec640d62d248d95da21129c01806b1f7751aa75be6a4894eb4c59642d6fad1 |

## Verified normal behavior

- The controlled empty store runs the real initializer and strict reader. Its receipt is successful with zero rows, ticker IWM, and lower date bound 2026-09-21 at the declared September 28 clock. This proves only absence in that isolated query.
- The missing-table case raises the actual DuckDB error; its receipt reports error with unknown row count. The unbound-store case raises before any query rather than fabricating a successful empty lookup.
- Synthetic mixed alerts are actually persisted and read with convictions 80 bullish and 40 bearish; independent signed arithmetic gives 0.2. The revised aligned-positive rows retain 80 and 60 bullish; the independent mean is 0.7. Neither number is win probability or real-market coverage.
- Source observations remain 14:29:30Z and 14:29:40Z. The explicit aligned rows retain a distinct 14:29:50Z creation time after ordinary DuckDB datetime conversion. This exercises the datetime-subclass compatibility fix through the actual reader.
- The archived QQQ raw chain produces 61 derived alerts under the declared historical clock. Every source observation remains unknown while every creation time is 2026-09-11T22:52:00Z. Source freshness is not inferred from creation time or the injected query clock.
- Concurrently open fixture objects have separate connections: the positive store returns its two QQQ rows while the empty store returns none. Inputs are deep-copied and remain unchanged. Module datetime bindings restore after reads and query errors; normal and exceptional context exit close the owned connection.
- Explicit synthetic chains/maps preserve their declared raw objects. Independent arithmetic checks the bracketing profile at strikes 95/105 as +10000/-9600, the hypothetical move's 365400 remaining seconds and rounded 1.89 USD estimate, and cached map price 100 versus supplied whole-map flip 101 while the separate quote remains 103. The supplied flip is not claimed to be calculated from the selected grid.

## Reproduced findings

1. **Future timestamps accepted in positive rows - fixed.** Initially, source observations and creation times later than the frozen evidence clock were saved/read successfully. Alert-specific validation now rejects these inconsistent times before persistence.
2. **Duplicate row identities conceal a lost row - fixed.** Initially, two declared rows with the same key produced a population receipt claiming two persisted rows, but the real upsert left one row. Final validation rejects duplicate identities before persistence.
3. **Positive recipe meaning can drift silently - fixed.** Initially, unknown parameters were ignored; an aligned-bullish variant accepted an explicit bearish row; conviction 101 was accepted; and an empty chain/ticker scope reported successful zero rows in positive mode. A missing synthetic lineage marker was also accepted. Each of these malformed positive inputs is now rejected.
4. **Explicit map axes can disagree with the screen - fixed.** The initial helper checked query/version but accepted different screen strike or expiry arrays from the declared raw map. Final validation rejects mismatched axes and out-of-scope selections, preserving the exact-identity recipe.

Non-finite conviction already failed through real storage conversion and cleaned up. Non-synthetic top-level chain/map labels already failed in preparation. These are passing failure behaviors, not new open findings.

The independent fifth probe (`output/research-alert-review-fifth/results.json`) confirms the four findings above are fixed: each malformed positive input now raises, explicit map axes mismatch raises, connection cleanup still completes, and all normal paths still preserve the declared inputs. Non-finite values now fail in explicit validation before storage. The same probe independently verifies the three explicit raw positive arithmetic examples above.

Two sibling conversion faults were then reproduced:

5. **Fractional conviction silently changes on storage - fixed.** The initial validator accepted 80.4, but the production integer column returned 80. Final validation rejects nonintegral values before persistence. The independent final probe reproduces the same input and receives ValueError; normal integer convictions remain unchanged.
6. **Equivalent UTC creation string gains four hours after reading - fixed.** Replacing the original exchange-local creation string with the equivalent `2026-09-28T14:29:50Z` initially passed time validation, but production storage discarded the offset and the legacy reader interpreted the stored wall time as New York, returning `2026-09-28T18:29:50Z`. Final validation requires the creation offset to match New York at that instant, rejecting the misleading representation. The final probe confirms rejection while normal exchange-local creation times round-trip correctly. Production persistence/reading behavior was not changed by this fix.

## Proposal metadata observation

The reviewer separately reported that the four newly synthetic cases initially retained copied real-only prerequisite and coverage labels. The final reread confirms those four cases now have synthetic coverage labels and prerequisites requiring frozen synthetic raw rows, actual production calculation/read checks, source/execution identity binding, and separate retention of the unproven real-positive predicate. The coverage owner reviews that amendment separately; this report does not seal it. The original real-input proposal remains unchanged, and real-positive gaps cannot be counted passed by synthetic input preparation.

## Limits

The frozen clock patches module globals and is intended only for this isolated evaluation process. The local lock serializes fixture reads/population; this is not authorization to inject fixture clocks into a live application. No live store was inspected, and no production emptiness/freshness claim follows from these operations.

This helper does not establish research routing, owner-history behavior, model budget use, answer grounding, saved-answer recovery, browser timing, usefulness or any remaining critical release checks. Source receipts and arithmetic are preparation evidence only. An unrelated Windows Python launch once failed before output with initialization exit 0xC0000142; a version check and subsequent full independent run succeeded without interrupting any process.

## Provenance-only update - 2026-09-26 23:18 UTC

The revised proposal's `remaining` source now points to `.planning/eval/research-fresh-proposal-context-20260926.md`. The reviewer independently verified that preserved file has the exact previously recorded source SHA256 `6768d0ef878059c945c66205e9a11a8925bbe6e17411a2bac01019b5e84d1f42`. The current revision-3 proposal SHA256 is `305a42af3a8d86ed8e39ad314a99c592ad2fb57ccab53faf575e507e3aa71c2b`; the earlier hash above remains the dated identity used for the final execution probe.

For an independent exact-delta check, the reviewer reversed only the new source path and its descriptive role text in memory, without writing the proposal. The resulting bytes hash to the prior reviewed identity `85ec640d62d248d95da21129c01806b1f7751aa75be6a4894eb4c59642d6fad1`. This establishes that all case bodies, criteria and other proposal content are unchanged. All four helper/test hashes above also still match. No tests, answers or model/provider operations were rerun for this source-reference-only change.
