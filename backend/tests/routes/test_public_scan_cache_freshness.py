"""Cached dashboard responses preserve per-name receipt ages without new scans."""
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routes import flowseeker as routes
from services import public_scanner as scanner


@pytest.mark.asyncio
@pytest.mark.parametrize("later_age", [61, 118])
async def test_cached_view_drops_expired_name_without_refresh_or_relabel(monkeypatch, later_age):
    clock = [1059.0]
    monkeypatch.setattr(routes, "time", SimpleNamespace(time=lambda: clock[0], monotonic=lambda: clock[0]))
    spy = ["SPY", "SPY-option", "call", 500, "2026-10-16", 25000, 100, .3, .5, 500]
    qqq = ["QQQ", "QQQ-option", "call", 400, "2026-10-16", 10000, 100, .3, .5, 400]
    keys = [scanner.ckey_of(row[0], row[2], row[3], row[4]) for row in [spy, qqq]]
    dated = [{"ticker": "SPY", "received_at": 1000, "contracts": 1, "examples": [spy]}]
    payload = dict(rows=[spy, qqq], count=2, quote_truth={key: {} for key in keys},
                   dealer={"SPY": {"regime": "positive"}, "QQQ": {"regime": "positive"}},
                   coverage=dict(universe=2, fresh=2, stale_dropped=[], max_age_s=59,
                                 checked_at=1059, fresh_window_seconds=60,
                                 received_at_by_ticker={"SPY": 1000, "QQQ": 1049}),
                   stale=False, asof="unchanged-scan-time", recent_findings=dated)
    original = copy.deepcopy(payload)
    scan = AsyncMock(return_value=payload)
    monkeypatch.setattr(routes, "public_market_scan", scan)
    monkeypatch.setattr(routes, "_public_dashboard_cache", None)
    first = await routes._public_dashboard_scan(1000, 500)
    assert first["count"] == 2
    clock[0] = 1000 + later_age
    cached = await routes._public_dashboard_scan(1000, 500)
    assert all(row[0] != "SPY" for row in cached["rows"])
    assert keys[0] not in cached["quote_truth"]
    assert "SPY" not in cached["dealer"]
    assert "SPY" in cached["coverage"]["stale_dropped"]
    assert cached["coverage"]["fresh"] == (1 if later_age == 61 else 0)
    assert cached["coverage"]["checked_at"] == 1059
    assert cached["asof"] == original["asof"]
    assert cached["recent_findings"] == dated
    assert cached["stale"] is True
    assert payload == original
    scan.assert_awaited_once_with(slice_size=2, max_expiries=2)
