import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routes import market_catalog, price_history


class RouteTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(market_catalog.router)
        app.include_router(price_history.router)
        self.client = TestClient(app)

    def test_directory_pages_and_filters_all_records(self):
        data = {"instruments": [{"symbol": f"T{i:05}", "options": i % 2 == 0} for i in range(15000)],
                "total": 15000, "optionable_total": 7500, "complete_provider_catalog": True}
        with patch.object(market_catalog, "get_catalog", AsyncMock(return_value=data)):
            response = self.client.get("/api/market/catalog?page=150&limit=100")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["instruments"][-1]["symbol"], "T14999")
            self.assertFalse(response.json()["has_more"])
            filtered = self.client.get("/api/market/catalog?q=T1499&options_only=true").json()
            self.assertEqual(filtered["matches"], 5)
            self.assertTrue(all(row["options"] for row in filtered["instruments"]))

    def test_price_history_does_not_claim_nodes_when_store_is_unavailable(self):
        from services import public_budget
        bars = [{"t": "2026-09-25T09:30:00-04:00", "o": 100, "h": 102, "l": 99, "c": 101}]
        adapter = types.ModuleType("services.public_api_adapter")
        adapter.fetch_bars_by_interval = AsyncMock(return_value=bars)
        engine = types.ModuleType("services.duckdb_engine")
        engine.db = object()
        with patch.dict(sys.modules, {"services.public_api_adapter": adapter, "services.duckdb_engine": engine}), \
             patch.object(price_history, "read_snapshots", side_effect=RuntimeError), \
             patch.object(public_budget.budget, "acquire", AsyncMock()), \
             patch.object(public_budget.budget, "release"):
            response = self.client.get("/api/heatseeker/price-history/SPY?days=5")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["node_status"], "unavailable")
        self.assertEqual(data["frames"][0]["time"], "2026-09-25T13:30:00+00:00")
        self.assertEqual(data["frames"][0]["nodes"], [])
        self.assertIn("prices_received_at", data)

    def test_invalid_page_and_history_ranges_are_rejected(self):
        self.assertEqual(self.client.get("/api/market/catalog?page=0").status_code, 422)
        self.assertEqual(self.client.get("/api/heatseeker/price-history/SPY?days=200").status_code, 422)

    def test_invalid_candles_do_not_claim_availability_or_extend_node_window(self):
        from services import public_budget
        bad = {"t": "2026-09-25T20:00:00Z", "o": 100, "h": 90, "l": 99, "c": 101}
        good = {"t": "2026-09-25T13:30:00Z", "o": 100, "h": 102, "l": 99, "c": 101}
        adapter = types.ModuleType("services.public_api_adapter")
        engine = types.ModuleType("services.duckdb_engine")
        engine.db = object()
        for bars in ([bad], [good, bad]):
            adapter.fetch_bars_by_interval = AsyncMock(return_value=bars)
            with patch.dict(sys.modules, {"services.public_api_adapter": adapter, "services.duckdb_engine": engine}), patch.object(price_history, "read_snapshots", return_value=[]) as read, patch.object(public_budget.budget, "acquire", AsyncMock()), patch.object(public_budget.budget, "release"):
                data = self.client.get("/api/heatseeker/price-history/SPY").json()
            if len(bars) == 1:
                self.assertEqual(data["price_status"], "unavailable")
                self.assertEqual(data["node_status"], "not_loaded")
                read.assert_not_called()
                self.assertNotIn("last_candle_at", data)
            else:
                self.assertEqual(data["candles"], 1)
                self.assertEqual(data["last_candle_at"], "2026-09-25T13:30:00+00:00")
                self.assertEqual(read.call_args.args[3].isoformat(), data["last_candle_at"])


if __name__ == "__main__":
    unittest.main()
