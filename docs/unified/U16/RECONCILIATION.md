# U16 — evidence/omission map (OpenCode takeover, 2026-10-08)

Method: every unified task mapped to preserved behavior, material delta,
exact evidence, and holder. The old 53-ledger + later rows are REFERENCES
(statuses never transferred to this wave). No tracked category is silently
omitted — each line below says done, blocked-with-reason, or held.

## Task map

| ID | State | Evidence / holder |
|---|---|---|
| U01 census/retention | Done, Cline ACCEPT | `U01/RETENTION-MAP.md` + hashes |
| U02 null-date | Done, Cline ACCEPT | review + 238-run + producer note |
| U03 old-desk review | Done, Cline ACCEPT (review complete) | dossier; proposal merged via PR115 fast-lane (`f1e76e82`), mount recorded |
| U04 neutral theme | Done, Cline ACCEPT (structure) | review; visual sign-off → U17 |
| U05 PNG background | Done, Cline ACCEPT (code+unit) | review + real-browser PNG receipt |
| U06 related | Cline verified-no-repair (WIP, no verdict yet); my probes complement | Cline verdict pending |
| U07 scanner | Same as U06 | Cline verdict pending |
| U08 history | Same as U06 | Cline verdict pending |
| U09 context/matrix | Done, Cline ACCEPT | review + 7-test matrix + STOCK-quirk handoff |
| U10 legacy export | Cline slice; my REPAIR_REQUIRED (2 minor doc/fidelity items) | Cline fix pending |
| U11 storage | Done, my ACCEPT | review; 5/5 re-run |
| U12 trinity | Done, my ACCEPT (slice) | review; 4/4 re-run + ruff |
| U13 budget/range | Done both sides (slice ACCEPT + sweep verified) | reviews; redeploy still needs human sign-off (`:8002` serves pre-slice code) |
| U14 controller | My dossier done; Cline verdict pending | `U14/REVIEW-NOTE.md`, 51/51 suite |
| U15 boundary | My dossier done (takeover) | 5-test contract, HOLD list inside |
| U16 | This record | — |
| U17 visual | BLOCKED: U06–U08 lack Cline verdicts | prep banked (routes, browser 11/11, interaction 6/6, Related/saved/history 130) |
| U18 gates | BLOCKED: on U10–U17 | prep banked (full frontend 2022 green; merged-head 2018 + flakes-resolved) |
| C17 exposure metric | OPEN, optional P2 | no admitted per-strike exposure series exists server-side (see below) |

## Omissions swept (finite)

Related/saved/history features, legacy recovery, friend immutability (77/77),
route identity (8), final-gate prep, commissioning separation — all mapped
above. No category uncovered. Historical REPAIR_REQUIRED items were
reproduced on current snapshots where in scope (U02/U04/U05/U09 parents,
T03 trio); unrelated peer heads unlocked nothing.

## C17 concrete gap (for whoever builds it)

An admitted per-strike exposure series (measured-vs-unknown basis flags)
does not exist in any backend envelope or endpoint at `8194eca4`; the
chain serves one canonical gex + basis per row (U12 established ADV-class
metrics refuse rather than invent). Closure path: version a measured series
into the envelope (producer-side, Cline-shaped work) OR explicitly defer
with reason. Frontend must not invent it. Unchanged by this record.

## Holds (all named, none absorbed)

H-PUBLICATION (no commits/pushes/merges/deploys without human word),
H-ORIGINAL-STOP (8000/8001 + user jobs intact), H-CAPTURE, H-EXECUTION,
H-CLINE-BINDING (Cline halted mid-U15; its lane preserved, unmerged),
H-TRIAD-PROMOTION (now a merged fact for this branch — recorded, not
waived), plus the 7 historical NAV holds.
