# FLOWW current work

## Current product and runtime — November 13, 2026

At the start of this Nov 13 follow-up, Git `main` was `f35db23c21f9d6e007cc3a0fdda68dc64147e0e6`, merged through PR 147. The product source checkpoint is `a6197f57d2629ad16f10c35d0791c6579c701204`, merged through PR 146; PR 147 changed documentation only. The product frontend tree is `081f1d358a6d4cc8107270fd2845a70a66240f5c` and backend tree is `00020c379d6a0bb72f2d7b6f8dc1a0a5cb24c997`. The PR 146 merge changed tests only; the product code checkpoint remains `5d5389908c89d9cd90cad50036dc7d3c3c3dddf0`. The backend tree hash moved because the corrected tests live under `backend/`.

The managed frontend on port 3000 and backend on port 8213 now serve release `a6197f57d`. The release finished with a native acceptance receipt at 2026-11-12T18:56:45Z after all seven required UI checks passed against the live candidate. The first acceptance attempt in the same window failed two checks because a cold-restarted backend held the first chart load on a provider slot for longer than the settle wait; no receipt was written for that attempt, and the same checks passed on the immediate rerun with the backend warm. Release `213dcee64` stays on disk as the rollback target. Never infer the served release from the Git branch.

The live release also fixes a serving defect: the old frontend hardcoded `http://localhost:8000` as its API base, while the current build derives the base from the page origin and points loopback traffic at `http://127.0.0.1:8213`.

The release required free disk capacity before it would start, because the helper keeps a closed full copy plus a verified restore. That space was created by retiring one already-archived old backup and by clearing regenerable installer caches. The capacity rule itself was not weakened, and the accepted backup is still retained for rollback.

Integrated source includes the R02 current-read scope binding and complete layout-symbol import (`777b68871`), backend replay bucket/pending parity (`e424c19bc`), W-2 analytical ETF expiry clock and lineage (`5c6aa5914`, `6783107ff`), and narrow-desktop pane stacking (`5d5389908`). Source evidence includes the complete frontend run of 302 suites / 2,970 tests and the affected backend tests and independent reviews retained in the continuation evidence. Those checks do not close runtime, account, or trading commissioning.

See [consolidation status](../docs/operations/CONSOLIDATION-2026-11-12.md) for completed work and remaining gates. Preserve the four host-only dirty paths, existing service owners, active stores/WALs, rollback recovery, and all historical evidence. Current Hermes cron activity is independent of FLOWW source ownership; do not resume old queued native admissions or infer source-writing authority from a running agent count.

## November 13 operations follow-up

The release remains `a6197f57d` on `:3000` and `:8213`; repository `main` moving forward does not reload it. Current free disk space is about 24 GiB, versus a fresh release requirement of about 11.7 GiB for the current 3.49 GB data directory plus the 2 GiB reserve. Recompute both values immediately before any future release.

The `/api/health` false-degradation issue is isolated to nonblocking DuckDB lock misses: they were labeled `unhealthy`, and the institutional alert probe separately forced the aggregate to `degraded`. The source correction reports these observations as `busy` and reserves `degraded` for confirmed unhealthy checks; focused regression tests cover both probe locations. This source change is not loaded into the running `a6197f57d` release. The exact live lock-owning thread/query remains unproven; the recurring alert scan is only a candidate workload. Production was not restarted or changed. One short macOS process sample did not expose the Python owner thread.

The Nov 13 Mac and Hermes sweep is retained in the private continuation records. It found stale/delayed scheduler runs, several valuable dirty worktrees, credential-shaped Trash contents, and an old listener on `0.0.0.0:8000`; none were removed or stopped during the read-only audit. Treat paper-trader catch-up runs as late runs, not on-time market coverage. Older scheduler descriptions below are dated scope, not current Hermes Desktop inventory.

## Retained November 8 and earlier checkpoints

The sections below are dated history. This current checkpoint supersedes their source/runtime status where it differs.


