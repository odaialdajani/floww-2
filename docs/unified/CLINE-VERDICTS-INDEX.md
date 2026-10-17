# Cline independent verdicts — unified wave (2026-10-07, evening)

Reviewer: Cline. Writer lane: `work/host-cline`. All verdicts review-only;
no commits, pushes, PR comments, merges, restarts, or peer-lane writes.
Every claim re-derived from exact committed/uncommitted source with own
commands; every test receipt re-executed. Evidence logs in `./evidence/`
with printed sha256.

| Dossier | Verdict | Remainder |
|---|---|---|
| U01 census/retention | ACCEPT | none (scope limits disclosed in verdict) |
| U02 range null-date patch | ACCEPT | 2 load-flake timeouts under parallel run disclosed; green `--runInBand` |
| U14 controller dossier | — | no snapshot published yet; OpenCode's move |

## 2026-10-08 progress (Cline-owned tasks)

- **PR115 MERGED** to main (`f1e76e82f86def6e869116911aafbb18d6c69ae6`) after
  Cline ACCEPT + Nav authorization; lint gate green on main, CI/CD main run
  in progress at close of this pass. Prior-packet T03 merge step complete.
- **U13 read-budget slice**: fresh counterexample (draft RED vs baseline —
  new dashboard GET families missing; raw `startswith` had no path
  boundaries), repaired in `work/host-cline` (`_READ_ONLY_GET_FAMILIES` +
  segment-boundary matcher), 27/27 extended pins green, 8/8 neighboring
  server tests green, ruff clean. See `U13/CLINE-WIP.md`. Broader U13 stays
  READY; OpenCode review pending.
- **U06 Related admission — verified, no repair needed** (`U06/CLINE-WIP.md`,
  `tests/unified/test_related_admission.py`, 11/11 green): exact adjacent pairs
  with no filling, 20-pair minimum, zero-variance refusal, clock validation,
  stale-vs-partial distinct, registry/directory honesty, local-only warming
  (503/403 before any provider work), zero-attempt cancellation, 8-call
  reservation cap.
- **U07 dated scanner observations — verified, no repair needed**
  (`U07/CLINE-WIP.md`, 9/9 green): original receipt/source clocks preserved,
  monotonic retention, duplicate/malformed/oversize refused, partial extras
  marked not upgraded, future receipts excluded from pages, bounded paging,
  `live=false`/`trade_eligible=false`/`complete_realtime_market=false` held.
- **U08 history integrity — verified, no repair needed** (`U08/CLINE-WIP.md`,
  7/7 green on in-memory DuckDB): stable keyset pages under inserts,
  ticker-bound signed cursors, unknown clocks/excluded identities counted,
  node age from observation time (late arrival never freshens), ambiguous
  clocks and malformed rows dropped.
- **U10 export/import** (`U10/CLINE-WIP.md`, 5/5 green): digest-gated import,
  atomic conflict refusal with rollback, round-trip on isolated synthetic
  copies incl. new `scripts/export_legacy_decisions.py` (uncapped per-ticker
  export + receipt header). Real-store completeness stays HELD on NAV-CAPTURE.
- **U11 store integrity** (`U11/CLINE-WIP.md`, 5/5 green): corrupt SQLite file
  previously crashed with uncaught `DatabaseError` → repaired to typed
  `cache_storage_unavailable`; durable reopen, digest-tamper refusal and
  cold-cache disclosure verified. Full unified suite: **68/68 green**.

- Combined unified suite: **58/58 green, ruff clean** (`evidence/u-final.log`,
  sha256 below with u06/u07/u08 logs). U17's Cline prerequisites
  (U06/U07/U08) now have verdict-request dossiers awaiting OpenCode review.

- **U12 Trinity provenance**: failed-first counterexamples (constant 75M ADV
  for every ticker; selected-ticker GI substituted as the SPX input; silent
  except-swallow), repaired in `work/host-cline/backend/routes/trinity.py` to
  typed unavailable/partial statuses with reasons (qualified ADV requires a
  per-session volume store none currently admits; constant substitute
  refused; self-substitution refused; constituent failure now typed partial,
  logged). 4/4 pins green, 73/73 final validation green (incl. v3-costsave,
  heatseeker, server, unified suites), ruff clean. See `U12/CLINE-WIP.md`.
  Adjacent observation (out of my write scope, recorded not edited): the
  same 75M constant exists in `routes/microstructure.py:176` and
  `routes/steal_three.py:222`; per-ticker lookup tables in
  `routes/heatseeker.py`, `routes/gex_analysis.py`,
  `services/morning_briefing.py`.
- **Prior-packet ledger**: T03 → ACCEPTED_AT_SHA `f1e76e82` with Cline
  review + 3 hashed packet-relative receipts; `check-closure.py` clean.
  Remaining: C17 (Cline P2 optional exposure metric) + 7 Nav external holds.

| U03 Triad proposal dossier | ACCEPT (review complete) | PR115 merge held — no merge authorization + promotion hold; Nav decision |
| U04 neutral theme | ACCEPT (structure) | visual sign-off = U17 |
| U05 chart PNG background | ACCEPT (code+unit) | real-browser PNG on frozen snapshot = U17 |
| U09 context matrix + brace fix | ACCEPT | none |

U14 (controller recovery/fencing): no dossier or registered snapshot exists
yet (registry empty, controller NOT_INITIALIZED) — nothing to review;
OpenCode's move.

## Notes for OpenCode / coordinator

- Had a registry been initialized, these verdicts would bind snapshot seals;
  none exist, so verdicts bind baseline `8194eca4` + EVIDENCE.json hashes,
  exactly as `REVIEW-REQUESTS.md` specified.
- U17 is unblocked w.r.t. my verdicts (U01,U02,U04,U05,U09 accepted; U06–U08
  remain Cline-owned and pending).
- Cline-owned queue starts now: U13 (budget/range sweep incl. the parent
  `test_dashboard_read_budget.py` draft), U12 (Trinity ADV), U06–U08, U10,
  U11, U15, U16.

## Prior-packet ledger note

T03's engineering prerequisites (adversarial review + 4/4 hosted gates at
`8320b0ab`) are met and recorded in `U03/CLINE-VERDICT.md`. C17 (admitted
exposure metric, optional P2) remains Cline-owned and open; interceptor is
not started this pass.
