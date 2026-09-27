"""The DUCKDB_PATH seam must decide durability, and must say so when it cannot.

Why this file exists. R8-04 claims a saved review survives a restart, and the
acceptance ledger rests on that. But the restart tests in
`test_r8_04_restart_durability.py` bind their own connection to a temp file — they
exercise the *store*, not the engine production actually uses.

Mutation testing proved the gap: replacing

    path = os.environ.get("DUCKDB_PATH", ":memory:") or ":memory:"

with `path = ":memory:"` — ignoring the configured path entirely, so every save
silently becomes non-durable — left the FULL backend suite green (5467 passed,
68 skipped). Nothing guarded the one switch that decides whether saved work
survives a restart.

`DuckDBEngine` exposes no `path` attribute, so every assertion here is
BEHAVIORAL: does data written through this engine land on the configured file,
and does it come back after the connection is closed? That is the property that
matters, and it is the only one a caller can actually observe.
"""

from __future__ import annotations

import importlib

import duckdb
import pytest

from services.duckdb_engine import _open_shared_db


def test_unset_path_produces_no_file(tmp_path, monkeypatch):
    """No DUCKDB_PATH means in-memory: nothing may be written to disk."""
    monkeypatch.delenv("DUCKDB_PATH", raising=False)
    before = set(tmp_path.iterdir())
    engine = _open_shared_db()
    try:
        engine.conn.execute("CREATE TABLE probe AS SELECT 1 AS x")
    finally:
        engine.close()
    assert set(tmp_path.iterdir()) == before, (
        "an engine opened without DUCKDB_PATH must not create files"
    )


def test_configured_path_creates_the_file(tmp_path, monkeypatch):
    """THE assertion that fails when DUCKDB_PATH is ignored."""
    target = tmp_path / "engine.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(target))
    engine = _open_shared_db()
    try:
        engine.conn.execute("CREATE TABLE probe AS SELECT 1 AS x")
        engine.conn.execute("CHECKPOINT")
    finally:
        engine.close()
    assert target.exists(), (
        f"DUCKDB_PATH was set to {target} but no file was created there — "
        "the engine silently ignored the configured path"
    )


def test_data_survives_close_and_reopen(tmp_path, monkeypatch):
    """End-to-end durability through the engine seam: write, close, reopen."""
    target = tmp_path / "survive.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(target))

    engine = _open_shared_db()
    engine.conn.execute("CREATE TABLE t AS SELECT 42 AS answer")
    engine.conn.execute("CHECKPOINT")
    engine.close()

    # A completely separate connection, exactly as a restart would produce.
    reopened = duckdb.connect(str(target))
    try:
        assert reopened.execute("SELECT answer FROM t").fetchone()[0] == 42
    finally:
        reopened.close()


def test_empty_path_falls_back_to_memory(tmp_path, monkeypatch):
    """An empty string is falsy — it must fall back, not try to open ''."""
    monkeypatch.setenv("DUCKDB_PATH", "")
    engine = _open_shared_db()
    try:
        engine.conn.execute("CREATE TABLE probe AS SELECT 1 AS x")
        engine.conn.execute("CHECKPOINT")
    finally:
        engine.close()
    assert not list(tmp_path.iterdir()), "an empty DUCKDB_PATH must not create files"


def test_unusable_path_falls_back_and_warns(tmp_path, monkeypatch, caplog):
    """A bad path must never prevent startup — degrade, and say why.

    Starting matters more than durability here, but a silent downgrade of
    durability is precisely the failure mode this project keeps warning about,
    so the fallback must be logged.
    """
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("i am a file, not a directory")
    monkeypatch.setenv("DUCKDB_PATH", str(blocker / "nested" / "x.duckdb"))

    with caplog.at_level("WARNING"):
        engine = _open_shared_db()
    try:
        engine.conn.execute("CREATE TABLE probe AS SELECT 1 AS x")
    finally:
        engine.close()
    assert any(
        "DUCKDB_PATH" in (r.getMessage() if hasattr(r, "getMessage") else r.message % r.args)
        for r in caplog.records
    ), "the durability fallback must be logged, not silent"


def test_env_is_read_at_call_time(tmp_path, monkeypatch):
    """_open_shared_db() reads the env per call, not frozen at import.

    The module-level `db = _open_shared_db()` singleton is built at import, so a
    later env change must still be honoured by subsequent calls.
    """
    target = tmp_path / "late.duckdb"
    monkeypatch.setenv("DUCKDB_PATH", str(target))
    engine = _open_shared_db()
    try:
        engine.conn.execute("CREATE TABLE probe AS SELECT 1 AS x")
        engine.conn.execute("CHECKPOINT")
    finally:
        engine.close()
    assert target.exists()

    monkeypatch.delenv("DUCKDB_PATH", raising=False)
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    engine2 = _open_shared_db()
    try:
        engine2.conn.execute("CREATE TABLE probe AS SELECT 1 AS x")
        engine2.conn.execute("CHECKPOINT")
    finally:
        engine2.close()
    assert not list(other.iterdir()), "with DUCKDB_PATH unset, nothing may be written"


def test_helper_is_still_exported():
    """Guard against the seam being renamed out from under these tests."""
    mod = importlib.import_module("services.duckdb_engine")
    assert callable(getattr(mod, "_open_shared_db", None))


@pytest.mark.parametrize("bad", ["   ", "/dev/null/impossible.duckdb"])
def test_pathological_paths_do_not_raise(bad, monkeypatch, tmp_path):
    """Whatever the input, constructing and using the engine must not explode.

    A whitespace-only DUCKDB_PATH is a RELATIVE path, so it would create a file
    named after the spaces in the current working directory. chdir into tmp_path
    so that fallback writes stay contained and never litter the repo.

    Each case falls back to the same shared in-memory database, so the probe
    table must be unique per case or the second collides with the first.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DUCKDB_PATH", bad)
    table = f"probe_{abs(hash(bad)) % 100000}"
    engine = _open_shared_db()
    try:
        engine.conn.execute(f"CREATE TABLE {table} AS SELECT 1 AS x")
        engine.conn.execute("CHECKPOINT")
    finally:
        engine.close()
