# Scoped coding fixture contract

`coding_admission.py` creates a new private disposable Git fixture; it does not
accept product prompts or attach to an existing OpenCode service. The only
acceptance ID is `pure-add-v1`: repair addition in `arithmetic.py`, preserve
`README.md`, pass a closed AST grammar and six externally defined numerical
cases. The deterministic checker does not execute arbitrary model Python.

The typed contract declares a full base SHA, canonical clean workspace, exact
regular files, bounded generations, steps, correction count, runtime and bytes.
An exclusive lease is derived from the canonical workspace, regardless of any
proposed caller lock path. It holds process locks on both the verified workspace
directory inode and a retained marker outside the checkout. Replacing the marker
with a genuine earlier `released` marker cannot admit another active owner.
Held/named directory identity and marker identity are rechecked before marker
writes, native launch/input, every generation transport and result acceptance.
Normal release records `released`; a crash retains `owned`, so a new
process refuses stale ownership. Cleanup never unlinks the file and never writes
a replacement inode. Stale or replaced ownership requires review.

Snapshots open every directory component and file through no-follow descriptors.
They verify regular type, one link, bounded bytes and stable name/descriptor
identity, size and timestamps before returning. They reject FIFOs, sockets,
devices, symlinks, hardlinks, concurrent file/directory replacement, ignored and
untracked files, and undeclared directories. Traversal is capped at 256 entries
and 262144 total bytes. The arithmetic checker uses the same safe reader. A
changed head or undeclared path refuses the result. There is no free-form
acceptance command or model-controlled shell.

`native_config()` generates the private OpenCode 2.2.5 v2 configuration at
runtime. It denies permissions/policies by default, enables only file read and
edit on the two declared paths, exposes only read/edit/write tools, and removes
MCP, external plugins, maintenance agents, user instructions and skills. Write
and patch use native `edit` permission. A real permissive session overlay is
used adversarially; forbidden permissions must still deny before model input.
The credential-free hostile replay additionally tries an actual outside edit.
The builtin `opencode.tools` management plugin is disabled: its worktree removal
tool shares the `edit` permission and would otherwise enter the advertised
catalog. Policy enforcement and other builtins remain present. No external
plugin is loaded. Dispatch uses a separate session with the exact restrictive
rules; the permissive overlay is used only for adversarial permission checks.

The worker has no provider credential. A fresh nonce protects one loopback
gateway route. The gateway requires exactly one Host and Authorization header,
and zero or one Origin header; repeated identical or conflicting values reject
before transport. Native requests with no Origin remain valid. It rejects other
paths, host/origin/auth/length violations, unknown fields and other
models. Any Transfer-Encoding or Content-Encoding header rejects by presence,
including empty values and duplicates in either order or casing. It pins the
complete edit/read/write catalog, including descriptions,
required fields, parameter types/properties and schema extras, to the reviewed
OpenCode 2.2.5 catalog digest
`67e1bb437fde5c8fc87349ab0e9862442bd66849de8f8a5c33c7404843fc32d2`
and policy `opencode-2.2.5-pure-add-v1`. Missing, empty, altered, extra, duplicate
or reordered tools reject. The exact saved catalog and binary digest appear in
the example's `native_envelope` reference section, separate from its task fields.
This is an illustration, not a generic JSON task loader. The gateway
caps the actual outgoing body at 1024 tokens and three total generations,
refuses duplicate requests, and closes admission after upstream failure. Its
only external route is one HTTPS POST to
`https://integrate.api.nvidia.com/v1/chat/completions` for
`minimaxai/minimax-m3.1-flash`; redirects, proxies, metadata discovery, automatic
retry and paid fallback are absent. The supervisor kills/reaps the private
process group at 90 seconds or its output limit. OpenCode itself cannot reach
external hosts; its OS sandbox permits only the gateway port and writes to its
private operational stores or the two fixture files. Global configuration,
personal contexts, credentials, project instructions and existing services are
outside this run. Presence of managed policy or changed native binary blocks
startup. Do not override managed policy to make a task pass.

Run offline first, using a fresh artifact directory:

```
/usr/bin/python3 ops/coding_admission.py --artifacts /PRIVATE/NEW/offline --hostile-offline
```

Live mode additionally requires explicit authorized credential-file selection.
Only `NVIDIA_API_KEY` is parsed, without dotenv expansion. The key stays in the
gateway parent process and is injected into the fixed official request only.
No key or credential file contents are written to receipts or tracked files.
There are at most three total live generations; a failed or ambiguous run parks
the task. Do not rerun a live canary automatically.

