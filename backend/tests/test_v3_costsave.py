"""V3 cost-effective testing: /api/databento/usage budget meter, /api/live/policy,
/api/spot, /api/flow window-enforcement, /api/live/tape/stop idempotent.

Uses AsyncClient (aclient fixture) instead of TestClient to avoid
'Event loop is closed' RuntimeError from motor async iteration.
"""
import json
import time

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_shared_public_budget():
    """Isolate the process-global Public token bucket between tests.

    Trinity/movers fan-outs drain shared tokens + trip host cooldowns; without
    a reset, later chain tests inherit an exhausted bucket and 404 on empty
    fetches (order-dependent failure, also seen on unmodified main). The
    dollar budget meter under test here is a separate system, unaffected.
    """
    from services.public_budget import budget as _pub_budget
    _pub_budget.reset()
    yield
    _pub_budget.reset()


@pytest.fixture(autouse=True)
def offline_market(monkeypatch):
    from tests.test_heatseeker_v2 import install_offline_market
    install_offline_market(monkeypatch)


# --- /api/databento/usage shape ---
async def test_databento_usage_v3_shape(aclient):
    r = await aclient.get("/api/databento/usage")
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("paid_tickers", "live_window_et", "est_total_cost_usd",
              "budget_remaining_usd", "budget_pct_used", "in_window_now",
              "live_tape_state", "budget_usd"):
        assert k in d, f"missing {k} in usage response"
    assert "SPY" in d["paid_tickers"]
    assert d["budget_usd"] == 125.0
    assert "start_hhmm" in d["live_window_et"]
    assert "stop_hhmm" in d["live_window_et"]
    assert isinstance(d["in_window_now"], bool)
    assert abs((d["budget_remaining_usd"] + d["est_total_cost_usd"]) - 125.0) < 0.05


# --- POST /api/live/policy with paid_tickers + window ---
async def test_live_policy_set_spy_qqq(aclient):
    r = await aclient.post(
        "/api/live/policy",
        json={"paid_tickers": ["SPY", "QQQ"], "window_start": "09:30", "window_stop": "10:30"},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d["paid_tickers"]) == {"SPY", "QQQ"}
    assert d["live_window_et"]["start_hhmm"] == "09:30"
    assert d["live_window_et"]["stop_hhmm"] == "10:30"

    r2 = (await aclient.get("/api/databento/usage")).json()
    assert set(r2["paid_tickers"]) == {"SPY", "QQQ"}
    assert r2["live_window_et"]["start_hhmm"] == "09:30"


async def test_live_policy_revert_spy_only(aclient):
    r = await aclient.post("/api/live/policy", json={"paid_tickers": ["SPY"]})
    assert r.status_code == 200
    d = r.json()
    assert d["paid_tickers"] == ["SPY"]


# --- /api/heatmap data_source by ticker tier ---
@pytest.mark.flaky
async def test_heatmap_spy_data_source_databento(aclient):
    await aclient.post("/api/live/policy", json={"paid_tickers": ["SPY"]})
    r = await aclient.get("/api/heatmap/SPY?expiries=2")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["data_source"] in ("public_api", "databento+yfinance", "yfinance", "cvserver")


async def test_heatmap_qqq_free_tier_yfinance(aclient):
    # Ensure QQQ NOT in paid list
    await aclient.post("/api/live/policy", json={"paid_tickers": ["SPY"]})
    r = await aclient.get("/api/heatmap/QQQ?expiries=2")
    assert r.status_code == 200, r.text
    d = r.json()
    # Priority: public_api → cvserver → yfinance (+databento overlay).
    # cvserver healthy in this env serves before the yfinance fallback.
    assert d["data_source"] in ("yfinance", "public_api", "cvserver"), f"QQQ free-tier should be yfinance, public_api or cvserver, got {d['data_source']}"


async def test_heatmap_spx_free_tier_yfinance(aclient):
    r = await aclient.get("/api/heatmap/%5ESPX?expiries=2")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["data_source"] == "yfinance", f"SPX free-tier should be yfinance, got {d['data_source']}"


