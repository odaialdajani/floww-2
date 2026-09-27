# Independent research worker recovery proof review - 2026-09-27

Status: PASS for the stated isolated research-worker recovery scope after corrections and independent execution. Read-only review of production/script; report only is reviewer-owned.

## Reproduced first-run failures

- `output/research-worker-recovery-20260927-0137/result.json` failed before server import completed. PyMongo platform metadata invokes a Windows version subprocess, correctly denied by the proof guard. The proof must use direct OS version metadata without weakening its child-program denial.
- `output/research-worker-recovery-20260927-0138/result.json` reached the recovered routes but failed the final unchanged quota assertion. The wording `What is the SPY price?` is intentionally not the narrow `is_price_lookup` grammar; only an explicit spot/underlying price qualifies. The synthetic model throws on restart, production falls back to a deterministic answer, and the final count catches the extra attempt. Use an explicit spot price question for the factual-only new-work case. Do not drop the unchanged call-count assertion. This demonstrates why answer mode alone is insufficient proof of no dispatch.

## Safety findings before independent rerun

- `guarded_environment` initially isolated Mongo but did not override `DUCKDB_PATH`. Importing server imports the DuckDB singleton, which immediately opens inherited storage and initializes tables. Set `DUCKDB_PATH=:memory:` explicitly before import.
- The initial socket guard accepts every loopback port. This does not itself prove that local proxy/broker services cannot be reached. Narrow the allowed destination to the isolated proof's actual Mongo endpoint; the in-process HTTP transport needs no listening port.

## Scope and substantive checks inspected

The script uses actual startup/research composition and real app route handlers with synthetic read/model seams. It explicitly expects one completed answer, two running answers and one queued answer before abrupt owned-child exit; validates startup marks all three unfinished requests interrupted; preserves exact saved answer and one interruption event; checks history, cursor continuation, duplicate identity and changed-request rejection; keeps uncertain usage counted; verifies another session cannot read/cancel/stream owned history; admits new factual work after restart; and reinitializes to check event-log idempotence.

This is a single-process research worker recovery proof against Mongo that remains running. It is not full application lifespan, a database crash, live browser recovery, backup restore, real external model availability, or paper/live trading proof. These limits are explicit in the script and must remain explicit in reporting.


## Final independent execution - 01:41 UTC

Command: backend/.venv/Scripts/python.exe -m scripts.verify_research_worker_recovery --run --output ../output/research-worker-recovery-independent-20260927-0141 (working directory backend).

The final script passed independently in 6.7 seconds. The owned crash child exited 73 exactly, and the fresh recovery child exited 0. Source hashes were unchanged during this run. Evidence is `output/research-worker-recovery-independent-20260927-0141/result.json` with separate crash/recovery receipts and preserved stdout/stderr logs.

Observed durable state changed from completed/running/running/queued to completed/interrupted/interrupted/interrupted. The exact completed answer survived. Synthetic dispatch count stayed 3, and usage entries remained completed/uncertain/uncertain. Restart performed zero model answer/catalog calls; only the explicitly requested new spot-price work read the synthetic cache once. Duplicate request identities returned existing turns without repeated work; changed content returned 409; disabled new work returned 503 while saved history remained accessible. A different session received empty history and 404 for every owned read/stream/cancel. Reinitialization did not grow terminal event logs.

The corrected script forces analytics storage to memory and asserts the actual open database has no file path, limits socket connects to loopback Mongo port 27017, forbids subprocesses inside children and forbids the real model bridge. No denied external/child/model attempts were recorded. The isolated Mongo database is retained as proof-owned evidence; no cleanup of any existing store was performed. The proof does not establish past-run isolation retrospectively: the early script lacked the explicit analytics-path guard, while the final independent run has it and checked the actual connection.

Log review found expected 409/503/404 responses from negative cases, existing deprecation warnings, and the optional AgentField package absent warning. No unexpected traceback or forbidden-boundary attempt occurred.

## Final source SHA-256 identities

- `backend/routes/agent.py`: `40f54240ba5ec47fd601255e73760ca91291f7df92c9300263ac3125fe4930df`
- `backend/scripts/verify_research_worker_recovery.py`: `18d2ff12056e021e6f1dc063a2f2a88efbd643a05c2d3f2638ee06c87df3a8ce`
- `backend/server.py`: `54be26a01b824c30bef472bca673f9421f0d4056837e5af9da8c32b8d3167681`
- `backend/services/agent/codex_model.py`: `e9d1d7c909c57c9d7c206a3d11cb833f0223252d1e5c391b473e9448a9fdf7d3`
- `backend/services/agent/contracts.py`: `6ac9434175ae6b02101a628271710515dc0d08d2ba688d113f7ec7dd66402273`
- `backend/services/agent/local_access.py`: `306a8c03940dea63ad0eb3badc3561aed1530c5d1dd4d7f9fc111b62f4d19a55`
- `backend/services/agent/read_budget.py`: `dac83653c5f73044b09521461589e9addfc090d8a0903f2ac4d2b550570441a4`
- `backend/services/agent/reads.py`: `62f64457e3e53a3863b4800906eb6d1221fedf252f5cc6e6a7a23d4710847e60`
- `backend/services/agent/repository.py`: `c578fce82b95de61f9f232606825b32fb245a6ad0add2e013da9f01cc74d10b9`
- `backend/services/agent/research.py`: `e5370729bb4bbb3a56841157a68937143d81b1e05998d1c92de171ac9d8832bb`

## Final conclusion and remaining limits

No remaining blocker or false success was found within this script's declared scope. The independent run proves owned research-worker restart recovery and saved route behavior against a running isolated Mongo instance, with synthetic cache/model inputs. It does not prove full app startup, database crash/journal recovery, backup restoration, browser/network reconnection, upstream model availability, prediction projection, or paper/live trading. Do not expand this pass into those claims.
