"""Serialize whole operations sharing a DuckDB connection, including rollback."""

import logging
import threading
import weakref
from contextlib import suppress
from functools import wraps
from time import perf_counter

log = logging.getLogger(__name__)
# Report only contention or operations lasting at least one second.
_SLOW_CONNECTION_SECONDS = 1.0

_registry = weakref.WeakKeyDictionary()
_registry_lock = threading.Lock()
_fallback_lock = threading.RLock()
_guard_state = threading.local()


def connection_lock(conn):
    # Native DuckDB connections support weak references. Coarse serialization
    # also keeps legacy/test adapters without weak-reference support safe.
    with _registry_lock:
        try:
            lock = _registry.get(conn)
            if lock is None:
                lock = threading.RLock()
                _registry[conn] = lock
            return lock
        except TypeError:
            return _fallback_lock


def guarded_connection(fn):
    """Serialize synchronous operations; time only the outermost guard per lock.

    Labels identify code, never connection/SQL/argument/exception payloads.
    Direct connection_lock users are serialized but are not timed here.
    """
    operation = f"{fn.__module__}.{fn.__qualname__}"

    @wraps(fn)
    def guarded(conn, *args, **kwargs):
        lock = connection_lock(conn)
        active = getattr(_guard_state, "active", None)
        if active is None:
            active = _guard_state.active = set()
        if lock in active:
            with lock:
                return fn(conn, *args, **kwargs)
        started = perf_counter()
        acquired = None
        try:
            with lock:
                acquired = perf_counter()
                active.add(lock)
                try:
                    return fn(conn, *args, **kwargs)
                finally:
                    active.remove(lock)
                    held = perf_counter() - acquired
        finally:
            # Emit after the outermost guarded acquisition is released, even
            # on failure. Nested guarded work is included in the outer hold.
            if acquired is not None:
                waited = acquired - started
                if waited >= _SLOW_CONNECTION_SECONDS or held >= _SLOW_CONNECTION_SECONDS:
                    # Diagnostics must never replace a result or exception.
                    with suppress(Exception):
                        log.warning(
                            "Slow shared connection operation=%s wait_seconds=%.3f hold_seconds=%.3f",
                            operation, waited, held,
                        )
    return guarded


@guarded_connection
def query_rows(conn, sql, params=None):
    """Consume the connection-owned result before releasing its lock."""
    return conn.execute(sql, params or []).fetchall()
