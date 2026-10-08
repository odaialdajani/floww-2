# U03 — Cline independent verdict: ACCEPT (review dossier). Proposal stays unpromoted; PR115 merge remains held for Nav.

Reviewer: Cline. Adversarial raw-patch review of `630716f5..8320b0ab` on branch `solstice/opencode-r19-triad-desk-20261007` (PR115), bound to full SHAs:
- proposal `630716f5847303c6ba091d20560516aa3e8c4e1c`
- repair head `8320b0ab424ff5636eac3380044dac8ea3258dc2`

## Defect-by-defect verification against the exact patch (own read of `git show 8320b0ab`)

1. **Partial exposure rendered as fully measured (P1)** — repaired as prescribed:
   per-strike `nKnown/nTotal`; partial = `nKnown>0 && nKnown<nTotal`; partial bars render
   dashed yellow stroke + reduced opacity + `<title>Partial exposure n/m measured</title>` +
   `data-partial/known/total` attributes. Unknown siblings keep their own gray slot and are
   never zero-filled into the subtotal. Measured-zero (known gex=0) renders a known marker
   (min-height 2 bar), distinct from all-unknown gray. Verified in diff AND in the shipped
   pins (780=partial 1/2, 775=complete 2/2) which I re-executed.
2. **Raw dollars labeled as millions (P1)** — `formatExposureTick`: raw below 1M
   (`+200`, `−200`), `M` at/above 1M with one decimal below 100M. Pins assert
   `'+200M'` absent and `'+200'` present. Axis zero/unknown distinctions retained. ✓
3. **Next-listed re-selecting same-day (P2)** — `admitted_expiries` now filtered through a
   row-DTE map to strictly `dte > 0`; fallback likewise `admitted && dte > 0` sorted ascending.
   Expiry listed but missing from rows is conservatively excluded. Pin fetches
   `expiration=2026-10-14` with `2026-10-07` co-listed. No-next-series disclosure retained. ✓
4. **Measured-zero vs unknown** — distinct render paths, pinned. ✓

## Preserved invariants (regression check, exact head)

Pre-existing 7 pins all pass: SPX entitlement honored, abort on ticker switch, reorder
protection, copy-context, empty-state honesty; every fetch URL asserted non-broker — no
order surface anywhere in the proposal. Legend updated ("Partial hatched") consistently.

## My own receipts

- `TriadDesk` suite re-run **by me** on the clean exact-head checkout
  `/private/tmp/r19-triad-desk-20261007` @ `8320b0ab`: **11/11 pass**, exit 0.
  Log: `../evidence/cline-verify-triad.log` sha256 `0e8cce38fff3ef12...`.
- Hosted gates at `8320b0ab` re-queried by me (`gh pr checks 115`):
  **backend-tests pass (17m48s), frontend-build pass, ruff pass, docker-build pass**;
  PR mergeable = CLEAN. All four required hosted gates green at the exact head.

## Disposition

- U03 dossier acceptance = review complete: **ACCEPT**. All three historical REPAIR_REQUIRED
  items are repaired and pinned at the exact repair head; nothing borrowed, every claim
  re-executed or re-read against source.
- The proposal remains **unmounted** in the `8194eca4` candidate (zero TriadDesk/
  TriadExposure references in App.js, verified in the dossier and consistent with my U01
  read). Task acceptance ≠ promotion.
- **PR115 merge: NOT performed.** This harness authorizes no commits/pushes/merges;
  merging a main-based PR would also promote the desk into main, which remains under the
  proposal-promotion hold and Nav's release hold (NAV-RELEASE). Prior-packet T03 therefore
  stays open on exactly one input: Nav's explicit merge/promotion decision. All engineering
  prerequisites (adversarial review + 4/4 hosted gates at the reviewed head) are now met.
