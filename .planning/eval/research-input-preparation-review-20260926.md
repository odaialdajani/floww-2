# Research input preparation review - 2026-09-26

**Verdict: PASS for raw input preparation only. NOT an execution seal, candidate evaluation, semantic acceptance, route proof, or trading authorization.** No remaining blocking defect was reproduced in the final reviewed helper against the unchanged 32-case proposal. Four proposed real-positive inputs remain absent and all 14 additional critical checks remain unexecuted.

## Scope and reviewed identities

The independent reviewer read `backend/scripts/research_comparison_inputs.py`, `backend/tests/agent/test_comparison_inputs.py`, the proposal's recipes/cases/truth criteria, and the referenced raw captures. Production and proposal files were read-only for this reviewer; fixes were made by the root agent and independently retested. No candidate answers were generated or inspected, and no model/provider/research-answer execution was requested.

- Helper SHA256: `e27eb6fca4d9b80235125ac9e41da3f12e9b3a4e33e9fee6b6e8934d1cf64f68`.
- Tests SHA256 after the test-only source-scope adjustment: `24680153d50b0e315572d06b864d8f34c10a67587f163fbb4a837c6efb0f5fdd`.
- Unchanged proposal SHA256: `0a163764f83fcac3e4d411125e5888c0a37926b298daed72ca8ece6be21ff2f8`.
- Final independently generated evidence: `output/research-input-review-final/review-results.json`, with source stability checked before/after the probe.
- Reproducible review probe: `output/research-input-review-probe.py`; run with a new suffix to preserve existing evidence.

## Reproduced findings and verified fixes

1. **History default fidelity - fixed.** The initial helper left the default current price at 100, yielding zero change where the history recipe promises prior/current 100/102. A failing check independently reproduced this before the root fix. The final bundle contains prior 100/current 102 and raw difference 2 for every history ticker. The explicit owned-price case still matches 100/102. Synthetic prior observation and receipt are separate, ordered values; the late observation remains an intraday anchor, and the other-owner seed is labeled accordingly. These are seed facts, not proof of an actual history read or authorization to expose other-owner values.

2. **Expiry mismatch fidelity - fixed.** Removing the put contract left prior/current on the same sole expiry, contradicting the case's criterion to add/remove an expiry. The final prior includes October 2 and October 9 contracts while the current input includes October 2 only. The prior expiry list matches its contract set and added contracts have matching explicit October 9 cutoff metadata. The original question and criteria were not changed.

3. **Late serialization failure leaves partial output - fixed for input validation.** A non-finite spot in a late case initially raised after 26 files had been written, preventing a retry into that directory. Final code serializes all inputs and report before creating output. The independent final probe repeats the late non-finite failure and observes no output directory and zero files.

4. **Reserved output-name collision - fixed.** A regex-valid case named `manifest` initially created 32 files and then collided with the final report filename; that filename held a case fixture, not a report. Final code rejects this name and Windows device names before creating output. Independent probes for `manifest` and `nul` leave no output; the focused test set also exercises the other reserved name families.

Earlier scratch runs retain failed evidence. Their end-of-run helper hash was not guaranteed to identify the imported version during concurrent root edits; use the final evidence, which verifies the helper was unchanged during the run, for version-bound conclusions.

## Independent verification

The final focused command `.venv/Scripts/python.exe -m pytest tests/agent/test_comparison_inputs.py -q --disable-warnings`, run from the backend directory using its environment, passed **16 tests** with 27 existing warnings. The actual helper command, run independently with output `output/research-input-review-command-final`, exited successfully and reported 32 cases, 28 with input material, zero model calls and `execution_ready=false`. The 28 includes two request-body-only refusal cases; it is not a claim that 28 cases contain market observations.

A narrow test-only follow-up at 22:57 UTC builds temporary unit proposals containing the three immutable raw archive references instead of requiring all dated documentation/application references to remain unchanged forever. The reviewer verified those three exact hashes, reran all 16 tests successfully, and confirmed the helper and real proposal hashes above are unchanged. The actual helper still verifies every reference supplied by the real proposal (13 in the independently run command); the earlier full-source preparation evidence is not replaced by these narrower unit tests. No source hash is recomputed into a unit proposal to conceal drift, and the archive identities/expected digests are retained exactly.

The independent probe verifies all 32 fixture hashes against the generated manifest; all 16 archived chain extractions are deeply equal to their original raw source objects, and the archived map is deeply equal to its captured body. This preserves original source labels, null observations, receipts, stale fields and contract data. All referenced source files and the proposal remain byte-for-byte unchanged.

Thirty-one per-ticker raw chain inventories were independently checked for spot, observation timestamps, contract and expiry counts, and zero-versus-missing open interest. The review independently recomputed visible map row sums with `math.fsum`; the missing-cell cumulative sequence remains `[3, null, null]`, and the selected measured-zero cell remains zero. These checks cover raw arithmetic and inventories only; they do not certify production calculations, financial interpretation, freshness, expiry selection, or model answer truth.

The final rejection probes cover wrong case count, duplicate and escaping case names, unknown recipe, future observation, changed source hash, escaping source path, reserved report name, Windows device name, and late non-finite input. Each rejects before output creation. Reusing an existing output directory raises and preserves the prior bundle. A network audit hook recorded zero network attempts during the independent probe; the helper imports only standard-library preparation code.

## Boundaries that remain open

- Real bracketing levels, paired-IV move evidence, coherent cached-map price/flip evidence, and fresh real directional alerts remain absent; all four remain in the denominator.
- No alert table was created, written, or queried. Controlled empty/error, derived unknown-freshness and synthetic-positive alert modes are declarations with null query proof, not observed evidence.
- History owner isolation, insertion/capture order, coverage eligibility and actual reads are still unproved. Raw differences are not answer facts and must not bypass later ownership/compatibility checks.
- No route admission, price bypass, display refusal, payload size, source-quality acceptance, model suitability, saving/recovery, budget races or any of the 14 critical checks was executed by this helper.
- The helper does not implement atomic publication for an interrupted disk write. Such interruption can leave incomplete output; it must remain unusable and must not be treated as accepted merely because a directory or filename exists. Future consumers need a complete valid manifest and matching fixture hashes. Existing output is deliberately never overwritten.
- Synthetic inputs remain synthetic; historical captures remain historical. This review makes no current-market, subscription-dollar, usefulness, trading-skill or release-readiness claim.

The strongest attempted refutation was that preparation-only labels could hide altered recipe facts or turn malformed input into seemingly complete output. The reproduced history and output faults were fixed without revising the frozen proposal, and final independent probes no longer reproduce them. Full case execution and semantic review remain separate unfinished work.
