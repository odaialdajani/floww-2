# Comparison command control review - 2026-09-27

Verdict: reviewed control findings closed in the inspected source and development checks. This is not fresh-comparison execution or release acceptance. No new acceptance requirements were added.

## Independent execution

The reviewer independently ran `backend/.venv/Scripts/python.exe -X utf8 -m pytest tests/agent/test_comparison_run.py tests/agent/test_comparison_transport.py --noconftest -o addopts= -q` from `backend` using Python 3.11.15.

Result: **23 passed, 0 failed, 0 skipped, 3 warnings in 4.86 seconds**. Warnings concern existing Hypothesis collection configuration and deprecated websocket interfaces. The reviewer read every result and the corresponding test assertions. These checks use invented development inputs, in-memory storage doubles and owned loopback HTTP listeners. No frozen functional answers, model calls, provider requests, shared quota changes or production-store writes occurred. The review changed only this report.

## Findings and closure evidence

| Original control finding | Current evidence and scope |
| --- | --- |
| Another output directory could repeat the same interrupted arm. | Before any case admission, `execute` inserts a unique durable registry claim using the fixed cohort identity plus arm. The claim survives failures. The development failure test attempts a second output directory, gets duplicate-key refusal, and observes exactly one call into the substituted development executor. Actual registry crash persistence was not exercised by this reviewer. |
| Re-sealing identical inputs could evade a seal-hash-only claim. | `cohort_identity` derives from the ordered 32 case IDs and raw fixture hashes, independent of randomized blind assignment, output path and seal time. Two development seals have the same identity. Execution uses that identity for its registry key, and seal verification recomputes it. |
| An entered case could be reported as `not_run` after an exception. | A durable started record is written before the case executor. The interrupted development test asserts all 32 rows remain, the entered row is `started_outcome_unknown`, and only the untouched 31 remain `not_run`. There is no automatic retry. |
| A transport exception could lose the owner/request identity needed to locate charged work. | The transport saves owner plus request ID before POST, then the returned turn ID after successful admission. Development tests verify both identities and the actual saved turn. A failing pre-request identity save causes zero admitted turns. A missing post-admission record can still be resolved from the already saved owner/request pair; this is recovery evidence, not retry authorization. |
| The critical receipt and closed-binding evidence could change without execution noticing. | Preparation retains these hashed references in `attachments`; end-of-preparation and execution verification recheck their bytes. A test mutates the critical receipt after sealing and asserts refusal. Added backend source also invalidates the execution identity. |
| Package tuples changed type after writing and reading a JSON seal. | Package identities now use lists. The test invokes the real environment-identity function and verifies exact JSON round-trip equality, rather than testing only a stubbed identity. |
| Hashing and parsing different reads allowed unverified bytes to be decoded. | Both `read_reference` and `verify_seal` hash and decode the same byte buffer. An adversarial development test makes a second file read return different JSON, then asserts the helper performs only one read and returns the checked value. |

## Other controls inspected

- Pending stronger-model/cost choices block preparation/sealing; requiring actual dollars is not silently converted into accepting unknown dollars. A candidate requires the explicit execution flag. Development tests check those refusals before output/admission.
- Manifest, oracle and grading IDs must preserve all 32 cases in order. Removing a manifest row is rejected rather than shrinking the denominator.
- Source catalog, fixture, independent expectation, grading, review, authority, dependency and executable identities remain checked. Reopening a saved answer is separate from grading it. Execution records `executed_not_graded` and never claims acceptance.
- Owner settings are copied into a newly admitted owner's preferences and read back before asking. The existing measured model wrapper forwards settings selection and the single-attempt property. This change does not force model routing or grant authorization.
- Actual model-entry and managed-dispatch counters remain distinct from upstream requests and dollar cost. Completed candidate turns read their actual owner from isolated storage before querying shared usage evidence. The command checks route maximums; missing/uncertain dispatch is not inferred from answer success.
- Quota checks retain the shared daily limit of 40 and historical usage minima. The tests prove a new/reset ledger and insufficient headroom are refused without altering their usage. The current whole-arm preflight conservatively asks for 32 slots, although the proposal has bypass/refusal cases. This can refuse sufficient narrower headroom; it does not raise the limit or authorize extra calls, and is not a new release gate.

The reviewer also inspected the root-produced `output/research-comparison-preparation-20260927-0000.json`. It retains 32 functional fixtures and 14 critical cases and reports blocked preparation: independent binding review, unresolved evidence, actual critical receipt, stronger choice and cost reply remain open. The reviewer did not rerun that preparation command or treat its saved artifact as a sealed comparison.

## Reviewed identities

| File | SHA-256 |
| --- | --- |
| `backend/scripts/research_comparison_run.py` | `36a6760b3b0131aa0d5a3475706acd1bb7315b00be5c008f60934bdc3ec74d91` |
| `backend/scripts/research_comparison_transport.py` | `7257397006d0718d812e2ca58a8842511e60a7c6bf518730e83a1078dd4426af` |
| `backend/tests/agent/test_comparison_run.py` | `0b72153d58c44bee5260adf00781e0cffc158af0f0780bcf88a19e3913fe5e2e` |
| `backend/tests/agent/test_comparison_transport.py` | `3c4c7db2945033d82c3e92cc9379e81cf6a2889ac1d7993b93260eacafed8636` |

No remaining concrete control defect was established in this bounded review. Actual frozen-case execution, live candidate behavior, real interrupted-process recovery, grading, browser display and overall plan completion remain outside this development result. Existing prerequisite decisions and evidence requirements are unchanged.
