# Combined local and partner update - 2026-10-06

User authorized bringing all work up to date, merging current partner work, committing and pushing. No deployment, capture, paid model turn or live-order activation is included.

## Composition and preservation

- Starting local main1398fa45, shared main6eaa3343 (145 commits newer). All16 local changed/new files were copied with SHA-256 identities to a separate dated safety folder and preserved in e454aa78.
- Integrated shared main and current combined candidate3f3f5abb (139 further commits). All nine current open-review heads are ancestors of the combined checkout: PR93,95,100,101,103,104,105,106,107.
- The older original replay/research source patches were patch-equivalent to the later combined work. Historical merges retained the newer canonical source and later evidence; all31 research conflict resolutions are byte-identical to the pre-history-merge files. Older exact work remains in merge ancestry. The historical closeout text is also preserved as a clearly dated archive.
- All existing sessions/services were retained. Only new owned checks/services were launched. Existing Mongo was not stopped. Copies of the configured DuckDB file and WAL were taken before app startup; these are file preservation, not a certified crash-consistent backup/restore exercise.

## Corrections required by combined checks

- Saved findings no longer claim an empty history on a failed, unknown or partial read. Four cases failed before correction; all74 focused mounted checks passed afterward.
- Windows expired-lease contenders no longer both acquire control. The old implementation used only a per-process thread lock on Windows. The new Windows byte-range sidecar lock retains the POSIX path and refuses lock failures. Independent red contention reproduction,31 root regressions,18 platform/deployment checks and20 independent checks passed, plus forced lock-failure and stale-owner refutation.
- The recorded-only fixture helper initializes its Windows event loop before forbidding every socket connection during reads. Eight Windows socket-pair failures were reproduced; independent attempted external access remains refused, including swallowed failures.
- Source/document checks skip installed Python environments identified by pyvenv.cfg and still inspect adjacent project source. The former secret/document scans entered .venv313. Red fixtures reproduced both scan defects; a separate before/after probe showed that dependency code previously backed a missing project claim and now refuses it.
- The bookmark test now uses a current observation date instead of a permanently aging September fixture; no production bookmark behavior changed.
- Installed already-declared hypothesis/sortedcontainers and CPU torch into the active local project environment. No trained artifacts changed. All141 model-related checks passed in a fresh process after installation; pip check reported no broken requirements.

## Validation status

- Full frontend:130 suites,1375 tests passed; production build passed. Existing warnings about React test cleanup and bundle size remain.
- Configured Bandit medium scan passed, Ruff passed, generated API reference matches383 paths. Truth audit227 passed/0 failed using the verified project Python rather than the Windows Store alias.
- Earlier full backend attempt:7366 passed,27 failed,43 existing skips; coverage69.62%. This was not accepted as green. It ran before the missing torch installation and final test-scope/date corrections. All affected groups subsequently passed.
- Final complete backend rerun: **7412 passed,42 skipped,0 failed**,1977 warnings; coverage **69.71%**, above the configured60% requirement. Exit0 at2026-10-06T11:38:15UTC; runtime662.15s. The final source was unchanged during this run. Local execution is Python3.13.15; this does not claim a Python3.12 container run or hosted acceptance.

## Actual application check and limits

- Started the actual compiled merged frontend on127.0.0.1:3000 and actual backend on127.0.0.1:8001 with existing saved history. Health returns200; actual OpenAPI returns383 paths with admission routes unmounted. SPY spot returned777.6, visibly labelled stale in its response, observed2026-10-06T11:04:13Z; direct chain returned1416 contracts. These are source observations, not a trading signal.
- Connected Chrome computer-use tried the real app. Comet blocked127.0.0.1 with ERR_BLOCKED_BY_CLIENT. No security bypass or alternate browser workaround was attempted. Visual acceptance remains unverified this turn.
- Live Public order activation remains off. Same-approval repeat submission remains an explicitly documented blocker if later armed; approval/capture/account/model/native/release commissioning holds remain. No actual order, cancellation, workflow activation or paid model request was made.
- Stored replay retains saved-source identity, but inherited background current-data polling continues; this was disclosed by review and not represented as fixed.

## Evidence and references

Local detailed receipts are retained under the ignored output/update-20261006 directory. Tests from older receipts are never presented as current acceptance.

- Python Windows byte-range locking reference: https://docs.python.org/3/library/msvcrt.html#msvcrt.locking
- Official CPU package installation reference: https://pytorch.org/get-started/locally/

## Final preservation check

Fresh independent review confirmed all nine inventoried review heads are ancestors, all31 older-source conflict resolutions retain their recorded bytes, and the final qc/test source identities match. Current style/API-reference receipts pass. Source/data test limits and commissioning holds above remain explicit. The shared main will be updated by a normal forward push; the exact published identity is checked after it completes.
