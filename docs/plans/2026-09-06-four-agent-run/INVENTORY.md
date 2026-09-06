# Evidence-backed sweep inventory

## Snapshot and proof boundary

Read-only GitHub query confirmed `origin/main=5b9d9a96a29951e548e883d108a806b93c2d11a9`, open issues #8/#17/#18, and zero open PRs. Friend main was inspected through GitHub read-only tools. The canonical working branch was `phase9/g1-reads-witness @ af265fe`; branch-local Discord receipts are not main receipts. No application suite or live provider behavior was tested during this planning sweep. Re-fetch at launch.

Classification: **gap** = directly observed missing/incorrect implementation; **verify** = code/claim exists but behavior needs proof; **candidate** = hypothesis or unspecific product request; **gated** = external approval/artifact required; **historical** = retain as provenance, not authorization.

## Corrections to previous prompts

| Previous claim/instruction | Verified correction | Queue |
|---|---|---|
| gsd/010 exposure-alert wiring missing | `ca423ba` is an ancestor of main; module, server snapshot hook and heatmap hook exist | D6 verify end-to-end |
| Port named round11 tests | Alert dispatcher, audit trail and websocket streamer test blobs match friend's main | P5 only novel delta |
| QC silent-except gate missing | Gate exists but its grep context parser expects the wrong separator and can false-pass | P1 |
| FastAPI bump only | Fork commit also changes PyMongo; choose minimal compatible dependency set after resolver/security comparison | P2 |
| CI green proves frontend tests | `ci.yml` contains nonblocking test/lint behavior | P4 |
| Every scanner call needs rebuilding | `acquire_n`, affordability trimming, 503 and coverage tests exist | D1–D5 reproduce gaps |
| `scan-public?ticker=SPY` tests SPY | Route accepts `slice_size` and `max_expiries`; ticker is not a selector | D2/E2 fixtures + real signature |
| Expiry must be today+2 or later | Existing zero-DTE behavior is intentional | D4 |
| Daily dollar cap is established | Current budget counts HTTP calls, in-flight requests, cooldown; monetary policy is not specified | D1 decision boundary |
| #18 requires identical full key sets/new shape_version | Actual issue is additive aliases/shared mapping; existing envelopes and frontend remain unchanged | D7 |
| Four API-only prompts cover backlog | They omit #17, CI false-green paths, institutional program, 19 evaluator findings, ownership conflicts | X1/E1/E3/P3 |
| A failing audit is wrong and should be deleted | Failures require triage; passing verification is legitimate; preserve valid findings | COMMON protocol |
| All done forbidden, 40 iterations minimum | Completion and blockers must be truthful; prioritize distinct evidence and useful changes | Four-hour budget |
| No leaked key | Credential-looking values remain in tracked planning documents; validity unknown | P6 |

## Master-plan disposition

| ID | Work | Status / observable exit | Owner |
|---|---|---|---|
| A1 | Dependency upgrade | gap: old pin; compatible branch, comparative advisories and full backend evidence required | Platform P2 |
| A2 | Silent-except/QC | gap: detector and runner can false-green; executable negative/positive tests | Platform P1/P3 |
| A3 | Exposure alerts | verify existing snapshot→dedup→storage→feed; no blind port | Data D6, Proof E2 |
| A4 | Round11 | named tests already identical; only new useful cases can be admitted | Platform P5 |
| B0 | v2 redesign inputs | gated: friend's queried tree lacks mockup directory and curious-cerf brief | Coordinator G1 |
| B1 | UI redesign review | gated on B0 + all audit findings; parallel preview + Nav visual sign-off before replacement | Experience reserve |
| B2 | Paid Phase 4 | gated independently on real Public-limit evidence; healthy 2+ week decision window cannot be compressed into four hours | Coordinator G2 |
| C1 | Oracle | VM provision gated; offline deploy/runtime/smoke readiness remains useful | Platform P7 / G3 |
| C2a | #18 row aliases | gap: shared row fields differ; use exact issue contract | Data D7 |
| C2b | #17 journal | gap: `TradeEntry.handleSave` only updates component state | Experience X1 |
| C3 | Phase 9 Gates B/C | contradictory historical statuses; mounted UI + exact-head tests + independent findings review required | X2/E1 |
| C4 | Documentation | duplicated STATE, stale phase/header/checklist/proposal statuses | Proof E5 |
| C5 | stale :8000 | current provenance unmeasured; PID/cwd/SHA and owner release before coordinator restart | E4 / G4 |

## All additional programs accounted for

