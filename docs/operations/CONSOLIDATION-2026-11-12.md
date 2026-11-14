# FLOWW consolidation — November 12, 2026

## November 14 source and operations checkpoint

Canonical GitHub `main` and local `main` are aligned at
`52a1b9ea97d3747ae0c4fbaad143574d8ecc2fd2`. PRs #148–#156 were merged through pull
requests, including the health busy-state correction, ticker-scoped data, bounded
microstructure cold reads, fetch admission, fail-closed QuickTrade validation, passive
anomaly GET compatibility, and bounded cvserver state with deterministic collector tests.
PR #155 added a separately reviewed bounded Heatseeker chain cache with post-fetch TTL and
same-key generation protection. Its backend, frontend, and Ruff checks passed on the PR head;
Docker passed on the merge commit. PR #156 is a docs-only checkpoint update; its backend,
frontend, Ruff, and Docker workflows all passed.

The November 14 GitHub settings probe returned 404 for classic `main` branch protection and
no configured repository rulesets. These changes used the pull request flow with no admin
override; GitHub is not currently enforcing the status checks as branch rules.

Production remains on the accepted `a6197f57d2629ad16f10c35d0791c6579c701204` release;
`213dcee64` remains the rollback release. The QuickTrade source change rejects market or
zero-price fallbacks, selects ask for buys and bid for sells, and refuses unsupported
single-symbol straddle/iron-condor requests. It has source and regression-test coverage;
no order was attempted and the source merge did not update the running app.

The exact writer behind recurring DuckDB busy intervals is not confirmed. Source review
identified `heatmap_history.record_snapshot` as a candidate because it holds the shared
connection lock through serialization and many inserts, but no live sample tied that
function to the observed lock. Hermes remains running with late and failed jobs; no manual
catch-up runs were used as evidence of on-time coverage. The local OpenBot tree remains
separate because its private launcher depends on a `server/` tree absent from upstream.

The machine sweep found about 22 GiB free and no high-confidence safe deletion target.
Credential-shaped Trash contents, active caches, live stores, backups, and unmerged work
remain preserved. Runtime receipts and raw recovery evidence remain local. Any later
release requires a fresh manifest, the unchanged capacity gate, and full native acceptance.

> Follow-up updated November 13: at the start of this follow-up, Git `main` was `f35db23c2` after docs-only PR 147; product source and the accepted served runtime remain independently pinned to `a6197f57d`.

## Source and publication

The product code checkpoint is `5d5389908c89d9cd90cad50036dc7d3c3c3dddf0`. It contains the integrated chart-scope callback, layout import, backend replay mirror, ETF expiry-clock lineage, and narrow-layout fixes. The outgoing 149-commit range was reviewed for accidental credentials, private account identifiers, host-only files, and transient artifacts before publication. Four pre-existing host-only dirty paths are excluded from this commit and publication.

A later merge of pull request 146 fixed two failing tests only: one used a hardcoded local interpreter path instead of the running one, and one needed the stale-refresh failure task held open before its result was read. Canonical source is now `a6197f57d2629ad16f10c35d0791c6579c701204`, with frontend tree `081f1d358a6d4cc8107270fd2845a70a66240f5c` and backend tree `00020c379d6a0bb72f2d7b6f8dc1a0a5cb24c997`. The backend tree hash moved only because those tests live under `backend/`; no product code changed.

The full frontend source check passed 302 suites and 2,970 tests. The production frontend build succeeded. Retained independent reviews and focused backend results cover the replay and expiry-clock corrections. The unused Python replay mirror has no identified production consumer; its parity repair is source evidence rather than proof of a live path.

## Running application

The managed frontend on port 3000 and backend on port 8213 now serve release `a6197f57d`. The release finished with a native acceptance receipt after all seven required UI checks passed against the live candidate. The first attempt in the same window failed two checks because a cold-restarted backend held the first chart load on a provider slot for longer than the settle wait; no receipt was written for that attempt, and the same checks passed on the immediate rerun with the backend warm. Release `213dcee64` stays on disk as the rollback target.

The live release also corrects a serving defect. The previous frontend hardcoded `http://localhost:8000` as its API base; the current build derives the base from the page origin and sends loopback traffic to `http://127.0.0.1:8213`.

The release required free disk capacity before it would start, because the helper keeps a closed full copy plus a verified restore. That space came from retiring one old backup that already had a verified archive and from clearing regenerable installer caches. The capacity rule was not weakened, and the accepted backup is still retained for rollback.

## Agent and scheduling work

The November 12 OpenBot upstream merge and retained gateway changes passed the focused 32-test suite on audited Bun 1.4.3 at that checkpoint; that result does not cover current upstream. A fresh Nov 13 fetch found local main 5 commits ahead and 183 behind upstream `e7f4c9dc`. Upstream has removed the old `server/` tree; the local full-pilot launcher depends on it, so this is a structural compatibility break. Keep the private gateway branch and installed kit preserved, and do not merge or publish the private commits until the proxy-only path is rehomed and tested against current upstream. The native gateway recovery remains held; its old owner's retained lock and exhausted budget must not be reset as routine cleanup.

The three paper-trader schedule definitions have successful execution evidence in the earlier continuation records. The Nov 13 Hermes inventory also found late catch-up fires and failed jobs; those do not prove on-time market-session coverage. Provider/model configuration, backlog, and each job's paper/dry-run constraints must be re-attested before changing scheduling. No live trading activation or venue-order authority is granted by this consolidation.

## Remaining scope

The latest 39-row ledger classifies 14 rows as actionable, 20 as partially actionable, and 5 as externally blocked. Those classifications are routing information, not completion. The original 450 historical requirements still require individual acceptance evidence. Remaining work includes gateway ownership recovery, OpenBot entitlement, research source authority and prospective outcomes, account/venue commissioning, cloud lifecycle, and an actual backup destination. Runtime acceptance for `a6197f57d` is closed; it does not close the remaining scope, and any later release must repeat the same guarded process.

Runtime receipts, complete raw-backup recovery archives, restore manifests, scheduler execution details, and historical failed attempts remain in the local continuation evidence. They are not copied into this public repository because publication needs only source and a truthful status checkpoint.

## November 13 operations follow-up

The live `/api/health` endpoint has periodically returned `degraded` when its nonblocking DuckDB lock probe could not acquire the shared connection lock. The source treated that observation as `unhealthy`, and a second busy alert-count probe also forced the aggregate verdict. The correction changes lock misses to `busy` and leaves `degraded` for confirmed unhealthy checks; regression coverage passed locally before this follow-up was prepared. The running `a6197f57d` service was not changed. A recurring alert scan is a plausible source of lock activity, but the exact lock owner has not been identified, so it is not recorded as root cause. One short macOS process sample did not expose the Python owner thread.

The read-only Mac/Hermes sweep found late or failed cron runs, delayed paper-trader catch-up runs, valuable unmerged worktrees, credential-shaped Trash contents, and an old listener on port 8000. Those findings and the current preservation list live in the private continuation record; public documentation does not include job payloads, credentials, or local receipts. Do not treat catch-up runs as on-time market coverage or remove unmerged/dirty work during cleanup.
