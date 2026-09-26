# Independent evaluation-resumption safety review

Date: 2026-09-26, completed 20:34 UTC. Scope: changes to backend/scripts/oauth_heldout_v2.py since commit99008be3. Final reviewed runner SHA256: `0aa977e3e9db2350e2acb6baaa48835eda8286f78be334e60beaf32b9c9597c4`.

## Result

Bounded pass after two independently reproduced gaps were repaired by the parent. This approves the reviewed runner safeguards, not candidate quality, evaluation acceptance, provider data, a changed quota, or any trading action. No candidate/model/provider request was made by this reviewer. Literal frozen questions, case expectations and candidate answers were not inspected.

## Findings reproduced, then closed

1. Earlier revision execution did not revalidate its recorded parent references. Changing a synthetic original input after refreeze still reached model-state preflight. Current validate_resumption resolves both parent references, verifies the preserved input/seal link, and compares every original field except the deliberately updated code hashes. The same probe now raises Frozen input changed before constructing either storage client or model.
2. Earlier CLI permitted prepare/seal with --revision, and revision execution accepted missing resumption metadata. A synthetic revision without an anchor reached model-state preflight against an empty usage collection. Current CLI requires refreeze for new revisions; execution requires the exact preserved historical anchor. The same probe now raises Revision requires the preserved usage anchor before constructing storage/model clients.

The independent probe is output/eval_resumption_review_probe.py. It compiles selected current runner functions from their actual syntax tree, supplies only synthetic temporary artifacts and fake storage/model classes, and deliberately stops before settings/exercise/dispatch. No production code was edited by the reviewer.

## Verified safeguards

- Refreeze retains the complete original synthetic cases and source references; existing revision files are refused. Original input/seal fixture bytes stay unchanged.
- Actual original frozen inputs and execution seal remain byte-identical to commit99008be3. Only hashes/equality were examined. Current input SHA256 is `00eef687dd33d7bc325fb2e9bd34830445f9357fb8d51546a5ae88a6d28c98d2`; original seal SHA256 is `a97a566466dd2f520e9fba608687c37690cf7ddf1b264aa7084709de4ad71262`.
- A synthetic research-code edit after sealing is refused before any clients/model are constructed. Execution still requires exact seal equality and per-file frozen hashes; resumption does not silently relax drift checking.
- A missing historical usage record in the selected usage collection is refused before model construction. Both already-created clients close on that refusal.
- Independently reran all14 focused parent tests:14passed,0failed,1.24seconds. Their synthetic paths include invalid revision/endpoint, changed original input, changed resumed case/candidate fields, changed parent reference, absent anchor, denied revision prepare/seal, empty ledger, failed baseline, insufficient daily allowance and unavailable model settings. The preflight tests confirm both clients close and no output is created.
- Read-only Mongo probes found original storage127.0.0.1:27018 / floww_public_research_acceptance / agent_oauth_usage still holds day:2026-09-11 with calls34. The same historical record is absent on isolated127.0.0.1:27017. Only this one ID and its calls field were read; neither store was modified.
- CodexModel still constructs OAuthUsage without an override, whose default daily limit is40. There is no new runner quota-setting argument. A separate synthetic test executed the actual OAuthUsage class: a ledger field daily_limit999 was ignored, state retained40, and the reservation guard at calls40 used calls<40 and refused a reservation. No real quota reservation was made.

## Boundaries

Parent owns final freeze, the zero-model baseline and any later authorized candidate run. The reviewed runner binds separate data/usage endpoint identities into its execution seal. Existing historic34calls were neither reset nor transferred into an empty ledger. Current-day usage and candidate allowance remain governed by the existing40-call daily counter; this review does not grant an increase.

Temporary fixture directories were created only under output and removed by their owning Python TemporaryDirectory scope. No original artifact, application window, running service, provider endpoint or production source file was changed. Concurrent history/catalog edits were outside this review and were not inspected or reverted. No full suite or candidate evaluation was run by this reviewer.
