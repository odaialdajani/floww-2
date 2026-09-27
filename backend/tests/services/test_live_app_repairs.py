from copy import deepcopy
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from services import public_api_adapter as adapter
from services.public_api import Quote

NOW = datetime(2026, 9, 27, 18, tzinfo=UTC)

def broker_for(day='2026-09-25', symbol='SPY', **bar):
    broker = MagicMock()
    broker.get_quotes = AsyncMock(return_value=[Quote(symbol='SPY', instrument_type='EQUITY', last=772.04, bid=760.01, ask=772.4, timestamp='2026-09-25T23:59:59Z')])
    broker.get_bars = AsyncMock(return_value={'symbol': symbol, 'regularMarket': {'bars': [dict(timestamp=datetime.fromisoformat(day).replace(tzinfo=ZoneInfo('America/New_York')).isoformat(), open=768.78, high=772.28, low=766.29, close=771.35, volume=10, **bar)]}})
    return broker

@pytest.mark.asyncio
async def test_rejected_book_uses_only_verified_completed_session(monkeypatch):
    monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER', 'public')
    broker = broker_for()
    result = await adapter._resolve_spot_observation(broker, 'SPY', 'test', now=NOW)
    assert result['price'] == 771.35
    assert result['source'] == 'public-session-close'
    assert result['event_time'] == '2026-09-25T20:00:00+00:00'
    assert result['fetched_at'] != result['event_time']
    await adapter._resolve_spot_observation(broker, 'SPY', 'test', now=NOW)
    assert broker.get_bars.await_count == 1

@pytest.mark.asyncio
@pytest.mark.parametrize('day,symbol,now', [('2026-09-24','SPY',NOW),('2026-09-28','SPY',NOW),('2026-09-25','QQQ',NOW),('2026-09-25','SPY',datetime(2026,9,28,15,tzinfo=UTC))])
async def test_invalid_close_cannot_bypass_book(monkeypatch,day,symbol,now):
    monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER','public')
    result = await adapter._resolve_spot_observation(broker_for(day,symbol), 'SPY', 'test', now=now)
    assert result['price'] is None

@pytest.mark.asyncio
@pytest.mark.parametrize('value', [-1, 0, float('nan'), 900])
async def test_bad_close_fails_closed(monkeypatch,value):
    monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER','public')
    broker = broker_for()
    broker.get_bars.return_value['regularMarket']['bars'][0]['close'] = value
    result = await adapter._resolve_spot_observation(broker,'SPY','test',now=NOW)
    assert result['price'] is None

@pytest.mark.asyncio
async def test_public_chain_enriches_without_mutating_cache(monkeypatch):
    from routes import public_api
    raw = {'spot': 100, 'contracts': [dict(type='call',strike=102.5,expiry='2026-10-16',T=30/365,iv=.2,gamma=.01,oi=10)], 'expiries':['2026-10-16']}
    before = deepcopy(raw)
    monkeypatch.setattr(public_api,'fetch_chain_from_public_api', AsyncMock(return_value=raw))
    result = await public_api.get_public_chain('SPY', expiration='2026-10-16', expirations=4)
    row = result['contracts'][0]
    assert row['gex'] == 1000
    assert row['vanna'] != 0 and row['charm'] != 0
    assert row['moneyness_pct'] == -2.5
    assert row['dte'] == 30
    assert raw == before


def test_chain_inputs_stay_unknown_and_zero_stays_zero():
    from services.chain_readings import chain_readings
    base = dict(type='put',strike=100,expiry='2026-10-16',T=30/365,iv=.2,gamma=.01,oi=10)
    rows=chain_readings([base,{**base,'oi':None},{**base,'gamma':0},{**base,'iv':None},{**base,'T':None},{**base,'gamma':float('inf')}],100,'SPY')
    assert rows[0]['gex']==-1000
    assert rows[1]['gex'] is None
    assert rows[2]['gex']==0
    assert rows[3]['vanna'] is None and rows[3]['charm'] is None
    assert rows[4]['dte'] is None and rows[4]['charm'] is None
    assert rows[5]['gex'] is None

