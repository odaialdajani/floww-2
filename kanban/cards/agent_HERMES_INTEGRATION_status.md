[2026-09-28T00:00:00Z] HERMES_INTEGRATION :: H3 slice COMPLETE :: branch=feat/h3-missing-input-neutrality :: HEAD=5cba1d9d :: base=d905c9d2
scope: backend/services/conviction_rank.py (norm_conf, norm_ml, rank_many blob guard)
tests: backend/tests/services/test_conviction_missing_inputs.py (NEW, 10 tests, red-first)
       backend/tests/services/test_universe_scan_conviction.py (expectation corrected + symmetry assertion)
gates: tests/services+tests/routes 4546 passed / 33 skipped / 0 failed; ruff clean
mutations: MUT1 conf->0.5 killed (2F) | MUT2 ml->0.5 killed (1F) | MUT3 old ml map killed (1F) | MUT4 blob guard removed killed (1F, only after 2 extra tests added; initially SURVIVED)
finding: packet's H3 mechanism ("fused score passed as flow") does not match code; real defects were absent-as-neutral 0.5, direction-in-quality 85.75-vs-60.25 asymmetry, and fused-blob re-read via key sniffing.
unchanged: tier thresholds; confluence/ml still supplied as None at flowseeker.py:2614,:2684 (open item, not claimed done)
next: open PR for 5cba1d9d and verify CI on exact head; do NOT merge without Nav's explicit go-ahead in-session
preserved: kanban/BOTTLENECK_ALERTS.md left unstaged/untouched (other agent)
no-merge/no-deploy/no-service-restart: honored
