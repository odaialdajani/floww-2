# FLOWW consolidation — November 12, 2026

## Source and publication

The product code checkpoint is `5d5389908c89d9cd90cad50036dc7d3c3c3dddf0`. It contains the integrated chart-scope callback, layout import, backend replay mirror, ETF expiry-clock lineage, and narrow-layout fixes. The outgoing 149-commit range was reviewed for accidental credentials, private account identifiers, host-only files, and transient artifacts before publication. Four pre-existing host-only dirty paths are excluded from this commit and publication.

A later merge of pull request 146 fixed two failing tests only: one used a hardcoded local interpreter path instead of the running one, and one needed the stale-refresh failure task held open before its result was read. Canonical source is now `a6197f57d2629ad16f10c35d0791c6579c701204`, with frontend tree `081f1d358a6d4cc8107270fd2845a70a66240f5c` and backend tree `00020c379d6a0bb72f2d7b6f8dc1a0a5cb24c997`. The backend tree hash moved only because those tests live under `backend/`; no product code changed.

The full frontend source check passed 302 suites and 2,970 tests. The production frontend build succeeded. Retained independent reviews and focused backend results cover the replay and expiry-clock corrections. The unused Python replay mirror has no identified production consumer; its parity repair is source evidence rather than proof of a live path.

## Running application

The managed frontend on port 3000 and backend on port 8213 now serve release `a6197f57d`. The release finished with a native acceptance receipt after all seven required UI checks passed against the live candidate. The first attempt in the same window failed two checks because a cold-restarted backend held the first chart load on a provider slot for longer than the settle wait; no receipt was written for that attempt, and the same checks passed on the immediate rerun with the backend warm. Release `213dcee64` stays on disk as the rollback target.

The live release also corrects a serving defect. The previous frontend hardcoded `http://localhost:8000` as its API base; the current build derives the base from the page origin and sends loopback traffic to `http://127.0.0.1:8213`.

The release required free disk capacity before it would start, because the helper keeps a closed full copy plus a verified restore. That space came from retiring one old backup that already had a verified archive and from clearing regenerable installer caches. The capacity rule was not weakened, and the accepted backup is still retained for rollback.

## Agent and scheduling work

OpenBot's upstream merge and retained gateway changes passed the focused 32-test suite on audited Bun 1.4.3. Full OpenBot application entitlement and the native gateway recovery remain separate held workstreams. The gateway's old owner is absent; its retained lock and exhausted budget must not be reset as routine cleanup.

The three paper-trader schedule definitions have successful execution evidence in the continuation records. A current execution can still be running or fail; historical success does not prove future reliability or order execution. Provider/model configuration and each job's paper/dry-run constraints must be re-attested before changing scheduling. No live trading activation or venue-order authority is granted by this consolidation.

## Remaining scope

The latest 39-row ledger classifies 14 rows as actionable, 20 as partially actionable, and 5 as externally blocked. Those classifications are routing information, not completion. The original 450 historical requirements still require individual acceptance evidence. Remaining work includes gateway ownership recovery, OpenBot entitlement, research source authority and prospective outcomes, account/venue commissioning, cloud lifecycle, and an actual backup destination. Runtime acceptance for `a6197f57d` is closed; it does not close the remaining scope, and any later release must repeat the same guarded process.

Runtime receipts, complete raw-backup recovery archives, restore manifests, scheduler execution details, and historical failed attempts remain in the local continuation evidence. They are not copied into this public repository because publication needs only source and a truthful status checkpoint.