@pytest.mark.asyncio
async def test_both_chain_routes_use_same_readings(monkeypatch):
    import server
    from routes import market_data, public_api
    raw={'spot':100,'contracts':[dict(type='call',strike=102.5,expiry='2026-10-16',T=30/365,iv=.2,gamma=.01,oi=10)],'expiries':['2026-10-16']}
    monkeypatch.setattr(public_api,'fetch_chain_from_public_api',AsyncMock(return_value=raw))
    monkeypatch.setattr(server,'fetch_spot_and_chains_merged',AsyncMock(return_value=raw))
    direct=await public_api.get_public_chain('SPY',expiration=None,expirations=4)
    merged=await market_data.chain('SPY',expiries=4,min_oi=0,expiry=None,dte_max=None)
    assert direct['contracts']==merged['rows']

@pytest.mark.asyncio
@pytest.mark.parametrize('date,close', [('2026-11-27T20:00:00+00:00','2026-11-27T18:00:00+00:00'),('2026-12-25T15:00:00+00:00','2026-12-24T18:00:00+00:00'),('2026-09-28T13:00:00+00:00','2026-09-25T20:00:00+00:00')])
async def test_holiday_early_close_and_preopen(monkeypatch,date,close):
    monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER','public')
    broker=broker_for(day=close[:10])
    result=await adapter._resolve_spot_observation(broker,'SPY','test',now=datetime.fromisoformat(date))
    assert result['event_time']==close

@pytest.mark.asyncio
async def test_ws_price_time_is_not_calculation_time(monkeypatch):
    from fastapi import WebSocketDisconnect

    import auth
    import server
    raw={'spot':100,'contracts':[{}],'spot_source':'public-session-close','spot_event_time':'2026-09-25T20:00:00+00:00','spot_fetched_at':'2026-09-27T20:00:00+00:00','event_time':None}
    monkeypatch.setattr(auth,'verify_ws_token',AsyncMock(return_value=True))
    monkeypatch.setattr(server,'fetch_spot_and_chains_merged',AsyncMock(return_value=raw))
    monkeypatch.setattr(server,'compute_gex_by_strike',lambda *a:[])
    monkeypatch.setattr(server,'classify_nodes',lambda *a:{})
    captured=[]
    async def capture(payload):
        captured.append(payload)
        raise WebSocketDisconnect()
    ws=MagicMock(accept=AsyncMock(),send_json=AsyncMock(side_effect=capture))
    await server.websocket_gex(ws,'SPY')
    assert captured[0]['source_event_time']==raw['spot_event_time']
    assert captured[0]['asof']!=raw['spot_event_time']
    assert captured[0]['chain_event_time'] is None

@pytest.mark.asyncio
async def test_close_fetches_coalesce_per_symbol_without_blocking_other_symbols():
    import asyncio

    from services.public_session_close import completed_public_close
    entered, release = asyncio.Event(), asyncio.Event()
    slow = broker_for()
    raw = slow.get_bars.return_value
    async def wait_bars(*a, **kw):
        entered.set()
        await release.wait()
        return raw
    slow.get_bars = AsyncMock(side_effect=wait_bars)
    fast = broker_for(symbol='QQQ')
    first = asyncio.create_task(completed_public_close(slow,'SPY',NOW))
    await entered.wait()
    second = asyncio.create_task(completed_public_close(slow,'SPY',NOW))
    try:
        result = await asyncio.wait_for(completed_public_close(fast,'QQQ',NOW),1)
        assert result['price']==771.35
    finally:
        release.set()
        results = await asyncio.gather(first,second)
    assert results[0]==results[1]
    assert slow.get_bars.await_count==1

@pytest.mark.asyncio
async def test_absent_quote_and_newly_closed_session_do_not_trigger_fallback(monkeypatch):
    monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER','public')
    broker=broker_for()
    broker.get_quotes.return_value=[]
    assert (await adapter._resolve_spot_observation(broker,'SPY','test',now=NOW))['price'] is None
    broker.get_bars.assert_not_awaited()
    broker=broker_for()
    assert (await adapter._resolve_spot_observation(broker,'SPY','test',now=datetime(2026,9,25,20,tzinfo=UTC)))['price'] is None
    broker.get_bars.assert_not_awaited()

@pytest.mark.asyncio
async def test_future_bar_time_is_not_a_completed_close(monkeypatch):
    monkeypatch.setenv('FLOWW_MARKET_DATA_PROVIDER','public')
    broker=broker_for()
    broker.get_bars.return_value['regularMarket']['bars'][0]['timestamp']='2026-09-25T23:59:59-04:00'
    assert (await adapter._resolve_spot_observation(broker,'SPY','test',now=NOW))['price'] is None

