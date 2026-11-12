"""Release changes must not change a configured journal's storage identity."""
import runpy
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "services/journal_store.py"


def test_configured_journal_stays_at_the_same_location_across_release_workdirs(monkeypatch, tmp_path):
    target = tmp_path / "durable" / "journal.duckdb"
    monkeypatch.setenv("FLOWW_JOURNAL_DB_PATH", str(target))
    for name in ("release-one", "release-two"):
        directory = tmp_path / name
        directory.mkdir()
        monkeypatch.chdir(directory)
        store = runpy.run_path(str(SOURCE))
        assert store["_DB_PATH"] == target
        assert store["_engine"] is None
    assert not target.exists()


def test_unconfigured_journal_preserves_the_existing_default(monkeypatch):
    monkeypatch.delenv("FLOWW_JOURNAL_DB_PATH", raising=False)
    store = runpy.run_path(str(SOURCE))
    assert store["_DB_PATH"] == SOURCE.parents[2] / "data/journal.duckdb"


def test_relative_configuration_cannot_silently_follow_each_release(monkeypatch):
    monkeypatch.setenv("FLOWW_JOURNAL_DB_PATH", "data/journal.duckdb")
    with pytest.raises(ValueError, match="absolute"):
        runpy.run_path(str(SOURCE))
