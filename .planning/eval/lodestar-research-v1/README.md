# Frozen research comparison

This set contains 32 new functional prompts. It is separate from the development unit examples and future market-session evidence. The manifest digest fixes the prompt, context, data scenario and human rubric before candidate comparison.

Run the same saved fixture for deterministic-only and both approved model candidates. Record the exact commit, model, provider, policy and prompt versions; actual charged cost, request count, first-progress time, final-answer time, saved/reloaded outcome and full validated answer. Missing usage stays reserved and is not zero cost. No paid candidate has been run for this set.

Automatic checks cover request bounds, ticker scope, evidence identities, no probability/order claims, and saved answer equality. These checks do not establish usefulness, real database recovery, model improvement or forward edge. Each human rubric remains unscored until an independent reviewer assesses the same evidence and answer blind to model label. Count refusals, missing-data cases and errors in all denominators.

Score each rubric as met / partly met / failed / not assessable, with a quote from the answer and the exact supporting evidence. A supported refusal can meet its rubric. A generic list of readings cannot count as answering an unsupported company/event/action request. Any grounding, ownership, budget or order-boundary failure blocks release regardless of average usefulness.

After using this set to diagnose or tune a candidate, retire it to development coverage and freeze a new unseen set before claiming a held-out comparison. No pass is inferred from the existence of these files.

## First capture and exposure status

The independent agent review assessed all 32 captured baseline answers: 14 met, 10 partly met and 8 failed their rubrics. This is not human trader approval. Its calendar finding reproduced a four-session week bug; that implementation bug was fixed after the preserved baseline capture. The captured answers and review intentionally remain unchanged.

These cases are now exposed development/regression evidence. They are no longer an unseen holdout for any candidate changed in response to the review. Freeze a separate unseen set before claiming model improvement. Use a new named output for any subsequent run; the capture command refuses to overwrite prior evidence.

The questions digest is SHA-256 of UTF-8 text with universal newlines normalized to LF, preserving all other characters. This is stable across Windows CRLF checkout conversion and is not a semantic canonical-JSON hash.
