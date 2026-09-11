"""Sparse-chain strategy (2026-09-08 owner directive: Public primary unlimited,
cvserver 20/hr scarce failover) + H1 compliance (real vendor rows only).

Proves on main-RED / branch-GREEN:
- <40-strike non-index chains re-fetch Public with 8 expiries (zero cvserver cost)
- still-<30-strike chains enrich from ONE cvserver full-chain call when richer
- cvserver hard-caps at HOURLY_CAP (default 20/hr) serving stale instead
- result strikes are always a subset of mocked vendor rows (no fabrication)
"""
# One shared loop for the whole module: server.py binds a global Motor client
# on first await, and per-test asyncio.run() loops orphan it ("attached to a
# different loop"). All impl tests run on _LOOP; motor stays bound.
import asyncio as _asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

import server
import services.cvserver_client as cvmod

_LOOP = _asyncio.new_event_loop()


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    server._BUILD_HEATMAP_CACHE.clear()
    cache, fails, rl, req_log = (
        dict(cvmod._cache), dict(cvmod._fails), cvmod._rl_until, list(cvmod._req_log))
    yield
    server._BUILD_HEATMAP_CACHE.clear()
    cvmod._cache.clear()
    cvmod._cache.update(cache)
    cvmod._fails.clear()
    cvmod._fails.update(fails)
    cvmod._rl_until = rl
    cvmod._req_log.clear()
    cvmod._req_log.extend(req_log)


def _contract(strike, exp="2026-09-18", typ="call"):
    return {"strike": float(strike), "expiry": exp, "T": 30 / 365.0,
            "type": typ, "oi": 100.0, "iv": 0.25, "volume": 10.0,
            "gamma": 0.05, "delta": 0.5, "theta": -0.02, "vega": 0.1,
            "bid": 1.0, "ask": 1.1, "mid": 1.05, "last": 1.05}


def _payload(ticker, spot, strikes, expiries=("2026-09-18",), source="public_api"):
    contracts = [c for s in strikes for c in
                 (_contract(s, expiries[0], "call"), _contract(s, expiries[0], "put"))]
    return {"ticker": ticker, "spot": spot, "expiries": list(expiries),
            "contracts": contracts, "data_source": source}


def _run_impl(ticker, fetch_mock):
    async def _no_velocity(ticker, current_nodes):
        # Infra seam: real impl reads Mongo snapshots (loop-bound client);
        # unit tests pin the empty-history shape it returns with no history.
        return {"velocity_score": 0, "rolling_floor": "stable",
                "rolling_ceiling": "stable", "history": []}

    with patch.object(server, "fetch_spot_and_chains_merged", new=fetch_mock), \
            patch.object(server, "save_snapshot", new=AsyncMock(return_value=None)), \
            patch.object(server, "velocity_and_rolling", new=_no_velocity):
        return _LOOP.run_until_complete(
            server._build_heatmap_impl(ticker, max_expiries=4, with_taps=False))


def test_sparse_chain_deepens_with_public_8_expiries():
    sparse = _payload("KYTX_D", 8.32, [5.0, 7.5, 10.0, 12.5])
    rich = _payload("KYTX_D", 8.32, [5.0 + 0.5 * i for i in range(60)])
    calls = []

    async def fake_fetch(ticker, max_expiries=4):
        calls.append(max_expiries)
        return rich if max_expiries >= 8 else sparse

    out = _run_impl("KYTX_D", fake_fetch)
    assert calls[0] == 4 and 8 in calls, "sparse chain must re-fetch Public with 8 expiries"
    out_sparse_strikes = _run_impl("KYTX_D0", AsyncMock(return_value=sparse))
    assert len(out["strikes"]) > len(out_sparse_strikes["strikes"])


def test_rich_chain_skips_deepen():
    rich = _payload("KYTX_R", 8.32, [5.0 + 0.5 * i for i in range(100)])
    calls = []

    async def fake_fetch(ticker, max_expiries=4):
        calls.append(max_expiries)
        return rich

    _run_impl("KYTX_R", fake_fetch)
    assert calls == [4], "rich chain must not re-fetch"


def test_index_tickers_skip_deepen():
    sparse = _payload("^SPX", 500.0, [490.0, 500.0, 510.0])
    calls = []

    async def fake_fetch(ticker, max_expiries=4):
        calls.append(max_expiries)
        return sparse

    _run_impl("^SPX", fake_fetch)
    assert calls == [4], "index tickers are excluded from deepen"


