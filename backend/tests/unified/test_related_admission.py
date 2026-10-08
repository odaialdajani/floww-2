"""U06: admit latest Related behavior — exact pairs, clocks, registry, warming.

Isolated counterexamples with injected facts and a tmp SQLite store;
no provider/network calls. Sessions come from the same calendar module the
service uses, so clocks are exact, not approximated.
"""
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import routes.related_tickers as rt
from services.agent.access.horizon import _calendar
from services.related_correlations import MIN_PAIRED_RETURNS, compare_series
from services.related_price_series import RelatedSeriesStore


def _sessions(n=25, end="2026-09-04"):
    return [s.date().isoformat() for s in _calendar().sessions_window(end, -n)]


def _close(day):
    return _calendar().session_close(day).to_pydatetime().astimezone(UTC).isoformat()


DAYS = _sessions()
LAST = DAYS[-1]
EXPECTED = _close(LAST)
NOW = datetime.fromisoformat(EXPECTED) + timedelta(minutes=30)


def make_series(ticker, closes, *, event_day=LAST):
    event = _close(event_day)
    received = (datetime.fromisoformat(event) + timedelta(minutes=30)).isoformat()
    return {
        "ticker": ticker,
        "source": "public_api",
        "price_basis": "provider_reported",
        "bars": [{"date": d, "close": c} for d, c in closes.items()],
        "event_time": event,
        "received_at": received,
    }


def full_closes(seed=100.0, drift=1.001):
    return {d: round(seed * (drift ** i), 4) for i, d in enumerate(DAYS)}


def compare(left, right, window=30):
    return compare_series(left, right, window=window, now=NOW, _window=(DAYS, EXPECTED))


def test_exact_adjacent_pairs_with_no_filling():
    right_closes = full_closes(seed=50.0, drift=0.999)
    del right_closes[DAYS[12]]
    result = compare(make_series("AAA", full_closes()), make_series("BBB", right_closes))
    assert result["reason"] in (None, "partial_history")
    assert result["paired_returns"] == len(DAYS) - 1 - 2  # both pairs touching the gap dropped
    assert result["coefficient"] is not None
    assert result["partial"] is True
    assert result["start_date"] == DAYS[0]
    assert result["end_date"] == LAST


def test_below_minimum_pairs_refused():
    right_closes = {d: c for d, c in full_closes(seed=50.0, drift=0.999).items() if d >= DAYS[-20]}
    result = compare(make_series("AAA", full_closes()), make_series("BBB", right_closes))
    assert result["paired_returns"] == MIN_PAIRED_RETURNS - 1
    assert result["coefficient"] is None
    assert result["reason"] == "insufficient_paired_returns"
    assert result["status"] == "unavailable"


def test_zero_variance_refused_not_invented():
    flat = {d: 10.0 for d in DAYS}
    result = compare(make_series("AAA", full_closes()), make_series("BBB", flat))
    assert result["coefficient"] is None
    assert result["reason"] == "zero_variance"


def test_series_clock_mismatch_refused():
    right = make_series("BBB", full_closes(seed=50.0, drift=0.999))
    right["event_time"] = _close(DAYS[-2])  # claims an older close than its last bar
    result = compare(make_series("AAA", full_closes()), right)
    assert result["coefficient"] is None
    assert result["reason"] == "invalid_series_clock"


def test_stale_and_partial_stay_distinct():
    right_closes = {d: c for d, c in full_closes(seed=50.0, drift=0.999).items() if d != LAST}
    right = make_series("BBB", right_closes, event_day=DAYS[-2])
    right["cache_stale"] = True
    result = compare(make_series("AAA", full_closes()), right)
    assert result["coefficient"] is not None
    assert result["partial"] is True
    assert result["stale"] is True
    assert result["status"] == "stale"
    assert result["reason"] == "dated_cache"


def test_self_comparison_excluded():
    s = make_series("AAA", full_closes())
    result = compare(s, s)
    assert result["coefficient"] is None
    assert result["reason"] == "self_comparison_excluded"


