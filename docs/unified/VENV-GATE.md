# Venv gate — CI-recipe interpreter (2026-10-08)

Built `/tmp/.../floww-venv` from `backend/requirements.txt` +
CI test packages (pytest/asyncio/httpx/cov/bandit/timeout, ruff 0.15.22).
NOT committed anywhere; lives outside the repo.

## Closed env gaps

- `tests/agent/`: **889 passed, 1 skipped** — includes all 24 modules
  that could not even collect on system python, and the 1 test that
  failed there for missing `mongomock_motor`. Root cause was environment,
  never product.
- `tests/unified/`: 90/90 under the venv (with pytest-timeout active).
- Bandit on slices: 21 HIGHs, ALL pre-existing `server.py` try/except
  patterns far outside every slice hunk (verified: slice adds no
  try/except). CI runs bandit advisory-only. No action.

No system-python results are superseded — they were identical where
runnable. Remaining CI-only surface: none for these suites.
