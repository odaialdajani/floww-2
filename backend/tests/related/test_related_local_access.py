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
