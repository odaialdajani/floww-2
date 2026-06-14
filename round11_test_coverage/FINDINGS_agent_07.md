# FINDINGS — Agent 07 (kanban: throughput_model + multi_repo)

## Services Covered
- `services/kanban/throughput_model.py`
- `services/kanban/multi_repo.py`

## Test Count
- **51 new tests** across 2 test files
  - `tests/services/kanban/test_throughput_model.py` (40 tests)
  - `tests/services/kanban/test_multi_repo.py` (12 tests — was 0, now 12)

## Bugs Found

### BUG-1: extract_card_features — YAML auto-parses ISO timestamps (xfail)
- **File**: `services/kanban/throughput_model.py:78-81`
- **Wrong**: When card frontmatter has unquoted `created_at: 2026-06-01T10:00:00Z`, PyYAML `safe_load` parses it as a `datetime.datetime` object. The code then calls `created.replace("Z", "+00:00")` — but `datetime.replace()` takes keyword args (like `tzinfo`), not string positional args. This raises `TypeError`, silently caught by `except (ValueError, TypeError)`, and falls to `features["completion_hours"] = features["estimate_hours"]` (often 0).
- **Right**: Either (a) handle `datetime` objects: `if isinstance(created, datetime): t_created = created`, or (b) document that card timestamps MUST be quoted strings, or (c) use `str(created).replace(...)` in the try block.
- **Impact**: Any real kanban card with unquoted ISO timestamps silently gets `completion_hours = estimate_hours` instead of the actual elapsed time.
- **Test**: `test_completion_hours_from_timestamps` (xfail)

### OBS-1: multi_repo.get_cross_repo_status is a stub
- **File**: `services/kanban/multi_repo.py:111-117`
- The function always returns `{"repos": {}, "cross_repo_cards": []}` regardless of input. This means `generate_multi_repo_status()` produces an empty "Repos" section and "No cross-repo cards detected" even when cards declare `affects_repos`. Not a bug per se — it's an incomplete implementation. Tests document current behavior.

### OBS-2: load_historical_data scans CARDS_DIR at import time
- **File**: `services/kanban/throughput_model.py:273`
- `CARDS_DIR` is a module-level constant derived from `REPO_ROOT`. Tests must monkeypatch all 4 module-level path constants (`REPO_ROOT`, `KANBAN_DIR`, `CARDS_DIR`, `HISTORY_FILE`) to redirect to tmp dirs. This is fragile — passing a path parameter would be cleaner.
