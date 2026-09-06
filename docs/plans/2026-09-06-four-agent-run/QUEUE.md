# Task contracts and reserve queues

Each task has a local ID; these are not invented GitHub issue numbers. Coordinator admits exact files before edits. Estimates include investigation and proof, are uncertain, and are not minimum activity quotas. Pick one eligible task, not an entire lane as one PR. Each build uses the COMMON red→green→relevant-suite→review cycle. Audit-only tasks may pass immediately and need no commit.

## Agent 1 — Platform integrity (approximately 300–420 minutes available)

### P1 — Replace false-green silent-except detection (45–75m, confirmed gap)
- Outcome O-1: an unjustified silent `except Exception: pass` fixture fails the gate; a supported explicit justification passes.
- O-2: multiline `except`, aliases, nesting, comments/strings containing apparent code, and syntax errors have deterministic, tested results. Malformed input fails validation; it is not silently ignored.
- O-3: reconcile existing offenders explicitly; the gate's advertised NEW-only/full-tree scope matches what it enforces. Prefer a baseline ratchet for pre-existing findings if applying the current NEW-only contract. Freeze baseline to main; branch cannot silently grow the allowlist.
- Files: `.github/workflows/lint.yml`; existing `qc/audit/*` implementation; new `qc/audit/check_silent_except.py` and dedicated new gate tests if absent. Compare fork `dc045bf4` by diff; do not copy its server/config changes.
- Proof: run parser/gate in a temporary fixture directory with known positive and negative cases; capture exit codes. Never plant a failure in running production code. Run Ruff and actual workflow-equivalent command.
- Exclusions: no whole-tree product exception rewrite; no test skips or blanket comment exemptions. If the gate requires a changed suppression policy, finish the decision contract before implementation.

### P2 — Dependency compatibility and real security evidence (60–100m, confirmed delta)
- O-1: evaluate FastAPI 0.110.1→0.136.3 using resolved dependencies; record whether Starlette 1.3.1 and PyMongo 4.6.3 from the fork are actually required/compatible. Do not treat a copied pin as evidence of compatibility.
- O-2: compare machine-readable dependency advisories on the same interpreter for baseline and proposed environment; record IDs/packages/severity and exact heads. Never repeat “7 advisories” without current proof.
- O-3: full backend suite passes before commit/PR handoff; exercise middleware, CORS, HTTP errors/422, lifespan, mounted routes and TestClient behavior. Production startup/import compatibility is independently checked.
- Files: `backend/requirements.txt`; `backend/pyproject.toml` only if dependency metadata needs a separately recorded lease. Test existing routes plus dedicated regression files only when a behavioral regression is exposed.
- Proof: independent venvs for baseline and proposed requirements; resolver output, focused tests, full `tests/ -q`, `ruff check .`, baseline/head security results. Missing audit connectivity is UNKNOWN, not clean.
- Dependencies: P4 runtime fact-finding can inform this; no concurrent environment mutations by another lane. Keep minimum patch independent of speculative latest-version upgrading.

### P3 — Honest QC runner and ownership guard (45–70m, confirmed runner gap + guard hypothesis)
- O-1: `qc/verify.sh` distinguishes command-not-installed from installed-command-failed; required command failure propagates nonzero status; advisory checks are explicitly named.
- O-2: correct `--ignore-missing-importers` if still present; prove fake command exit 1 cannot print an equivalent all-green summary.
- O-3: verify `scripts/loop_guard.sh` first-match ownership against the catch-all preceding Discord entries. Write fixture tests; propose/fix only with coordinator ownership amendment. A caller-set owner/signoff string alone is not evidence of another lane's consent.
- Files: `qc/verify.sh`, `qc/audit/security_regression.sh`, new shell-runner tests. `scripts/loop_guard.sh`/ownership table are conditional separate leases; otherwise deliver a finding, not a guard bypass.
- Proof: stubs in a temporary PATH return missing/success/failure; capture truthful final status and exit codes. Do not execute a surprise suite of mutating or live scripts from qc without first reading them.

