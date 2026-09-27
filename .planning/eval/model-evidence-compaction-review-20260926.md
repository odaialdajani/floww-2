# Independent bounded evidence-compaction review - 2026-09-26

Scope: services/agent/explanations.py, codex_model.py, codex_bridge.py, model.py; focused existing tests and synthetic fake-client probes only. No held-out question/answer files were opened. No real model, provider, broker, app startup or production storage was used. No production files were edited. Owned output is this report plus temporary synthetic probes under output/compaction-review-1GR9gw/. The previously completed frozen30-case evaluation predates these changes and is not evidence of their answer quality.

## Confirmed compaction properties

A focused offline run passed32 tests: existing explanation/Codex/grounded-model tests plus five independent synthetic probes. --noconftest excluded app fixtures; tests.offline_network guarded real network; mock Mongo and fake bridge/httpx.MockTransport captured both actual request inputs.

- Exact reconstruction: replacing each evidence_group with its ordered list reproduces every original explanation dictionary, including ID, text, ticker, horizon and original ordered fact_ids. Distinct ordered lists (a,b), (b,a), and (a,a) stay distinct; matching lists share one group; empty lists round-trip.
- Scope: synthetic SPY/all, QQQ/all and SPY/week references remain associated with the original matching scope. The representation changes citation repetition only, not the original36-menu bound or the original per-explanation evidence selection. All source facts remain in both transport inputs.
- Mutation: facts unchanged after both model calls; mutating emitted citation lists does not mutate the original menu; wire text/group tampering does not change select_explanations regeneration from source facts.
- Output authority: evidence_1 is not an explanation ID; fabricated IDs and IDs from another ticker's facts fail selection. Existing server-side explanation selection remains authoritative. The lower-level model transports still report structurally parsed responses and rely on later server validation, as before.
- Admission: a synthetic multibyte oversized fact refuses both models before external/fake dispatch or quota/cost reservation. The default OAuth limit still admits exactly40 reservations and refuses41. No caps increased.
- Instruction wiring: Codex base/developer instructions and the OpenRouter system message both tell the model how evidence_group resolves via explanation_evidence. Captured Codex bridge content and OpenRouter actual POST user content both contain the same original facts and losslessly reconstructible explanations.

## Confirmed inherited boundary defect

An additional fake-transport boundary reproduction passed by demonstrating a defect: OpenRouter checks its48000byte body before adding provider.only. A preselection body of exactly48000bytes was dispatched as48026bytes after selection. The current HEAD version has the same check-before-addition order, so this edge predates compaction. It is not a fact-loss or explanation-forgery defect, but prevents claiming the final serialized request is capped at48000bytes.

Narrow recommendation sent to parent: after provider selection, recompute full canonical request byte count and reject above the cap before reservation/dispatch; calculate reservation from that final byte count. Source: output/compaction-review-1GR9gw/test_body_boundary.py. The existing8192-byte reservation allowance means this small demonstrated overage is not itself proof of spending above the reserved maximum. OAuth's existing limit applies to content rather than full app-server wrapper; no change to that design was made.

Verdict at20:48UTC: no losslessness, scope-mixing, mutation, forged-explanation acceptance or cap-increase defect found in the compaction itself. One inherited final-body cap edge was independently reproduced and reported for narrow repair. No fresh model answer-quality claim is made.

## Final closure - 20:52 UTC

Parent applied narrow final-body repair. Independently inspected that final canonical byte count is recomputed after provider.only, both the48000byte cap and selected provider context fit are checked before reserve/dispatch, and monetary reservation uses the final byte count. Adapted only the owned output boundary probe from demonstrating a dispatched48026byte request to requiring unavailable, no second POST, and no reservation.

Final focused command: backend virtualenv Python -m pytest --noconftest output/compaction-review-1GR9gw/test_compaction_review.py output/compaction-review-1GR9gw/test_body_boundary.py tests/agent/test_explanations.py tests/agent/test_codex_model.py tests/agent/test_grounded_model.py -q -p tests.offline_network -o addopts= --tb=short (output paths supplied absolutely; cwd backend). Result: **36 passed, 1 existing Hypothesis directory warning, 0.70s**, exit0. All clients fake and stores mocked/memory-only. The rerun includes exact-at-cap reservation, one-byte-over-cap refusal and final provider context mismatch regressions.

SHA-256 of exact reviewed production sources, unchanged before/after final run:

- backend/services/agent/explanations.py: c1f2b5fa216782bdf1e8b767517eb29dbcd790722874d66a98c58205c8f26031
- backend/services/agent/codex_model.py: e9d1d7c909c57c9d7c206a3d11cb833f0223252d1e5c391b473e9448a9fdf7d3
- backend/services/agent/codex_bridge.py: 677b9c1db16202f5209c00f5a422ef8304d3c8a17570b97c2f7ce7c2eb68271f
- backend/services/agent/model.py: fccb7c068e400380bd5d012831422cf376e2df068e6f11b161dbe423f825f8a3

Final bounded verdict: inherited body-cap finding is closed at these hashes. No outstanding defect found in the requested compaction/size-admission scope. This is structural and fake-client validation; it does not upgrade the pre-repair frozen evaluation into a fresh answer-quality result.