| Source/program | Disposition for this run | Exit or next decision |
|---|---|---|
| `.planning/eval/phase-9/fix-queue.md` F1–F19 | E1 revalidate all 19 separately | Each finding links current source, evidence and resolved/open/gated verdict; no blanket closure |
| `institutional_loop/AGENT_B_DATA.md` | D1–D5/E2: transport accounting, bars/ADV, measured dealer inputs, freshness, overlap, off-hours, fallback, universe | Reproduce before patch; label aggregate-data limitations |
| `institutional_loop/AGENT_A_SIGNALS.md` | E3: signing parity, VPIN/O-S/Amihud/Kyle proxies, skew/CW, MAD/FDR, change points, Roll, accumulation/concentration | Audit scientific feasibility and existing tests; new algorithms require a separate contract; frozen model/GEX conventions survive |
| `institutional_loop/AGENT_C_MONEY.md` | E3: horizons, calibration, Kelly, advisor inputs, earnings, campaign promotion, rule economics, fill/fee/idempotency/kill switch, tracker | Offline deterministic evidence; no profitability or witnessed-fill claims from unit tests |
| `institutional_loop/AGENT_D_PROOF.md` | E2–E4: replay, fuzz, chaos, health, single-flight, fan-out, perf | Freeze clock/input/baseline/context/calibration; compare exact heads |
| Institutional Phase-2 §12 | future: time-of-day baselines, market tide, MCP guardrails, Atlas-lite/replay | Source-indexed candidates; do not build merely to occupy time |
| `DISCORD_RESTART_PLAN.md` | supersedes old 24h clock; transport/read/paper/hardening/final gates remain separate | N1 same guild, N2 channel, N3 non-admin help, N4 human paper approval/close, N5 later bot split |
| G1 command reliability quick plan | active existing branch; preserve all WIP | Offline-green differs from witnessed-green; do not duplicate G1 commits |
| G2 retries/attempt persistence/digest | E3 offline audit; existing owner release required for any patch | Valid persisted attempts, bounded retry/idempotency and no duplicate outbound send in fakes |
| G3 paper loop | E3 offline audit; existing `floww-g3` owns implementation | Submission seed is not fill reconciliation; reject fabricated fill/P&L witnesses |
| B1 snapshot-cadence proposal | verify receipt and behavior | Scheduler, market-hours, bounded tickers/storage cap/status; no extra fetch loop without budget contract |
| B2 earnings-cache proposal | verify source/module/route receipt; decision-gated if absent | No resurrection of killed Public Earnings Hub; confirm actual Finnhub contract first |
| B3 FINRA ATS/Reg SHO | verify receipt; discovery if absent | Confirm dataset layouts, publication lag and coverage; never portray weekly/short-volume proxies as live directional prints |
| `shipped-signals-persistence.md` | verify Amihud daily storage, Roll rollup, Hawkes sample history | Insufficient sample history remains explicit; no synthetic live readings |
| BACKLOG B quant | E5 source check: registry/catalog/normalization/per-signal reports | `/signals` route exists; registry/normalization completeness needs proof |
| BACKLOG C ML | candidate: OOS-lock, rolling validation, dashboard | Read-only validation/replay allowed; models/retraining stay frozen |
| BACKLOG D/E backtest/alerts | verify reports, costs, persistence, alert quality; per-alert economic gating candidate | No rebuild of landed routes/Mongo persistence; no assumed YAML loader |
| BACKLOG F/G journal/portfolio | X1 plus verify existing portfolio, equity/drawdown and ticker attribution | Signal/strategy attribution is distinct from ticker attribution; live-execution ADR remains future |
| BACKLOG H frontend | X2/X3; TanStack already present | App.js decomposition/config changes remain frozen; test count is not acceptance |
| BACKLOG I observability | E2/P3 verify counters are wired to actual paths | Distinguish rate admission from upstream calls/fallback counts; no fabricated dollars |
| BACKLOG J ADR/process | E5/P3 verify landed ADRs, hook/commit policy and honest gate exits | Avoid unrelated hook rollout unless separately contracted |
| Round9/10 plans/AUTO cards | historical triage receipts exist; eight genuine model/theme candidates remain per ROADMAP | Revalidate only contradicting evidence; no retired Schwab/Alpha restoration or IEEE redesign |
| Root PLAN/IMPLEMENTATION/MASTER + Oracle round dispatch docs | historical architecture/provider/deploy directions | Source register retains them; no priority over current Public-first/protected-main instructions |
| Issue #8 X chatter | credit-blocked despite ready label | No new spend, no production X calls to fill a loop |
| Azure, Phase4 early build, redesign before B0, model v4 retrain | explicitly excluded | Record once; never cycle back to them as fallback work |

## Documentation reconciliation targets

`STATE.md`: duplicate project position/header and obsolete phase remnants. `ROADMAP.md`: Phase4 ACTIVE vs gated; 6.4 COMPLETE vs three unchecked lines; compose complete vs NOT STARTED/Gate B IN PROGRESS. `CONTRACT_REQUESTS.md`: CR-001/002 stale-open candidates. Phase3 tracking and phase7 headers conflict with closure text. `BACKLOG.md`: stale portfolio/alert/ADR/TanStack claims. B1/B2/B3/public-budget proposal headers need main-code receipts before edits. Historical ledger timestamps/counts are claims, not present-session measurements.

Security evidence must record filenames, line numbers and detector categories only. Do not reproduce candidate secrets, test credentials against vendors, rewrite git history or rotate accounts from this task. Review tracked current files and history separately; removing a current value does not revoke it.

## Limits

This is a broad source/history/issue sweep, not a proof that every reachable code path works. `source-register.txt` enumerates discovered planning sources so workers can account for remaining items explicitly. Candidate tasks require a failing reproduction or a clarified contract before implementation. Work done by other agents after this snapshot must be incorporated through fresh evidence, never overwritten.
