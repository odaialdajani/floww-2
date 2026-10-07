import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from test_related_price_series import NOW, payload

from services.related_price_series import RelatedSeriesStore, validate_daily_payload


def admitted(symbol="AAA", n=31):
    return validate_daily_payload(symbol, payload(symbol, n), now=NOW, received_at=NOW)


def test_read_only_empty_cache_does_not_create_a_database_or_cursor(tmp_path):
    path = tmp_path / "empty.sqlite3"
    store = RelatedSeriesStore(path)
    assert store.get("AAA", now=NOW) is None
    assert store.scope("scope", total=20)["cursor"] == 0
    assert not path.exists()


def test_valid_series_survives_restart_and_latest_failure_keeps_original_clocks(tmp_path):
    path = tmp_path / "cache.sqlite3"
    store = RelatedSeriesStore(path)
    assert store.save(admitted(), now=NOW)
    store.close()
    resumed = RelatedSeriesStore(path)
    resumed.failure("AAA", "provider_read_failed", now=NOW + timedelta(seconds=1))
    row = resumed.get("AAA", now=NOW + timedelta(seconds=2))
    assert len(row["bars"]) == 31 and row["received_at"] == NOW.isoformat()
    assert row["latest_fetch"]["status"] == "failed" and row["latest_fetch"]["reason"] == "provider_read_failed"
    assert row["latest_fetch"]["retry_at"] > (NOW + timedelta(seconds=2)).timestamp()
    resumed.close()


def test_older_or_future_series_cannot_replace_newer_admitted_closes(tmp_path):
    store = RelatedSeriesStore(tmp_path / "cache.sqlite3")
    assert store.save(admitted(), now=NOW)
    older = admitted()
    older["event_time"] = "2026-10-05T20:00:00+00:00"
    older["bars"].pop()
    older["received_at"] = "2026-10-05T21:00:00+00:00"
    assert store.save(older, now=NOW) is False
    future = admitted()
    future["received_at"] = "2026-10-08T12:00:00+00:00"
    assert store.save(future, now=NOW) is False
    assert store.get("AAA", now=NOW)["bars"][-1]["date"] == "2026-10-06"
    store.close()


def test_capacity_and_payload_bounds_do_not_evict_valid_history_silently(tmp_path):
    store = RelatedSeriesStore(tmp_path / "cache.sqlite3", max_names=1, max_payload_bytes=4096, max_store_bytes=8192)
    assert store.save(admitted("AAA"), now=NOW)
    assert store.save(admitted("BBB"), now=NOW) is False
    assert store.get("AAA", now=NOW) is not None
    assert store.get("BBB", now=NOW) is None
    store.close()


def test_progress_cursor_is_persistent_and_scope_does_not_bleed_into_another_window(tmp_path):
    path = tmp_path / "cache.sqlite3"
    store = RelatedSeriesStore(path)
    store.advance("AAA:30:all:hash:20261006", 8, total=100, now=NOW)
    store.close()
    store = RelatedSeriesStore(path)
    assert store.scope("AAA:30:all:hash:20261006", total=100)["cursor"] == 8
    assert store.scope("AAA:90:all:hash:20261006", total=100)["cursor"] == 0
    store.close()


def test_get_of_an_existing_closed_store_does_not_create_side_files(tmp_path):
    path = tmp_path / "cache.sqlite3"
    store = RelatedSeriesStore(path)
    assert store.save(admitted(), now=NOW)
    store.close()
    before = {file.name for file in tmp_path.iterdir()}
    assert before == {"cache.sqlite3"}
    reader = RelatedSeriesStore(path)
    assert reader.get("AAA", now=NOW) is not None
    reader.close()
    assert {file.name for file in tmp_path.iterdir()} == before
