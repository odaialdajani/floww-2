"""Isolated checks: no server startup or live provider requests."""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from services import market_catalog as catalog


def equity(symbol, options="BUY_AND_SELL", trading="BUY_AND_SELL", kind="EQUITY"):
    return {"instrument": {"symbol": symbol, "type": kind}, "trading": trading, "optionTrading": options}


class CatalogTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        catalog._cache = None
        catalog._loaded_at = catalog._retry_at = 0

    def test_provider_shapes_and_option_eligibility(self):
        rows = catalog.parse_instruments([
            equity("SPY"), equity("BRK.B", "DISABLED"), equity("SPY"),
            equity("CLOSED", trading="DISABLED"), equity("BTC", kind="CRYPTO"),
            equity("UNKNOWN", None), equity("bad/value"),
            {"instrument": "broken"}, equity("SPY", ["broken"]), equity("SPY"),
        ])
        self.assertEqual([r["symbol"] for r in rows], ["BRK.B", "SPY", "UNKNOWN"])
        self.assertEqual([r["symbol"] for r in rows if r["options"]], ["SPY"])

    async def test_broad_catalog_replaces_fixed_list_and_is_cached(self):
        items = [equity(f"STK{i}") for i in range(16000)]
        with patch.object(catalog, "_fetch_instruments", AsyncMock(return_value=items)) as fetch:
            first = await catalog.get_catalog()
            second = await catalog.get_catalog()
        self.assertEqual(first["total"], 16000)
        self.assertEqual(len(catalog.cached_scan_symbols()), 16000)
        self.assertEqual(fetch.await_count, 1)
        self.assertFalse(first["complete_exchange_catalog"])
        second["instruments"].clear()
        self.assertEqual(len(catalog.cached_scan_symbols()), 16000)

    async def test_failure_preserves_directory_but_marks_stale(self):
        with patch.object(catalog, "_fetch_instruments", AsyncMock(return_value=[equity("SPY")])):
            await catalog.get_catalog()
        with patch.object(catalog, "_fetch_instruments", AsyncMock(side_effect=OSError)) as fetch:
            result = await catalog.get_catalog(refresh=True)
            again = await catalog.get_catalog(refresh=True)
        self.assertTrue(result["stale"])
        self.assertEqual(again["total"], 1)
        self.assertEqual(fetch.await_count, 1)

    async def test_failure_does_not_claim_complete_or_make_up_symbols(self):
        with patch.object(catalog, "_fetch_instruments", AsyncMock(side_effect=OSError)):
            result = await catalog.get_catalog()
        self.assertEqual(result["total"], 0)
        self.assertFalse(result["complete_provider_catalog"])
        self.assertTrue(result["stale"])


if __name__ == "__main__":
    unittest.main()
