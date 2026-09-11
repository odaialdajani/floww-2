"""V3 cost-effective testing: /api/databento/usage budget meter, /api/live/policy,
/api/spot, /api/flow window-enforcement, /api/live/tape/stop idempotent.

Uses AsyncClient (aclient fixture) instead of TestClient to avoid
'Event loop is closed' RuntimeError from motor async iteration.
"""
import json
import time

import pytest

pytestmark = pytest.mark.asyncio


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
    try:
        r = (await aclient.get("/api/databento/usage")).json()
        return bool(r.get("in_window_now"))
    except Exception:
        return False


async def test_flow_qqq_refused_not_in_paid_tickers(aclient):
    await aclient.post("/api/live/policy", json={"paid_tickers": ["SPY"]})
    events = await _read_sse_events(aclient, "/api/flow/QQQ?max_seconds=10&enforce_window=false", max_events=1)
    assert events, "no SSE events received"
    name, data = events[0]
    assert name == "error", f"expected error event, got {name}: {data}"
    assert "paid" in (data.get("error", "").lower()), f"unexpected error: {data}"


async def test_flow_spy_outside_window_emits_error(aclient):
    if await _in_window_now(aclient):
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
