"""U11: store isolation + restart integrity on isolated synthetic copies only.

No original service restart, no user Mongo, no live paths: every store here
is a tmp-path synthetic instance of the same classes.
"""
import sqlite3
import time
from datetime import UTC, datetime, timedelta

import pytest

from services.agent.access.horizon import _calendar
from services.public_scan_observations import PublicScanObservations
from services.related_price_series import RelatedSeriesStore


def _sessions(n=25, end="2026-09-04"):
    return [s.date().isoformat() for s in _calendar().sessions_window(end, -n)]


DAYS = _sessions()
LAST_CLOSE = _calendar().session_close(DAYS[-1]).to_pydatetime().astimezone(UTC)
NOW = LAST_CLOSE + timedelta(minutes=30)


def _series(ticker="AAA"):
    return {
        "ticker": ticker,
        "source": "public_api",
        "interval": "1d",
        "price_basis": "provider_reported",
        "bars": [{"date": d, "close": round(100.0 * (1.001 ** i), 4)}
                 for i, d in enumerate(DAYS)],
        "event_time": LAST_CLOSE.isoformat(),
        "received_at": (LAST_CLOSE + timedelta(minutes=20)).isoformat(),
    }


def test_related_series_survives_close_and_reopen(tmp_path):
    path = str(tmp_path / "series.db")
    store = RelatedSeriesStore(path)
    assert store.save(_series(), now=NOW)
    store.close()
    reopened = RelatedSeriesStore(path)
    got = reopened.get("AAA", now=NOW)
    assert got is not None
    assert got["event_time"] == LAST_CLOSE.isoformat()
    assert [b["date"] for b in got["bars"]] == DAYS
    reopened.close()


def test_related_series_digest_tamper_never_served(tmp_path):
    path = str(tmp_path / "series.db")
    store = RelatedSeriesStore(path)
    assert store.save(_series(), now=NOW)
    store.close()
    raw = sqlite3.connect(path)
    payload = raw.execute("SELECT payload FROM related_series WHERE ticker='AAA'").fetchone()[0]
    raw.execute("UPDATE related_series SET payload=? WHERE ticker='AAA'",
                (payload.replace('"close":', '"close":9', 1),))
    raw.commit()
    raw.close()
    reopened = RelatedSeriesStore(path)
    got = reopened.get("AAA", now=NOW)
    # checksum mismatch -> stored bars dropped, never served; the symbol can
    # only appear via its separate attempt record with EMPTY bars
    assert got is not None and got["bars"] == [] and got["event_time"] is None
    assert reopened.read_error is None  # integrity refusal is not a storage outage
    reopened.close()


def test_corrupt_store_file_discloses_unavailable_not_data(tmp_path):
    path = tmp_path / "dead.db"
    path.write_bytes(b"this is not a sqlite database")
    store = RelatedSeriesStore(str(path))
    result = store.many(["AAA"], now=NOW)
    assert result == {}  # no fabricated rows
    assert store.read_error == "cache_storage_unavailable"


def test_missing_store_file_is_cold_cache_not_crash_safe_claim(tmp_path):
    store = RelatedSeriesStore(str(tmp_path / "never.db"))
    assert store.get("AAA", now=NOW) is None
    assert store.read_error is None


def test_scan_observations_survive_restart_with_clocks(tmp_path):
    path = str(tmp_path / "scan.db")
    store = PublicScanObservations(path)
    row = ["AAA", 0, "call", 165.0, "2026-10-16", 1000.0, 1.0, 2.0, 1.5, 0.01]
    key = f"{row[0]}|{row[2]}|{float(row[3]):g}|{row[4]}"
    pack = {"received_ts": NOW.timestamp() - 100, "status": "ok", "rows": [row],
            "extras": {key: {"volume_source_time": "2026-10-06T15:00:00Z"}},
            "event_time": "2026-10-06T15:00:00+00:00", "source": "public_api",
            "history_status": "available", "selection": {}}
    assert store.save("AAA", pack, scope="rotating") == "saved"
    store.close()
    reopened = PublicScanObservations(path)
    page = reopened.page(now=NOW.timestamp())
    assert page["rows"] and page["rows"][0][0] == "AAA"
    meta = page["observations_by_ticker"]["AAA"]
    assert meta["receipt_clock_status"] == "known"
    assert page["live"] is False
    reopened.close()
