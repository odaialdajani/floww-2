import React from 'react';
import {render,screen,fireEvent,waitFor,act} from '@testing-library/react';
import axios from 'axios';
import FlowseekerProBlademap from './FlowseekerProBlademap';
jest.mock('./MarketCoverage',()=>()=>null);
jest.mock('axios',()=>({get:jest.fn(async()=>({data:{tickers:['SPY','NVDA','COIN'],total:3,complete_provider_catalog:true,has_more:false}}))}));
beforeEach(()=>{axios.get.mockImplementation(async url=>({data:String(url).includes("/tickers/all")?{tickers:["SPY","NVDA","COIN"],total:3,complete_provider_catalog:true,has_more:false}:{default:["SPY"]}}));localStorage.clear();global.fetch=jest.fn(async()=>({ok:true,status:200,json:async()=>({rows:[]})}));});
test('screener stock picker uses the full list and remembers focus after returning',async()=>{const view=render(<FlowseekerProBlademap active/>);const input=screen.getByRole('combobox',{name:'Focused ticker'});fireEvent.change(input,{target:{value:'COIN'}});await waitFor(()=>expect(screen.getByRole('option',{name:'COIN'})).toBeInTheDocument());fireEvent.click(screen.getByRole('option',{name:'COIN'}));await waitFor(()=>expect(JSON.parse(localStorage.getItem('th-prefs-v1')).focusTicker).toBe('COIN'));view.unmount();await act(async()=>{render(<FlowseekerProBlademap active/>);});expect(screen.getByText('Selected COIN')).toBeInTheDocument();expect(screen.getByRole('heading',{name:'Stock details · COIN'})).toBeInTheDocument();});
test('malformed old focus does not cause a remote path lookup',async()=>{localStorage.setItem('th-prefs-v1',JSON.stringify({focusTicker:'../orders'}));await act(async()=>{render(<FlowseekerProBlademap active/>);});expect(screen.getByText('Selected SPY')).toBeInTheDocument();await waitFor(()=>expect(screen.getByRole('heading',{name:'Stock details · SPY'})).toBeInTheDocument());expect(global.fetch.mock.calls.some(([url])=>String(url).includes('../orders'))).toBe(false);});


test.each(['../ORDERS', {ticker:'COIN'}, 42, ''])('malformed saved default stock uses a safe fallback: %j',async defaultTicker=>{
 localStorage.setItem('floww_settings',JSON.stringify({defaultTicker}));
 await act(async()=>{render(<FlowseekerProBlademap active/>);});
 expect(screen.getByText('Selected SPY')).toBeInTheDocument();
 expect(screen.getByRole('heading',{name:'Stock details · SPY'})).toBeInTheDocument();
 expect(global.fetch.mock.calls.filter(([url])=>String(url).includes('/regime/') || String(url).includes('/heatmap/') || String(url).includes('/vpin/')).every(([url])=>String(url).includes('/SPY'))).toBe(true);
});

test.each(['COIN','BRK.B','^SPX'])('a valid default stock remains the requested focus: %s',async defaultTicker=>{
 localStorage.setItem('floww_settings',JSON.stringify({defaultTicker}));
 await act(async()=>{render(<FlowseekerProBlademap active/>);});
 expect(screen.getByText('Selected '+defaultTicker)).toBeInTheDocument();
 expect(screen.getByRole('heading',{name:'Stock details · '+defaultTicker})).toBeInTheDocument();
 expect(global.fetch.mock.calls.some(([url])=>String(url).includes('/vpin/'+encodeURIComponent(defaultTicker)))).toBe(true);
});

test('a valid saved screener focus takes priority over the default stock',async()=>{
 localStorage.setItem('floww_settings',JSON.stringify({defaultTicker:'COIN'}));
 localStorage.setItem('th-prefs-v1',JSON.stringify({focusTicker:'NVDA'}));
 await act(async()=>{render(<FlowseekerProBlademap active/>);});
 expect(screen.getByText('Selected NVDA')).toBeInTheDocument();
 expect(global.fetch.mock.calls.some(([url])=>String(url).includes('/vpin/NVDA'))).toBe(true);
 expect(global.fetch.mock.calls.some(([url])=>String(url).includes('/vpin/COIN'))).toBe(false);
});
