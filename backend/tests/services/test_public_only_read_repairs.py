"""Offline policy regressions: execute complete production functions, no app boot.

AST loading only removes route decorators, avoiding server import-time .env/DB
initializers. Provider, persistence and unrelated analytic collaborators are
in-memory; the policy/control-flow function bodies are not rewritten or sliced.
Run standalone with --noconftest to avoid the app-wide persistence fixtures.
"""

import ast
import asyncio
import builtins
import logging
import os
import sys
import time
import types
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException, Query

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))


def functions_from(path, env):
    tree = ast.parse((BACKEND / path).read_text())
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if path == 'server.py':
        nodes = [n for n in nodes if n.name in {
            '_build_heatmap_impl', '_top_up_strike_set', 'fetch_spot_and_chains', '_logged_task', '_display_quality',
            'build_heatmap', '_revalidate_heatmap', '_public_heatmap_cache_allowed'}]
    elif path == 'routes/flowseeker.py':
        nodes = [n for n in nodes if n.name in {'options_chain', 'public_chain_flat', '_remember_chain'}]
    for node in nodes:
        node.decorator_list = []
    module = ast.Module([ast.ImportFrom('__future__', [ast.alias('annotations')], 0), *nodes], [])
    exec(compile(ast.fix_missing_locations(module), str(BACKEND / path), 'exec'), env)
    return env


def module_stub(monkeypatch, name, **values):
    module = types.ModuleType(name)
    module.__dict__.update(values)
    monkeypatch.setitem(sys.modules, name, module)
    return module


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    import socket

    monkeypatch.setattr(socket.socket, 'connect', Mock(side_effect=AssertionError('network forbidden')))
    monkeypatch.delenv('FLOWW_MARKET_DATA_PROVIDER', raising=False)
    module_stub(monkeypatch, 'server',
                fetch_spot_and_chains=Mock(side_effect=RuntimeError('legacy producer forbidden')),
                calc_probability_distribution=Mock())
    module_stub(monkeypatch, 'yfinance', Ticker=Mock(side_effect=RuntimeError('Yahoo forbidden')))
    module_stub(monkeypatch, 'services.duckdb_engine', db=types.SimpleNamespace(conn=None))


def chain(count=1, source='public_api'):
    return {'ticker': 'SPY', 'spot': 100.0, 'data_source': source,
            'expiries': ['2099-01-16'], 'contracts': [
                {'strike': 100.0 + i, 'expiry': '2099-01-16', 'type': 'call',
                 'gamma': 0.01, 'delta': 0.5, 'oi': 10, 'volume': 1, 'iv': 0.2}
                for i in range(count)]}


