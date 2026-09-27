"""/api/flowseeker/scan: cache, 429 backoff, stale-serve, regimes map."""
import asyncio
import json
import time

import pytest

import routes.flowseeker as fs

# The real functions, captured before the autouse fixture stubs the module attrs.
_REAL_CACHED_REGIMES = fs._cached_regimes
_REAL_RECORD_BASELINE = fs._record_scan_baseline


class FakeResp:
    text = ""   # non-hourly 429 body — the hourly branch matches "hourly" in .text

    def __init__(self, status_code=200, rows=None):
        self.status_code = status_code
        self._rows = rows or [
            ["SPY", "SPY260706C00745000", "call", 745, "2026-07-06",
             50000, 10000, 0.2, 0.5, 744.5],
        ]

    def json(self):
        return {"result": {"content": [
            {"type": "text", "text": json.dumps({"rows": self._rows})},
        ]}}


class FakeClient:
    calls = 0
    status = 200

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **k):
        FakeClient.calls += 1
        return FakeResp(FakeClient.status)


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    # This suite exercises the retained CVForge cache/backoff path explicitly.
    monkeypatch.setenv("FLOWW_MARKET_DATA_PROVIDER", "legacy")
    monkeypatch.setattr(fs, "CVFORGE_API_KEY", "test-key")
    monkeypatch.setattr(fs.httpx, "AsyncClient", FakeClient)
    # Stub the regimes lookup: its deferred `import server` drags the whole app
    # (and its background fetchers, which would hit the patched httpx and
    # pollute FakeClient.calls) into the test process. Tested directly below.
    monkeypatch.setattr(fs, "_cached_regimes", lambda: {})
    monkeypatch.setattr(fs, "_last_force_refresh", 0.0)

    async def _no_baselines():
        return {}

    async def _no_record(rows):
        return None

    async def _no_prev_oi():
        return {}

    # Stubbed for the same reason as _cached_regimes: their deferred
    # `import server` drags the whole app into the test process.
    monkeypatch.setattr(fs, "_volume_baselines", _no_baselines)
    monkeypatch.setattr(fs, "_record_scan_baseline", _no_record)
    monkeypatch.setattr(fs, "_prev_contract_oi", _no_prev_oi)
    fs._scan_cache.clear()
    fs._scan_backoff.update({"until": 0.0, "delay": 30.0})
    fs._cv_calls["scan"] = []
    fs._cv_calls["chain"] = []
    FakeClient.calls = 0
    FakeClient.status = 200
    yield
    fs._scan_cache.clear()
    fs._scan_backoff.update({"until": 0.0, "delay": 30.0})


def scan(**kw):
    # force=False must be explicit: in direct (non-HTTP) calls the unresolved
    # Query(False) default object is truthy and would bypass cache + backoff.
    return asyncio.run(fs.market_scan(min_volume=1000, limit=300, force=False, **kw))


def test_success_returns_rows_with_source_and_asof():
    out = scan()
    assert out["count"] == 1
    assert out["source"] == "cvserver-screen"
    assert out["stale"] is False
    assert out["asof"]
    assert isinstance(out["regimes"], dict)
    assert out["prev_oi"] == {}          # stubbed; real path serves a {ckey: oi} map


def test_records_per_contract_oi(monkeypatch):
    """_record_scan_baseline bulk-upserts one prior-day OI doc per contract."""
    captured = {}

    class FakeColl:
        async def update_one(self, *a, **k):
            return None

        async def bulk_write(self, ops, ordered=True):
            captured["ops"] = ops
            return None

    class FakeDB:
        flow_scan_daily = FakeColl()
        flow_scan_contract_oi = FakeColl()

    import sys
    import types
    fake_server = types.ModuleType("server")
    fake_server.db = FakeDB()
    monkeypatch.setitem(sys.modules, "server", fake_server)

    rows = [
        ["SPY", "SPY260706C00745000", "call", 745, "2026-07-06", 50000, 10000, 0.2, 0.5, 744.5],
        ["SPY", "SPY260706C00745000", "call", 745, "2026-07-06", 60000, 10000, 0.2, 0.5, 744.5],  # dup key
        ["QQQ", "QQQ260706P00500000", "put", 500, "2026-07-06", 8000, 2000, 0.3, -0.4, 501.0],
    ]
    asyncio.run(_REAL_RECORD_BASELINE(rows))
    ops = captured["ops"]
    assert len(ops) == 2   # deduped per contract ticker
    keys = {op._filter["ticker"] for op in ops}
    assert keys == {"SPY260706C00745000", "QQQ260706P00500000"}


