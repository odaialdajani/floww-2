# Round 11 — Agent 04 (ML Infra) — Findings

**Branch:** `round11/agent-04-mlinfra`

## Services covered

| Service | Test file | Tests |
|---|---|---|
| `services/ml/health_monitor.py` | `tests/services/ml/test_health_monitor.py` | 21 |
| `services/ml/gex_inference.py` | `tests/services/ml/test_gex_inference_extra.py` | 23 |

## Test summary

- **Total:** 44 tests (43 passed, 1 xfailed)
- **Regression:** No new failures introduced (26 pre-existing failures from other round11 agents)

## Bugs found

### 1. `gex_concentration` never computed

- **File:** `backend/services/ml/gex_inference.py`
- **Line:** 18 (in `GEX_REQUIRED_FEATURES` frozenset)
- **Detail:** `gex_concentration` is listed in `GEX_REQUIRED_FEATURES` but `compute_gex_features()` never computes or sets this key. The feature dictionary returned by `compute_gex_features` does not include it.
- **Impact:** Any downstream code that expects `gex_concentration` in the GEX feature dict will get a `KeyError` or silently missing data.
- **Marking:** `test_feature_set_superset_of_gex_required` is marked `@pytest.mark.xfail` pending a source fix.
