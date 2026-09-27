"""backend/services — service-layer modules.

Contains async-aware classes wrapping external dependencies
(MongoDB, DuckDB, Public.com, etc.) and domain
operations (paper trading, ML inference, GEX history).

This file exists primarily to make pytest's full-suite collection
succeed. Without it, pytest treats `services` as a namespace
package and bails with `ModuleNotFoundError: services is not a
package` on ~20 test files.
"""