def test_cvserver_enriches_when_still_sparse(monkeypatch):
    sparse = _payload("KYTX_E", 8.32, [5.0, 7.5, 10.0, 12.5])
    cvrich = _payload("KYTX_E", 8.32, [5.0 + 0.5 * i for i in range(50)],
                      source="cvserver")
    monkeypatch.setattr(cvmod, "CVSERVER_API_KEY", "test-key")
    cv_calls = []

    async def fake_cv(symbol, max_expiries=4):
        cv_calls.append(symbol)
        return cvrich

    monkeypatch.setattr(cvmod, "fetch_chain_from_cvserver", fake_cv)
    out = _run_impl("KYTX_E", AsyncMock(return_value=sparse))
    assert cv_calls == ["KYTX_E"], "exactly one cvserver call for enrichment"
    assert out["data_source"] == "cvserver"
    assert len(out["strikes"]) > 3


def test_public_kept_when_cvserver_poorer(monkeypatch):
    sparse = _payload("KYTX_P", 8.32, [5.0, 7.5, 10.0, 12.5])
    poorer = _payload("KYTX_P", 8.32, [7.5, 10.0], source="cvserver")
    monkeypatch.setattr(cvmod, "CVSERVER_API_KEY", "test-key")
    monkeypatch.setattr(cvmod, "fetch_chain_from_cvserver",
                        AsyncMock(return_value=poorer))
    out = _run_impl("KYTX_P", AsyncMock(return_value=sparse))
    assert out["data_source"] == "public_api"


def test_enrich_skipped_without_key(monkeypatch):
    sparse = _payload("KYTX_N", 8.32, [5.0, 7.5, 10.0, 12.5])
    monkeypatch.setattr(cvmod, "CVSERVER_API_KEY", "")
    called = []
    real_fetch = cvmod.fetch_chain_from_cvserver

    async def spy(symbol, max_expiries=4):
        called.append(symbol)
        return await real_fetch(symbol, max_expiries=max_expiries)

    monkeypatch.setattr(cvmod, "fetch_chain_from_cvserver", spy)
    _run_impl("KYTX_N", AsyncMock(return_value=sparse))
    assert called == [], "no cvserver call without a key"


def test_result_strikes_subset_of_vendor_rows(monkeypatch):
    """H1: deepen/enrich only swap vendor payloads — no fabricated strikes."""
    sparse = _payload("KYTX_H", 8.32, [5.0, 7.5, 10.0, 12.5])
    rich = _payload("KYTX_H", 8.32, [5.0 + 0.5 * i for i in range(60)])
    vendor_strikes = {c["strike"] for c in rich["contracts"]}

    async def fake_fetch(ticker, max_expiries=4):
        return rich if max_expiries >= 8 else sparse

    out = _run_impl("KYTX_H", fake_fetch)
    assert {s["strike"] for s in out["strikes"]} <= vendor_strikes


def test_top_up_unit():
    from server import MIN_GRID_STRIKES, _top_up_strike_set
    assert MIN_GRID_STRIKES == 8
    full = [7.5, 10.0, 5.0, 12.5, 2.5, 15.0, 17.5, 20.0, 22.5]
    assert _top_up_strike_set({7.5, 10.0, 5.0}, full, 8) == set(full[:8])
    assert _top_up_strike_set(set(full[:8]), full, 8) == set(full[:8])
    assert _top_up_strike_set(set(), [], 8) == set()


def test_floor_shows_all_listed_for_thin_name():
    """KYTX: band left 3 of 8 listed; floor restores all 8 with full data."""
    payload = _payload("KYTX_F", 8.32, [2.5, 5.0, 7.5, 10.0, 12.5, 15.0, 17.5, 20.0])
    out = _run_impl("KYTX_F", AsyncMock(return_value=payload))
    got = sorted(s["strike"] for s in out["strikes"])
    assert got == [2.5, 5.0, 7.5, 10.0, 12.5, 15.0, 17.5, 20.0]
    assert all("gex" in s for s in out["strikes"]), "every shown row carries analytics"
    assert sorted(out["grid"]["strikes"]) == got, "grid tracks the topped-up set"
    assert out["expiries_used"] == ["2026-09-18"]


def test_cvserver_cap_refuses_over_quota():
    now = time.time()
    cvmod._req_log.extend([now - 60 * i for i in range(20)])
    called = []

    async def boom():
        called.append(1)
        return {"ticker": "X", "spot": 1.0}

    import asyncio
    out = _LOOP.run_until_complete(cvmod._cached_call("cap-test", 60, boom))
    assert called == [], "21st hourly call must not reach upstream"
    assert out is None  # nothing cached -> None (stale beats nothing)


def test_cvserver_under_cap_fetches():
    now = time.time()
    cvmod._req_log.extend([now - 60 * i for i in range(19)])

    async def ok():
        return {"ticker": "X", "spot": 1.0}

    import asyncio
    out = _LOOP.run_until_complete(cvmod._cached_call("cap-test-2", 60, ok))
    assert out == {"ticker": "X", "spot": 1.0}
