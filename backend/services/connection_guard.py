"""Serialize whole operations sharing a DuckDB connection, including rollback."""

import threading
import weakref
from functools import wraps

_registry = weakref.WeakKeyDictionary()
_registry_lock = threading.Lock()
_fallback_lock = threading.RLock()


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
    """For synchronous functions whose first argument is the connection."""
    @wraps(fn)
    def guarded(conn, *args, **kwargs):
        with connection_lock(conn):
            return fn(conn, *args, **kwargs)
    return guarded


@guarded_connection
def query_rows(conn, sql, params=None):
    """Consume the connection-owned result before releasing its lock."""
    return conn.execute(sql, params or []).fetchall()