def builder(monkeypatch, raw=None):
    import services.solstice_scope as scope

    fetch = AsyncMock(return_value=chain() if raw is None else raw)
    cv = module_stub(monkeypatch, 'services.cvserver_client', CVSERVER_API_KEY='fixture-only',
                     fetch_chain_from_cvserver=AsyncMock(return_value=chain(45, 'cvserver')),
                     fetch_chain_for_heatmap=AsyncMock(return_value=chain(45, 'cvserver')))
    daily = module_stub(monkeypatch, 'services.agent.daily_bar_evidence',
                        ensure_public_daily_bars=AsyncMock(return_value=None))
    module_stub(monkeypatch, 'services.market_provenance', cached_market_copy=lambda data, *a, **kw: data)
    original_import = builtins.__import__

    def isolated_import(name, *args, **kwargs):
        if name.startswith(('services.', 'domain.')):
            allowed = ('services.solstice_scope', 'services.cvserver_client',
                       'services.agent.daily_bar_evidence', 'services.market_provenance')
            if name not in allowed:
                raise ImportError('unrelated optional collaborator isolated: ' + name)
        return original_import(name, *args, **kwargs)

    env = {'__builtins__': {**vars(builtins), '__import__': isolated_import},
           'asyncio': asyncio, 'os': os, 'time': time, 'datetime': datetime,
           'UTC': UTC, 'timedelta': timedelta, 'HTTPException': HTTPException,
           'log': logging.getLogger('policy-test'), '_BUILD_HEATMAP_CACHE': {},
           '_BUILD_HEATMAP_CACHE_TTL': 30, '_background_tasks': set(),
           'MIN_GRID_STRIKES': 8, '_shutdown_event': asyncio.Event(),
           '_BUILD_HEATMAP_STALE_TTL': 900, '_BUILD_HEATMAP_INFLIGHT': set()}
    functions_from('server.py', env)
    env.update(fetch_spot_and_chains_merged=fetch,
               _display_surfaces=lambda *args: ('OI', 'vendor-supplied-greeks',
                                               [{'strike': 100.0, 'gex': 1.0}], {'strikes': [100.0]}),
               _attach_strike_volumes=lambda *args: None,
               classify_nodes=lambda *args: {}, detect_patterns=lambda *args: [],
               calc_skew_metrics=lambda *args: {'atm_iv': 0.25},
               calc_realized_volatility=Mock(return_value={'rv_close': 0.15}),
               calc_iv_rank_percentile=Mock(return_value={'iv_rank': 40.0}),
               velocity_and_rolling=AsyncMock(return_value={}),
               save_snapshot=AsyncMock(), _sanitize=lambda value: value)
    for name in ('calc_implied_move', 'calc_probability_distribution', 'calc_aggregate_gex_curve',
                 'detect_opportunities', 'calc_iv_surface_data', 'calc_market_regime',
                 'calc_implied_pdf', 'calc_gamma_flip_levels', 'calc_hedge_impulse_curve',
                 'calc_pressure_cloud', 'calc_charm_integral'):
        env[name] = lambda *args: {}
    return env, fetch, cv, daily, scope


def run_build(env, ticker='SPY', **kwargs):
    async def run():
        result = await env['_build_heatmap_impl'](ticker, with_taps=False, **kwargs)
        if env['_background_tasks']:
            await asyncio.gather(*list(env['_background_tasks']))
        return result
    return asyncio.run(run())


@pytest.mark.parametrize('ticker', ['^SPX', 'I:SPX'])
def test_public_index_failure_never_enters_cv_screen(monkeypatch, ticker):
    env, fetch, cv, _, _ = builder(monkeypatch)
    monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER', 'public')
    fetch.side_effect = HTTPException(503, 'Public unavailable')
    with pytest.raises(HTTPException) as exc:
        run_build(env, ticker)
    assert exc.value.status_code == 503
    cv.fetch_chain_from_cvserver.assert_not_awaited()
    cv.fetch_chain_for_heatmap.assert_not_awaited()
    assert fetch.await_count == 1


def test_public_sparse_chain_retains_real_public_rows(monkeypatch):
    env, fetch, cv, _, _ = builder(monkeypatch)
    monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER', 'public')
    out = run_build(env)
    assert out['data_source'] == 'public_api'
    assert fetch.await_count == 2  # Public deepening remains allowed.
    cv.fetch_chain_from_cvserver.assert_not_awaited()


@pytest.mark.parametrize('source', ['cvserver', 'yfinance', 'public_api', None])
def test_public_builder_rejects_pre_policy_warm_payload(monkeypatch, source):
    env, fetch, _, _, scope = builder(monkeypatch, chain(45))
    key = scope.cache_key('SPY', scope.request_query(4, 'day', None, False, False, 200))
    old = {'spot': 100, 'strikes': [100], 'data_source': source, 'iv_rank': {'iv_rank': 99}}
    env['_BUILD_HEATMAP_CACHE'][key] = {'ts': time.time(), 'data': old}
    monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER', 'public')
    out = run_build(env)
    assert out is not old
    fetch.assert_awaited_once()
    assert out['scope_echo'] == key


def test_public_builder_does_not_schedule_yahoo_vol_studies(monkeypatch):
    env, _, _, daily, _ = builder(monkeypatch, chain(45))
    monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER', 'public')
    out = run_build(env)
    env['calc_realized_volatility'].assert_not_called()
    env['calc_iv_rank_percentile'].assert_not_called()
    for study in ('iv_rank', 'realized_vol'):
        assert out[study]['status'] == 'unavailable'
        assert out[study]['reason'] == 'PUBLIC_ONLY_STUDY_UNAVAILABLE'
        assert not any(isinstance(v, (int, float)) for v in out[study].values())
    daily.ensure_public_daily_bars.assert_awaited_once()