def _request(headers=None, client=("127.0.0.1", 1234), method="POST"):
    raw = [(b"host", b"localhost")] + [
        (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
    ]
    return Request({"type": "http", "method": method, "path": "/api/related/AAA/warm",
                    "headers": raw, "client": client})


@pytest.mark.asyncio
async def test_warm_refuses_remote_and_foreign_origin_before_any_provider_work(monkeypatch):
    monkeypatch.setenv("FLOWW_AGENT_DEPLOYMENT", "local")

    async def forbidden(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("provider work started for an untrusted client")

    monkeypatch.setattr(rt, "warm_snapshot", forbidden)
    body = rt.WarmRequest()
    with pytest.raises(HTTPException) as exc:
        await rt.related_ticker_warm("AAA", body, _request(client=("203.0.113.9", 443)))
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc2:
        await rt.related_ticker_warm("AAA", body, _request(headers={"origin": "https://evil.example"}))
    assert exc2.value.status_code == 403


def test_warm_requires_explicit_local_mode(monkeypatch):
    from starlette.requests import Request as _Req

    monkeypatch.delenv("FLOWW_AGENT_DEPLOYMENT", raising=False)
    from services.agent.local_access import require_local
    with pytest.raises(HTTPException) as exc:
        require_local(_Req({"type": "http", "method": "POST", "path": "/x",
                            "headers": [(b"host", b"localhost")], "client": ("127.0.0.1", 1)}))
    assert exc.value.status_code == 503


def _registry(tmp_path):
    reg = {
        "version": 1,
        "products": [
            {"symbol": "AAA", "underlying": "IDX", "product_type": "etf",
             "source_urls": ["https://issuer.example/aaa"], "verified_at": "2026-08-01"},
            {"symbol": "BBB", "underlying": "IDX", "product_type": "etf",
             "source_urls": ["https://issuer.example/bbb"], "verified_at": "2026-08-01"},
        ],
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(reg))
    return str(path)


@pytest.mark.asyncio
async def test_warm_cancellation_makes_zero_provider_attempts(tmp_path):
    store = RelatedSeriesStore(str(tmp_path / "series.db"))
    catalog = {"symbols": ["AAA", "BBB"], "available": True, "asof": EXPECTED, "stale": False}

    async def disconnected():
        return True

    result = await rt.warm_snapshot(
        "AAA", now=NOW, store=store, catalog=catalog,
        registry_path=_registry(tmp_path), disconnected=disconnected,
    )
    batch = result["batch"]
    assert batch["attempted"] == 0
    assert batch["reserved_calls"] == 0
    assert batch["fetched"] == 0
    assert result["coverage"]["eligible"] == 1


@pytest.mark.asyncio
async def test_batch_reservation_never_exceeds_eight_calls(tmp_path, monkeypatch):
    store = RelatedSeriesStore(str(tmp_path / "series.db"))
    catalog = {"symbols": ["AAA", "BBB"], "available": True, "asof": EXPECTED, "stale": False}
    calls = []

    async def fake_warm(symbol, store, *, now=None, max_reserved_calls=8):
        calls.append((symbol, max_reserved_calls))
        assert 0 < max_reserved_calls <= 8
        return {"symbol": symbol, "status": "fetched", "reason": None, "reserved_calls": 8}

    monkeypatch.setattr(rt, "warm_daily_series", fake_warm)

    async def connected():
        return False

    result = await rt.warm_snapshot(
        "AAA", now=NOW, store=store, catalog=catalog,
        registry_path=_registry(tmp_path), disconnected=connected,
    )
    assert result["batch"]["reserved_calls"] <= 8
    assert len(calls) == 1  # second symbol does not fit the remaining budget


def test_bounded_paging_and_directory_refusal(tmp_path):
    store = RelatedSeriesStore(str(tmp_path / "series.db"))
    registry = _registry(tmp_path)
    catalog = {"symbols": ["AAA", "BBB"], "available": True, "asof": EXPECTED, "stale": False}
    page = rt.build_snapshot("AAA", store=store, catalog=catalog, registry_path=registry,
                             now=NOW, limit=1, offset=0)
    assert page["comparisons_limit"] == 1
    assert page["has_more"] is False  # only one related name exists
    assert page["coverage"]["eligible"] == 1
    refused = rt.build_snapshot("ZZZ", store=store, catalog=catalog, registry_path=registry, now=NOW)
    assert refused["status"] == "unavailable"
    assert refused["reason"] == "selected_not_in_cached_provider_directory"
    no_reg = rt.build_snapshot("AAA", store=store, catalog=catalog,
                               registry_path=str(tmp_path / "missing.json"), now=NOW)
    assert no_reg["registry_coverage"]["available"] is False
