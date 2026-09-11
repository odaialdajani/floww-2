"""Venue-vs-journal drift detection (read-only).

RED contract: nothing compares the venue position against open journal
cards, so partial fills, canceled closes, and seeded-card skew go
unnoticed. check_position_journal_drift() reports venue qty, net journal
qty, and drift without mutating anything. Fail-open: never raises.
"""
from __future__ import annotations

import contextlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.duckdb_engine import DuckDBEngine  # noqa: E402
from services.journal_store import (  # noqa: E402
    init_journal_tables,
    save_seeds,
)


@pytest.fixture
def jeng():
    eng = DuckDBEngine(":memory:")
    init_journal_tables(eng)
    yield eng
    with contextlib.suppress(Exception):
        eng._conn.close()


def _seed(ticker, action="buy", quantity="2", **over):
    base = {
        "ticker": ticker, "type": "equity", "action": action, "strike": 0.0,
        "expiry": "", "quantity": quantity, "entry_price": 1.25,
        "exit_price": "", "entry_date": "2026-08-22", "exit_date": "",
        "notes": "", "gex_regime": "", "setup": "drift", "tags": "auto",
        "ckey": f"{ticker}|call|500|2026-09-18|{action}|{quantity}",
    }
    base.update(over)
    return base


class _FakeClient:
    def __init__(self, positions=None, fail=False):
        self.positions = positions
        self.fail = fail

    async def get_positions(self):
        if self.fail:
            raise RuntimeError("venue down")
        return self.positions


class TestPositionJournalDrift:
    async def test_aligned_quantities(self, jeng):
        from routes.alpaca import check_position_journal_drift

        save_seeds(jeng, [_seed("DRF_OK")])
        out = await check_position_journal_drift(
            "DRF_OK", client=_FakeClient([{"symbol": "DRF_OK", "qty": "2"}]),
            engine=jeng)
        assert out["status"] == "aligned"
        assert out["drift"] == 0
        assert out["venue_qty"] == 2.0

    async def test_stale_card_detected(self, jeng):
        from routes.alpaca import check_position_journal_drift

        save_seeds(jeng, [_seed("DRF_STALE")])
        out = await check_position_journal_drift(
            "DRF_STALE", client=_FakeClient([]), engine=jeng)
        assert out["status"] == "drift"
        assert out["venue_qty"] == 0
        assert out["journal_qty"] == 2.0

    async def test_venue_only_detected(self, jeng):
        from routes.alpaca import check_position_journal_drift

        out = await check_position_journal_drift(
            "DRF_BARE", client=_FakeClient([{"symbol": "DRF_BARE", "qty": "1"}]),
            engine=jeng)
        assert out["status"] == "drift"
        assert out["journal_qty"] == 0

    async def test_net_journal_sign(self, jeng):
        """Buy 2 + sell 1 nets to 1 against a venue 1."""
        from routes.alpaca import check_position_journal_drift

        save_seeds(jeng, [_seed("DRF_NET"), _seed("DRF_NET", action="sell",
                                                  quantity="1")])
        out = await check_position_journal_drift(
            "DRF_NET", client=_FakeClient([{"symbol": "DRF_NET", "qty": "1"}]),
            engine=jeng)
        assert out["status"] == "aligned"
        assert out["journal_qty"] == 1.0

    async def test_venue_failure_is_unknown(self, jeng):
        from routes.alpaca import check_position_journal_drift

        save_seeds(jeng, [_seed("DRF_DOWN")])
        out = await check_position_journal_drift(
            "DRF_DOWN", client=_FakeClient(fail=True), engine=jeng)
        assert out["status"] == "unknown"
        assert out["venue_qty"] is None

    @pytest.mark.parametrize("qty", ["nan", "inf", "broken"])
    async def test_malformed_venue_quantity_is_unknown(self, jeng, qty):
        from routes.alpaca import check_position_journal_drift
        result = await check_position_journal_drift(
            "SPY", client=_FakeClient([{"symbol": "SPY", "qty": qty}]), engine=jeng)
        assert result["status"] == "unknown"
        assert result["drift"] is None

    async def test_equity_drift_does_not_count_option_contracts(self, jeng):
        from routes.alpaca import check_position_journal_drift
        save_seeds(jeng, [_seed("SPY", type="call", strike=500, expiry="2026-09-18")])
        result = await check_position_journal_drift("SPY", client=_FakeClient([]), engine=jeng)
        assert result["status"] == "aligned"
        assert result["journal_qty"] == 0
