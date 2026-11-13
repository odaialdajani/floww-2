# FLOWW consolidation — November 12, 2026

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

The November 12 OpenBot upstream merge and retained gateway changes passed the focused 32-test suite on audited Bun 1.4.3 at that checkpoint. A fresh Nov 13 read-only comparison shows the local OpenBot clone has moved 5 commits ahead and 39 behind its cached upstream reference; fetch/review and tests are required before any further alignment. Full OpenBot application entitlement and the native gateway recovery remain separate held workstreams. The gateway's old owner is absent; its retained lock and exhausted budget must not be reset as routine cleanup.

The three paper-trader schedule definitions have successful execution evidence in the earlier continuation records. The Nov 13 Hermes inventory also found late catch-up fires and failed jobs; those do not prove on-time market-session coverage. Provider/model configuration, backlog, and each job's paper/dry-run constraints must be re-attested before changing scheduling. No live trading activation or venue-order authority is granted by this consolidation.

## Remaining scope

The latest 39-row ledger classifies 14 rows as actionable, 20 as partially actionable, and 5 as externally blocked. Those classifications are routing information, not completion. The original 450 historical requirements still require individual acceptance evidence. Remaining work includes gateway ownership recovery, OpenBot entitlement, research source authority and prospective outcomes, account/venue commissioning, cloud lifecycle, and an actual backup destination. Runtime acceptance for `a6197f57d` is closed; it does not close the remaining scope, and any later release must repeat the same guarded process.

Runtime receipts, complete raw-backup recovery archives, restore manifests, scheduler execution details, and historical failed attempts remain in the local continuation evidence. They are not copied into this public repository because publication needs only source and a truthful status checkpoint.

## November 13 operations follow-up

The live `/api/health` endpoint has periodically returned `degraded` when its nonblocking DuckDB lock probe could not acquire the shared connection lock. The source treated that observation as `unhealthy`, and a second busy alert-count probe also forced the aggregate verdict. The correction changes lock misses to `busy` and leaves `degraded` for confirmed unhealthy checks; regression coverage passed locally before this follow-up was prepared. The running `a6197f57d` service was not changed. A recurring alert scan is a plausible source of lock activity, but the exact lock owner has not been identified, so it is not recorded as root cause. One short macOS process sample did not expose the Python owner thread.

The read-only Mac/Hermes sweep found late or failed cron runs, delayed paper-trader catch-up runs, valuable unmerged worktrees, credential-shaped Trash contents, and an old listener on port 8000. Those findings and the current preservation list live in the private continuation record; public documentation does not include job payloads, credentials, or local receipts. Do not treat catch-up runs as on-time market coverage or remove unmerged/dirty work during cleanup.
