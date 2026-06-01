# Agent 6 — Request Deduplication

## Dedup Logic

`RequestDeduplicator` stores one `asyncio.Future` per request key.

- `execute(key, func)` returns immediately with the shared future if the same
  key is already in flight.
- The first caller runs `func()`; other callers await the same future.
- On success or failure, the finalizer sets `result`/`exception`, then pops the
  key so later requests can retry.
- Multiple waiters consuming a shared exception call `future.exception()` to
  prevent asyncio "Future exception was never retrieved" warnings.

## Integration

- `backend/routes/data_providers.py` adds:
  - `build_chain_data_key(ticker, dte_max, expiries)`
  - `fetch_chain_data_with_dedup(...)` which wraps any `fetch_func` through the
    global `deduplicator`
- Key format: `chain:{ticker}:{dte_max}:{expiries}`
- Single requests continue to work unchanged.

## Test Output

```
backend/tests/services/test_request_deduplicator.py::test_concurrent_same_key PASSED
backend/tests/services/test_request_deduplicator.py::test_concurrent_different_keys PASSED
backend/tests/services/test_request_deduplicator.py::test_exception_propagation PASSED
backend/tests/services/test_request_deduplicator.py::test_cleanup_on_complete PASSED
4 passed in 0.16s
```

## Quota Savings Estimate

High-concurrency ticker windows (e.g. `/api/heatseeker/flip-zones`) fan out
multiple identical requests within seconds. Deduping them typically reduces
outbound provider calls from N→1 without changing response semantics.

## Links

- [[Round10 Infrastructure]]
- [[Agent7 GracefulShutdown]]
