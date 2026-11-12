"""Loop responsiveness for the heatmap read path (B01).

The heatmap build must not run its synchronous CPU sections on the event-loop
thread: an unrelated queued loop callback has to keep running while the
calculation and the returned-payload copy are in flight. These checks drive the
real backend/server.py implementation offline and also pin the contracts the
scheduling change must not alter: exact payload values, scope/cache/query
identity and independent mutable payloads per reader.
"""

import asyncio as _asyncio
import copy
import threading
import time
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest

import server

_LOOP = _asyncio.new_event_loop()

_CLOCK_KEYS = {
    "asof", "available_at", "built_at", "event_time", "fetched_at", "generated_at",
    "observed_at", "received_at", "recorded_at", "snapshotId", "source_age_s",
    "source_received_at", "stale_age_s",
}

_COMPARED_SECTIONS = (
    "spot", "strikes", "grid", "nodes", "patterns", "map_query", "data_source",
    "exposure_basis", "model_basis", "quality", "metrics", "implied_move",
    "prob_distribution", "aggregate_curve", "opportunities", "iv_surface", "skew",
    "market_regime", "implied_pdf", "gamma_flip", "hedge_impulse", "pressure_cloud",
    "charm_integral", "expiries_used", "gamma_regime_v1",
)


def _contract(strike, expiry="2026-11-20", option_type="call"):
    return {"strike": float(strike), "expiry": expiry, "T": 30 / 365.0,
            "type": option_type, "oi": 100.0, "iv": 0.25, "volume": 10.0,
            "gamma": 0.05, "delta": 0.5, "theta": -0.02, "vega": 0.1,
            "bid": 1.0, "ask": 1.1, "mid": 1.05, "last": 1.05}


def _chain(strikes=60, expiries=("2026-11-20",)):
    contracts = [c for index in range(strikes) for expiry in expiries
                 for c in (_contract(80.0 + index, expiry, "call"),
                           _contract(80.0 + index, expiry, "put"))]
    return {"ticker": "REPRO", "spot": 100.0, "expiries": list(expiries),
            "contracts": contracts, "data_source": "public_api"}


async def _no_velocity(ticker, current_nodes):
    return {"velocity_score": 0, "rolling_floor": "stable",
            "rolling_ceiling": "stable", "history": []}


@contextmanager
def _offline(chain, calls=None):
    async def _fetch(ticker, max_expiries=4):
        if calls is not None:
            calls.append((ticker, max_expiries))
        return copy.deepcopy(chain)

    async def _daily_bars(ticker, **kwargs):
        return None

    with patch.object(server, "fetch_spot_and_chains_merged", new=_fetch), \
            patch.object(server, "save_snapshot", new=AsyncMock(return_value=None)), \
            patch.object(server, "velocity_and_rolling", new=_no_velocity), \
            patch.object(server, "calc_realized_volatility",
                         new=lambda *a, **k: {"rv_close": 0.15}), \
            patch.object(server, "calc_iv_rank_percentile",
                         new=lambda *a, **k: {"iv_rank": 40.0}), \
            patch("services.agent.daily_bar_evidence.ensure_public_daily_bars", new=_daily_bars):
        yield


def _build(chain, inline=False):
    async def _inline_to_thread(func, /, *args, **kwargs):
        return func(*args, **kwargs)

    with _offline(chain):
        if inline:
            with patch.object(_asyncio, "to_thread", new=_inline_to_thread):
                return _LOOP.run_until_complete(
                    server._build_heatmap_impl("REPRO", max_expiries=4, with_taps=False))
        return _LOOP.run_until_complete(
            server._build_heatmap_impl("REPRO", max_expiries=4, with_taps=False))


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    server._BUILD_HEATMAP_CACHE.clear()
    # An earlier shutdown test leaves the global event set; the heatmap read
    # path must not inherit that leaked state.
    monkeypatch.setattr(server, "_shutdown_event", _asyncio.Event())
    yield
    server._BUILD_HEATMAP_CACHE.clear()


def _probe(original, loop, observations):
    def wrapper(*args, **kwargs):
        observation = {
            "off_loop": threading.current_thread() is not threading.main_thread(),
            "probe_ok": False,
        }
        observations.append(observation)
        if observation["off_loop"]:
            answered = threading.Event()
            loop.call_soon_threadsafe(answered.set)
            observation["probe_ok"] = bool(answered.wait(timeout=5))
        return original(*args, **kwargs)
    return wrapper


def _outer_probe(original, loop, observations):
    """Probe only the outermost call of a self-recursive function."""
    state = {"seen": False}

    def wrapper(*args, **kwargs):
        if state["seen"]:
            return original(*args, **kwargs)
        state["seen"] = True
        observation = {
            "off_loop": threading.current_thread() is not threading.main_thread(),
            "probe_ok": False,
        }
        observations.append(observation)
        if observation["off_loop"]:
            answered = threading.Event()
            loop.call_soon_threadsafe(answered.set)
            observation["probe_ok"] = bool(answered.wait(timeout=5))
        return original(*args, **kwargs)
    return wrapper


