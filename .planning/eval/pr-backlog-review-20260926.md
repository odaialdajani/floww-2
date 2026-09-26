# Open pull-request backlog review - 2026-09-26

Read-only review while the parent integrates incoming main. Only this report was written by the reviewer. No branch switch, reset, merge, commit, dependency installation, provider/model/order call, remote comment or PR mutation was performed.

## Frozen references and scope

- Local pre-merge HEAD: `dba50893403922a2f82e2be7c5a2671ea8d37780`.
- Incoming main: `79b28ec25d4f9c3cedd983ecd14a27e88b2f8948`.
- Open PR metadata was read live with `gh pr list --state open`, including exact remote head IDs. Code comparisons and mounted probes used immutable Git snapshots, not the concurrently changing conflicted worktree.

| PR | Exact head | Recommendation |
| --- | --- | --- |
| 49 | `d9371e22ce0644a8c42316137d347a44701eda01` | Bring in its bounded sidebar source/test fix after the main merge. Screenshot artifacts are optional evidence. |
| 12 | `2f7013f13cb862df0a0729e0b5eb1597dfcb2d7a` | Port useful paging commit `07cf098c50f5fbe3d2118f72c8dd1d850b6ca692`, correcting the reproduced page-state defect. Do not blindly merge the whole branch. |
| 3 | `ca255571c3e2dae059567fba3f74d180750b1e38` | Unchanged since earlier review; retain the prior do-not-merge decision. |
| 4 | `008e31b95f7076e1fe1da143055918ecc854b658` | Unchanged since earlier review; retain the corrected local source-time handling instead of merging. |
| 5 | `7d3d75c58c9baa254922770177fdf27c88e23aee` | Unchanged since earlier review; retain the prior do-not-merge decision. |

## PR 49: useful, narrow correction

Its sole commit has incoming main `79b28ec25d4f9c3cedd983ecd14a27e88b2f8948` as its direct parent and merge base. The delta is two frontend source/test files plus a screenshot index and two PNGs: 23 added lines, one removed line, excluding binary bytes.

`SkylitMetricsSidebar` currently calculates raw structural gamma totals and wall/node anchors even when the main grid shows VEX or Charm. Main labels the section using the active grid mode, which can imply those summaries are VEX/Charm values. The PR labels those cases `GEX structural` and keeps GEX/overlay behavior. This correction is absent from frozen incoming main. No data formula, request, trading behavior or dependency change is included.

Independent mounted React probes using the PR component passed for raw VEX, raw Charm and raw GEX headings. The VEX/Charm probes expected `Key Levels · GEX structural · OI`; GEX retained `Key Levels · GEX · OI`. These are bounded semantic rendering checks, not verification of screenshot provenance or a full visual audit.

## PR 12: useful paging with one reproduced defect

Merge base is `5db4971a297164023547911991c9984ed5193ef2`. The unique commits are:

- `07cf098c50f5fbe3d2118f72c8dd1d850b6ca692`: adds ticker pages and four mounted tests.
- `2f7013f13cb862df0a0729e0b5eb1597dfcb2d7a`: only adds an fsevents resolution to yarn.lock; no paging dependency requires this additional change.

Ticker bar and universe helper blobs are unchanged between that merge base, frozen incoming main and local pre-merge HEAD. Therefore the useful paging behavior is not already present. Main currently shows the first 500 buttons plus an out-of-window active ticker; full-universe search already exists. The PR adds reachable 500-button pages and follows externally selected listed tickers. The underlying universe preserves supplied order; this is pagination, not a new alphabetical sort or evidence of full exchange coverage.

Independent mounted probes passed the PR's normal next-page, previous-page, disabled-boundary, active-follow and small-universe behaviors.

**Confirmed defect, medium:** page state is only visually clamped. With a supported free-text/unlisted active ticker, the follow-active effect does not reset the stored page when the universe shrinks. Reproduction against the actual PR component:

1. Supply 1,500 symbols and active ticker `NOTLISTED`.
2. Click Next twice, reaching stored page index 2.
3. Replace the universe with its first 600 symbols. The visible page clamps to index 1 and reads `showing 100 of 600 · page 2/2`.
4. Click Previous once. The handler decrements stale stored index 2 to 1, leaving the visible page unchanged at `showing 100 of 600 · page 2/2`.

The branch's four tests do not cover a shrinking universe with an unlisted active selection. Correct the stored state when the page count shrinks, or derive navigation from the clamped current page; retain full search/free-text behavior and add this exact regression before accepting the port. This review did not modify the PR or implementation.

## Older PRs: freshness verification only

PR 3's live tip matches the exact `ca255571` tip recorded in the existing session checkpoint. PRs 4 and 5 have unchanged remote-ref reflog entries from the original 2026-09-11 fetch at 11:24:34 -0400; their current live GitHub head IDs match those entries exactly. No full repeat audit was justified.

The retained earlier findings, from repository checkpoint/goal documents, are: PR 3 restores obsolete AlphaPod/UI behavior and useful narrow fixes already exist; PR 4 substitutes current receipt time for absent source time, making old cached evidence appear fresh; PR 5 includes broken literal-plus lines and obsolete tab behavior. The original review recorded Ruff failures on 4/5. These historical defects were not rerun or relabeled as newly tested in this review. No PR was closed or commented on.

## Verification method and limits

The custom read-only Node probe loaded each exact Git blob through Babel in memory and mounted the real components with installed React, jsdom and Testing Library. The universe helper came from frozen incoming main. Fetch was replaced with a throwing guard. No temporary source files or dependency changes were needed. The successful probe printed the normal paging passes, the exact unchanged-before/after page defect, and all three sidebar-heading passes. An initial probe-loader attempt failed before rendering because its in-memory module filename was unset; fixing the runner metadata produced the successful results above and did not touch a running application.

No full frontend/backend suite was run because the parent is resolving a concurrent integration. Recommendations apply to the exact commits above; the final integrated source still requires its own regression and build checks.
