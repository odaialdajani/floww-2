# SPARK_STATE — Solstice R11/R12 implementation (Spark owner post-Zed handoff)

- HEAD: `72cdd943` on `solstice/r11-opus` (== origin). Base `origin/main` = `ca3dd8b5`. PR90 OPEN, mergeable, UNSTABLE (lint job fails only on silent-except gate: `backend/routes/solstice_scan.py:50`).
- Zed WIP (67 dirty paths, strip-back direction) backed up to `/tmp/zed-wip-backup/` (patch verified re-appliable; untracked tarball). Checkout restored to clean HEAD. Untracked user files kept in place (2 local coverage tests, evidence/, SolsticeSymbolMaps, r11 scripts).
- Hermes baseline worktree: `/tmp/floww2-head` (detached @72cdd943).
- Done: items 1 (invalid-vs-missing delta split: canonical, kernels, coverage, profiles, grid/inspector UI, docs), 2 (scan feed warning + red test; gate clean; API docs 373 paths current; PR89 behaviors green), 3 (indigo layout verified vs fixture receipt), 4 (Raw+Δ 2-pane compare; listed-date scope bound; replay context restore), 5 (App arrow-key hijack fixed; shell 100dvh binding kills fitRows feedback; full browser receipt passes 13 views + 60 resizes).
- Next: item 6 — Lodestar context gating (extend only with snapshot-resolved acceptance tests, else explicit unavailable).
- Blockers: none on implementation. No deploy/orders/retrain.
