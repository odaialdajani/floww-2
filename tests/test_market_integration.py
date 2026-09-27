import asyncio
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import httpx
from services import market_catalog, public_scanner
from services.public_api import PublicBroker
from services.public_request_pacer import RequestPacer


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_expired_stock_keeps_age_without_retaining_contract_payload(self):
        public_scanner._reset_state()
        old = time.time() - 600
        public_scanner._slices["OLD"] = {"ts": old, "rows": [["OLD"]] * 60,
                                         "extras": {"large": "discard"}, "dealer": {"old": True}}
        with patch.object(public_scanner, "scan_slice", AsyncMock(return_value={"OLD": {"status": "failed"}})):
            result = await public_scanner.scan_next(universe=["OLD"], slice_size=1)
        self.assertEqual(result["coverage"]["stale_dropped"], ["OLD"])
        self.assertEqual(public_scanner._slices["OLD"], {"ts": old, "rows": [], "extras": {}, "dealer": None, "event_time": None})
        public_scanner._reset_state()

    async def test_cooldown_preserves_cursor_and_unvisited_names(self):
        from services import public_budget
        budget = public_budget.PublicBudget()
        budget.record_429("api.public.com", retry_after=300)
        public_scanner._reset_state()
        with patch.object(public_budget, "budget", budget), \
             patch.object(public_scanner, "scan_slice", AsyncMock()) as scan:
            with self.assertRaises(public_budget.BudgetExhausted):
                await public_scanner.scan_next(universe=["A", "B", "C"], slice_size=2)
        self.assertEqual(public_scanner._cursor, 0)
        self.assertEqual(public_scanner._attempts, {})
        scan.assert_not_called()

    async def test_expired_coverage_does_not_make_fresh_returned_rows_stale(self):
        from routes import flowseeker
        view = {"columns": [], "rows": [], "count": 0, "tickers": ["NEW", "OLD"],
                "coverage": {"stale_dropped": ["OLD"], "max_age_s": 0}}
        with patch.object(public_scanner, "scan_next", AsyncMock(return_value=view)), \
             patch.object(flowseeker, "_spawn_bg", lambda coroutine: coroutine.close()), \
             patch.object(flowseeker, "_cached_regimes", return_value={}), \
             patch.object(flowseeker, "_volume_baselines", AsyncMock(return_value={})), \
             patch.object(flowseeker, "_prev_contract_oi", AsyncMock(return_value={})):
            result = await flowseeker.public_market_scan(slice_size=2, max_expiries=2)
        self.assertFalse(result["stale"])
        self.assertEqual(result["coverage"]["stale_dropped"], ["OLD"])

    async def test_queued_sweeps_do_not_hold_request_slots(self):
        from routes import flowseeker
        from services import public_budget
        budget = public_budget.PublicBudget(capacity=60, refill_per_sec=0, max_inflight=4)
        async def fetch(tickers, **kwargs):
            await budget.acquire_n(4, "api.public.com")
            try:
                await asyncio.sleep(0)
                return {t: {"status": "ok", "received_ts": time.time(), "rows": [], "extras": {}, "dealer": None} for t in tickers}
            finally:
                budget.release()
        public_scanner._reset_state()
        with patch.dict(os.environ, {"FLOWW_PUBLIC_UNIVERSE": "A,B,C,D"}), \
             patch.object(public_budget, "budget", budget), \
             patch.object(public_scanner, "scan_slice", fetch), \
             patch.object(flowseeker, "_record_scan_baseline", AsyncMock()), \
             patch.object(flowseeker, "_run_institutional_alerts", AsyncMock()):
            results = await asyncio.gather(*(public_scanner.sweep_once(slice_size=1) for _ in range(4)))
        self.assertEqual(results[-1]["coverage"]["fresh"], 4)
        self.assertEqual(results[-1]["coverage"]["latest_failed"], 0)
        self.assertEqual(budget._inflight, 0)
        public_scanner._reset_state()

    async def test_http_hook_respects_active_provider_cooldown(self):
        from services import public_budget, public_request_pacer
        budget = public_budget.PublicBudget()
        budget.record_429("api.public.com", retry_after=300)
        with patch.object(public_budget, "budget", budget):
            with self.assertRaises(public_budget.BudgetExhausted):
                await public_request_pacer.pace_request(httpx.Request("GET", "https://api.public.com/test"))

    async def test_real_saved_snapshot_is_visible_only_after_receipt(self):
        import duckdb
        from datetime import UTC, datetime
        from routes.price_history import read_snapshots
        from services.heatmap_history import record_snapshot
        from services.price_node_history import build_history

        conn = duckdb.connect(":memory:")
        class Engine:
            def query_strict(self, sql, params):
                cursor = conn.execute(sql, params)
                return [dict(zip([c[0] for c in cursor.description], row)) for row in cursor.fetchall()]
        try:
            saved = record_snapshot(conn, {
                "ticker": "SPY", "spot": 100, "asof": "2026-09-25T14:00:00Z",
                "source_received_at": "2026-09-25T14:01:00Z", "expiries_used": ["2026-09-25"],
                "metrics": {"walls": [{"wall_id": "wall", "mid": 100, "low": 99, "high": 101}]},
            }, query_key="SPY:day")
            self.assertIsNotNone(saved)
            rows = read_snapshots(Engine(), "SPY", datetime(2026, 9, 25, 13, tzinfo=UTC),
                                  datetime(2026, 9, 25, 15, tzinfo=UTC))
            bars = [{"t": f"2026-09-25T14:0{i}:00Z", "o": 100, "h": 102, "l": 99, "c": 101} for i in range(3)]
            result = build_history("SPY", bars, rows)
            self.assertEqual(result["frames"][0]["nodes"], [])
            self.assertEqual(result["frames"][1]["nodes"][0]["level"], 100)
            self.assertEqual(result["frames"][1]["snapshot_id"], saved)
        finally:
            conn.close()

    async def test_real_transport_uses_documented_catalog_filters(self):
        seen = []
        async def respond(request):
            seen.append(request)
            return httpx.Response(200, json={"instruments": []})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            broker = PublicBroker("not-a-key", client=client)
            broker._access_token = "test"
            broker._token_expires_at = time.time() + 60
            await broker.get_all_instruments(type_filter=["EQUITY"], trading_filter=["BUY_AND_SELL"])
        self.assertEqual(seen[0].url.params.get_list("typeFilter"), ["EQUITY"])
        self.assertEqual(seen[0].url.params.get_list("tradingFilter"), ["BUY_AND_SELL"])
        self.assertNotIn("type", seen[0].url.params)

    async def test_pacer_spaces_concurrent_calls_without_bursting(self):
        now = [100.0]
        observed = []
        async def sleep(delay):
            now[0] += delay
        limiter = RequestPacer(clock=lambda: now[0], sleep=sleep)
        async def request():
            await limiter.wait()
            observed.append(now[0])
        await asyncio.gather(*(request() for _ in range(20)))
        self.assertTrue(all(b - a >= 0.125 for a, b in zip(observed, observed[1:])))

    async def test_full_catalog_rotates_and_failure_does_not_count_as_fresh(self):
        from services.public_budget import budget
        public_scanner._reset_state()
        names = [f"T{i:05}" for i in range(8786)]
        catalog = {"instruments": [{"symbol": t, "options": True} for t in names],
                   "stale": False, "complete_provider_catalog": True}
        visited = []
        async def scan(tickers, **kwargs):
            visited.extend(tickers)
            return {t: {"status": "failed"} if t == names[0] else {
                "status": "ok", "received_ts": time.time(), "rows": [], "extras": {}, "dealer": None,
                "expiries_checked": 2} for t in tickers}
        with patch.dict(os.environ, {"FLOWW_PUBLIC_UNIVERSE": ""}), \
             patch.object(market_catalog, "_cache", catalog), \
             patch.object(market_catalog, "get_catalog", AsyncMock(return_value=catalog)), \
             patch.object(public_scanner, "scan_slice", scan), \
             patch.object(budget, "peek_available", AsyncMock(return_value=60)):
            first = await public_scanner.scan_next(slice_size=12)
            second = await public_scanner.scan_next(slice_size=12)
        self.assertEqual(visited, names[:24])
        self.assertEqual(first["coverage"]["universe"], 8786)
        self.assertEqual(second["coverage"]["fresh"], 23)
        self.assertEqual(second["coverage"]["latest_failed"], 1)
        self.assertEqual(second["coverage"]["never_scanned"], 8786 - 24)
        self.assertFalse(second["coverage"]["complete_realtime_market"])
        public_scanner._reset_state()

    async def test_missing_catalog_does_not_silently_scan_featured_names(self):
        from services.public_budget import budget
        empty = {"instruments": [], "stale": True, "complete_provider_catalog": False}
        public_scanner._reset_state()
        with patch.dict(os.environ, {"FLOWW_PUBLIC_UNIVERSE": ""}), \
             patch.object(market_catalog, "_cache", None), \
             patch.object(market_catalog, "get_catalog", AsyncMock(return_value=empty)), \
             patch.object(public_scanner, "scan_slice", AsyncMock()) as scan, \
             patch.object(budget, "peek_available", AsyncMock(return_value=60)):
            result = await public_scanner.scan_next()
        scan.assert_not_called()
        self.assertEqual(result["coverage"]["universe"], 0)
        self.assertFalse(result["coverage"]["catalog_available"])


if __name__ == "__main__":
    unittest.main()