The receipt is source/fixture evidence with independent review pending. A real
model completion, native board status, green tests or a fixture pass does not
admit arbitrary product coding, a release, service control, publication,
accounts or orders. A broader task needs a reviewed acceptance contract,
protected-path rules and reviewer before dispatch. Corrections are limited to
three and confined to the failed unit; this fixture runner performs none.

## Separately registered product task

`coding_worker.py` registers only `receipt-next-action-v1`, registry
`floww-coding-registry.v1`. It exports `ops/operations_receipt.py` from the exact
`191e3df9ef54db155d512d7e44577fd48188d12c` Git object and checks its declared
SHA-256. Unrelated working files, project instructions, Git hooks, credentials
and personal context are never exported. The private export has a separate clean
Git baseline and the same directory/marker lease and native/gateway boundaries.
The new acceptance ID admits only the one declared path; the arithmetic fixture
and its checker are unchanged.

The model can edit only the existing action selector. Everything before and
after it must be byte-identical to the trusted baseline. A closed AST permits
only branch conditions and literal action assignments, with no calls or imports.
The externally owned checker and baseline under the private continuation's
`coding-trusted` directory are pinned by hash and excluded from model write
scope. The checker runs under a fixed isolated standard-library Python command
with network and writes denied, never imports the candidate module, and checks
772 priority/preservation cases, including all four watchdog states and three
receipt states. It also structurally freezes the four higher-priority branches,
the non-reviewed condition and the reviewed `else`. Its result must match the
safe candidate hash. The checker SHA-256 is
`7f08a14078c24795dfa55bbe290be578db36279f6b38b39b9de4753afad4d2b8`.
Neither model text nor a model-provided test result establishes acceptance.

The next prerequisite is selected inside the existing non-reviewed branch:
`mode_binding_unverified` → `verify_liquid_paper_binding`, then
`provider_parked` → `inspect_parked_provider`, then `runtime_unverified` →
`verify_runtime_acceptance`, then the existing independent-review fallback.
The existing unresolved ledger, missing/stale review and unavailable watchdog
precedence is preserved. Reviewed receipts still select `none`; capabilities
remain false. This contract is specific to this first task. Another task needs
a separately accepted registry change.

Run local positive and hostile native replays without any provider credential:

```
/usr/bin/python3 ops/coding_worker.py --source /PATH/TO/REPOSITORY --artifacts /PRIVATE/NEW/offline
/usr/bin/python3 ops/coding_worker.py --source /PATH/TO/REPOSITORY --artifacts /PRIVATE/NEW/hostile --hostile-offline
```

Live dispatch additionally requires a clean frozen implementation and a private
externally created admission file. Its closed JSON schema binds `schema` to
`floww-coding-live-admission.v2`, the task ID, `implementation_commit` to the
reviewed full SHA, the registry, base SHA, checker SHA, literal `approved: true`,
and all fixed caps: generations 3, output tokens 1024, seconds 90, input bytes
65536, output bytes 262144 and steps 3. An external reviewer supplies a fresh
32-character lowercase hexadecimal `admission_id`, integer Unix `issued_at` and
`expires_at`. The validity interval must contain the current time and span at
most 900 seconds. Validity is checked again before key access and each model
generation, and also bounds the generation deadline.

The fixed trusted ledger is
`/Users/nav/Library/Application Support/FLOWW/operations/coding-admissions`.
It is independent of approval filenames, directories and artifact locations.
The central ID marker is created exclusively and fsynced, then the directory is
fsynced before key access or native launch. No-follow/private-owner checks,
a nonblocking directory lock, current directory identity checks and an inode
witness in the private trusted parent guard consumption. Marker/witness damage,
directory replacement, concurrent ownership and partial crash state refuse;
consumption records are never automatically deleted or repaired. Copying or
renaming an approved JSON record cannot create another budget. Duplicate keys,
incorrect types and old v1 records refuse. A failed/crashed attempt requires
fresh external review and a new ID. Do not generate approval IDs or grants from
model output.
Only an explicitly admitted run uses `--live --admission /PRIVATE/approval.json
--credential-file /PRIVATE/credential`. There are at most three official model
POSTs, 1024 output tokens each, with no automatic retry or fallback.

Receipts retain before/after hashes, actual request/catalog evidence, sandbox
policy, checker result and a candidate patch. No source file is written back,
published or installed. The parent integrator must independently review and
admit any product patch. The worker is one-shot and installs no dispatcher,
schedule or service.
