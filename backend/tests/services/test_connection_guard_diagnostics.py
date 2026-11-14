"""Payload-free timing diagnostics must preserve the shared connection contract."""

import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import duckdb
import pytest

from services import connection_guard as guard


def clock(monkeypatch, *readings):
    values = iter(readings)
    monkeypatch.setattr(guard, "perf_counter", lambda: next(values), raising=False)


def diagnostics(caplog):
    return [r for r in caplog.records if r.name == "services.connection_guard"]


def test_slow_hold_reports_identity_and_timings_without_payload(monkeypatch, caplog):
    conn = duckdb.connect(":memory:")
    clock(monkeypatch, 10.0, 10.125, 12.625)
    caplog.set_level(logging.WARNING)
    try:
        assert guard.query_rows(conn, "SELECT ?", ["secret-credential"]) == [("secret-credential",)]
    finally:
        conn.close()
    records = diagnostics(caplog)
    assert len(records) == 1
    message = records[0].getMessage()
    assert "services.connection_guard.query_rows" in message
    assert "wait_seconds=0.125" in message
    assert "hold_seconds=2.500" in message
    assert "SELECT" not in message
    assert "secret-credential" not in message
    assert records[0].exc_info is None


def test_fast_operations_are_silent(monkeypatch, caplog):
    clock(monkeypatch, 10.0, 10.125, 10.250)
    conn = duckdb.connect(":memory:")
    try:
        assert guard.query_rows(conn, "SELECT 1") == [(1,)]
    finally:
        conn.close()
    assert diagnostics(caplog) == []


def test_slow_wait_is_distinct_from_short_hold(monkeypatch, caplog):
    conn = duckdb.connect(":memory:")
    started = Event()
    readings = iter((10.0, 12.0, 12.125))

    def timed():
        value = next(readings)
        started.set()
        return value

    monkeypatch.setattr(guard, "perf_counter", timed, raising=False)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with guard.connection_lock(conn):
                result = pool.submit(guard.query_rows, conn, "SELECT 1")
                assert started.wait(5)
                assert not result.done()
            assert result.result(timeout=5) == [(1,)]
    finally:
        conn.close()
    records = diagnostics(caplog)
    assert len(records) == 1
    assert "wait_seconds=2.000" in records[0].getMessage()
    assert "hold_seconds=0.125" in records[0].getMessage()


def test_failure_preserves_exception_and_releases_lock_before_logging(monkeypatch, caplog):
    conn = duckdb.connect(":memory:")
    clock(monkeypatch, 0.0, 0.125, 2.125)
    failure = RuntimeError("secret-error-payload")
    acquired = []

    class CheckReleased(logging.Handler):
        def emit(self, record):
            def take_lock():
                lock = guard.connection_lock(conn)
                ok = lock.acquire(timeout=1)
                acquired.append(ok)
                if ok:
                    lock.release()
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(take_lock).result(timeout=5)

    @guard.guarded_connection
    def inner(conn):
        raise failure

    @guard.guarded_connection
    def fail(conn):
        return inner(conn)

    handler = CheckReleased()
    logger = logging.getLogger("services.connection_guard")
    logger.addHandler(handler)
    try:
        with pytest.raises(RuntimeError) as raised:
            fail(conn)
        assert raised.value is failure
        assert acquired == [True]
        assert "secret-error-payload" not in diagnostics(caplog)[0].getMessage()
        clock(monkeypatch, 10.0, 10.0, 12.0)
        assert guard.query_rows(conn, "SELECT 7") == [(7,)]
        assert len(diagnostics(caplog)) == 2
        assert acquired == [True, True]
    finally:
        logger.removeHandler(handler)
        conn.close()


def test_nested_operations_report_only_outermost_hold_after_release(monkeypatch, caplog):
    conn = duckdb.connect(":memory:")
    clock(monkeypatch, 0.0, 0.125, 2.125)

    @guard.guarded_connection
    def outer(conn):
        return guard.query_rows(conn, "SELECT 42")

    try:
        assert outer(conn) == [(42,)]
    finally:
        conn.close()
    messages = [record.getMessage() for record in diagnostics(caplog)]
    assert len(messages) == 1
    assert "outer" in messages[0]
    assert "query_rows" not in messages[0]
    assert "hold_seconds=2.000" in messages[0]


@pytest.mark.parametrize("fails", [False, True])
def test_logging_failure_cannot_change_operation_result(monkeypatch, fails):
    conn = duckdb.connect(":memory:")
    clock(monkeypatch, 0.0, 0.125, 2.125)
    failure = ValueError("operation failure")

    class BrokenHandler(logging.Handler):
        def emit(self, record):
            raise RuntimeError("logging failure")

    @guard.guarded_connection
    def operation(conn):
        if fails:
            raise failure
        return 42

    logger = logging.getLogger("services.connection_guard")
    handler = BrokenHandler()
    logger.addHandler(handler)
    try:
        if fails:
            with pytest.raises(ValueError) as raised:
                operation(conn)
            assert raised.value is failure
        else:
            assert operation(conn) == 42
        with ThreadPoolExecutor(max_workers=1) as pool:
            def take_lock():
                lock = guard.connection_lock(conn)
                ok = lock.acquire(timeout=1)
                if ok:
                    lock.release()
                return ok
            assert pool.submit(take_lock).result(timeout=5)
    finally:
        logger.removeHandler(handler)
        conn.close()


@pytest.mark.parametrize(
    ("acquired", "finished", "warned"),
    [(0.0, 0.999, False), (0.0, 1.0, True), (0.999, 0.999, False), (1.0, 1.0, True)],
)
def test_threshold_applies_to_wait_and_hold_separately(monkeypatch, caplog, acquired, finished, warned):
    clock(monkeypatch, 0.0, acquired, finished)
    conn = duckdb.connect(":memory:")
    try:
        assert guard.query_rows(conn, "SELECT 1") == [(1,)]
    finally:
        conn.close()
    assert bool(diagnostics(caplog)) is warned
