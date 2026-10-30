from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from auth import verify_api_key
from routes.related_tickers import WarmRequest, related_ticker_warm


def request(path='/api/related/NVDA/warm', *, host='127.0.0.1', origin='http://127.0.0.1:3000', forwarded=False, method='POST'):
    headers=[(b'host',b'127.0.0.1:8001'),(b'origin',origin.encode())]
    if forwarded: headers.append((b'x-forwarded-for',b'127.0.0.1'))
    return Request({'type':'http','method':method,'path':path,'headers':headers,'client':(host,1234),'query_string':b''})


@pytest.fixture(autouse=True)
def local_mode(monkeypatch):
    monkeypatch.setenv('FLOWW_AGENT_DEPLOYMENT','local')
    monkeypatch.delenv('API_SECRET_KEY',raising=False)
    monkeypatch.delenv('FLOWW_AGENT_ORIGINS',raising=False)


@pytest.mark.asyncio
async def test_exact_local_price_cache_read_works_without_order_key():
    assert await verify_api_key(request()) is True


@pytest.mark.asyncio
@pytest.mark.parametrize('kwargs',[{'host':'192.0.2.1'},{'origin':'https://foreign.example'},{'origin':''},{'forwarded':True},{'path':'/api/related/NVDA/warm/orders'},{'path':'/api/public/orders'},{'method':'DELETE'},{'path':'/api/related/../../orders/warm'}])
async def test_anonymous_remote_and_other_mutations_stay_disabled(kwargs):
    with pytest.raises(HTTPException): await verify_api_key(request(**kwargs))


@pytest.mark.asyncio
async def test_router_itself_rejects_remote_before_provider_work(monkeypatch):
    work=AsyncMock(side_effect=AssertionError('No provider work'))
    monkeypatch.setattr('routes.related_tickers.warm_snapshot',work)
    with pytest.raises(HTTPException): await related_ticker_warm('NVDA',WarmRequest(),request(host='192.0.2.1'))
    work.assert_not_called()


@pytest.mark.asyncio
async def test_price_cache_check_runs_without_the_research_agent(monkeypatch):
    """The read workspace has no agent; checking related prices must still work."""
    from services.agent.local_access import require_local

    monkeypatch.delenv('FLOWW_AGENT_DEPLOYMENT', raising=False)
    assert await verify_api_key(request()) is True

    work = AsyncMock(return_value={'batch': {'done': True}})
    monkeypatch.setattr('routes.related_tickers.warm_snapshot', work)
    result = await related_ticker_warm('NVDA', WarmRequest(), request())
    assert result == {'batch': {'done': True}}
    work.assert_awaited_once()

    # Dropping the deployment flag must not relax the boundary.
    with pytest.raises(HTTPException) as no_origin:
        await verify_api_key(request(origin=''))
    assert no_origin.value.status_code == 403
    with pytest.raises(HTTPException) as foreign:
        await verify_api_key(request(origin='https://foreign.example'))
    assert foreign.value.status_code == 403
    # The agent surface still requires the explicit deployment.
    with pytest.raises(HTTPException) as gated:
        require_local(request(path='/api/agent/ask'))
    assert gated.value.status_code == 503