Updated November 8, 2026. Canonical source remains `/Users/nav/Documents/GitHub/floww-2`, local `main`. This terminal is the sole integration and deployment owner. Muse remains personal; older controller prompts and retired worktrees must not be resumed.

The accepted product source includes chart visibility Settings Sync, readable narrow/high-zoom pane stacking, Stock header and utility placement, and retired service-worker registration. Product code is pinned at `1f96685759b109db9f17f28a2e809bf766d57e0f`; later documentation-only commits can be attested by the exact frontend/backend trees. Frontend tree: `96d91cc619bf478c4ceea64b30308691bb4dc002`. Backend tree: `3deaeb5d653f6024235544754e966ad8e2a26d51`. The latter includes response-completion receipt clocks and release of owned Public request slots without refunding spent tokens.

Fresh checks: all 296 frontend suites / 2,934 tests passed; the 212-case affected backend selection passed separately on Python 3.12 and the installed Python 3.14.6. Both retained the original three-second snapshot deadline under network denial. Compiled synthetic Stock preview passed the bounded normal/200% header, utility, focus, layout and persistence checks. That is separate from managed release acceptance.

The managed frontend3000/backend8213 were last re-attested at `4a6cb4944` before the prepared full-main transaction. Do not infer the running SHA from `main` or this document. Read `/Users/nav/floww-free-setup-20261108/release/COMBINED-SOURCE.json`, the eventual managed deployment receipt and actual served assets/version. Root must verify the closed full-directory backup, six-store disposable restore, all fifteen original journal rows, protected controls, all served files and native app behavior before accepting a new runtime. Original8000, Mission Control8085, OpenCode and Hermes remain protected.

Free setup and durable continuation: `/Users/nav/floww-free-setup-20261108/REPORT.md`, `STATE.json`, and `NEXT.md`. The existing CopilotKit/OpenBot clone was updated to `62a96334`; its bounded NIM gateway, dedicated local database and dependencies are prepared. Genuine Intelligence project binding remains pending; no fake key, paid fallback or completed whole-app startup is claimed. Hermes Desktop completed one exact zero-tool connection check through the three-request capped gateway. Its existing shared research circuit remains parked with all consumed admissions and failed trials preserved.

An owner-private cloud companion has an actual cloud-task save/read proof and one accepted follow-up timer receipt. Its finite hourly timer is not a permanent cloud Hermes machine or exact-minute scheduler. Sites resource retirement/migration is required before2027 paid hosting; no new paid infrastructure is authorized. The connected Linux machine passed an isolated21-case code job, but its provider/ownership/free-tier classification is unverified. No credential was transferred there.

Trading remains held. Source authority for current Greek/OI clocks is missing, normalized retained snapshots are not raw vendor responses, and the authenticated Liquid request has no verified atomic simulated destination. A separate raw research collector is being prepared offline in an isolated worker; it has no startup/schedule or execution authority. Preserve the observed-input pilot loss of$4.30, incomplete replay and all unknowns. No venue order was placed or profitability proven.

The original450-row queue remains `/Users/nav/floww-ui-correction-20261107/history/CURRENT-450-ROW-QUEUE.json`; row-by-row acceptance is not closed by test totals. Preserve the four canonical host-only dirty paths, protected calculations/models, Screener/TidehunterPro work, stores, rollback releases and recovery evidence. Time Machine still requires an actual writable destination. No Codex hook trust or privacy bypass was performed.

## Historical November 7 checkpoints

The records below describe their dated source/runtime states and are retained as history. The November8 checkpoint and live receipts above supersede them.

Updated November 7, 2026. The current owner request is autonomous FLOWW research/paper/coding operations with minimal manual session continuation, plus Mac usability. See [autonomy specification](../docs/operations/AUTONOMY-SPEC.md) and [implementation plan](../docs/superpowers/plans/2026-11-07-floww-autonomy.md). The user explicitly requests parallel workers under one accountable integrator. Older no-worker rosters and retired controller prompts are historical and must not be resumed.

