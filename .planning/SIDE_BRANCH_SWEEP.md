# Complete side-branch reconciliation - 2026-09-27

Status: RECOVERY VERIFIED; publication and branch cleanup pending. Main starting point: ed6bce671bd4f58d195d2350b1d6bf2ba8715473.

## User outcome

Sweep all side branches, reconcile useful missing work with current main and colleague work, validate the combined result, commit/push main, delete side branches only after useful work is recovered, verified and archived; continue with main only. The previous zero-divergence result covered the current work branch only and is not an exhaustive historical certificate.

## Completion checks

1. Freeze and preserve all current references and local side work; keep a verified recovery bundle.
2. Account for every nonancestor remote branch, every distinct unmatched non-merge patch, and unique merge-resolution edits. Each requires an evidence-backed disposition, not an assumption based on its name.
3. Port missing useful changes into the current implementation with tests; preserve later accuracy, source freshness, data availability and interface decisions. Do not replay obsolete whole files over corrected code.
4. Keep previous paper/live restrictions. Latest owner direction20:21: useful removed work must be recovered; obsolete work may stay removed. Restore based on actual missing value and current compatibility, not age or branch labels.
5. Retain historical documents, old models and retired implementations as recoverable history with clear labels. Archive status is not a claim that obsolete features are active or model artifacts are validated.
6. Only mark branch histories reconciled after their code, tests, records and merge-only edits are accounted for. Verify final ancestry and zero unchecked review items.
7. Run the relevant failure reproductions and final combined checks, independent review, real display/path checks where changed, then ordinary non-force push main. After all preceding checks, delete the explicitly inventoried side branches; retain recovery bundle and reachable historical records. Refuse deletion of any tip that moved since review.

## Frozen inventory and recovery

-Initially275 origin branch references;99 tips not literal ancestors of main. One later colleague branch (3commits, identical to main squash ba845699) was also reviewed.
-318 distinct non-patch-equivalent non-merge commits:180 historical-document commits,100 backend/tooling commits,23 frontend commits,15 mixed commits.
-35 merge-only resolutions reviewed; no unique missing useful resolution found.
-284-ref full bundle verified at output/side-branch-sweep-20260927/before-sweep.bundle.
-Old20260926 integration copy:209 changed files copied and byte-verified, staged/unstaged patches preserved. Its185/187 backend added lines and86/90 frontend added lines are retained verbatim; remaining lines reviewed as stronger later changes. Broader staged revisions remain covered by historical/sweep review, not silently assumed.

## Work ownership

Root owns integrations, document/evidence preservation, tests and publication. Independent reviewers examine backend, frontend and merge-only history. Review files and exact candidate/patch inventories are local under output/side-branch-sweep-20260927 until conclusions are safe to publish. No outside provider/model/broker calls are needed for the branch audit.

## Clarifications and limits

User20:21clarified useful work should be restored and useless removed work may stay removed. Final desired state is main only after historical preservation and verified useful-code reconciliation. A whole obsolete feature is not useful merely because its branch was never merged; compare current replacements and preserve history. No claim of global optimality or profitable trading accuracy can follow from a successful merge alone.

## Verified recovery result

All769 initially nonancestor commits are individually accounted for (318distinct unmatched nonmerge,416main-equivalent nonmerge,35merge-only). Three later colleague commits and one final documentation update bring the total to773. Full original reviews are preserved in `.planning/eval/side-branch-sweep-20260927/full-review-evidence.json.gz`; compact per-commit and recovery decisions are beside it. Historical classifications describe the starting state; final recovery decisions supersede missing/partial labels.

364combined backend tests passed with current dependencies onPython3.13;104frontend suites/914tests and production build passed. Independent recoveries and four strict typing modules passed. Browser tooling exposed no available browser; actual rendered verification remains unavailable and is not claimed. No actual Python3.12 local execution or live/provider/model operation was performed.

Recovered command error/counter/help behavior, detailed account readings with real broker shapes and missing-value safeguards, chart focus/scrollbars/manual review controls, research storage/explicit notification/pure position checks, type safeguards, optional five-ticker command, edge tests, route outage/consistency checks, Windows setup guide and security pin. The original measurement upgrade plan and all three local model hashes are preserved unchanged.

Unsafe pooled Roll/pin/drift displays, parity-breaking feature optimization, platform-only binary and obsolete external AlphaPod capture stay archived. AlphaPod capture is only an iframe into an old localhost3456 service, with no unique math/data; shared accessibility support survives. This implements the owner20:21 instruction allowing obsolete work to remain removed.

Existing nonfinite Greek input handling and fractional order-list display are follow-up items, not claims of full application correctness. Retired test bytecode was preserved outside source to prevent a false presence failure.