def test_metric_surfaces_run_off_the_event_loop_and_keep_the_loop_responsive():
    import domain.exposure_metrics as exposure_metrics
    import services.gex_core as gex_core
    import services.wall_structure as wall_structure

    observations: list[dict] = []
    chain = _chain()

    with _offline(chain), \
            patch.object(exposure_metrics, "compute_raw_oi",
                         new=_probe(exposure_metrics.compute_raw_oi, _LOOP, observations)), \
            patch.object(gex_core, "compute_gex_grid_vendor",
                         new=_probe(gex_core.compute_gex_grid_vendor, _LOOP, observations)), \
            patch.object(wall_structure, "discover_walls",
                         new=_probe(wall_structure.discover_walls, _LOOP, observations)):
        payload = _LOOP.run_until_complete(
            server._build_heatmap_impl("REPRO", max_expiries=4, with_taps=False))

    assert observations, "the metric surfaces were not exercised"
    assert all(item["off_loop"] for item in observations), (
        "a metric surface ran on the event-loop thread: queued loop work was blocked")
    assert all(item["probe_ok"] for item in observations), (
        "an unrelated queued loop callback could not run during the metric surfaces")
    assert "error" not in payload.get("metrics", {}), payload.get("metrics", {}).get("error")
    assert payload["spot"] == 100.0
    assert payload["strikes"] and all("gex" in row for row in payload["strikes"])
    assert payload["metrics"]["gex_net_v1"] is not None
    assert payload["map_query"]["expiries"] == 4


def test_off_loop_scheduling_keeps_payload_values_identical():
    scheduled = _build(_chain())
    inline = _build(_chain(), inline=True)

    for section in _COMPARED_SECTIONS:
        assert _stable(scheduled.get(section)) == _stable(inline.get(section)), (
            f"the scheduling change altered the {section} section")


def test_gamma_regime_uses_the_isolated_calculation_boundary():
    from services.solstice_regime import regime_at_spot

    dispatched = []

    async def calculate(function, *args):
        if function is regime_at_spot:
            dispatched.append(function)
        return await _asyncio.to_thread(function, *args)

    chain = _chain(strikes=2)
    with _offline(chain), patch.object(server, "run_cpu", new=calculate):
        result = _LOOP.run_until_complete(server._build_heatmap_impl("REPRO", with_taps=False))
    assert dispatched == [regime_at_spot]
    assert result["gamma_regime_v1"] == regime_at_spot(100.0, chain["contracts"], "REPRO")


def test_same_scope_readers_share_one_build_and_keep_independent_payloads():
    from services.solstice_scope import request_query

    calls: list[tuple] = []
    chain = _chain()

    async def _read():
        return await _asyncio.gather(
            server.build_heatmap("REPRO", max_expiries=4, with_taps=False, mode="day"),
            server.build_heatmap("REPRO", max_expiries=4, with_taps=False, mode="day"))

    with _offline(chain, calls=calls):
        first, second = _LOOP.run_until_complete(_read())

    assert len(calls) == 1, "same-scope readers duplicated the map build"
    assert first["map_query"] == second["map_query"] == request_query(
        4, "day", None, False, False, 200)
    assert first["spot"] == second["spot"] == 100.0
    first["strikes"].append({"strike": 999.0, "gex": 0.0})
    assert len(second["strikes"]) != len(first["strikes"]), (
        "readers shared one mutable payload")


def test_cached_market_copy_runs_off_the_event_loop():
    import services.market_provenance as market_provenance
    from services.solstice_scope import cache_key, request_query

    observations: list[dict] = []
    query = request_query(4, "day", None, False, False, 200)
    server._BUILD_HEATMAP_CACHE[cache_key("REPRO", query)] = {
        "ts": time.time(),
        "data": {"ticker": "REPRO", "spot": 100.0, "data_source": "public_api",
                 "strikes": [{"strike": 100.0, "gex": 1.0}]},
        "provider_policy": "public",
    }

    with patch.object(market_provenance, "cached_market_copy",
                      new=_outer_probe(market_provenance.cached_market_copy, _LOOP, observations)):
        payload = _LOOP.run_until_complete(
            server.build_heatmap("REPRO", max_expiries=4, with_taps=False, mode="day"))

    assert observations, "the cached market copy was not exercised"
    assert all(item["off_loop"] for item in observations), (
        "the cached market copy ran on the event-loop thread: queued loop work was blocked")
    assert all(item["probe_ok"] for item in observations), (
        "an unrelated queued loop callback could not run during the cached market copy")
    assert payload["spot"] == 100.0
    assert payload["stale_age_s"] is None or payload["stale_age_s"] >= 0


def test_sanitize_runs_off_the_event_loop():
    observations: list[dict] = []

    with _offline(_chain(strikes=2)), \
            patch.object(server, "_sanitize",
                         new=_outer_probe(server._sanitize, _LOOP, observations)):
        payload = _LOOP.run_until_complete(
            server._build_heatmap_impl("REPRO", max_expiries=4, with_taps=False))

    assert observations, "the payload sanitizer was not exercised"
    assert all(item["off_loop"] for item in observations), (
        "the payload sanitizer ran on the event-loop thread: queued loop work was blocked")
    assert all(item["probe_ok"] for item in observations), (
        "an unrelated queued loop callback could not run during the payload sanitizer")
    assert payload["spot"] == 100.0


def _stable(value):
    if isinstance(value, dict):
        return {key: _stable(item) for key, item in value.items() if key not in _CLOCK_KEYS}
    if isinstance(value, list):
        return [_stable(item) for item in value]
    return value
