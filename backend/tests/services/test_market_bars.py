"""B1: C13 bars/ADV provider contract (Agent B, institutional loop).

get_1min_bars / get_daily_bars / get_adv_21d over paid Public data:
budget-gated, cached (day-granular, RTH-aware TTL), OHLC-validated with
quarantine counters, stale-serve on failure, None when cold+unavailable.
Pure helpers tested without network; I/O paths via monkeypatched upstream.
"""

import pytest

import services.market_bars as mb


@pytest.fixture(autouse=True)
def clean():
    mb._reset_state()
    yield
    mb._reset_state()


def _bar(t, o=10.0, h=10.5, lo=9.8, c=10.2, v=1000.0):
    return {"t": t, "o": o, "h": h, "l": lo, "c": c, "v": v}


def test_period_selection():
    assert mb._period_for("1min", 1) == ("DAY", "ONE_MINUTE")
    assert mb._period_for("1min", 5) == ("WEEK", "ONE_MINUTE")
    assert mb._period_for("1min", 30) == ("MONTH", "ONE_MINUTE")
    assert mb._period_for("daily", 60) == ("YEAR", "ONE_DAY")


def test_validate_drops_bad_candles_and_counts():
    rows = [
        _bar("2026-09-04T10:00:00"),
        {"t": "x", "o": 1, "h": 0.5, "l": 2, "c": 1},   # h < l
        {"t": "x", "o": -1, "h": 2, "l": 1, "c": 1},    # negative
        {"t": "x", "o": 1, "h": 2, "l": 1},             # missing close
        "not-a-dict",
        _bar("2026-09-04T10:01:00", v=0),               # zero volume OK
    ]
    out = mb._validate(rows)
    assert len(out) == 2
    assert mb.quarantine_counts()["total"] == 4


def test_slice_sessions_keeps_last_n_days():
    rows = [_bar(f"2026-09-0{d}T10:{m:02d}:00") for d in (2, 3, 4) for m in (0, 1)]
    out = mb._slice_sessions(rows, 2)
    days = {r["t"][:10] for r in out}
    assert days == {"2026-09-03", "2026-09-04"}


def test_adv_21d_mean_and_min_sessions():
    bars = [_bar(f"2026-08-{d:02d}T00:00:00", v=1000.0 * d) for d in range(1, 22)]
    assert mb._adv_from_daily(bars) == pytest.approx(sum(1000.0 * d for d in range(1, 22)) / 21)
    assert mb._adv_from_daily(bars[:5]) is None
    assert mb._adv_from_daily([]) is None


@pytest.mark.asyncio
async def test_cache_hit_costs_zero_tokens(monkeypatch):
    calls = {"up": 0, "acq": 0}

    async def fake_upstream(ticker, period, aggregation, sessions='regular'):
        calls["up"] += 1
        return [_bar("2026-09-04T10:00:00")]

    class Budget:
        async def acquire(self, host="public"):
            calls["acq"] += 1

        def release(self):
            pass

    monkeypatch.setattr(mb, "_upstream", fake_upstream)
    monkeypatch.setattr(mb, "_budget", Budget())
    a = await mb.get_daily_bars("SPY", days=5)
    b = await mb.get_daily_bars("SPY", days=5)
    assert a == b and len(a) == 1
    assert calls == {"up": 1, "acq": 1}


@pytest.mark.asyncio
async def test_stale_serve_on_upstream_failure(monkeypatch):
    async def ok_upstream(ticker, period, aggregation, sessions='regular'):
        return [_bar("2026-09-04T10:00:00")]

    async def bad_upstream(ticker, period, aggregation, sessions='regular'):
        raise RuntimeError("vendor down")

    class Budget:
        async def acquire(self, host="public"):
            pass

        def release(self):
            pass

    monkeypatch.setattr(mb, "_budget", Budget())
    monkeypatch.setattr(mb, "_upstream", ok_upstream)
    first = await mb.get_daily_bars("SPY", days=5)
    # expire beyond the daily TTL, then fail upstream -> stale served, error recorded
    for key in list(mb._CACHE):
        ts, payload = mb._CACHE[key]
        mb._CACHE[key] = (ts - (mb._DAILY_TTL + 10), payload)
    monkeypatch.setattr(mb, "_upstream", bad_upstream)
    second = await mb.get_daily_bars("SPY", days=5)
    assert second == first
    assert mb.last_error()["reason"] == "upstream-failure"


@pytest.mark.asyncio
async def test_budget_exhausted_cold_returns_none(monkeypatch):
    from services.public_budget import BudgetExhausted

    class DeadBudget:
        async def acquire(self, host="public"):
            raise BudgetExhausted(retry_after=30)

        def release(self):
            pass

    async def boom(ticker, period, aggregation, sessions='regular'):  # pragma: no cover
        raise AssertionError("must not be called")

    monkeypatch.setattr(mb, "_budget", DeadBudget())
    monkeypatch.setattr(mb, "_upstream", boom)
    assert await mb.get_daily_bars("SPY", days=5) is None
    assert mb.last_error()["reason"] == "budget-exhausted"


@pytest.mark.asyncio
async def test_adv_uses_daily_path(monkeypatch):
    async def fake_daily(ticker, days=60):
        return [_bar(f"2026-08-{d:02d}T00:00:00", v=2000.0) for d in range(1, 25)]

    monkeypatch.setattr(mb, "get_daily_bars", fake_daily)
    assert await mb.get_adv_21d("SPY") == pytest.approx(2000.0)