@pytest.mark.parametrize('mode', [None, 'legacy', 'PUBLIC', ' public'])
def test_non_public_modes_keep_sparse_cv_and_yahoo_studies(monkeypatch, mode):
    if mode is not None:
        monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER', mode)
    env, _, cv, _, _ = builder(monkeypatch)
    out = run_build(env)
    cv.fetch_chain_from_cvserver.assert_awaited_once()
    assert out['data_source'] == 'cvserver'
    assert out['realized_vol'] == {'rv_close': 0.15}
    assert out['iv_rank'] == {'iv_rank': 40.0, 'rv_iv_spread': 0.1, 'rv_close': 0.15}


def test_public_builder_reuses_own_safe_cache(monkeypatch):
    env, fetch, _, _, _ = builder(monkeypatch, chain(45))
    monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER', 'public')
    first = run_build(env)
    assert run_build(env) is first
    fetch.assert_awaited_once()


@pytest.mark.parametrize('age', [0, 120])
def test_public_wrapper_rejects_legacy_fresh_or_stale_cache(monkeypatch, age):
    env, _, _, _, scope = builder(monkeypatch)
    key = scope.cache_key('SPY', scope.request_query(4, 'day', None, False, False, 200))
    old = {'spot': 100, 'strikes': [100], 'data_source': 'yfinance'}
    env['_BUILD_HEATMAP_CACHE'][key] = {'ts': time.time() - age, 'data': old}
    env['_build_heatmap_impl'] = AsyncMock(side_effect=HTTPException(503, 'Public unavailable'))
    monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER', 'public')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(env['build_heatmap']('SPY', with_taps=False))
    assert exc.value.status_code == 503
    assert not env['_background_tasks']


def test_revalidate_preserves_public_policy_cache_marker(monkeypatch):
    env, _, _, _, scope = builder(monkeypatch, chain(45))
    monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER', 'public')
    key = scope.cache_key('SPY', scope.request_query(4, 'day', None, False, False, 200))
    asyncio.run(env['_revalidate_heatmap'](key, 'SPY', 4, False, 'day', None, False, 200))
    assert env['_BUILD_HEATMAP_CACHE'][key]['provider_policy'] == 'public'


@pytest.mark.parametrize('name', ['max_pain_drift_endpoint', 'consensus_drift_endpoint'])
def test_public_accumulating_study_refuses_before_legacy_producer(monkeypatch, name):
    env = steal()
    monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER', 'public')
    with pytest.raises(HTTPException) as exc:
        env[name]('SPY', accumulate=True)
    assert exc.value.status_code == 503
    sys.modules['server'].fetch_spot_and_chains.assert_not_called()


def flow(monkeypatch, public=None):
    adapter = module_stub(monkeypatch, 'services.public_api_adapter',
                          fetch_chain_from_public_api=AsyncMock(return_value=public),
                          public_to_nested=lambda value: None if value is None else {
                              'symbol': 'SPY', 'chain': [{'strikes': [100]}]})
    env = {'asyncio': asyncio, 'os': os, 'time': time, 'Query': Query,
           'HTTPException': HTTPException, 'logger': logging.getLogger('policy-test'),
           '_chain_cache': {}, 'CACHE_TTL': 600, '_CHAIN_CACHE_MAX': 500}
    functions_from('routes/flowseeker.py', env)
    env.update(_cvforge_chain=AsyncMock(return_value={'chain': [1], 'source': 'cvserver'}),
               _yfinance_chain_sync=Mock(return_value={'chain': [1], 'source': 'yfinance'}))
    return env, adapter


