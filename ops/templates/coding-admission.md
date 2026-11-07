# Scoped coding fixture contract

`coding_admission.py` creates a new private disposable Git fixture; it does not
accept product prompts or attach to an existing OpenCode service. The only
acceptance ID is `pure-add-v1`: repair addition in `arithmetic.py`, preserve
`README.md`, pass a closed AST grammar and six externally defined numerical
cases. The deterministic checker does not execute arbitrary model Python.

The typed contract declares a full base SHA, canonical clean workspace, exact
regular files, bounded generations, steps, correction count, runtime and bytes.
An exclusive lease is derived from the canonical workspace, regardless of any
proposed caller lock path. It uses a retained file and process lock outside the
checkout. Normal release records `released`; a crash retains `owned`, so a new
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
paths, host/origin/auth/encoding/length violations, unknown fields and other
models. It pins the complete edit/read/write catalog, including descriptions,
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