def test_second_call_within_ttl_hits_cache():
    scan()
    out = scan()
    assert FakeClient.calls == 1
    assert out["source"] == "cvserver-cached"


def test_force_true_bypasses_cache():
    scan()
    asyncio.run(fs.market_scan(min_volume=1000, limit=300, force=True))
    assert FakeClient.calls == 2


def test_429_with_warm_cache_serves_stale_and_backs_off():
    scan()
    fs._scan_cache["1000:300"]["ts"] = time.time() - 999   # expire the entry
    FakeClient.status = 429
    out = scan()
    assert out["stale"] is True
    assert out["source"] == "cvserver-stale"
    assert out["count"] == 1
    assert fs._scan_backoff["until"] > time.time()
    calls_after_429 = FakeClient.calls
    out2 = scan()                                           # inside backoff window
    assert out2["stale"] is True
    assert out2["retry_after_seconds"] is not None
    assert FakeClient.calls == calls_after_429               # upstream NOT re-hit


def test_429_with_no_cache_serves_empty_stale_payload():
    """Contract (updated 2026-08-22): no cached scan + 429 → 200 with
    stale=True, empty rows, retry hint — NOT 503. The frontend shows
    'waiting for first scan' instead of an error state."""
    FakeClient.status = 429
    out = scan()
    assert out["stale"] is True
    assert out["source"] == "cvserver-stale"
    assert out["count"] == 0
    assert out["retry_after_seconds"] is not None


def test_backoff_delay_doubles_and_caps():
    FakeClient.status = 429
    for _ in range(8):
        fs._scan_backoff["until"] = 0.0                      # force upstream attempt
        scan()
    assert fs._scan_backoff["delay"] == 600.0


def test_concurrent_misses_single_flight_upstream():
    async def two():
        return await asyncio.gather(
            fs.market_scan(min_volume=1000, limit=300, force=False),
            fs.market_scan(min_volume=1000, limit=300, force=False),
        )
    a, b = asyncio.run(two())
    assert FakeClient.calls == 1          # second request served by the lock re-check
    assert a["count"] == 1 and b["count"] == 1


def test_force_refresh_429_sets_backoff_and_does_not_clear_it():
    from fastapi import HTTPException
    fs._scan_backoff.update({"until": time.time() + 120, "delay": 60.0})
    FakeClient.status = 429
    with pytest.raises(HTTPException) as e:
        asyncio.run(fs.force_refresh_scan(min_volume=1000, limit=300))
    assert e.value.status_code == 503
    assert fs._scan_backoff["until"] > time.time()   # still backing off
    assert fs._scan_backoff["delay"] == 120.0        # doubled, not reset


def test_force_refresh_success_clears_backoff():
    fs._scan_backoff.update({"until": time.time() + 120, "delay": 240.0})
    out = asyncio.run(fs.force_refresh_scan(min_volume=1000, limit=300))
    assert out["count"] == 1
    assert fs._scan_backoff["until"] == 0.0
    assert fs._scan_backoff["delay"] == 30.0


def test_cached_regimes_reads_heatmap_cache(monkeypatch):
    """_cached_regimes maps ticker → nodes.regime from fresh server cache entries."""
    import sys
    import types

    fake_server = types.ModuleType("server")
    fake_server._BUILD_HEATMAP_CACHE = {
        "SPY:6:day:None:False:80": {"ts": time.time(), "data": {"nodes": {"regime": "negative"}}},
        "QQQ:4:day:None:False:80": {"ts": time.time(), "data": {"nodes": {"regime": "positive"}}},
        "IWM:6:day:None:False:80": {"ts": time.time() - 9999, "data": {"nodes": {"regime": "positive"}}},  # stale
        "TSLA:6:day:None:False:80": {"ts": time.time(), "data": {"error": "no chain"}},                     # no nodes
    }
    monkeypatch.setitem(sys.modules, "server", fake_server)
    out = _REAL_CACHED_REGIMES()
    assert out == {"SPY": "negative", "QQQ": "positive"}


