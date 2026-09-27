"""Whole-universe traversal, independently of provider availability."""
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from services import market_catalog, public_budget, public_scanner


class FullRotationTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_catalog_name_is_attempted_and_failures_stay_visible(self):
        names = [f"STOCK{i:05}" for i in range(8786)]
        failures = {names[0], names[4387], names[-1]}
        catalog = {"instruments": [{"symbol": name, "options": True} for name in names],
                   "stale": False, "complete_provider_catalog": True}
        budget = public_budget.PublicBudget()
        visited = []

        async def scan(tickers, **kwargs):
            visited.extend(tickers)
            return {name: {"status": "failed"} if name in failures else {
                "status": "ok", "received_ts": time.time(), "rows": [], "extras": {},
                "dealer": None, "expiries_checked": 2} for name in tickers}

        public_scanner._reset_state()
        try:
            with patch.dict(os.environ, {"FLOWW_PUBLIC_UNIVERSE": ""}), \
                 patch.object(public_budget, "budget", budget), \
                 patch.object(market_catalog, "_cache", catalog), \
                 patch.object(market_catalog, "get_catalog", AsyncMock(return_value=catalog)), \
                 patch.object(public_scanner, "scan_slice", scan):
                while len(set(visited)) < len(names):
                    remaining = len(names) - len(visited)
                    result = await public_scanner.scan_next(slice_size=min(12, remaining))
                self.assertEqual(visited, names)
                self.assertEqual(result["coverage"]["attempted"], len(names))
                self.assertEqual(result["coverage"]["never_scanned"], 0)
                self.assertEqual(result["coverage"]["latest_failed"], len(failures))
                self.assertFalse(result["coverage"]["complete_realtime_market"])
                await public_scanner.scan_next(slice_size=12)
                self.assertEqual(visited[len(names):], names[:12])
        finally:
            public_scanner._reset_state()


if __name__ == "__main__":
    unittest.main()