### P4 — Runtime and frontend CI integrity (45–75m, confirmed mismatch)
- O-1: map Python in Docker/deploy, CI, pyproject and local runtime; select a supported runtime based on resolver/import tests and deployment contract. A product runtime change requiring a new decision remains a separate proposed patch.
- O-2: measure actual frontend test/lint baseline; replace nonblocking tests policy only after resolving relevant failures within scope, so failing required tests block CI.
- Files: `.github/workflows/ci.yml`, `.github/workflows/lint.yml`, deployment Dockerfiles discovered by `rg --files`; do not edit frozen frontend manifests/CRACO/App.js.
- Proof: actual interpreter version, dependency install/import, workflow equivalent; demonstrate gate failure in a local fixture/workflow check. Run frontend full suite/build and record separate results; never hide baseline failures with `|| true`.
- Exclusions: legacy Azure deploy repair; unrelated npm upgrade; frozen-file work requires Nav's existing explicit scope or new approval.

### P5 — Fork receipt and novel-test audit (25–45m, verify)
- O-1: compare fork candidate diff and blob identity with main, including dependency and QC multi-file commits; classify every candidate as identical/landed/different/excluded.
- O-2: named `test_alert_dispatcher.py`, `test_audit_trail.py`, `test_websocket_streamer.py` are identical at sweep time; only import a demonstrated novel supported failure case.
- Files: read-only fork tree/history, lane evidence; any new tests get explicit paths. Do not revive retired Schwab provider support.
- Proof: full blob/commit identities plus content diff for squash/ported changes. Commit ancestry proves exact commit landing; different SHAs alone do not prove different code.

### P6 — Redacted secret exposure assessment (30–50m, confirmed credential-looking text)
- O-1: inventory tracked current/history candidate locations without values; distinguish unverified strings from confirmed active credentials.
- O-2: prepare a focused current-doc redaction patch under an exclusive docs lease, plus a rotation-status handoff naming provider/location only. Account rotation and git history rewriting are not authorized.
- Files: root `MASTER_PLAN.md`, `.planning/DATA_SOURCES.md`, `.planning/ROADMAP.md`, relevant handoff docs and further detector-confirmed paths. Central docs lease must be released by Proof before edits.
- Proof: redacted scanner category/path/line report before/after, no values in logs/fixtures/commits. Avoid blanket deletion of useful documentation.

### P7 — Oracle readiness without provisioning (30–60m, offline reserve)
- O-1: validate `deploy/free/README.md`, setup script, compose/Caddy and smoke command against the selected runtime and environment variable names.
- O-2: produce a concrete provision→bootstrap→DNS/TLS→health/PWA→monitoring checklist with exact existing commands; identify secret injection points without values.
- Proof: shell syntax/static checks, compose validation with harmless placeholders if supported, no network bootstrap execution. VM/DNS/cert/public URL checks remain NOT RUN until provisioned.

## Agent 2 — Public data path and contracts (approximately 320–480 minutes available)

### D1 — One owner for upstream budget debits (60–90m, source-supported bypass hypothesis)
- O-1: enumerate broker HTTP call sites and all callers: direct routes, adapter, scanner, fetch coordinator, cache router and retry/auth flows. Tag existing admission tokens separately from HTTP-call tokens.
- O-2: reproduce a direct route budget bypass using mocked transport; pin real upstream call counts, retries, cancellation and release on exception. Verify no double debit when scanner reserves fan-out.
- O-3: fix only reproduced violations against institutional C8 rate/inflight/cooldown contract. Determine process topology before claiming an account-wide limit; process-local bucket is not distributed enforcement.
- Files: `backend/services/{public_api,public_budget,public_api_adapter,public_scanner,fetch_coordinator,cache_router}.py`, `backend/routes/{public_api,public_brokerage}.py`; dedicated relevant tests.
- Proof: fake clock and transport counters for cache hit/miss, partial fan-out, 429, timeout, cancellation and concurrent callers. Existing `test_public_budget.py`, `test_public_advantage.py`, integration/client tests.
- Exclusions: new daily-dollar spend policy, purchasing credits, live broker writes, centralized distributed quota architecture without an approved contract.

### D2 — Fair scanner cursor under low affordability (35–55m, hypothesis)
- O-1: freeze a universe larger than affordable slice; successive scans eventually visit every eligible ticker without systematic starvation.
- O-2: cursor accounts for actually scanned work after trimming; skipped prior slices retain correct age/coverage metadata under the existing contract.
- Files: `public_scanner.py`, `test_public_advantage.py` or dedicated new scanner test. Read real route signature in `routes/flowseeker.py`.
- Proof: deterministic multi-cycle low-token fixture and an unconstrained control. `/scan-public?ticker=SPY` is not a valid selector; never use it as proof.

