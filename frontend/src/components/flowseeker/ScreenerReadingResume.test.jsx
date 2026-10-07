import React from 'react';
import {act,render,screen,waitFor} from '@testing-library/react';
import FlowseekerProBlademap from './FlowseekerProBlademap';
import {clearScreenerReading} from './screenerReadingCache';
jest.mock('./MarketCoverage',()=>()=>null);
jest.mock('../heatseeker/useTickerDirectory',()=>()=>({tickers:['SPY'],status:'complete',retry:jest.fn()}));
const payload={columns:['underlying_ticker','ticker','contract_type','strike_price','expiration_date','day_volume','open_interest','implied_volatility','delta','underlying_price'],rows:[['SPY','SPY261106C00760000','call',760,'2026-11-06',5000,1200,.22,.4,755]],source:'public-scan',stale:false,asof:'2026-10-06T20:00:00+00:00'};
beforeEach(()=>{localStorage.clear();clearScreenerReading();});
test('returning to the screener retains dated rows while the next read is pending',async()=>{let scanReads=0;global.fetch=jest.fn(async url=>{if(String(url).includes('/scan?limit=')){if(++scanReads>1)return new Promise(()=>{});return {ok:true,status:200,json:async()=>payload};}return {ok:true,status:200,json:async()=>({})};});const first=render(<FlowseekerProBlademap active/>);await waitFor(()=>expect(document.querySelector('#pulse tbody tr')).not.toBeNull());expect(document.querySelector('#pulse tbody tr').textContent).toContain('SPY');first.unmount();await act(async()=>{render(<FlowseekerProBlademap active/>);});expect(document.querySelector('#pulse tbody tr')).not.toBeNull();expect(screen.getByRole('status',{name:'Retained scanner results'})).toHaveTextContent('Earlier results kept');expect(document.querySelector('#pulse tbody tr').textContent).toContain('SPY');});
