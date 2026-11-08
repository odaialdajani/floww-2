# Stored Public source adapter — uncommissioned

`backend/services/agent/paper/public_source_adapter.py` implements the existing
`TrustedPaperAdapter` interface. Nothing installs it in an application, creates
a book, changes policy, issues approval, starts a recorder, or submits an order.
The existing admission service remains responsible for funded risk assessment,
durable lease/stop fencing, immutable artifacts, accounting and capacity limits.

## Trust and persisted records

The constructor requires an existing account reader, a `StoredPublicSnapshots`
reader pinned to one server-selected existing DuckDB, and an
`AuthenticatedEvidenceDirectory`. Capture requests may select only
`{"confirmation_id": "<64 hex content digest>"}`. Request quote fields, model
output, calendars, equity and approval flags cannot establish source truth.

The evidence directory is an **external trust interface, not an approval
issuer**. It only reads bounded, regular, non-symlink files named by their content
digest. Files contain `kind`, `body`, and `signature`; signatures are standard
Python `hmac` HMAC-SHA256 over canonical `{"kind": kind, "body": body}` JSON.
Separate constructor-provided keys authenticate owner records (`confirmation`,
`policy_acceptance`) and source records (`source_evidence`). There are no default
keys, signer, writer, provisioning path, network route, or environment-key lookup.
Only test fixtures issue synthetic records into temporary directories.

A signature establishes that a configured issuer attested to bytes. It **does
not prove the factual accuracy of lifecycle, costs, source units or ownership**.
Before commissioning, an independently reviewed issuer must verify those facts,
authenticate the actual owner session, manage keys and revocation, and persist
immutable records. No such production issuer or authenticated confirmation store
has been established in this repository. This adapter must remain unconfigured
until that gap is closed. Its confirmation lifetime and exact policy/account
version binding are not a substitute for issuer revocation design.

Owner confirmation binds exact owner/account/internal venue/recovery epoch,
account version, accepted time, expiry, proposal version, canonical economics,
current policy digest, exact policy-acceptance reference, and exact source-evidence
reference. The signed source bundle binds the same ownership and policy,
economics digest, validity window, exact stored row content hashes, snapshot and
contract selections, complete contract metadata, cost evidence, and session-open
observation. Verification rereads these exact records; it never chooses a newer
snapshot, issues a replacement confirmation, or grants a Boolean risk pass.

## Stored schema and bounded reads

`StoredPublicSnapshots` reads the real `heatmap_snapshots_v2` and
`contract_observations_v2` recorder schemas. It selects only required columns,
uses parameterized queries, limits each exact identity to two rows to detect
ambiguity, and reads all selected rows in one read-only transaction. Up to 64
unique contract selections and 64 KiB output are allowed. The isolated read-only
child process has one thread, a 64 MiB DuckDB memory setting, and a constructor
bounded timeout of at most five seconds (default three). Child timeout kills and
reaps the process. No recorder initialization or migration function is called.
The child disables external access, automatic extension installation and loading,
and requires both named inputs to be actual base tables in the main schema.
Stored views cannot redirect these reads to files, network sources or extensions.
An active writer lock can cause a normal refusal; do not copy an open database
without its supported consistent snapshot/WAL procedure.

Numeric quote columns are read as decimal text from the stored DOUBLE value.
This preserves the retained value; it cannot recover original provider decimal
precision. Exact strike text is required and matched to the full OSI identity.
Both bid and ask event clocks must be present, fresh, no later than receipt, and
no later than the actual decision clock. Their separate clocks remain in the
captured quote; the older side controls executable freshness and valuation.
Positive integer sizes on both sides are mandatory. Unknown size is distinct
from measured zero in readiness reports; both refuse execution.

The recorder's `DEFAULT_STANDARD` multiplier is **not** accepted as contract
proof. The source row must have explicit multiplier provenance and match a
separately attested standard multiplier of 100. Signed metadata must also state
USD per-share option premium units, contracts for quote size, known unadjusted
status, clear corporate-action status, active lifecycle, exact strike/right/
expiry/underlying and standard 100-share physical deliverable. This first adapter
supports standard equity/ETF American options only. Index, adjusted, unknown and
other products refuse. All last-trade, expiration, exercise and settlement
deadlines must still be ahead. No lifecycle processing or exercise is implemented.

The maintained XNYS calendar supplies session time, including holidays and early
closes. Entry and reduction capture refuse outside that conservative session or
at the close. No 16:15 special product extension is inferred. Missing calendar
support refuses. The verification CLI has no clock override.

## Risk, full valuation and liquidity

Every held or working contract and the requested contract requires exactly one
stored row and complete metadata. All current holdings are valued through the
existing valuation service, using the existing accepted mark policy. Opening
equity must be independently attested at the actual session open; initial cash
is never substituted for it. Current policy acceptance is independently checked.
Opening trade cost evidence must match the exact metadata/lifecycle digests and
existing risk formula. Current policy risk is still calculated by the existing
risk service at stage and fill; valid source inputs can produce a risk refusal.

Quote liquidity identity uses provider, exact contract, selected executable side
and that side's source-event timestamp. Snapshot ID, receipt refresh, new
confirmation, opposite-side refresh, or changed price/size at an unchanged side
timestamp cannot create new same-side liquidity. Existing accounting either
recognizes the earlier event or conservatively refuses changed content under its
old identity. This may refuse a legitimate revision lacking a distinct provider
side clock; it never infers replenishment from retrieval time. Reusing a source
clock for changed content requires an explicitly supported future provider-event
contract, not a new adapter-generated ID.

## Read-only verification and actual proof limits

Run from the repository with `PYTHONPATH=backend`:

```
python3.12 -m scripts.verify_public_paper_source --saved-observations /private/saved.json
python3.12 -m scripts.verify_public_paper_source --snapshot-db /private/cold.duckdb --snapshot-id ID --contract-id OSI
```

The CLI only reads local evidence and always returns exit status 2 / admitted
false: readiness inspection is not confirmation or execution admission. It never
contacts a provider. The saved-scan reader accepts the existing
`public-scan-observations` page shape and reports original bid/ask/receipt clocks,
missing sizes, unknown units/multiplier/lifecycle/cost/approval, and absence of an
immutable recorder snapshot. That legacy page is never converted to executable
`CapturedInputs`.

On November 7 ET, one bounded existing saved-data endpoint read retained a SPY
contract with stale distinct bid/ask clocks, absent sizes and all the above
missing authorities; the real clock was Saturday. It correctly refused. Raw
private evidence and exact checks are in the continuation report; no actual
market source, policy, account or venue was commissioned. Acceptance tests use
synthetic rows written through the real recorder into temporary DuckDB plus
explicitly synthetic issuer keys. They do not establish real source semantics.