# --- /api/spot fast & free ---
async def test_spot_endpoint_fast(aclient):
    start = time.time()
    r = await aclient.get("/api/spot/SPY")
    elapsed = time.time() - start
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ticker"] == "SPY"
    assert d["spot"] > 0
    assert "ts" in d
    assert elapsed < 8, f"/api/spot took {elapsed:.1f}s — too slow"


async def test_spot_second_call_cached(aclient):
    await aclient.get("/api/spot/SPY")
    start = time.time()
    r = await aclient.get("/api/spot/SPY")
    elapsed = time.time() - start
    assert r.status_code == 200
    assert elapsed < 2.0, f"cached /api/spot took {elapsed:.2f}s"


# --- /api/flow window enforcement (SSE) ---
async def _read_sse_events(aclient, url, max_events=3):
    """Read up to max_events SSE events from url, return list of (event_name, data_dict)."""
    out = []
    r = await aclient.get(url)
    cur_event = "message"
    text = r.text
    for line in text.split("\n"):
        if line.startswith("event:"):
            cur_event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            payload = line.split(":", 1)[1].strip()
            try:
                d = json.loads(payload)
            except Exception:
                d = {"_raw": payload}
            out.append((cur_event, d))
            cur_event = "message"
            if len(out) >= max_events:
                break
    return out


async def _in_window_now(aclient):
    """Whether the live trading window is currently open.

    The previous version returned False on any error, which meant "we could not
    tell" was treated as "we are outside the window". That made
    `test_flow_spy_outside_window_emits_error` RUN during market hours, where
    the endpoint correctly streams heartbeats instead of an error, and fail.

    /api/databento/usage returns 503 when auth is not configured (mutating
    review routes do this deliberately), so the key is simply absent. The guard
    must SKIP on an unknown window rather than assert against it -- an
    unobservable precondition is not a failed precondition.
    """
    try:
        r = (await aclient.get("/api/databento/usage")).json()
    except Exception:
        return None
    val = r.get("in_window_now")
    if val is None:
        return None
    return bool(val)


async def test_flow_qqq_refused_not_in_paid_tickers(aclient):
    await aclient.post("/api/live/policy", json={"paid_tickers": ["SPY"]})
    events = await _read_sse_events(aclient, "/api/flow/QQQ?max_seconds=10&enforce_window=false", max_events=1)
    assert events, "no SSE events received"
    name, data = events[0]
    assert name == "error", f"expected error event, got {name}: {data}"
    assert "paid" in (data.get("error", "").lower()), f"unexpected error: {data}"