@pytest.mark.parametrize('failure', ['empty', 'exception', 'budget'])
def test_public_drill_chain_never_falls_back(monkeypatch, failure):
    from services.public_budget import BudgetExhausted

    env, adapter = flow(monkeypatch)
    monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER', 'public')
    if failure == 'exception':
        adapter.fetch_chain_from_public_api.side_effect = RuntimeError('provider down')
    elif failure == 'budget':
        adapter.fetch_chain_from_public_api.side_effect = BudgetExhausted(retry_after=7)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(env['options_chain']('SPY'))
    assert exc.value.status_code == 503
    env['_cvforge_chain'].assert_not_awaited()
    env['_yfinance_chain_sync'].assert_not_called()


@pytest.mark.parametrize('source', ['cvserver', 'yfinance', None])
def test_public_drill_chain_rejects_non_public_warm_cache(monkeypatch, source):
    env, adapter = flow(monkeypatch, chain())
    old = {'chain': [1], 'data_source': source}
    env['_chain_cache']['SPY'] = (time.time(), old)
    monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER', 'public')
    result = asyncio.run(env['options_chain']('SPY'))
    assert result is not old
    assert result['data_source'] == 'public_api'
    adapter.fetch_chain_from_public_api.assert_awaited_once()


@pytest.mark.parametrize('route', ['options_chain', 'public_chain_flat'])
def test_chain_route_has_only_adapter_owned_budget_admission(monkeypatch, route):
    import services.public_budget as budgets
    from services.public_budget import PublicBudget

    budget = PublicBudget(max_inflight=1, refill_per_sec=0)
    monkeypatch.setattr(budgets, 'budget', budget)
    env, adapter = flow(monkeypatch)
    admitted = []

    async def admitted_fetch(*args, **kwargs):
        await budget.acquire_n(8, 'api.public.com')
        admitted.append(8)
        try:
            return chain()
        finally:
            budget.release()
    adapter.fetch_chain_from_public_api.side_effect = admitted_fetch
    if route == 'public_chain_flat':
        result = asyncio.run(env[route]('SPY', expirations=6, expiration=None, fields=None))
        assert result['ok'] is True
    else:
        result = asyncio.run(env[route]('SPY'))
        assert result.get('data_source') == 'public_api'
    assert admitted == [8]
    assert budget._inflight == 0
    assert budget.status()['available'] == budget.status()['capacity'] - 8


def test_legacy_drill_chain_keeps_cv_then_yahoo_fallback(monkeypatch):
    env, _ = flow(monkeypatch)
    assert asyncio.run(env['options_chain']('SPY'))['source'] == 'cvserver'
    env['_chain_cache'].clear()
    env['_cvforge_chain'].return_value = None
    assert asyncio.run(env['options_chain']('SPY'))['source'] == 'yfinance'


def steal():
    env = {'os': os, 'asyncio': asyncio, 'datetime': datetime, 'UTC': UTC, 'Query': Query,
           'HTTPException': HTTPException, 'yf': types.SimpleNamespace(Ticker=Mock(
               side_effect=RuntimeError('Yahoo must not be entered'))),
           '_income_cache': {}, '_income_inflight': {}, '_INCOME_CACHE_TTL': 30}
    return functions_from('routes/steal_three.py', env)


@pytest.mark.parametrize('name,args', [
    ('_load_chain', ('SPY',)), ('_load_chain_window', ('SPY', 7, 45)),
    ('_load_multi_expiry_chain', ('SPY',)), ('dual_gex', ('SPY',)),
    ('iv_mid', ('SPY', 6)), ('max_pain_route', ('SPY', 4)),
    ('chain_consensus_route', ('SPY', 4)), ('strike_cone_endpoint', ('SPY',)),
    ('risk_neutral_density_endpoint', ('SPY', 1)),
    ('risk_neutral_density_path_endpoint', ('SPY', '2099-01-16')),
    ('realized_volatility_endpoint', ('SPY',)),
])
def test_public_extra_studies_fail_closed_before_producer(monkeypatch, name, args):
    env = steal()
    monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER', 'public')
    # Local imports must not grant a producer network or persistence access.
    with pytest.raises(HTTPException) as exc:
        env[name](*args)
    assert exc.value.status_code == 503
    assert exc.value.detail['status'] == 'unavailable'
    assert exc.value.detail['reason'] == 'PUBLIC_ONLY_STUDY_UNAVAILABLE'
    env['yf'].Ticker.assert_not_called()


