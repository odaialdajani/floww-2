# R13 hosted container acceptance

Package A, Revision 2. Base/main: `9a6c02954557922e9b0d73d6011daf7430f72c16`.
Previous candidate: `c9c02750295426954131226b29e6aa88d6334d24`; its Docker job was **skipped**, not tested.

## Gate and boundary

The existing `docker-build` job builds the Python 3.12 backend and Node 20 frontend images and smoke-tests backend import/frontend static assets. It contains no registry login/push, deployment action or production secret. Azure deployment remains manual-only; this change does not dispatch it.

Main retains its gate. Same-repository pull requests now run it; fork heads do not. This job has only `contents: read`, checks out the exact PR head (otherwise `github.sha`), verifies/logs that SHA, labels both images with it, and logs image IDs/platform/revision. Runtime smoke uses `--network none`, starts no app lifespan or service, and checks nonempty frontend index/asset manifest plus JS/CSS directories. Build dependency downloads remain networked. This is build/import/static-asset acceptance, not HTTP readiness, live-market, deployment, human or strategy acceptance.

No local Docker daemon is started. No frozen Docker/application configuration is changed. Backend/frontend/lint must pass on the fresh candidate, followed by an **executed successful** Docker job before merge. The old skipped run cannot validate the workflow correction.

## Regression and content binding

- `tests/solstice/test_r13_container_gate.py`: four failures on the old workflow, then four passes with this correction. Docker boundary/runtime-doc module sweep: **12 passed**; focused Ruff and whitespace pass.
- Separate self-review: condition excludes fork heads; explicit candidate checkout; read-only permission; no masked failure, publish/deploy step, secrets or daemon startup. Branch protection API returned 404; no protection policy is inferred from that response. Harness gates remain mandatory.
- All **71 protected paths** match the verified base.
- Application content remains unchanged from `c9c02750`: **362 browser-bound source hashes** match; compiled/served bundle hashes match. Fixture SHA256 `9ae4ac44bcde416a9207be4a5bcbe69598d99fcfa0be9ae6a2142821a77caf9d` is unchanged.
- Reuse the prior source-bound 16-shot/60-resize/native Chromium 200% receipt **by content equivalence only**. Its source/build label stays `c9c02750`; it is not relabeled as a new capture. Historical `r11` CSS-zoom evidence stays unchanged.

Fresh exact-head CI result/image identities and merge verdict will be published on PR91 after execution. Until then: **pending, no merge/completion claim**.
