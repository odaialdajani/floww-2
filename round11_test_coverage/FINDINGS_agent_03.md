# FINDINGS — Agent 03 (round11/agent-03-mlfeat)

## Services covered
- `services/ml_realtime_features.py`

## Test file created
- `tests/services/test_ml_realtime_features.py`

## Test count
68 tests across 7 test classes:
- `TestEmptyGex` — 2 tests
- `TestKurtosis` — 5 tests
- `TestComputePriceFeaturesRealtime` — 17 tests
- `TestComputeGexFeatures` — 22 tests
- `TestComputeOiFeatures` — 8 tests
- `TestComputeIvFeatures` — 10 tests
- `TestIntegration` — 2 tests

## Bugs found
None. All 68 tests pass against the current source.

## Coverage summary

### `compute_price_features_realtime`
- Happy path: spot, close, high_low_range, open_close_diff
- Moving averages (ma_5, ma_10, ma_20, ma_50) with golden values
- close_to_ma ratios
- Period returns (1d, 2d, 3d, 5d, 10d, 20d) with golden values
- RSI-14: uptrending → 100, insufficient data → 50
- MACD: insufficient data → 0.0
- realized_vol_20d: insufficient data → 0.0
- Fallback behavior when idx < window (MA defaults to close, returns default to 0.0)
- All values finite (no NaN/Inf)

### `compute_gex_features`
- Golden-oracle 4-contract chain: net_gex, total_abs_gex, net_gex_normalized
- King strike/gex/distance_pct
- Regime flags (positive/negative)
- positive_gex, negative_gex, gex_ratio
- Floor/ceiling strikes and distances
- gex_num_strikes, gex_mean, gex_std, gex_skew (IQR), gex_kurtosis
- top5_concentration (few strikes → 1.0, many strikes → between 0 and 1)
- Empty chain → _empty_gex()
- Zero-gamma contracts excluded
- Sign convention: calls positive, puts negative
- CALL/PUT string types recognized alongside C/P
- Floor found when positive-gex strike exists below spot
- All values finite

### `compute_oi_features`
- total_call_oi, total_put_oi with golden values
- put_call_oi_ratio
- ATM OI (within 1% of spot) and atm_put_call_oi_ratio
- Volume features: total_call_volume, total_put_volume, put_call_volume_ratio
- OI-weighted strike and distance
- Empty chain → zeros
- Zero spot → no crash, ATM zeros
- All values finite

### `compute_iv_features`
- avg_call_iv, avg_put_iv with golden values
- iv_skew (put - call)
- avg_iv, min_iv, max_iv, iv_range
- ATM IV (within 0.5% of spot)
- No IV contracts → zeros dict
- 25d IV buckets (delta filtering)
- Zero spot → no crash
- All values finite

### `_empty_gex`
- All 22 keys present, all values 0.0

### `_kurtosis`
- < 4 values → 0.0
- Constant array (std=0) → 0.0
- Normal distribution → near 0
- Uniform distribution → approx -1.2

### Integration
- GEX + OI + IV feature key sets are non-overlapping
- Combined feature vector > 30 features, all finite

## Verification
```
$ cd backend && .venv/bin/python3 -m pytest tests/services/test_ml_realtime_features.py -q
68 passed, 17 warnings in 0.94s

$ cd backend && .venv/bin/ruff check tests/services/test_ml_realtime_features.py
All checks passed!
```