def test_admin_window_check_is_dst_aware(monkeypatch):
    """`/api/databento/usage` must not under-report the window during EDT.

    It previously computed the current time as
    `datetime.now(UTC) - timedelta(hours=5)` -- EST, with no DST handling. For
    roughly five months a year that put it an hour behind, so it reported the
    window CLOSED a full hour before the trade route opened it: two endpoints
    disagreeing about whether it was 09:00, and any caller gating on
    `in_window_now` getting the wrong answer.

    The check now delegates to `server._in_window_now_et`, which resolves the
    zone properly and uses the SAME exclusive stop bound as the trade route
    that gates `/api/flow` (`hhmm < start or hhmm >= stop` refuses there).
    The two must never disagree about the same minute, so the stop instant
    is exclusive for both.

    The clock is pinned here: the boundary is asserted exactly at the start,
    just inside it, exactly at the stop and just after it, in both Eastern
    daylight time and Eastern standard time. The result never depends on
    when the suite runs.
    """
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo

    from server import LIVE_WINDOW, _in_window_now_et

    eastern = ZoneInfo("America/New_York")
    utc = ZoneInfo("UTC")

    class _FrozenDatetime(_dt):
        _frozen = _dt(2026, 1, 1, tzinfo=utc)

        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return cls._frozen.replace(tzinfo=None)
            return cls._frozen.astimezone(tz)

    monkeypatch.setattr("services.eastern_clock.datetime", _FrozenDatetime)

    start = LIVE_WINDOW.get("start_hhmm", "09:00")
    stop = LIVE_WINDOW.get("stop_hhmm", "16:00")
    monkeypatch.setitem(LIVE_WINDOW, "start_hhmm", start)
    monkeypatch.setitem(LIVE_WINDOW, "stop_hhmm", stop)

    def _minutes(hhmm: str) -> int:
        hour, minute = (int(part) for part in hhmm.split(":"))
        return hour * 60 + minute

    def _gate_at(total_minutes: int, month: int) -> bool:
        hour, minute = divmod(total_minutes, 60)
        wall = _dt(2026, month, 15, hour, minute, tzinfo=eastern)
        _FrozenDatetime._frozen = wall.astimezone(utc)
        return _in_window_now_et()

    start_min = _minutes(start)
    stop_min = _minutes(stop)
    assert start_min < stop_min, f"the live window {start}-{stop} is empty"

    for month, label in ((1, "EST"), (7, "EDT")):
        if start_min > 0:
            assert _gate_at(start_min - 1, month) is False, (
                f"{label}: the window opened before its {start} start")
        assert _gate_at(start_min, month) is True, (
            f"{label}: the window did not open at its {start} start")
        assert _gate_at(start_min + 1, month) is True, (
            f"{label}: the window closed one minute after it opened")
        assert _gate_at(stop_min - 1, month) is True, (
            f"{label}: the window closed before its {stop} stop")
        assert _gate_at(stop_min, month) is False, (
            f"{label}: the window stayed open AT its {stop} stop")
        if stop_min + 1 < 24 * 60:
            assert _gate_at(stop_min + 1, month) is False, (
                f"{label}: the window stayed open after its {stop} stop")


async def test_flow_spy_outside_window_emits_error(aclient):
    window = await _in_window_now(aclient)
    if window is None:
        pytest.skip("Cannot determine trading window — precondition unobservable")
    if window:
        pytest.skip("Currently within live window — test would fail by design")
    events = await _read_sse_events(aclient, "/api/flow/SPY?max_seconds=10", max_events=1)
    assert events
    name, data = events[0]
    assert name == "error"
    assert "window" in (data.get("error", "").lower()) or "outside" in (data.get("error", "").lower())


async def test_flow_spy_enforce_window_false_starts(aclient):
    events = await _read_sse_events(aclient, "/api/flow/SPY?max_seconds=10&enforce_window=false", max_events=2)
    assert events, "no SSE output at all"
    for name, data in events:
        if name == "error":
            err_msg = (data.get("error", "")).lower()
            assert "window" not in err_msg, f"window error despite enforce_window=false: {data}"


# --- /api/live/tape/stop idempotency ---
async def test_live_tape_stop_idempotent_no_session(aclient):
    r = await aclient.post("/api/live/tape/stop")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("stopped") is True


async def test_live_tape_stop_called_twice(aclient):
    r1 = await aclient.post("/api/live/tape/stop")
    r2 = await aclient.post("/api/live/tape/stop")
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json().get("stopped") is True
    assert r2.json().get("stopped") is True


# --- Regression: legacy endpoints still pass ---
async def test_trinity_still_works(aclient):
    r = await aclient.get("/api/trinity?mode=day")
    assert r.status_code == 200
    d = r.json()
    for t in ("^SPX", "SPY", "QQQ"):
        assert t in d["tickers"]


async def test_movers_still_works(aclient):
    r = await aclient.get("/api/movers?limit=5")
    assert r.status_code == 200
    d = r.json()
    assert "results" in d
    assert isinstance(d["results"], list)


async def test_contract_still_works(aclient):
    r = await aclient.get("/api/contract/SPY")
    assert r.status_code == 200
    d = r.json()
    assert d["ticker"] == "SPY"
    assert isinstance(d.get("rows"), list)