### D3 — Successful-empty vs failed/stale slices (35–55m, hypothesis)
- O-1: successful fresh zero-unusual-row result does not preserve obsolete unusual rows as current. A failed refresh may retain stale data only with the established explicit age/reason.
- O-2: merged result coverage/truncated semantics match actual slices, not requested slices; untouched rows preserve identity/order contract.
- Files: `public_scanner.py`, adapter only if reproduction needs boundary normalization, dedicated partial-data tests.
- Proof: old nonempty→fresh empty; old nonempty→timeout; missing quote; partial expiry success; JSON finite-value serialization. Check both envelope and actual row provenance.

### D4 — Quotes, expiration and session truth (45–70m, hypothesis/verify)
- O-1: quote symbol identity, missing/zero/nonfinite prices and provider timestamp policy are respected. Never globally coerce unknown prices into zero.
- O-2: expired expirations filtered only according to supported contract; valid 0DTE preserved; requested vs returned coverage distinguished.
- O-3: timezone/DST, weekend, holiday/early-close behavior audited against repository calendar policy. If no canonical policy exists, record a decision instead of inventing one.
- Files: `public_api_adapter.py`, `public_api.py`, existing `test_public_api_adapter_regressions.py`, `test_public_api_partial_data.py`, `tests/test_public_spot_validation.py`.
- Proof: fixed clock/provider fixtures; `math.isfinite` or typed boundary validation covers NaN and ±Infinity. Distinguish zero volume (valid) from zero price (potentially unavailable).

### D5 — Concurrent cooldown/cache and measured bars (40–65m, hypotheses)
- O-1: concurrent success cannot accidentally erase a still-active 429 contract; cancellation releases in-flight admission.
- O-2: same-key cache misses coalesce; fresh/stale/error outcomes and ages remain distinguishable; metrics count actual upstream work.
- O-3: bars validation and measured 21-day ADV already exist—verify incomplete/nonfinite/out-of-order bars and no invented dealer ADV values.
- Files: budget/cache/coordinator; `market_bars.py` read-only unless separately leased. Existing public/cache/market-bars tests.
- Proof: fake clock, delayed transport, overlapping tasks, bounded call counts; no live quota exhaustion.

### D6 — Existing exposure wiring reaches consumers (35–60m, verify)
- O-1: snapshot fixture→VEX wall/charm pin event→dedup→persist→actual REST/SSE consumer preserves type/ticker/timestamp and delivers once under retry.
- O-2: inspect wall disappearance/zero-grid handling and consumer filters; change only a confirmed contract violation.
- Files: `exposure_alerts.py`, `tests/services/test_exposure_alerts.py`; read `server.py`, `routes/data_providers.py`, feed routes. These shared files require a temporary exclusive whole-file lease before any change.
- Proof: in-process integration with fake storage/stream sink, not Discord or a live alert dispatch. `ca423ba` already landed; no port task.

### D7 — Exact issue #18 additive contract (45–75m, confirmed gap)
- O-1: base rows gain `last`, `open_interest` mirroring `oi`, `midpoint`, `osi` null if unknown, retaining every prior key and value.
- O-2: both routes use shared mapping; last prefers positive midpoint, then bid/ask midpoint, then available one-sided side, then 0, as issue #18 specifies. This route-specific fallback is not permission for scanner zero-price fabrication.
- O-3: preserve base/strike envelopes, cache fetches, gamma recomputation and GEX S¹/S² conventions; no frontend changes.
- Files: `backend/routes/analytics.py`, `backend/tests/test_contract_strike_route.py` plus dedicated parity regression if needed.
- Proof: same-leg fixtures compare shared fields/values, preexisting fields unchanged, calls/puts, unknown OSI, one-sided/empty cases. Full route suite and relevant GEX tests if helper impact warrants.
- GitHub contract: https://github.com/mrbeast1179-sketch/floww/issues/18 . No arbitrary `shape_version`, no mandatory equality of every unrelated field, no expansion to `/public/chain` without a new contract.

## Agent 3 — User experience and journal (approximately 260–390 minutes available)

