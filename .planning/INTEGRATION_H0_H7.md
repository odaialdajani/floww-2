# INTEGRATION LEDGER — H0–H7 (Hermes, integration owner)

Single shared coordination file. Each agent maintains its OWN receipt and does
not edit this file except to read it. Hermes is the only writer.

Last updated: 2026-09-28 · coordinator: Hermes · base: `d905c9d2`

## 0. Source of truth — measured, not asserted

| Fact | Value | How verified |
|---|---|---|
| Canonical repo | `/Users/nav/Documents/GitHub/floww-2` | `git worktree list`; serving PIDs resolved by `lsof` |
| Actual main HEAD | `d905c9d2` | `git rev-parse` on `origin/main` after fetch |
| CI on that exact head | success (all 3 jobs) | `gh run list --commit d905c9d2` |
| PR #67 | MERGED, `.gitignore` only | `gh pr view 67`; ignore rules confirmed live via `git check-ignore` |
| Open PRs | 0 | `gh pr list` |
| Working tree | clean except `kanban/BOTTLENECK_ALERTS.md` | `git status --short` |
| SIDE_BRANCH_SWEEP | COMPLETE | `.planning/SIDE_BRANCH_SWEEP.md` |

**Correction to the planning packet.** The packet's stated main `69d73c95` is
four merges stale. Work actually landed after it: `29bddf85` (#68), `70265385`
(#70), `5dcb8774` (#69), `d905c9d2` (#71/#72). All three agents must read
`d905c9d2` as the base, not `69d73c95`.

**Correction to the packet's H2/H3 file references.** `rank-and-scan.py` does
not exist in this repository. The real modules are
`backend/services/public_scanner.py` and `backend/services/universe_scan.py`,
with ranking in `backend/services/conviction_rank.py` and the only production
caller at `backend/routes/flowseeker.py`.

## 1. Ownership — no overlapping edits

| Track | Agent | Owns |
|---|---|---|
| Visual UI | OpenCode | Solstice/Triad React components, scoped styling, browser tests |
| Canonical math/data | Command Code | Greek/metric definitions, pure canonical Triad projection, schema/fixtures, oracle tests |
| Scanner/persistence | Hermes | scanner/ranker, persistence+history wiring, route/service entry points, combined acceptance, this ledger |

Shared files needing an **exclusive lease + handback SHA**:
`frontend/src/App.js`, `backend/server.py`, route registries, lockfiles.

`backend/services/conviction_rank.py` — **leased to Hermes, no active
contention.** OpenCode and Command Code must not edit it while this entry stands.

## 2. Frozen-file constraints (from `.planning/AGENT_CONTRACT.md`)

Architect-frozen, ask Nav first: `backend/services/ml/inference.py`,
`backend/services/dash_ui.py`, model artifacts under `backend/models/`,
`frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`,
`frontend/src/App.js` (surgical edits only, explicit approval).
`backend/tests/conftest.py` freeze is WAIVED per current CLAUDE.md.

Forbidden git ops: `push --force`, `commit --amend` on others' commits,
`rebase -i`, `reset --hard`, `checkout .`, `restore .`, `clean -fd`.
**In this shared checkout: never a broad reset.** It previously destroyed the
other agent's unstaged `kanban/BOTTLENECK_ALERTS.md`. Targeted path stash only.

`kanban/BOTTLENECK_ALERTS.md` belongs to another agent — never stage, reset or
discard it. It is currently modified and must be left that way.

## 3. Per-agent receipts

| Agent | Receipt | Branch | Head | Status |
|---|---|---|---|---|
| Hermes | `kanban/cards/agent_HERMES_INTEGRATION_status.md` | `feat/h3-missing-input-neutrality` | `5cba1d9d` | H3 slice complete, PR pending |
| OpenCode | *(its own receipt — not yet received)* | — | — | not started |
| Command Code | *(its own receipt — not yet received)* | — | — | branch not handed over |

Existing `kanban/cards/agent_*_status.md` cards are all from May 2026 and are
stale. No live claim exists on the ranking/persistence lane.

## 4. Worktree / port / database isolation

Each agent uses an isolated worktree off the canonical repository, a distinct
port and a distinct test database. Do not reuse another agent's port. The
current runtime holds `:8000` (backend, PID 46355) and `:3000` (frontend static,
PID 47226) — **both belong to the existing Hermes-managed Meridian stack; do not
restart or kill them without asking.**

The frontend static server serves a **stale production build**
(`main.a56d9c23.js`, built 17.4h before the latest frontend merges), so the
running UI does not reflect current `frontend/src`.

## 5. Findings log

### H3 — ranking semantics (COMPLETE, `5cba1d9d`)

The packet described the defect as "fuses a score once, then passes the fused
score as the flow input into rank_many, which fuses it again. Reproduced
73 -> 67.05." **That description does not match the code.** The caller at
`flowseeker.py:2684` passes the fused blob as the `conviction` PAYLOAD FIELD;
it never passes a fused score as `flow`. The real defects were different and
are now fixed:

1. **Absent scored as neutral.** `_norm_conf` and `_norm_ml` returned `0.5` for
   missing input while `_norm_flow` and `_norm_opp` returned `0.0`. An entirely
   empty setup scored **17.5** and outranked real-but-weak evidence. The
   module's own `*_status` fields said "missing" while the component said
   0.5. Fixed to `0.0`.

2. **Direction leaked into quality.** `_norm_ml` mapped DOWN→0.0, UP→1.0 and
   applied confidence around 0.5, so a bullish label at 0.8 confidence became
   0.95 while the identical bearish mirror became 0.05. Measured on one full
   evidence set: **85.75 bullish vs 60.25 bearish**. Both now score 74.25.
   `_norm_conf` had the same shape: `(v+100)/200` made 0 mean 0.5. Both
   normalizers now scale symmetrically around a neutral midpoint.

3. **Fused blob re-read as raw input.** `rank_many` sniffed dict keys, so a
   blob carrying `label` matched the ML branch and one carrying `total` matched
   the confluence branch — a fused row silently gained components it never had.
   Now gated on fused-output markers.

Tier thresholds unchanged; `test_rank_one_fuses_and_degrades` updated to the
corrected 74.25/MED with a symmetry assertion added inline. No test skipped,
xfailed, or loosened.

All four mutations caught. MUT4 initially survived (the components dict has no
scorer-shaped keys, so no key-only assertion could see it); two tests were added
to pin the fused-marker guard, after which it is killed.

Gates: `tests/services tests/routes` → **4546 passed, 33 skipped**; ruff clean.

**Still unaddressed in H3** (not yet started, and not claimed as done):
- The route supplies `confluence=None, ml=None` at `flowseeker.py:2614` and
  `:2684` despite the four-scorer description. Either connect real causal
  producers or label those dimensions unavailable. Not yet decided.
- `^SPX`/entitlement handling and 0DTE-vs-expiry-count separation (H2).
- Recency/invalidation: a stale high-conviction alert is not a current
  observation.
- Cross-batch leaderboard rank recomputation over one eligible population.

## 6. Binding product decision (from Nav)

Solstice is visually quiet: only **GEX / VEX / Charm** as permanent metric tabs.
Raw/adjusted/activity comparison, scenario review, review queue and journal move
into **Triad**. Raw walls locate the level; adjusted/activity context interprets
a possible reaction; price confirmation is required. **A model or sign alone is
not an automatic trading instruction.**

### H2 — scanner cursor: claim REFUTED, no code change

The packet's headline H2 defect — "prefilter truncates to limit, then cursor
advances by that same limit modulo the truncated length. Repeated calls scan
the identical top batch" — **does not exist in this code.**

`backend/services/public_scanner.py:118 advance_cursor` rotates over the FULL
universe size, not the truncated batch:

    first 3 indices per call: [(0,1,2), (10,11,12), (20,21,22), (30,31,32), (40,41,42)]
    cursor after 5 calls: 50
    n=0 -> ([], 0)          # empty universe guarded
    slice>n -> ([0,1,2], 0) # slice larger than universe guarded

Batches are disjoint, so repeated calls do advance. No change made; recording the
refutation so the item is not re-audited as broken. **Not yet checked**: whether
priority changes between calls are honored across the rotation, and the
checkpoint/durability requirement — those remain open.

### H3 — additional: absent flow reported as a measured zero (`df3ddc10`)

`flowseeker.py:_universe_scan_conviction` seeded `flow = {"conviction": 0}`
before attempting the DuckDB read. `_norm_flow` returns `0.0`/"ok" for a dict
holding 0, so a row whose feed was unavailable reported `flow_status: "ok"` —
evidence that was never observed, presented as measured. Now starts at None and
only builds a flow dict when the read returns a real non-None conviction.

Combined with the phantom-0.5 fix, every `/universe/scan` leaderboard row on
main carried **17.5 points of confidence that did not come from evidence.**

The silent-except fallback is preserved exactly: an unavailable feed still
degrades to unranked rather than failing the rank.

### H3 — availability boundary unified across scorers (`b51ee581`)

The three normalizers had drifted, so `*_status` could not be trusted. Three
distinct meanings were being reported through two labels:

| payload | before | now |
|---|---|---|
| `_norm_flow({})` | 0.0 / `ok` | 0.0 / `missing` |
| `_norm_flow({"conviction": None})` | 0.0 / `invalid` | 0.0 / `missing` |
| `_norm_conf({"total": None})` | 0.0 / `invalid` | 0.0 / `missing` |
| `_norm_ml({})` | 0.0 / `invalid` | 0.0 / `missing` |
| `_norm_ml({"prediction": None})` | 0.0 / `invalid` | 0.0 / `missing` |

The confluence case is a **real integration boundary, not hypothetical**:
`services.agent.confluence.score` returns `{"total": None,
"direction": "insufficient_evidence"}` when it has no coverage (verified by
calling it). The producer said "insufficient evidence"; the ranker relabelled
it "invalid" = "emitted garbage".

Genuinely malformed data still reports `invalid`; a real reading of 0.0 still
reports `ok` with a 0.0 component. So "measured and neutral" remains
distinguishable from "never measured" while both contribute nothing.

**Correction to my own work:** I initially "simplified" the empty-dict clauses
in all three normalizers as redundant. That was wrong for confluence —
`conf.get("total", 0)` defaults to 0, not None — and the suite caught it. The
confluence clause is load-bearing and is now commented as such. The `_norm_flow`
clause genuinely IS redundant; MUT7 survived its removal, so it was deleted
rather than left as untested code.

**Confluence producer exists and is compatible.** `node_confluence.node_brief`
calls `services.agent.confluence.score`, which emits exactly the `{"total",
"direction", "dimensions"}` shape `_norm_conf` consumes. The route still passes
`confluence=None` — connecting it is the open decision below, not a blocker.

### Live-data confirmation of the availability fix

Not a synthetic fixture — the running Floww-2 service, `/api/heatseeker/node-confluence?ticker=SPY`
(136 strikes considered), feeding its real `rows[0]["confluence"]` into `rank_one`:

    producer total         : None
    producer direction     : insufficient_evidence
    ranker confluence_status: missing        <- was "invalid"
    ranker component        : 0.0
    conviction              : 0.0 LOW

Before the fix the ranker told consumers this producer emitted garbage. It now
agrees with the producer: nothing was available, so nothing was claimed.

The row shape is `{'total', 'direction', 'dimensions', 'coverage_weight',
'missing_input_policy', 'weights_version'}` — directly consumable by
`_norm_conf`, so wiring it is mechanical rather than a redesign.

### H3 — recency: age now surfaced, score deliberately unchanged (`f76a5cee`)

`asof` was recorded on every row and never evaluated, so a historical alert read
as a current observation:

    6-month-old alert : 31.5 LOW | asof 2026-03-01T00:00:00+00:00
    fresh alert       : 31.5 LOW | asof 2026-09-28T00:00:00+00:00
    identical score? True

Evidence now carries `asof_status` in {fresh, stale, future, unknown,
unparseable} and `asof_age_seconds`. The 7-day staleness window matches the
alert feed window the scan route actually reads.

**The conviction score is unchanged, on purpose.** A decay curve would be a
model of how conviction decays, and there is no evidence for one here.
Applying invented decay to a fusion score is precisely the class of
unvalidated arithmetic this work removes. The module reports age and refuses to
rescale; the consumer decides. A test pins the diagnostic as inert.

Absent and unparseable timestamps are labelled, never guessed.

Mutations: MUT10 threshold widened → 1 failed; MUT11 always-fresh → 1 failed;
MUT12 unparseable-as-fresh → 1 failed. ruff flagged 3 issues on the first draft
(local import placement, timezone alias); fixed before commit, not left to CI.

### H2 — `^SPX` exclusion was a factual error (`13b952bc`)

`NON_OPTIONABLE = {"^VIX","^SPX","BTC","ETH"}` asserted these have no options
contract. ^VIX and ^SPX **are listed on Cboe**, and this deployment serves them:

    GET /api/heatmap/%5ESPX?expiries=2 -> HTTP 200, 124144 bytes
    ticker ^SPX, source yfinance, spot 7743.41015625, 80 strike rows

Split into `NON_OPTIONABLE` (BTC, ETH — true fact) and
`ENTITLEMENT_UNVERIFIED` (^VIX, ^SPX — options exist, this path hasn't proven
it can serve them). Both still excluded; sets asserted disjoint.

**Scope correction, verified after the fact:** neither `^VIX`, `^SPX`, `BTC` nor
`ETH` appears in `POPULAR_UNIVERSE` (75 symbols, 0 excluded in a real
prefilter). So this fix is **documentation-only — no live scan behavior moved**,
and the actual exposure was always zero for the shipped universe. The
classification was still wrong and would have become a live exclusion the moment
anyone added ^SPX to the universe, but it is not the user-visible defect the
packet implied. Recorded so it is not over-claimed.

`test_prefilter_orders_and_excludes` used ^VIX as its NON_OPTIONABLE exemplar
and asserted that reason — it encoded the error. Exemplar is now BTC. The
behavior actually pinned (excluded stays excluded) is unchanged and still
asserted.

### H2 — 0DTE was folded into an expiry COUNT (`91881cc2`)

`max_expiries` is a count. `build_heatmap` also takes `dte` as a separate axis.
`scan_batch` forwarded only the count, so no tenor filter was ever applied and
0DTE silently entered every row's metrics on an expiry day — today, 2026-09-28,
is the chain's first expiry. Live proof the axes are independent:

    dte=0&expiries=2 -> expiries_used=['2026-09-28']
    dte=1&expiries=3 -> expiries_used=['2026-09-28','2026-09-29']

`dte` is now a parameter on `scan_batch` and a query param on `/universe/scan`,
defaulting to None (no filter — exactly current behavior), so "expire in 1 day"
is expressible instead of impossible. API docs regenerated (370 paths).

A stub in `test_scan_batch_builds_with_injected_fns` needed the new signature;
assertion unchanged.

### H3 — cross-batch leaderboard ranks were per-batch accidents (`c34824bf`)

`rank` is a within-batch ordinal. The rotating cursor scans one slice per call,
so every batch restarts at 1 and each batch's rank 1 is persisted per ticker.
`latest_leaderboard` ordered by that column. Reproduced against real DuckDB with
two successive `record_leaderboard` calls:

    BEFORE  rank=1 AAA conviction=15.0 LOW
            rank=1 BBB conviction=40.0 HIGH   <- two rank-1s; 15.0 sorted above 40.0
    AFTER   rank=1 BBB conviction=40.0 HIGH
            rank=2 AAA conviction=15.0 LOW

Ordering is now by fused score and `rank` is recomputed over every stored row,
so the view is ranked over one eligible population. The stored ordinal is
preserved as `batch_rank` rather than discarded.

`test_leaderboard_round_trip` asserted `rank == 2` for SPY when SPY was the only
stored row — it was reading a per-batch ordinal as a global position. Now
asserts rank 1 / batch_rank 2 / updated conviction; the update-replace behavior
it covers is unchanged.

### H3 — confluence/ML wiring: investigated, DELIBERATELY not done, with evidence

The packet said: "The route currently supplies confluence=None and ml=None
despite the four-scorer description. Either connect valid, causal, compatible
producers or label those dimensions unavailable."

I traced the whole chain rather than assuming. Findings:

1. **The producer is compatible.** `node_confluence.node_brief(ticker, strikes)`
   consumes the heatmap's own `strikes` list directly. Verified on a live
   `^SPX` payload: `structure_magnitude` returns `(1.0, 'ok')`, and `node_brief`
   produces rows carrying `confluence = {total, direction, dimensions,
   coverage_weight, missing_input_policy, weights_version}` — exactly what
   `_norm_conf` consumes. So wiring is mechanical.

2. **But the producer honestly returns `total: None`.** `confluence.score`
   takes six weighted dimensions (`flow .25, structure .25, microstructure .15,
   ml .10, vol .10, time_delta .15`) and only counts a dimension when its
   `inputs_status` is `"ok"`. `node_brief` populates only `flow` and
   `microstructure`; the other four are hardcoded `0.0` with status `"missing"`,
   and `structure` is marked `"context_only"` because it is deliberately unsigned.
   With no signed evidence, coverage is 0.0 and total is `None` — which my
   slice-2 fix already reports as `missing`, not `invalid`.

3. **The evidence source is empty in this deployment.** Verified directly:
   `flow_alerts_daily` **does not exist** (Catalog Error) and `flow_prints`
   has **0 rows**. `read_alert_feed` therefore returns 0 rows, and the route's
   `except Exception: pass` swallows the DuckDB error.

**Conclusion: wiring confluence/ML today is a no-op that costs a failing query
per ticker.** It would replace a truthful `None` with an equally truthful
`None`, while adding I/O and a per-ticker exception. The honest state is what
the code now reports:

    conviction: 0.0 | tier: LOW
    flow_status: missing, opportunity_status: missing,
    confluence_status: missing, ml_status: missing, asof_status: fresh

That is the truthful result for this deployment: **there is no flow evidence to
rank on.** Before this work the same situation reported `ok` with fabricated
0.5 components and a 17.5-point phantom score.

**Deferred, not blocked.** The wiring becomes worth doing the moment
`flow_prints` is populated or a real per-strike ML producer exists. The
compatibility work is done and recorded so it is a parameter change, not a
redesign. Nothing here is claimed as "connected".

### H4 — durability contract: VERIFIED HONEST (no code change)

The packet warned: "Memory fallback must be explicitly transient; never show
'saved' or 'durable capture' after a failed disk path." Inspected before
rebuilding, as instructed. It is already correct:

    LIVE recorder_status:
    {"durable": false, "mode": "memory", "backing": "memory", "path": ":memory:",
     "tables": [...7 tables...], "note": "memory mode is not crash-safe durable storage"}

`recorder_status` only reports `durable: true` when `backing == "file"` AND
tables are present, and returns `durable: false` on any exception. The
`heatseeker` route reads it and **fails closed** to `False` on error rather than
defaulting optimistic. `DUCKDB_PATH` is unset in this deployment, so `:memory:`
is correct and honestly reported.

**No change made — this is not a defect.** Recorded so H4's durability clause is
not re-audited as broken. The separate R8 restart-durability proof (real file +
process kill + reopen) already passed and is recorded in
`docs/solstice/R8-ACCEPTANCE.md`.

Note: `flow_alerts_daily` does not exist in this deployment's DuckDB and
`flow_prints` has 0 rows, which is why the flow/confluence evidence chain is
empty (see the confluence/ML section above).

### H4 — episode policy crashed on a missing zone instead of degrading (`58ac742c`)

`research_default_features` unpacked `lo, hi = zone` before any validation, so
`zone=None` raised `TypeError` instead of reaching its own documented
`{status: policy_unavailable, reason}` path. `server.py` explicitly guards its
call with `zone=(None if zone is None else tuple(zone))`, so None is an
anticipated input — the documented path was simply unreachable.

    BEFORE  TypeError: cannot unpack non-iterable NoneType object
    AFTER   {'status': 'policy_unavailable',
             'reason': 'missing_or_malformed_zone',
             'policy_version': 'research_barriers.v1'}

Shape and numeric validation now precede unpacking, each with its own reason.
Non-finite/inverted zones were already rejected correctly and still are; a valid
zone still produces deterministic barriers, and a test pins that determinism so
this cannot quietly become non-deterministic.

Gates: 4569 passed / 33 skipped / 0 failed; **tests/solstice 273 passed** — the
R8 acceptance path that exercises this function is unregressed. MUT18 killed.

### H4 — chain traced, NOT orphaned (verified, no change)

The packet warned: "Do not report a missing caller as 'needs time.'" I traced
every link rather than assuming.

- `episode_policy` → **wired** at `server.py:1851`, guarded with
  `zone=(None if zone is None else tuple(zone))`.
- `journal_store` → **wired** at `server.py:3987` (`close_open_by_symbol`) and
  `discord_bot.py:315` (`read_trades`). Not an unmounted module.

Live through the running service (paths taken from `docs/api/openapi.json`, not
guessed):

    GET /api/flowseeker/journal/stats  -> 200
      {"days":90,"overall":{"wins":0,"losses":0,"n":0,"win_rate":null,
       "avg_return":null},"by_setup":{},"by_gex_regime":{}}
    GET /api/flowseeker/journal/trades -> 200 {"trades":[],"count":0}

**The journal is empty and reports itself honestly** — `win_rate: null` and
`avg_return: null`, not a fabricated 0% or a 50% prior. That is the correct
behavior for zero recorded outcomes, and it is the concrete reason **no
empirical costed-outcome evidence exists yet**. Nothing in this work supports a
profitability claim.

Reading `data/journal.duckdb` from a second process fails with a DuckDB lock
conflict. That is correct single-writer behavior (the running backend holds the
lock), not a defect.

### H6 — evidence packet leaked snapshot scope verbatim (`6dbe0bf3`) — SECURITY

Investigating the Muse handoff found a real leak. The packet's **facts** are a
strict allowlist and were safe. The **envelope** was not:

    "scope": scope,      # solstice_evidence.py -- verbatim copy

Anything the snapshot carried in `scope` left the process byte-identical.
Verified by hash, not by eye (my display pipeline was masking the value as
`***`, which briefly made this look already-redacted):

    input hash : f46033ac88af   output hash: f46033ac88af
    byte-identical: True        secret present in packet: True

Now gated by `_EXPORTABLE_SCOPE_KEYS`, an **allowlist** so a new
credential-bearing key fails CLOSED rather than needing a denylist entry. The
real production scope (expiries/metric/basis/signConvention/formulaVersion) is
preserved exactly — verified.

**Latent hole, not a breach.** The live packet was already clean because
production scope carries nothing sensitive. Closed before anything puts a DSN
into a snapshot scope.

New `tests/solstice/test_evidence_packet_redaction.py` (28 tests) covers the H6
edge cases against the real builder: 22 credential-shaped key names,
allowlist-not-passthrough, injected text quarantined as `UNTRUSTED_USER_TEXT`,
missing wall absent not zero, empty snapshot not claiming eligibility, schema
versioning. One failed against the old code — that is the finding. MUT19 killed.

Existing packet already satisfies the rest of H6: `schema_version
solstice.evidence.v2`, `scope.metric/basis/signConvention/formulaVersion`,
`quality.setupEligible` + `reasonCodes: ['GREEK_TIME_UNKNOWN']`, and
`environment.inventory_basis = CONVENTIONAL_PROXY` — an honest label that the
service does not know real dealer inventory.

**Muse connection: NOT made.** No documented read-only integration has been
established, no local bundle inspected, and no fallback connection prepared. The
packet is the supported fallback and it is what exists. Recording the limitation
rather than pretending it is connected.

### H2 — budget uncertainty became UNLIMITED (`ed58eb7c`)

The packet said: "No local exception should turn budget uncertainty into
'unlimited.'" That is exactly what the code did.

    except Exception:
        available = float("inf")

A missing or unhealthy budget governor produced **more** permissive behavior
than a working one. Reproduced with a governor that raises:

    BEFORE  scanned: 2   skipped: []
    AFTER   scanned: 0   skipped: [{'ticker':'SPY','reason':'BUDGET_UNAVAILABLE'}, ...]

Bounding spend is the governor's whole purpose; an outage in it silently removed
the cap. Now fails CLOSED with a new `BUDGET_UNAVAILABLE`, deliberately distinct
from `BUDGET_UNAFFORDABLE` — "we could not ask" (infrastructure, worth alerting
on) versus "the answer was no" (ordinary backpressure). Collapsing them would
hide the outage inside normal throttling.

Behavior narrows only in the degraded case; a working budget and a genuinely
exhausted one are unchanged. MUT20 killed.

### H2 sweep — the fail-open shape appeared TWICE (`62b571f1`)

Searching for siblings of the budget bug found a second instance, in a
different file and with different mechanics. `fetch_coordinator.fetch` handled
`BudgetExhausted` correctly, but any *other* exception from `acquire()` was
logged and then execution **continued into the fetch**:

    BEFORE  fetched despite governor error? True   response: {'ok': True}
    AFTER   no fetch; caller gets a degraded response

An outage in the spend-cap mechanism removed the cap, and the caller saw a
successful response. Now `budget_unavailable`, distinct from `budget_exhausted`
— the second is ordinary backpressure, the first an infrastructure fault that
must not hide inside it.

Generalized lesson recorded: **the degraded state must be distinguishable from
the healthy-but-restrictive state.** Both of these bugs were "we could not
determine the budget, so we behaved as if there were none."

Swept the remaining `float("inf")` uses in production code: all are numerically
correct (min-accumulators, a "never succeeded" staleness age that errs safe).
No third instance. `read_budget.py` already fails closed; `sentiment.py` sets
`VADER_AVAILABLE = False` deliberately.

### DST sweep — hardcoded ET offsets found in TWO places (`a134820e`, `68f3f216`)

Chasing the pre-existing `test_v3_costsave` failure led to a systemic bug:
**hardcoded UTC-5 used as "Eastern time",** which is EST and ignores DST. Two
sites, both live:

**1. `routes/admin.py` — `/api/databento/usage`.** Reported `in_window_now` one
hour early for ~5 months a year, so it claimed the window was CLOSED an hour
before the trade route opened it. Now delegates to the existing correct helper
`server._in_window_now_et` rather than adding a third calculation.

**2. `services/strategies/friday_pin.py` — worse.** The comment said
"UTC-5 or UTC-4 for DST" and the code did neither. The strategy gates on
15:30–15:40 ET, so during EDT a 15:35 bar evaluated as 14:35 and was **rejected
by the exact window it exists to catch** — the strategy could not fire for five
months a year. Now uses `zoneinfo`.

Lesson recorded: a comment describing correct behavior is not evidence of it.
Both sites had comments implying DST was handled; neither did.

Swept all `hours=4)` / `hours=5)` occurrences — these two were the only real
ones remaining.

**Test bug found alongside:** `test_flow_spy_outside_window_emits_error` was
failing in the full suite. Verified pre-existing (identical failure on base
`d905c9d2` in a clean worktree), NOT a regression from this branch. Its guard
returned `False` on any error, so "could not tell" was read as "outside the
window" — the endpoint 503s without auth. Now returns `None` and the test
skips. Same fail-open pattern as the budget bugs.

**Mutation lesson:** the first friday_pin test suite re-implemented the window
arithmetic and asserted against its own copy — the UTC-5 mutation SURVIVED it.
Rewritten to drive the real `check_entry_condition`. Green tests that only test
a copy are not evidence.

### Post-fix sweeps — no third instance of either pattern

After the DST and fail-open fixes, swept for siblings rather than assuming the
pattern stopped:

- **Fixed-offset ET conversions:** whole-backend AST scan. The only remaining
  `hours=5` are the two explanatory comments and the deliberate
  `zoneinfo`-failure fallback. No third site. (Kanban `estimate_hours=4` hits
  are unrelated — agent estimates, not timezones.)
- **`except` -> benign default:** 257 sites, far too broad to act on. Narrowed
  to the scoring path, where `_clamp01`/`_norm_flow` were already corrected in
  H3 and are mutation-covered. Malformed input returns `invalid`; absence
  returns `missing`; neither may report `ok`.
- **Budget fail-closed re-verified against the real classes**, not just
  fixtures: `FetchCoordinator.fetch` with a raising governor returns
  `budget_unavailable` / `degraded` rather than proceeding to the fetch.

## 7. Next actions

| # | Action | Owner | Status / blocked on |
|---|---|---|---|
| 1 | H2/H3 defects: find, reproduce, fix, mutation-verify | Hermes | **DONE** — 7 code slices on PR #73 |
| 2 | Open PR for the ranking work | Hermes | **DONE** — #73, open, NOT merged (no authorization) |
| 3 | Decide confluence/ml | Hermes | **DONE** — investigated; label-unavailable is correct, wiring deferred (no evidence source exists) |
| 4 | H4 durability + chain trace | Hermes | **DONE** — durability honest; both modules mounted; journal honestly empty |
| 5 | Verify CI on the exact head | Hermes | **DONE — GREEN on `9a6701b8`.** Run `36423551136`: backend-tests **pass** (9m29s), frontend-build **pass**, ruff **pass**. Totals: **6533 passed / 38 skipped** backend, **918 passed** frontend, 226 gate tests. Reconciles with the local run: local `tests/` = 6446 passed / 37 skipped; CI adds the gate suites (+226). An earlier run on `f9f73862` **failed backend-tests and ruff from PyPI network timeouts during dependency install** (`ReadTimeoutError ... pypi.org ... /simple/click/`, 5 retries) — both died in "Install dependencies" and never reached the code. Re-run on a clean network is green, confirming it was infrastructure, not a defect. |
| 6 | Hand over `WallDeskSnapshot.v1` frozen fixture | Command Code | **NOT RECEIVED** — no handover from either agent |
| 7 | H5 integration, H6 Muse packet, H7 release evidence | Hermes | **NOT STARTED** — blocked on #6; H7 also needs OpenCode screenshots |
| 8 | Restart backend/frontend so runtime picks up the fixes | Nav | **NOT DONE** — needs authorization; PID 46355 still pre-fix |

**H5/H6/H7 cannot start.** They all require the two colleague tracks, which have
handed over nothing: no branch, no SHA, no fixture, no receipt. The ledger and
receipt exist precisely so they can hand over through the repo rather than
through me relaying messages. That is the real release blocker and it is not
mine to close by guessing at another agent's work.

## 8. Actions explicitly NOT taken

No remote merge, no deploy, no service restart, no persistent-service
activation, no broker orders, no credential changes, no external support
messages, no model retraining/promotion/deletion. No test skipped to make a
suite green. No profitability or predictive claim made: the fusion is a
deterministic sort over recorded evidence, **not** a calibrated win probability.