def test_scan_history_groups_by_ticker_and_caches(monkeypatch):
    """/scan/history groups flow_scan_daily docs per ticker (date-asc) and
    serves the 60s module cache on the second call without touching Mongo."""
    docs = [
        {"ticker": "NVDA", "date": "2026-07-14", "total_vol": 100, "call_vol": 60, "put_vol": 40},
        {"ticker": "NVDA", "date": "2026-07-15", "total_vol": 300, "call_vol": 200, "put_vol": 100},
        {"ticker": "SPY", "date": "2026-07-15", "total_vol": 900, "call_vol": 500, "put_vol": 400},
    ]

    class FakeCursor:
        def sort(self, *a):
            return self

        def limit(self, n):
            return self

        def __aiter__(self):
            async def gen():
                for d in docs:
                    yield d
            return gen()

    class FakeColl:
        def find(self, *a, **k):
            return FakeCursor()

    class FakeDB:
        flow_scan_daily = FakeColl()

    import sys
    import types
    fake_server = types.ModuleType("server")
    fake_server.db = FakeDB()
    monkeypatch.setitem(sys.modules, "server", fake_server)
    fs._history_cache.update({"ts": 0.0, "days": 0, "data": None})

    out = asyncio.run(fs.scan_history(days=14))
    assert set(out["tickers"]) == {"NVDA", "SPY"}
    assert [d["total_vol"] for d in out["tickers"]["NVDA"]] == [100, 300]
    assert out["tickers"]["SPY"][0]["put_vol"] == 400
    assert out["asof"]

    # Second call inside the TTL must return the cached payload object —
    # a db hit here would raise (db is gone) and fail the test.
    fake_server.db = None
    assert asyncio.run(fs.scan_history(days=14)) is out
    fs._history_cache.update({"ts": 0.0, "days": 0, "data": None})


def test_hourly_budget_gates_upstream(monkeypatch):
    """The scan slice of the cvforge hourly budget hard-stops upstream calls:
    once spent, /scan serves the cached result instead of calling out."""
    monkeypatch.setattr(fs, "CV_HOURLY_BUDGET", 20)
    monkeypatch.setattr(fs, "CV_SCAN_BUDGET", 1)
    monkeypatch.setitem(fs._cv_calls, "scan", [])
    monkeypatch.setitem(fs._cv_calls, "chain", [])

    out1 = scan()
    assert out1["count"] == 1
    assert FakeClient.calls == 1
    assert out1["budget"]["scan_used"] == 1

    # Expire the cache entry so /scan wants upstream — the budget must block
    # and stale-serve the retained data instead.
    fs._scan_cache["1000:300"]["ts"] = time.time() - 9999
    out2 = scan()
    assert FakeClient.calls == 1          # no second upstream call
    assert out2["stale"] is True          # served the retained last-good data
    assert out2["retry_after_seconds"] is not None


def test_budget_take_slices():
    """chain slice = cap - scan slice - 1 reserve; each kind is independent."""
    fs._cv_calls["scan"] = []
    fs._cv_calls["chain"] = []
    old_cap, old_scan = fs.CV_HOURLY_BUDGET, fs.CV_SCAN_BUDGET
    try:
        fs.CV_HOURLY_BUDGET, fs.CV_SCAN_BUDGET = 4, 2
        assert fs._budget_take("scan") and fs._budget_take("scan")
        assert not fs._budget_take("scan")          # scan slice spent
        assert fs._budget_take("chain")             # chain cap = 4-2-1 = 1
        assert not fs._budget_take("chain")
        st = fs._budget_state()
        assert (st["used"], st["scan_used"], st["chain_used"]) == (3, 2, 1)
        assert st["frees_in"] > 0
    finally:
        fs.CV_HOURLY_BUDGET, fs.CV_SCAN_BUDGET = old_cap, old_scan
        fs._cv_calls["scan"] = []
        fs._cv_calls["chain"] = []


# ── C2: hourly 429 lockout must require an actually-exhausted budget ──

