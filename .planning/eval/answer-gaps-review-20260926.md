# Independent development-only answer-gap review

Result: no new blocking defect found in the four-file change reviewed. This is offline development evidence, not fresh held-out acceptance.

## Checks run

- 43 focused existing history and initial-capability tests passed in 1.44 seconds using backend/.venv and isolated test collection.
- 15 independent adversarial checks passed through a temporary probe in output/answer-gaps-review-probes.py. Results are retained in output/answer-gaps-review-probes-result.json.
- The probe used an in-memory Mongo substitute and synthetic XLK observations, separate from the frozen comparison. No model/provider calls or live account/store changes were made. Every child process used Node execFile with windowsHide:true.

## Attempts to refute the change

History: multiple records with different source times selected the newest relevant coverage mismatch and displayed its exact 3-versus-8 counts. Other-owner, future, wrong-ticker and wrong-horizon records did not contaminate the note. A new owner received no count leakage. Closing-history requests ignored intraday mismatches. Invalid boolean coverage was not rendered as a count. When a genuinely compatible older record existed, the existing matching-history behavior returned its price change with its actual older observation time, rather than attaching the newest mismatch time.

Volatility: null, boolean, negative and infinite IV values did not count as positive inputs. An explicit instant with the wrong contract date did not count as usable. Healthy non-ATM contracts and a later valid expiry could not enable an estimate when the nearest ATM pair lacked inputs. The calculator was replaced with a function that would fail the probe if any such invalid case reached it. A valid ATM pair still produced an estimate after restoring the calculator. Missing price, stale-but-present price and unknown chain time remained distinct. The revised explanation says estimates are absent while raw inputs may exist, avoiding a claim that IV itself must be missing.

The full-service test independently rerun among the 43 focused tests demonstrates that an earlier-saved question reaches the history path and preserves the coverage mismatch in the saved answer without inventing a price change. The new previously alternative is visible in the same intent expression; it was not separately exercised through a second end-to-end saved turn in this review.

## Limits and verification notes

The positive-IV and future-expiry counts are deliberately separate counts across saved contracts. They do not prove the same contract pair supplies both. The new displayed sentence explicitly says this, and the independent non-ATM/later-expiry probes confirm the original strict estimate checks still decide eligibility.

An initial test attempt selected backend/.venv313, which lacks mongomock_motor, and stopped during collection. The correct backend/.venv completed all 43 tests. The first custom probe had missing unique request identities in its own inserted fake rows; after fixing only that test fixture, all 15 checks passed. Neither was an application regression.

No production files or frozen comparison artifacts were changed by this reviewer. Only this review and temporary output probes/results were written. The prior blind-grade SHA256 remains 5e4b98bebe7d3315348533d1929cfaa5ba59bd24806ed8f03d2ba03c50f429d5. The old comparison scores and incomplete acceptance verdict remain unchanged. These fixes were developed after exposure, so they require new independently frozen questions before any new unseen acceptance claim.

## Reviewed source hashes

- backend/services/agent/research.py: e42a107ba407c08d841144efd0e2b6114311e73e1fbd62102aac11b5974b862f
- backend/services/agent/saved_history.py: 283b820a4a31a5fe08d2f129d54d74462a3e6625053d1155d84ff1f96ed44903
- backend/services/agent/volatility_reads.py: db605cfc07a02e78e118a9af5ae8e930b9d90b7eeb1c9409503bb56b54d0c9dc
- backend/services/agent/explanations.py: c6ffc90647fa863896b5aabb1769c4908ab3a6e0b8b2d97f839737c0eb00b28b
