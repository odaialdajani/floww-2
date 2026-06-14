# FINDINGS — Agent 05 (round11)

## Services covered
- `services/websocket_streamer.py` — ConnectionManager class
- `services/logging_config.py` — StructuredFormatter, setup_logging, get_correlation_id, CorrelationIdMiddleware
- `services/graph_updater.py` — module-level (stub with logger only)

## Test counts
| Service | Test file | Tests |
|---|---|---|
| websocket_streamer | tests/services/test_websocket_streamer.py | 22 |
| logging_config | tests/services/test_logging_config.py | 24 |
| graph_updater | tests/services/test_graph_updater.py | 4 |
| **Total** | | **50** |

## Bugs found
None.

Notes:
- `graph_updater.py` is a stub (19 lines, module-level logger only, no public class/functions). Tests pin the current public surface. When the implementation is fleshed out, these tests will need updating.
- All golden values in logging_config tests were independently derived (e.g., record.module comes from os.path.splitext(basename(pathname))[0], not from the dotted logger name).
