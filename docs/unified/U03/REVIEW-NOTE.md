# U03 — Independent review: unpromoted older Triad desk proposal

Owner: OpenCode. Reviewer: Cline. Status: dossier recorded, pending Cline review.
Disposition scope: REVIEW ONLY. Nothing in this task mounts, copies, or
promotes the proposal into the 8194 candidate.

## Proposal identity

- Original proposal SHA: `630716f5847303c6ba091d20560516aa3e8c4e1c`
  (branch `solstice/opencode-r19-triad-desk-20261007`, PR115 review-only).
- Repair head: `8320b0ab424ff5636eac3380044dac8ea3258dc2` (OpenCode,
  pushed to the proposal branch under the prior packet; exact-head review
  `references/continuation-review-pr115-630716f5.md` prescribed the three
  repairs — this harness did not re-derive them, it verifies them).
- Candidate boundary (baseline `8194eca4`): ZERO references to
  `TriadDesk`/`TriadExposure` in `frontend/src/App.js`;
  `frontend/src/components/triad/` holds only `StrikeExposureProfile.jsx`
  and `useReviewJournal.js`. The proposal is unmounted. Latest
  TrinityView/volatility/navigation intact (no triad-lane file touched in
  unified lanes).

## Historical findings vs exact repair head (reproduced from the review doc)

1. Partial exposure shown as fully measured → FIXED: per-strike
   nKnown/nTotal, hatched partial bar, `Partial n/m measured` title,
   `data-partial` flags. Pinned: 780 (1/2) partial, 775 (2/2) complete.
2. Axis labels raw dollars as millions (`+200M`) → FIXED:
   `formatExposureTick` (raw dollars below 1M, M at/above). Pinned: `+200`,
   `−200`, `1.0M`-style; `+200M` asserted absent.
3. Next-listed re-selects same-day expiry → FIXED: earliest admitted strictly
   future DTE (range_map filtered by row DTE, fallback likewise DTE>0).
   Pinned: 0DTE → Next fetches `expiration=2026-10-14`, not `2026-10-07`.
4. Measured-zero vs all-unknown distinguished (zero renders known marker,
   unknown renders gray slot).

## Receipts bound to the repair head

- `TriadDesk` suite: **11/11 green at exactly `8320b0ab`**
  (7 pre-existing + 4 repair pins), re-run on the committed head —
  command `CI=true craco test --testPathPattern="TriadDesk"`, exit 0.
- File SHA256 at head: `TriadExposure.jsx`
  `4c84eda7b13a0a35c9ddcd551652a7f0e93d503729581d2fb019e612e4ed2ca3`,
  `TriadDesk.jsx`
  `5f1b49e3dabec61ab75db85c8d5c9b4e1643234110c643a9314f2efca30bd636`,
  `TriadDesk.test.jsx`
  `a7a0b8495bfc3e0f0bd3985947f1df4129daaf70c58883caf2a4e974b56b67df`.
- No order-surface calls in any test (every fetch URL asserted
  non-broker); SPX entitlement, abort/reorder, copy-context, empty-state
  behaviors retained (pre-existing 7).

## Hosted gates on the repair head (2026-10-08)

`gh pr checks 115`: all four green at the repair head —
backend-tests 17m48s, docker-build 3m59s, frontend-build 3m27s, ruff 2m14s
(run 37706066474/66482). These cover build/lint/test compilation, not the
three consumer counterexamples (covered by the 11/11 above).

## Main-branch gates on the merge (2026-10-08)

`f1e76e82` on `main`: lint SUCCESS (2m7s), full CI/CD SUCCESS (22m15s,
runs 37708985400/37708985364). Merge-gate loop closed. Remaining T03 step:
Cline post-merge adversarial review (no recorded review at merge).

## Mount update (2026-10-08 — supersedes "unmounted" above)

PR115 MERGED as `f1e76e82` (fast-lane, zero recorded reviews — same pattern
as PR111/PR114). The proposal is now mounted in `main`: merged `App.js`
imports `TriadDesk` and renders `<TriadDesk ticker={ticker} />` inside the
legacy Triad View section. Wiring passes ONLY `ticker` — no order/submit
props; `TriadDesk.jsx` references no order API (verified by read at the
repair head, byte-identical at `f1e76e82`). Sibling legacy trade-submit
handlers in the same view are pre-existing mainline code, untouched by the
PR (PR App.js delta was 9 lines: import + mount). Cline post-merge
adversarial review should explicitly confirm the mount introduces no
order path through the new desk. H-TRIAD-PROMOTION is now a merged fact,
not a hold, for this branch — recorded, not waived by OpenCode.

## Classification

REPAIR_REQUIRED items from the historical review are repaired and pinned at
the proposal head. This dossier does NOT admit the proposal to the app and
does NOT substitute for Cline's adversarial raw-patch review + merge
decision on PR115 (prior-packet T03, still the gating step there).
Promotion/mount would need a separately authorized scoped task
(H-TRIAD-PROMOTION hold stands).

## Next

Cline: adversarial review of the `630716f5..8320b0ab` raw patch on PR115;
merge per fast-lane only on your ACCEPT.
