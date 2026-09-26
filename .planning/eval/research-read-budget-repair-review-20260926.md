# Independent research read-budget repair review

Date: 2026-09-26. Final full bounded recheck: 21:57:55 UTC; final allocation/cleanup follow-up: 21:59:08 UTC.

## Verdict

Two concrete regressions were reproduced in the first repair. Both were corrected by the owning agent and independently rechecked through the actual ResearchService. No unresolved blocker was found in this bounded offline review. This is development verification, not fresh model/provider acceptance or trading authorization.

The reviewer changed no production source or existing test file. Only scratch probes/results under output/research-budget-review-* and this report were written. All Python processes used hidden Node execFile with windowsHide:true. Every successful probe installed an outbound socket guard and reported zero network attempts; no real model or provider was called. In-memory stores and synthetic current option observations were used.

## Reproduced regressions, now closed

1. **High: rejected cancellation mutated another owner's active question.** ResearchService.cancel looked up its in-process budget by turn ID and closed it before repository.finish checked the owner. With Alice's flow callback held in a thread, Bob's cancellation returned None while Alice's budget changed from open to closed. Alice later saved a completed answer with the requested structure omitted and a 'Question stopped' gap. The route calls service.cancel directly and only converts None to 404 afterwards, so the service mutation was not protected by a prior route ownership check. The correction reads the owned turn before touching its budget. The identical independent reproduction now leaves Alice's budget open, completes its remaining readings and produces no stopped gap.

2. **Medium: narrow word matching silently dropped requested move evidence.** On a valid saved call/put pair, 'Explain SPY flow and expected moves' invoked context and flow only; 'Explain SPY gamma and implied move' invoked context and structure only. Both completed without an implied-move fact or an omission gap. The singular phrase 'expected move' produced the valid move facts on the same fixture. The correction recognizes expected/implied move plurals and keeps broad evidence for single-ticker questions except clear history-only/price lookups. All three independent answer-level cases now contain 'Implied move estimate'. Additional structure synonyms were added for multi-ticker selection.

Before-fix evidence is preserved in output/research-budget-review-first-result.json. Corrected evidence is separately saved in output/research-budget-review-fixed-result.json; the original reproduction was not overwritten by the fixed recheck.

## Independent passing checks

- Mixed synchronous reads and asynchronous history operations share one allowance: four entered reads that raise plus four entered history operations total eight; the ninth history operation is refused before callback entry. Failed reads retain their charge, and the denial is recorded separately.
- A timed-out worker stays charged. Closing the question freezes its timed-out/unresolved state; releasing that worker later does not change the frozen activity or convert the timeout to success.
- Reservation save failure enters zero callbacks. A reservation save that consumes the remaining question time also enters zero callbacks.
- Actual service save failure before entry produces a failed turn with zero entries and no answer. Failure after callback completion produces a failed turn with one recorded entry and no answer. Private exception text is absent.
- Frozen history memoization returns an independent copy. Mutating a returned result cannot change the saved result; changing the history comparison mode incurs a new charged operation.
- Startup recovery converts an unfinished saved reservation to interrupted_unknown and marks the recorded entry count incomplete; it does not claim the callback never ran or retry it.
- Wrong-owner cancellation and all three move-wording cases pass through the actual service after the corrections.

Persistence evidence: output/research-budget-review-persistence-result.json. Mixed-cap/late-worker evidence: output/research-budget-review-cap-result.json. Executable companions have the same stems ending in .py; the fixed cancellation/wording companion is output/research-budget-review-fixed.py.

Additional final correction checks passed: a permitted cancellation whose final write fails stops the worker, saves interrupted, enters no fixture-model callback and never publishes the late reading; failed initial history is memoized so a fixture-model follow-up does not retry the unavailable read. Evidence: output/research-budget-review-final-result.json and its matching .py companion. Fixture model callbacks returned controlled objects only; no model service was called.

The final allocation/cleanup follow-up also passes independently: cancelling immediately after admission saves a complete zero-reservation/zero-entry record, closes the held budget, and leaves no tracked task or budget. A question held behind an occupied work slot until its deadline fails with a complete zero-entry record and also leaves neither tracked task nor budget. Evidence: output/research-budget-review-prestart-result.json and its .py companion. Only research.py changed for this follow-up; its final hash is refreshed below.

## Boundaries

The final source still uses deterministic words to choose narrower multi-ticker work. The tested phrases and added synonyms are covered; this review does not prove arbitrary natural-language completeness. Requests needing more than eight capabilities must retain explicit partial-coverage gaps. Saved reservation versus observed entry versus unresolved completion remain distinct. Existing exposed model comparison cases remain exposed and cannot become fresh acceptance from these tests. The root agent owns the complete regression suite and final source manifest.

## Final rechecked source identity

- backend/services/agent/read_budget.py: dac83653c5f73044b09521461589e9addfc090d8a0903f2ac4d2b550570441a4
- backend/services/agent/research.py: e5370729bb4bbb3a56841157a68937143d81b1e05998d1c92de171ac9d8832bb
- backend/services/agent/reads.py: 62f64457e3e53a3863b4800906eb6d1221fedf252f5cc6e6a7a23d4710847e60
- backend/services/agent/repository.py: c578fce82b95de61f9f232606825b32fb245a6ad0add2e013da9f01cc74d10b9