### X1 — Exact issue #17 persistence (60–90m, confirmed gap)
- O-1: Save Trade Idea writes `floww_trades_v2` in existing TradeJournal shape; survives component unmount/remount and page reload; appears in existing journal/analytics consumers.
- O-2: iron_condor, long_straddle, call_spread, put_spread, single_leg map without loss/fabricated legs. Strikes/credit/debit/premium in notes/setup; contracts→quantity; regime→gex_regime.
- O-3: existing in-session list still shows 10 newest first. Preserve journal key/schema, template definitions and checklist fetching.
- Files: `frontend/src/components/TradeEntry.jsx`, `tradeMath.js`, `tradeMath.test.js`, new `TradeEntry.test.jsx` if absent. TradeJournal.jsx, TradeAnalytics.jsx, QuickTradePanel.jsx are read-only references for this issue.
- Proof: fixture mapper tests for all five templates, existing journal loader compatibility, UI save/unmount/remount/reload workflow. Storage unavailable/corrupt/exhausted behavior follows existing policy; if that policy would lose existing records or misreport success, surface an explicit follow-up decision.
- GitHub contract: https://github.com/mrbeast1179-sketch/floww/issues/17 . No server persistence or live/paper broker execution.

### X2 — Phase 9 compose and consumer acceptance (45–75m, verify)
- O-1: reconcile W1–W8/CR-001/CR-002 with mounted `FlowseekerProBlademap`; each intended existing surface has a path to render or an explicit retired/gated receipt.
- O-2: exercise filters, drawer, tracker, modal, quote/dealer and empty/stale/error states with recorded sanitized payloads. Use real components, not a JSON/node assertion masquerading as a rendered UI test.
- O-3: inspect 360/768/1440px layouts for clipping, horizontal tape scrolling and keyboard access. No v2 redesign without B0.
- Files: `FlowseekerProBlademap.jsx/.css/.test.jsx`, targeted chart/tracker/filter components only after enumerating exact paths. App.js and scanLogic.js remain read-only unless lease/freeze resolved.
- Proof: focused Jest, full CRACO suite, build; browser visual evidence when available. Automated pass does not replace Nav visual sign-off.

### X3 — Fix independently reproduced Phase9 findings (45–90m reserve)
- Input: E1 finding ID with current source + fixture + expected behavior. Coordinator admits one finding and exact files.
- O-1: resolve the observable defect without changing statistical meaning or portraying aggregate proxies as actual prints/sweeps.
- O-2: preserve unknown-side/NO_QUOTE/uncalibrated states; avoid fabricated certainty or numeric crash probabilities.
- Proof: regression test plus render evidence; for citation corrections trace claim to its actual source. If scientific interpretation is unresolved, deliver revised claim options for decision instead of inventing authority.

### X4 — Consumer stability, polling and remount audit (45–70m reserve)
- O-1: test repeated ticker changes, abort on unmount, stale response arrival order, empty response, malformed row and partial data in existing flowseeker components.
- O-2: ensure combined pollers do not cause duplicate fetches contrary to current cache policy; verify cost captions reflect available evidence rather than invented billing.
- Files: exact existing hook/component paths identified in X2; new lane-owned tests. Backend changes route to Data.
- Proof: fake timers/network, real hook renders and cleanup assertions; profile only a demonstrated slow path with reproducible before/after workload.

### X5 — Redesign readiness and journal resilience specification (30–65m reserve)
- O-1: create B0 receipt checklist: directory, brief, “no structure” verdict and 40+ findings traceability, responsive states, approved preview mount plan.
- O-2: list unresolved journal error/recovery policy choices discovered in X1 with concrete reproductions and proposed observable outcomes.
- Proof: reviewable document in lane evidence; no speculative replacement UI or broadened storage schema. If B0 arrives mid-run, coordinator admits review only before implementation.

## Agent 4 — Independent proof and backlog closure (approximately 310–450 minutes available)

