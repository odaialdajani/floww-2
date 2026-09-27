"""Real local observation storage plus semantic snapshot regressions."""
import asyncio
import json
import math
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

BACKEND = next(parent / "backend" for parent in Path(__file__).resolve().parents if (parent / "backend").is_dir())
sys.path.append(str(BACKEND))

from services import public_scanner as scanner  # noqa: E402
from services.scan_observations import (  # noqa: E402
    SnapshotObservations,
    eligible_quote,
    select_observations,
    volume_change,
)

NOW = datetime(2026, 9, 25, 14, tzinfo=UTC).timestamp()


def contract(osi="TEST", volume=1000, **changes):
    return {**dict(osi=osi, volume=volume, bid=1.0, ask=1.2, last=1.2, mid=1.1,
                strike=100, type="call", expiry="2026-10-16", oi=100), **changes}


def observations(now=NOW, volume=1000):
    return select_observations([contract(volume=volume)], [], now)[0]


class ObservationTests(unittest.TestCase):
    def test_source_rewind_cannot_replace_newer_baseline_or_invent_change(self):
        first = contract(volume_timestamp=NOW, bid_timestamp=NOW, ask_timestamp=NOW)
        saved, _ = select_observations([first], [], NOW + 1)
        old = contract(volume=1200, volume_timestamp=NOW - 10,
                       bid_timestamp=NOW - 10, ask_timestamp=NOW - 10)
        self.assertIsNone(volume_change(old, saved["TEST"], NOW + 20)["snapshot_volume_change"])
        next_saved, _ = select_observations([old], [], NOW + 20, saved)
        self.assertEqual(next_saved["TEST"]["volume"], 1000)
        self.assertEqual(next_saved["TEST"]["volume_timestamp"], NOW)
        self.assertTrue(next_saved["TEST"]["uncertain"])

    def test_signing_never_uses_quote_after_the_trade(self):
        previous = {"TEST": {**observations()["TEST"], "quote_timestamp": NOW + 5,
                              "received_at": NOW + 6, "mid": 1.4}}
        current = {**contract(), "bid": 1.0, "ask": 2.0, "mid": 1.5, "last": 1.5,
                   "bid_timestamp": NOW - 10, "ask_timestamp": NOW - 10, "last_timestamp": NOW - 10}
        _, extras = scanner.unusual_rows_from_chain({"ticker": "TEST", "spot": 100, "contracts": [current]},
                                                     now=NOW + 20, observations=previous)
        self.assertIsNone(next(iter(extras.values()))["signed_side"])

    def test_previous_days_expire_without_allowing_clock_rewind(self):
        store = SnapshotObservations(":memory:", symbol_limit=1)
        try:
            store.write("OLD", NOW, observations())
            self.assertEqual(store.write("NEW", NOW + 86400, observations(NOW + 86400)), "saved")
            self.assertIsNone(store.read("OLD"))
            self.assertEqual(store.write("OLD", NOW + 60, observations(NOW + 60)), "out_of_order")
            self.assertIsNotNone(store.read("NEW"))
        finally:
            store.close()

    def test_receipt_difference_does_not_claim_arrival_rate(self):
        previous = observations()["TEST"]
        result = volume_change(contract(volume=1600), previous, NOW + 60)
        self.assertEqual(result["snapshot_volume_change"], 600)
        self.assertEqual(result["snapshot_elapsed_seconds"], 60)
        self.assertEqual(result["volume_change_basis"], "snapshot_receipt")
        self.assertIsNone(result["vol_delta"])
        self.assertIsNone(result["velocity_per_min"])

    def test_rate_requires_two_recent_source_volume_times(self):
        previous = {**observations()["TEST"], "volume_timestamp": NOW - 2}
        result = volume_change(contract(volume=1600, volume_timestamp=NOW + 58), previous, NOW + 60)
        self.assertEqual(result["vol_delta"], 600)
        self.assertEqual(result["velocity_per_min"], 600)
        for bad in (None, NOW - 3600, NOW + 61):
            result = volume_change(contract(volume=1600, volume_timestamp=bad), previous, NOW + 60)
            self.assertIsNone(result["velocity_per_min"])

    def test_invalid_volume_never_becomes_zero(self):
        for value in (None, True, -10, math.nan, math.inf, "bad"):
            with self.subTest(value=value):
                records, _ = select_observations([contract(volume=value)], [], NOW)
                self.assertFalse(records)
                result = volume_change(contract(volume=300), {"volume": value, "received_at": NOW}, NOW + 60)
                self.assertIsNone(result["snapshot_volume_change"])

    def test_drop_day_change_and_backward_clock_have_no_new_activity(self):
        previous = observations()["TEST"]
        for now, volume in ((NOW, 1200), (NOW - 1, 1200), (NOW + 60, 300), (NOW + 86400, 1200)):
            result = volume_change(contract(volume=volume), previous, now)
            self.assertIsNone(result["snapshot_volume_change"])
            self.assertIsNone(result["velocity_per_min"])

    def test_quote_sign_requires_matching_actual_times(self):
        self.assertFalse(eligible_quote(contract(), NOW))
        current = contract(bid_timestamp=NOW, ask_timestamp=NOW, last_timestamp=NOW)
        self.assertTrue(eligible_quote(current, NOW))
        for key, value in (("ask_timestamp", NOW + 1), ("bid_timestamp", NOW - 61),
                           ("last_timestamp", NOW - 30)):
            self.assertFalse(eligible_quote({**current, key: value}, NOW))

    def test_quote_ring_uses_new_contiguous_source_quotes(self):
        def item(at):
            return contract(bid_timestamp=at, ask_timestamp=at)
        first, _ = select_observations([item(NOW)], [], NOW)
        self.assertEqual(first["TEST"]["mid_ring"], [1.1])
        same, _ = select_observations([item(NOW)], [], NOW + 1, first)
        self.assertEqual(same["TEST"]["mid_ring"], [1.1])
        second, _ = select_observations([item(NOW + 10)], [], NOW + 10, same)
        self.assertEqual(second["TEST"]["mid_ring"], [1.1, 1.1])
        distant, _ = select_observations([item(NOW + 3600)], [], NOW + 3600, second)
        self.assertEqual(distant["TEST"]["mid_ring"], [1.1])
        future, _ = select_observations([{**item(NOW), "ask_timestamp": NOW + 1}], [], NOW)
        self.assertEqual(future["TEST"]["mid_ring"], [])

    def test_per_name_bound_preserves_current_emitted_contracts(self):
        contracts = [contract(osi=f"C{i}", volume=1000 + i, strike=100 + i) for i in range(100)]
        saved, capped = select_observations(contracts, ["C0"], NOW)
        self.assertTrue(capped)
        self.assertEqual(len(saved), 60)
        self.assertIn("C0", saved)

    def test_restart_and_same_or_older_observation_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.sqlite3"
            store = SnapshotObservations(path)
            self.assertEqual(store.write("TEST", NOW, observations()), "saved")
            self.assertEqual(store.write("TEST", NOW, observations()), "unchanged")
            self.assertEqual(store.write("TEST", NOW, observations(volume=1100)), "out_of_order")
            self.assertEqual(store.write("TEST", NOW - 1, observations(NOW - 1)), "out_of_order")
            store.close()
            script = "import sys,json;sys.path.insert(0,sys.argv[1]);from services.scan_observations import SnapshotObservations;s=SnapshotObservations(sys.argv[2]);print(json.dumps(s.read('TEST')));s.close()"
            result = subprocess.run([sys.executable, "-c", script, str(Path(scanner.__file__).resolve().parent.parent), str(path)],
                                    capture_output=True, text=True, check=True,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.assertEqual(json.loads(result.stdout)["records"], observations())

    def test_capacity_refuses_new_name_without_evicting_existing(self):
        store = SnapshotObservations(":memory:", symbol_limit=2)
        try:
            store.write("FIRST", NOW, observations())
            store.write("SECOND", NOW, observations())
            self.assertEqual(store.write("THIRD", NOW, observations()), "capacity_reached")
            self.assertIsNotNone(store.read("FIRST"))
            self.assertEqual(store.write("FIRST", NOW + 60, observations(NOW + 60, 1600)), "saved")
            self.assertEqual(store.read("FIRST")["records"]["TEST"]["volume"], 1600)
        finally:
            store.close()

    def test_concurrent_writes_cannot_replace_newer_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.sqlite3"
            stores = [SnapshotObservations(path) for _ in range(10)]
            try:
                def save(index):
                    return stores[index].write("TEST", NOW + index, observations(NOW + index, 1000 + index))
                with ThreadPoolExecutor(max_workers=10) as pool:
                    list(pool.map(save, range(10)))
                self.assertEqual(stores[0].read("TEST")["records"]["TEST"]["volume"], 1009)
            finally:
                for store in stores:
                    store.close()

    def test_corruption_and_invalid_write_refuse(self):
        store = SnapshotObservations(":memory:")
        try:
            with self.assertRaises(ValueError):
                store.write("TEST", NOW, {"TEST": {**observations()["TEST"], "volume": True}})
            store.write("TEST", NOW, observations())
            store._db().execute("UPDATE observations SET sha256='changed' WHERE ticker='TEST'")
            with self.assertRaises(ValueError):
                store.read("TEST")
        finally:
            store.close()

    def test_two_complete_8786_name_rotations_keep_all_selected_baselines(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SnapshotObservations(Path(directory) / "full.sqlite3")
            counts = []
            for cycle in range(2):
                hits = 0
                for index in range(8786):
                    symbol = f"T{index:05}"
                    at = NOW + cycle * 7200 + index * 0.5
                    contracts = [contract(osi=f"{symbol}C{leg}", volume=1000 + cycle * 100, strike=100 + leg) for leg in range(3)]
                    prior = store.read(symbol)
                    for item in contracts:
                        delta = volume_change(item, prior["records"].get(item["osi"]) if prior else None, at)
                        hits += delta["snapshot_volume_change"] == 100
                        self.assertIsNone(delta["velocity_per_min"])
                    selected, _ = select_observations(contracts, [], at)
                    self.assertEqual(store.write(symbol, at, selected), "saved")
                counts.append(hits)
            store.close()
            self.assertEqual(counts, [0, 26358])

    def test_scan_storage_failure_keeps_history_unknown(self):
        async def execute():
            scanner._reset_state()
            chain = {"ticker": "TEST", "spot": 100, "fetched_at": datetime.now(UTC).isoformat(),
                     "contracts": [contract()], "stale": False}
            with patch("services.public_api_adapter.fetch_chain_from_public_api", AsyncMock(return_value=chain)), \
                 patch.object(scanner, "_get_adv", None), \
                 patch.object(scanner._observations_store(), "read", side_effect=OSError("offline")), \
                 patch.object(scanner._observations_store(), "write", side_effect=OSError("offline")):
                result = await scanner.scan_slice(["TEST"])
            self.assertEqual(result["TEST"]["history_status"], "unavailable")
            self.assertTrue(result["TEST"]["rows"])
            self.assertTrue(all(item["velocity_per_min"] is None for item in result["TEST"]["extras"].values()))
            scanner._reset_state()
        asyncio.run(execute())

    def test_disk_write_does_not_block_other_async_work(self):
        async def execute():
            scanner._reset_state()
            entered, release = threading.Event(), threading.Event()
            real = scanner._observations_store().write
            def slow(*args):
                entered.set()
                if not release.wait(3):
                    raise AssertionError("event loop blocked by disk write")
                return real(*args)
            chain = {"ticker": "TEST", "spot": 100, "fetched_at": datetime.now(UTC).isoformat(),
                     "contracts": [contract()], "stale": False}
            with patch("services.public_api_adapter.fetch_chain_from_public_api", AsyncMock(return_value=chain)), \
                 patch.object(scanner, "_get_adv", None), patch.object(scanner._observations_store(), "write", side_effect=slow):
                task = asyncio.create_task(scanner.scan_slice(["TEST"]))
                for _ in range(1000):
                    if entered.is_set():
                        break
                    await asyncio.sleep(0.001)
                self.assertTrue(entered.is_set())
                release.set()
                self.assertEqual((await task)["TEST"]["history_status"], "available")
            scanner._reset_state()
        asyncio.run(execute())


if __name__ == "__main__":
    unittest.main()


def test_future_or_invalid_source_does_not_poison_next_baseline():
    for source_time in (NOW + 1000, 'bad-time', True):
        bad = contract(volume=300, volume_timestamp=source_time)
        saved, _ = select_observations([bad], [], NOW)
        assert saved['TEST']['uncertain'] is True
        assert volume_change(contract(volume=500), saved['TEST'], NOW + 60)['snapshot_volume_change'] is None
        clean, _ = select_observations([contract(volume=500)], [], NOW + 60, saved)
        assert volume_change(contract(volume=600), clean['TEST'], NOW + 120)['snapshot_volume_change'] == 100
        assert volume_change(bad, observations()['TEST'], NOW + 10)['snapshot_volume_change'] is None


def test_store_capacity_requires_exact_integer():
    for value in (True, 1.5, '2'):
        with unittest.TestCase().assertRaises(ValueError):
            SnapshotObservations(':memory:', symbol_limit=value)


def test_identical_contracts_collapse_and_conflicting_duplicates_are_unknown():
    item = contract(volume=1000)
    for contracts, expected in (([item, dict(item)],1),([item,contract(volume=2000)],0),([contract(volume=2000),item],0)):
        rows, extras = scanner.unusual_rows_from_chain({"ticker":"TEST","spot":100,"contracts":contracts}, now=NOW)
        saved, _ = select_observations(contracts,[],NOW)
        assert len(rows)==expected
        assert len(extras)==expected
        assert len(saved)==expected


def test_colliding_display_identity_excludes_both_distinct_contracts():
    rows, extras = scanner.unusual_rows_from_chain({"ticker":"TEST","spot":100,"contracts":[contract("ONE"),contract("TWO",2000)]},now=NOW)
    saved,_=select_observations([contract("ONE"),contract("TWO",2000)],[],NOW)
    assert rows==[] and extras=={} and saved=={}


def test_current_quote_must_not_arrive_after_trade_source_time():
    assert not eligible_quote(contract(bid_timestamp=NOW,ask_timestamp=NOW,last_timestamp=NOW-1),NOW)


def test_startup_lock_retries_and_closes_failed_connection():
    import sqlite3
    from unittest.mock import MagicMock
    from services import scan_observations as module
    first = MagicMock()
    lock = sqlite3.OperationalError("database is locked")
    lock.sqlite_errorcode = sqlite3.SQLITE_BUSY
    first.execute.side_effect = lock
    actual = sqlite3.connect(":memory:")
    store = SnapshotObservations(":memory:")
    try:
        with patch.object(module.sqlite3, "connect", side_effect=[first, actual]):
            assert store.write("TEST", NOW, observations()) == "saved"
        first.close.assert_called_once()
        assert store.read("TEST")["records"] == observations()
    finally:
        store.close()


def test_non_lock_startup_failure_closes_connection_and_does_not_retry():
    import sqlite3
    from unittest.mock import MagicMock
    from services import scan_observations as module
    connection = MagicMock()
    connection.execute.side_effect = sqlite3.OperationalError("disk unavailable")
    store = SnapshotObservations(":memory:")
    with patch.object(module.sqlite3, "connect", return_value=connection) as connect:
        with unittest.TestCase().assertRaises(sqlite3.OperationalError):
            store.read("TEST")
        assert connect.call_count == 1
    connection.close.assert_called_once()
    assert store._connection is None
