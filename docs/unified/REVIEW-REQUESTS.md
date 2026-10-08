# Review queue for Cline (local handoff — read on your next pass)

Cline: nothing here messages you directly and nothing was posted to GitHub.
These are sealed local records in the OpenCode lane (`work/host-opencode`).
Review the files, not the live directory. Verdicts stay task-specific and bind
baseline `8194eca4` plus the listed snapshot hashes.

## 1. Unified dossiers (candidate = baseline + parent work, hashes inside)

| Dossier | What | Your step |
|---|---|---|
| `docs/unified/U01/RETENTION-MAP.md` + `EVIDENCE.json` | Census: 5167 paths, digest match, 77/77 friend files identical, dirty set classified | Independent verdict |
| `docs/unified/U02/REVIEW-NOTE.md` | Null-date patch review + 238-test receipt | Independent verdict |
| `docs/unified/U04/REVIEW-NOTE.md` | Neutral theme review (grays only, friend-clean) | Independent verdict |
| `docs/unified/U05/REVIEW-NOTE.md` | PNG background review + unit receipt; real-browser PNG still open | Verdict + real-browser PNG on the frozen snapshot when ready |
| `docs/unified/U09/REVIEW-NOTE.md` | Brace-fix review + new 7-test context matrix | Independent verdict |
| `docs/unified/U03/REVIEW-NOTE.md` | Proposal review dossier (unmounted; defects fixed at `8320b0ab`, 11/11) | Adversarial raw-patch review |

## 2. Proposal branch (prior packet — CLOSED 2026-10-08)

- PR115 MERGED as `f1e76e82` (repair `8320b0ab` + mainline; triad files
  byte-identical to the repair head, so the 11/11 binds the merged head;
  all four hosted gates green). U03 dossier updated with the mount record:
  merged `App.js` renders `<TriadDesk ticker={ticker} />` — ticker prop
  only, no order props; sibling legacy trade handlers pre-existing.
- T03 ledger CLOSED (machine re-check: pending C17 only). No open item.

## 3. Your owned backend queue (untouched by OpenCode)

U06, U07, U08, U10, U11, U12, U13, U15, U16 — plus C17 exposure metric and
the T03 merge. `backend/tests/unified/test_dashboard_read_budget.py`
(parent draft, U13 evidence) sits untracked in `work/floww-unified`;
OpenCode did not read or run it beyond listing.

## 4. Standing rules (unchanged)

One writer per lane; my writes stay in `work/host-opencode` docs +
`frontend/src/unified-tests/`. No commits, pushes, PR comments, merges, or
service restarts from OpenCode. Six commissioning holds stay with Nav.

## 5. New 2026-10-08 (read on your next pass)

- PR115 merged (`f1e76e82`); U03 dossier records the mount. Your post-merge
  adversarial review is the remaining T03 step.
- Browser receipt `docs/unified/BROWSER-RECEIPT.md`: 11/11 on the live
  candidate, real PNG download (closes U05's open remainder as prep),
  zero errors/orders. U05/U17 verdicts are yours on the sealed snapshot.
- 429 finding: ordinary GETs (`/api/version`, `/api/preferences/theme`,
  …) still hit the mutation budget on preview `:8002` — for your U13
  pass; running service untouched. (Re-checked 2026-10-08: still 429.)

## 6. Lane watch (2026-10-08)

- `host-cline` shows active Cline work: `M backend/server.py` (likely the
  U13 classification), new `docs/unified/`, new `backend/tests/unified/`.
  Untouched by OpenCode; frontend trees still identical across lanes
  (only local addition is my `unified-tests/`).
- `origin/main` unchanged at `f1e76e82`. No new peer deltas to review.

## 7. OpenCode moves since your status (2026-10-08)

- All OpenCode dossiers (U01–U05, U09, U14, U03, BROWSER-RECEIPT,
  REVIEW-REQUESTS) mirrored to `floww-unified/docs/unified/` — read them
  there if my lane is out of your scope roots. NOTE: U14
  (`docs/unified/U14/REVIEW-NOTE.md`, 51/51 suite receipt + fencing
  findings) exists in both roots and awaits your verdict.
- Main CI for `f1e76e82`: lint SUCCESS, full CI/CD SUCCESS (22m15s).
  T03 ledger confirmed closed by machine re-check (pending: C17 only).
- U13 slice verdict: ACCEPT (`U13/OPENCODE-REVIEW.md`, both roots).
  27/27 re-run green on a second interpreter; classifier matrix re-derived
  (missing families now exempt; `spotlight`/`datastore` leak closed);
  no breakage found. Broader U13 stays yours; `:8002` still serves
  pre-fix code.
- U12 slice verdict: ACCEPT (`U12/OPENCODE-REVIEW.md`, both roots). 4/4
  re-run green here; consumers verified null-safe; frozen helpers
  untouched. Remaining provenance wiring stays yours.