def test_public_income_rejects_warm_legacy_study(monkeypatch):
    env = steal()
    args = ('SPY', 'both', 0.0, 0, 7, 45, 25)
    env['_income_cache'][('legacy', *args)] = (time.time(), {'spot': 100, 'puts': [1]})
    monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER', 'public')
    module_stub(monkeypatch, 'services.public_api_adapter',
                fetch_chain_from_public_api=AsyncMock(return_value=None),
                fetch_option_expiry_listing=AsyncMock(return_value=None),
                fetch_chain_for_expiries=AsyncMock(side_effect=AssertionError('No listing, no chain read')))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(env['_run_income_screener'](*args))
    assert exc.value.status_code == 503
    env['yf'].Ticker.assert_not_called()


@pytest.mark.parametrize('mode', [None, 'legacy', 'PUBLIC'])
def test_legacy_income_warm_cache_still_works(monkeypatch, mode):
    env = steal()
    if mode is not None:
        monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER', mode)
    args = ('SPY', 'both', 0.0, 0, 7, 45, 25)
    env['_income_cache'][('legacy', *args)] = (time.time(), {'spot': 100, 'puts': [1]})
    assert asyncio.run(env['_run_income_screener'](*args)) == {'spot': 100, 'puts': [1], 'cached': True}


def test_legacy_index_failure_keeps_cv_screen(monkeypatch):
    env, fetch, cv, _, _ = builder(monkeypatch)
    fetch.side_effect = HTTPException(503, 'Public unavailable')
    out = run_build(env, '^SPX')
    assert out['data_source'] == 'cvserver'
    cv.fetch_chain_from_cvserver.assert_awaited_once()
    cv.fetch_chain_for_heatmap.assert_awaited_once()


def test_public_nested_chain_warm_cache_costs_no_admission(monkeypatch):
    env, adapter = flow(monkeypatch, chain())
    monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER', 'public')
    first = asyncio.run(env['options_chain']('SPY'))
    adapter.fetch_chain_from_public_api.side_effect = AssertionError('cache must not spend')
    assert asyncio.run(env['options_chain']('SPY')) is first
    assert adapter.fetch_chain_from_public_api.await_count == 1


def test_flat_chain_reports_adapter_budget_exhaustion(monkeypatch):
    from services.public_budget import BudgetExhausted

    env, adapter = flow(monkeypatch)
    adapter.fetch_chain_from_public_api.side_effect = BudgetExhausted(retry_after=7)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(env['public_chain_flat']('SPY', expirations=6, expiration=None, fields=None))
    assert exc.value.status_code == 503
    assert exc.value.detail == {'error': 'public budget exhausted', 'retry_after': 7}
    assert adapter.fetch_chain_from_public_api.await_args.kwargs['raise_budget_exhausted'] is True


@pytest.mark.parametrize('mode', [None, 'legacy', 'PUBLIC'])
@pytest.mark.parametrize('name,args', [
    ('_load_chain', ('SPY',)), ('_load_chain_window', ('SPY', 7, 45)),
    ('_load_multi_expiry_chain', ('SPY',)),
])
def test_non_public_modes_keep_yahoo_loader_entry(monkeypatch, mode, name, args):
    env = steal()
    if mode is not None:
        monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER', mode)
    with pytest.raises(RuntimeError, match='Yahoo must not be entered'):
        env[name](*args)
    env['yf'].Ticker.assert_called_once_with('SPY')


def test_public_sync_chain_refuses_legacy_cache(monkeypatch):
    env = {'os': os, 'HTTPException': HTTPException}
    functions_from('server.py', env)
    env['cache_get'] = Mock(return_value=chain(source='yfinance'))
    env['yf'] = types.SimpleNamespace(Ticker=Mock(side_effect=RuntimeError('Yahoo forbidden')))
    monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER', 'public')
    with pytest.raises(HTTPException) as exc:
        env['fetch_spot_and_chains']('SPY')
    assert exc.value.status_code == 503
    env['cache_get'].assert_not_called()
    env['yf'].Ticker.assert_not_called()