def test_known_greeks_survive_missing_derivation_inputs():
    from services.chain_readings import chain_readings
    row=chain_readings([dict(type='call',strike=100,vanna=.3,charm=-.2)],100,'SPY')[0]
    assert row['vanna']==.3 and row['charm']==-.2

@pytest.mark.asyncio
async def test_movers_coalesces_requests_and_limits_each_response(monkeypatch):
    import asyncio

    from services import movers
    movers._CACHE.clear()
    started, release = asyncio.Event(), asyncio.Event()
    calls=[]
    async def compute(**kw):
        calls.append(kw)
        started.set()
        await release.wait()
        return dict(status='ok',results=[{'ticker':str(i)} for i in range(5)],coverage={'valid':5})
    monkeypatch.setattr(movers,'compute_movers',compute)
    first=asyncio.create_task(movers.get_movers(limit=1))
    await started.wait()
    second=asyncio.create_task(movers.get_movers(limit=3))
    await asyncio.sleep(0)
    release.set()
    try:
        one,three=await asyncio.gather(first,second)
        assert len(calls)==1
        assert len(one['results'])==1
        assert len(three['results'])==3
        one['results'][0]['ticker']='changed'
        assert (await movers.get_movers(limit=3))['results'][0]['ticker']=='0'
    finally:
        movers._CACHE.clear()

@pytest.mark.asyncio
@pytest.mark.parametrize('fails',[True,False])
async def test_movers_stale_response_cannot_mutate_saved_reasons(monkeypatch,fails):
    from services import movers
    movers._CACHE.clear()
    monkeypatch.setattr(movers,'completed_session_pair',lambda **kw:('2026-09-25','2026-09-24'))
    payload={'status':'partial','results':[{'ticker':'SPY'}],'reason_codes':['MISSING_SESSION_CLOSE']}
    key=('2026-09-25','2026-09-24',movers.UNIVERSE_ID,'previous_completed_session')
    movers._CACHE[key]={'ts':0,'payload':deepcopy(payload)}
    fake=AsyncMock(side_effect=RuntimeError('offline')) if fails else AsyncMock(return_value={'status':'unavailable'})
    monkeypatch.setattr(movers,'compute_movers',fake)
    try:
        for _ in range(2):
            result=await movers.get_movers()
            assert result['status']=='stale'
            assert result['reason_codes']==['MISSING_SESSION_CLOSE','PROVIDER_FAIL']
            assert movers._CACHE[key]['payload']==payload
    finally:
        movers._CACHE.clear()

@pytest.mark.asyncio
@pytest.mark.parametrize('fails',[True,False])
async def test_failed_movers_scan_is_shared_by_overlapping_callers(monkeypatch,fails):
    import asyncio

    from services import movers
    movers._CACHE.clear()
    started, release = asyncio.Event(), asyncio.Event()
    calls=[]
    async def compute(**kw):
        calls.append(kw)
        started.set()
        await release.wait()
        if fails:
            raise RuntimeError('offline')
        return dict(status='unavailable',results=[])
    monkeypatch.setattr(movers,'compute_movers',compute)
    first=asyncio.create_task(movers.get_movers())
    await started.wait()
    second=asyncio.create_task(movers.get_movers())
    await asyncio.sleep(0)
    release.set()
    one,two=await asyncio.gather(first,second)
    assert len(calls)==1
    assert one['status']==two['status']=='unavailable'
    assert not movers._INFLIGHT

@pytest.mark.asyncio
async def test_movers_disconnect_does_not_cancel_shared_scan(monkeypatch):
    import asyncio

    from services import movers
    movers._CACHE.clear()
    started, release=asyncio.Event(),asyncio.Event()
    async def compute(**kw):
        started.set()
        await release.wait()
        return dict(status='ok',results=[{'ticker':'SPY'}])
    fake=AsyncMock(side_effect=compute)
    monkeypatch.setattr(movers,'compute_movers',fake)
    first=asyncio.create_task(movers.get_movers())
    await started.wait()
    second=asyncio.create_task(movers.get_movers())
    await asyncio.sleep(0)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    release.set()
    try:
        assert (await second)['results']==[{'ticker':'SPY'}]
        fake.assert_awaited_once()
    finally:
        movers._CACHE.clear()
