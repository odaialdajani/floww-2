import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from services.price_node_history import build_history


def bar(t):
    return {"t": f"2026-09-10T{t}:00+00:00", "o": 100, "h": 102, "l": 99, "c": 101}


def snap(asof, received, level=100, scope="SPY|4|day", ticker="SPY"):
    return {"ticker": ticker, "snapshot_id": f"{level}-{asof}", "query_key": scope,
            "asof_ts": f"2026-09-10T{asof}:00+00:00",
            "received_at": f"2026-09-10T{received}:00+00:00",
            "walls_json": [{"wall_id": "wall", "mid": level}]}


class HistoryTests(unittest.TestCase):
    def test_late_data_never_leaks_backwards(self):
        result = build_history("SPY", [bar("14:00"), bar("14:01"), bar("14:02")],
                               [snap("14:00", "14:02")])
        self.assertEqual([bool(f["nodes"]) for f in result["frames"]], [False, False, True])

    def test_node_changes_gaps_and_old_late_arrivals(self):
        result = build_history("SPY", [bar("14:00"), bar("14:02"), bar("14:30")],
                               [snap("14:00", "14:00"), snap("14:02", "14:02", 105),
                                snap("14:03", "14:29", 110)])
        self.assertEqual([f["nodes"][0]["level"] if f["nodes"] else None for f in result["frames"]],
                         [100, 105, None])

    def test_scope_and_ticker_isolation(self):
        result = build_history("SPY", [bar("14:05")],
                               [snap("14:00", "14:00"), snap("14:01", "14:01", 200, "other"),
                                snap("14:02", "14:02", 300, ticker="QQQ")], "SPY|4|day")
        self.assertEqual(result["frames"][0]["nodes"][0]["level"], 100)

    def test_late_old_reading_does_not_rewind_newer_state(self):
        result = build_history("SPY", [bar("14:12")],
                               [snap("14:10", "14:10", 110), snap("14:00", "14:11", 100)])
        self.assertEqual(result["frames"][0]["nodes"][0]["level"], 110)

    def test_future_arrival_cannot_choose_default_view(self):
        result = build_history("SPY", [bar("14:12")],
                               [snap("14:10", "14:10", 110), snap("14:11", "14:30", 100, "other")])
        self.assertEqual(result["query_key"], "SPY|4|day")
        self.assertEqual(result["frames"][0]["nodes"][0]["level"], 110)

    def test_invalid_prices_and_unknown_timestamps_are_not_drawn(self):
        bad = {**snap("14:00", "14:00"), "received_at": None}
        bad_bar = {**bar("14:01"), "h": float("inf")}
        result = build_history("SPY", [bar("14:00"), bad_bar], [bad])
        self.assertEqual(len(result["frames"]), 1)
        self.assertEqual(result["frames"][0]["nodes"], [])

    def test_expiry_depths_do_not_mix_when_old_recorder_key_matches(self):
        first = {**snap("14:00", "14:00", 100), "expiries": '["2026-09-11"]'}
        second = {**snap("14:01", "14:01", 200), "expiries": '["2026-09-11", "2026-09-18"]'}
        result = build_history("SPY", [bar("14:00"), bar("14:02")], [first, second])
        self.assertEqual(len(result["scopes"]), 2)
        self.assertEqual(result["frames"][0]["nodes"], [])
        self.assertEqual(result["frames"][1]["nodes"][0]["level"], 200)

    def test_out_of_range_numeric_date_does_not_crash_chart(self):
        result = build_history("SPY", [{**bar("14:00"), "t": 1e100}], [])
        self.assertEqual(result["frames"], [])


if __name__ == "__main__":
    unittest.main()