### E1 — Revalidate every Phase9 finding F1–F19 (60–90m)
- O-1: one receipt per ID in `.planning/eval/phase-9/fix-queue.md`: exact source/head, original claim, reproduction or source check, resolved/open/gated and evidence path.
- O-2: prioritize incorrect prices, fabricated scientific claims, unknown-side handling, crash probabilities and double-weighting; route concrete UI fixes to X3 and backend fixes to Data.
- Write scope: new `backend/tests/run_20260906_proof/` or new frontend proof test directory only when test-runner discovery supports it; otherwise lease exact new test paths. Never modify builder-owned existing tests to validate their own claim.
- Proof: passing audit can close a finding with no patch; valid failing test stays a documented draft/reproduction until repaired. Do not merge a deliberately red test PR or suppress it to get green.

### E2 — Public integration/replay/chaos matrix (60–90m)
- O-1: trace direct chain, merged chain, scanner, heatmap/contract, exposure feed consumers at exact build heads. Test malformed/empty/partial/stale/429/timeout/cancellation/concurrent outcomes with mocked provider transport.
- O-2: freeze clock, rows, quote provenance, regimes, baselines, previous OI and calibration; repeated replay deterministic. Single-flight/call-count assertions are independent of builder implementation choices.
- O-3: inspect `/metrics` and health wiring without exposing account data; distinguish TestClient proof from live deployed proof.
- Scope: new independent tests/evidence only. Live smoke reserved to coordinator's limited read-only budget and identified isolated service.

### E3 — Institutional and Discord truth audit (50–80m)
- O-1: map A/B/C/D contracts to existing code/tests and classify completion claims, including signing/proxy labels, horizon persistence/calibration, advisor inputs/Kelly, fees/fill/idempotency/kill switch.
- O-2: audit G1/G2/G3 branch/main receipts separately; submission seed is not fill, HTTP 200 is not Discord witness, offline approval fixture is not a human approval.
- O-3: produce gate table for GATE-0/1/2/3/FINAL, Sync-2 and U6 with missing artifact and owner. Never send commands/messages or order requests.
- Proof: existing test inventory plus selected read-only fixture tests after startup isolation; targeted new reproductions. Mathematical or live-trading strategy changes stay decision-gated.

### E4 — Exact-head independent review and runtime proof (60–90m, starts when task receipt arrives)
- O-1: review full diff against task O/X contract before quality/performance. Pin baseline/head; independently run implicated checks with recorded environment.
- O-2: verify actual served code provenance (process command/cwd, immutable revision where available) before calling a live result evidence for a branch. Missing `/api/version` is NOT VERIFIED, not a fabricated SHA.
- O-3: integrated backend/full frontend/build checks at the combined head after relevant changes; candidate-only results remain labeled candidate-only.
- No API load tests, writes or bot restarts. Logs supplement endpoint/process proof; they neither automatically lie nor substitute for payload verification.
- Result: APPROVED/REWORK/BLOCKED with evidence and material limits. Nav owns merge; all required checks must pass on final PR head.

### E5 — Reconcile all remaining source claims (45–75m reserve)
- O-1: work through INVENTORY and source register; map every actionable item encountered to landed-with-receipt, current task, blocked owner, superseded, or future candidate. Preserve unmatched items explicitly.
- O-2: reconcile STATE/ROADMAP/BACKLOG/CR/proposal contradictions once with source/test evidence. Do not churn hashes/counts or rewrite historical logs to make them agree.
- Files: dedicated new reconciliation report first; edits to central docs require exclusive lease, especially after P6 redaction.
- Proof: stable requirement IDs and file references. Existing code is not sufficient proof of scheduler mounting/consumer reachability; state that distinction.

## Dependencies and admission order

- P1/P2/P3 have Track A integration priority. P4 fact-finding informs P2. P5 can close immediately if no novel delta.
- D7 and X1 are independent issue contracts. D1–D6 share one Data owner and run sequentially; shared server/routes get an exclusive lease only after incumbent release.
- E1/E2/E3 start independently; E4 preempts reserve audits when a reviewable receipt arrives. X3 waits for a concrete E1 finding.
- P6 and E5 must not edit the same docs concurrently. P3 guard amendments need incumbent ownership consent.
- Any task depending on an unmerged predecessor uses an explicit candidate integration branch for testing only, or waits for merge while taking independent work. It cannot claim main acceptance from a stacked branch.
- At admission expand each task's exact file list, existing callable interfaces, test fixture design and O/X outcomes into a short task card. Where semantics remain open, status is DISCOVERY—not BUILD. No auto-created product requirements, 90% coverage quota, fixed iteration quota, or forced “optimization.”