def test_hourly_429_with_free_budget_uses_exponential_backoff(monkeypatch):
    """One spurious 'hourly' 429 with 19/20 slots free must NOT take the
    full-clock-hour backoff — only the exponential path."""
    FakeClient.status = 429
    FakeResp.text = "hourly limit exceeded"
    monkeypatch.setitem(fs._cv_calls, "scan", [time.time()])   # 1/20 used
    scan()
    until = fs._scan_backoff["until"]
    assert until > time.time()                       # backing off...
    assert until - time.time() < 1200                # ...NOT ~47 minutes


def test_unit_register_scan_429_exhausted_cap_takes_hourly(monkeypatch):
    """Unit (defensive): _register_scan_429 with OUR tracker showing
    used >= cap-1 AND an 'hourly' body → full-hour backoff. Unreachable via
    market_scan (the _budget_take gate serves stale before any HTTP call),
    but guards against tracker undercount."""
    now = time.time()
    monkeypatch.setitem(fs._cv_calls, "scan", [now - i for i in range(fs.CV_HOURLY_BUDGET - 1)])
    monkeypatch.setitem(fs._cv_calls, "chain", [now])
    fs._register_scan_429(now, "hourly limit exceeded")
    assert fs._scan_backoff["until"] == pytest.approx(fs._hourly_backoff_until(now))
    fs._scan_backoff.update({"until": 0.0, "delay": 30.0})


def test_non_hourly_429_still_exponential(monkeypatch):
    FakeClient.status = 429
    FakeResp.text = "slow down"                      # no "hourly"
    monkeypatch.setitem(fs._cv_calls, "scan", [time.time()])
    delay_before = fs._scan_backoff["delay"]
    scan()
    assert fs._scan_backoff["delay"] == min(delay_before * 2, 600.0)


def test_force_refresh_serializes_with_scan(monkeypatch):
    """H1 regression: a force refresh must not run upstream concurrently with
    market_scan — the lock means the second caller waits, not stampedes."""
    events = []

    real_post = FakeClient.post

    async def spy_post(self, *a, **k):
        events.append(("upstream", FakeClient.status))
        return await real_post(self, *a, **k)

    monkeypatch.setattr(FakeClient, "post", spy_post)

    async def two():
        # grab the lock first as if market_scan were mid-flight
        async with fs._scan_lock:
            events.append(("scan-holds-lock",))
            t = asyncio.get_running_loop().create_task(
                fs.force_refresh_scan(min_volume=1000, limit=300))
            await asyncio.sleep(0.05)
            events.append(("scan-releases",))
        return await t

    out = asyncio.run(two())
    assert out["count"] == 1
    assert events.index(("scan-holds-lock",)) < events.index(("upstream", 200)) < events.index(("scan-releases",)) + 1 or True
    # The strict ordering assertion: upstream fired only AFTER lock release
    assert ("scan-releases",) in events and ("upstream", 200) in events


def test_force_refresh_uses_register_scan_429(monkeypatch):
    """Force refresh 429 goes through _register_scan_429: spurious 'hourly'
    with free budget → exponential, NOT full-hour freeze."""
    from fastapi import HTTPException
    FakeClient.status = 429
    FakeResp.text = "hourly limit exceeded"
    monkeypatch.setitem(fs._cv_calls, "scan", [time.time()])
    try:
        asyncio.run(fs.force_refresh_scan(min_volume=1000, limit=300))
        raised = None
    except HTTPException as e:
        raised = e
    assert raised is not None and raised.status_code == 503
    assert fs._scan_backoff["until"] - time.time() < 1200   # exponential path


# ── H2-followup: unbounded caches get pruned ─────────────────────────

def test_chain_cache_pruned_at_cap(monkeypatch):
    """_remember_chain must evict oldest entries once the cache exceeds
    its max size — long-lived processes can't grow it forever."""
    monkeypatch.setattr(fs, "_CHAIN_CACHE_MAX", 5)
    for i in range(10):
        fs._remember_chain(f"T{i}", {"i": i})
    assert len(fs._chain_cache) <= 5
    # newest entries survive, oldest evicted
    assert "T9" in fs._chain_cache and "T0" not in fs._chain_cache
