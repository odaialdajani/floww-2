# U13 — Cline WIP: dashboard read-budget slice repaired; broader task stays READY

Owner: Cline. Baseline `8194eca43a580121901516b291c1b2435da7ce2c`, worktree
`work/host-cline` (uncommitted; publication held). Reviewer: OpenCode.

## Fresh counterexample (RED, recorded first)

Draft `backend/tests/unified/test_dashboard_read_budget.py` (parent draft,
untracked in `work/floww-unified`) **fails against the exact baseline
middleware**: `GET /api/related/SPY` (and `/api/market/*`, `/api/solstice/*`,
`/api/ensemble/*`, `/api/version`) are not in the committed exemption tuple, so
ordinary dashboard reads consumed the per-IP burst budget — the 429 storm seen
in previews tonight. Baseline family list also used raw `startswith`, so
near-prefix lookalikes (`/api/spotlight`, `/api/relatedness`) would have been
exempt — a boundary violation vs the U13 acceptance text.
Log: `../evidence/u13-red.log` sha256 `66a07321de8e5729...` (exit 1).

## Repair (own lane only, write_paths: backend/server.py + the test file)

`backend/server.py`:
- New `_READ_ONLY_GET_FAMILIES` tuple = baseline families + `/api/related`,
  `/api/market`, `/api/solstice`, `/api/ensemble`, `/api/version`.
- New `_is_read_only_dashboard_path()` enforces **segment boundaries**
  (`path == family or path.startswith(family + "/")`), closing the lookalike
  hole for old and new families alike.
- GET-only; all POST/PUT/PATCH/DELETE and every non-listed path (incl.
  `/api/public`, `/api/alpaca`, `/admission`) keep the burst budget. No
  broker/admission, capture, activation, provider-budget or auth change.

`backend/tests/unified/test_dashboard_read_budget.py` extended from the parent
draft (7 family pins + mutation pins + unclassified pin) with:
- 8 near-prefix lookalike probes (`/api/spotlight`, `/api/relatedness`,
  `/api/heatmap2u`, `/api/tickersXYZ`, `/api/agentic/run`, `/api/version2`,
  `/api/chainmail`, `/api/datastore`) — all must stay limited.
- 3 family-root probes (`/api/version`, `/api/screener`, `/api/related`).
- 4 broker/admission GET probes — never exempt.

## Receipts (GREEN)

- Extended draft: **27 passed**, exit 0 — `../evidence/u13-green.log` sha256 `e4e71915fdc3e049...`.
- Neighboring regression `backend/tests/server/`: **8 passed**, exit 0 — `../evidence/u13-server-regression.log` sha256 `a388c1f3cc5cc680...`.
- `ruff check server.py tests/unified/test_dashboard_read_budget.py`: **All checks passed**.

## Honest scope

This is the **read-budget sub-slice only**. U13's broader acceptance (budget
refusal/cancellation/error accounting, per-process caps, cold/warm fan-out,
range null grids, multiplier identity, tamper rejection, …) is **not** claimed;
U13 remains READY with this slice as admitted evidence pending OpenCode review.