Canonical source is `/Users/nav/Documents/GitHub/floww-2`, local `main`. The old `.worktrees/integration-candidate-20261025` is retained historical material, not the current source. Stock chart is `heatseeker`; Market view is `trinity`. The managed frontend on `3000` and backend on `8213` were observed at release `3948b9c715c687ad89839ed884040c7dc7e8cced` before this operations-only change. Re-attest actual runtime/version/served assets; a newer documentation commit alone does not reload the app.

Current product delivery: `/Users/nav/floww-ui-correction-20261107/DELIVERY.md`. Current acceptance queue: `/Users/nav/floww-ui-correction-20261107/history/CURRENT-450-ROW-QUEUE.json`. All 450 rows remain present; acceptance and profitability are not inferred from green tests. Older ledger and the historical consolidated plan remain evidence.

Native operations uses a new scoped graph/profiles. Initial research/audit cards are blocked until tool/model/evidence admission is verified. The model-free observer cannot trade, call models, edit source or restart services. Hermes board completion is not independent acceptance. Muse personal work stays separate.

Liquid Paper execution is requested, but cannot start until authentication, fresh simulated-destination/mode evidence, instrument policy, trusted risk at stage/fill, durable reconciliation and stop controls are verified. No live orders, paid fallback or stale-controller resumption. Existing capture/price producer/notification/account flags are not silently changed by this request.

Preserve protected calculation/model/inference/Screener/TidehunterPro work, existing host-only dirty files, active stores, recovery copies and original service `8000`. One integration writer; isolated worker checkouts with exact path ownership. Do not stop or replace older recovery services from a dated prompt.

Current continuation receipt: `/Users/nav/floww-continuation-20261107/REPORT.md`. Previous execution receipt: `/Users/nav/floww-execution-20261107/REPORT.md`. Prior foundation/Mac receipts: `/Users/nav/macbook-improvements-20261107/`. Source-level checks, installed configuration, running-service proof, account commissioning and prospective trading results are separate statuses.


November 7 execution: coding fixture, saved-research source, Liquid read-only gate
and internal synthetic paper admission passed independent review. Native research
remains parked; no real source adapter, generic product dispatcher or venue
executor is commissioned. The added model-free consolidated receipt runs locally
and reports those blockers. It cannot activate any task. The paired premium app
remains 3948b9c71; this source change is not a new managed application release.

## November 7 continuation — accepted source, explicit runtime gaps

The continuation adds a bounded stored Public adapter with independently
authenticated persisted authority interfaces, exact structure/order lineage and
fresh fill-source selection. Independent source review and a complete synthetic
entry/reduction roundtrip pass; production issuer/keys, source truth, wiring and
actual book admission remain unprovisioned. Liquid submission remains closed.

Research has a smaller deterministic input, a shared four-pair daily prepayment
ledger and failure circuit, and isolated offline diagnostics. The newly admitted
real pair made one request per role; both hit ReadTimeout and their follow-ups
were blocked. The shared circuit is parked and the trial state is paused. No
research schedule is installed. Previous failures remain retained.

The registered coding task now uses a fixed admission-ID ledger, a pinned
772-case structural checker, minimal source context and safe SSE diagnostics.
The first live trial made two requests and hit its byte cap without a patch.
The separately reviewed changed-input trial made three attempts: read, edit,
then an unfinished response at the deadline. Its exported edit independently
passes and matches the root's already committed receipt fix. This accepts an
artifact, not native completion, a persistent dispatcher or publication authority.
No more model trial is authorized by those consumed admissions.

Three legacy jobs have source/effect/delivery contracts and local synthetic
previews; their actual schedules, retired model pins and delivery remain
unchanged. Muse stays personal. The model-free receipt now names specific
prerequisites while retaining unresolved-ledger, evidence and availability
precedence; all action capabilities remain false.

Combined verification: 203 operations tests, 323 affected paper/lease/source
tests and 50 subtests pass. These are source checks, not whole-product, account,
profitability or future-session evidence. Protected source, the four canonical
dirty files, active stores and the 450-row historical queue remain preserved.
The paired premium release remains 3948b9c71; no product restart is implied.
