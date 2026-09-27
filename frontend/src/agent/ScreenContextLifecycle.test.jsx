import React from 'react';
import {render,screen,fireEvent,waitFor,act} from '@testing-library/react';
import AppShell from '../shell/AppShell';
import SkylitDashboard from '../components/heatseeker/SkylitDashboard';
import OptionsChainTable from '../components/OptionsChainTable';
import axios from 'axios';
import {fetchPublicChain} from '../lib/publicApi';
jest.mock('axios',()=>({get:jest.fn(),post:jest.fn()}));
jest.mock('../lib/publicApi',()=>({fetchPublicChain:jest.fn()}));
jest.mock('../agent/AgentModelSettings',()=>()=>null);
jest.mock('../shell/Sidebar',()=>()=>null);
jest.mock('react-plotly.js',()=>()=>null);
jest.mock('../components/heatseeker/SkylitTickerBar',()=>()=>null);
jest.mock('../components/heatseeker/SkylitControlBar',()=>()=>null);
jest.mock('../components/heatseeker/SkylitHeatmapGrid',()=>()=>null);
jest.mock('../components/heatseeker/SkylitMetricsSidebar',()=>()=>null);
jest.mock('../components/heatseeker/ExposureStrip',()=>()=>null);
jest.mock('../components/heatseeker/StockDirectory',()=>()=>null);
jest.mock('../components/heatseeker/PriceNodeHistory',()=>()=>null);
jest.mock('../components/heatseeker/ReplayStrip',()=>()=>null);
jest.mock('../components/flowseeker/AlertEngineStrip',()=>()=>null);
beforeAll(()=>Object.defineProperty(globalThis,'crypto',{value:require('crypto').webcrypto,configurable:true}));
test('grid to chain switch must not submit the previous ticker and expiry context',async()=>{
 axios.get.mockResolvedValue({data:{decisions:[],rows:[]}});
 fetchPublicChain.mockImplementation(async ticker=>({ticker,contracts:[],expiries:['2026-10-02'],n_contracts:0}));
 let submitted;
 global.fetch=jest.fn(async(url,options)=>({ok:true,json:async()=>{
  if(String(url).endsWith('/session'))return {};
  if(String(url).endsWith('/ask')){submitted=JSON.parse(options.body);return {turn_id:'test-turn'};}
  return {turn_id:'test-turn',status:'completed',ticker:submitted.ticker,horizon:submitted.horizon,text:'Synthetic saved answer for '+submitted.ticker};
 }}));
 const map={ticker:'SPY',asof:'2026-09-27T14:00:00Z',event_time:'2026-09-27T13:59:50Z',map_query:{expiries:4,mode:'day',dte:0},strikes:[{strike:650}],grid:{strikes:[650],expiries:['2026-09-28'],grid:{'2026-09-28':{'650':123}}}};
 const view=render(<AppShell page='heatseeker'><SkylitDashboard ticker='SPY' dte={0} data={map} spot={650}/></AppShell>);
 await act(async()=>{});
 // App.js uses this same conditional lifecycle: chain replaces SkylitDashboard while AppShell stays mounted.
 view.rerender(<AppShell page='heatseeker'><h1>Visible ticker QQQ</h1><OptionsChainTable ticker='QQQ' spot={500}/></AppShell>);
 await waitFor(()=>expect(fetchPublicChain).toHaveBeenCalledWith('QQQ',expect.anything()));
 await screen.findByText(/Options Chain/);
 fireEvent.change(screen.getByRole('option',{name:'All Expiries'}).parentElement,{target:{value:'2026-10-02'}});
 await act(async()=>{});
 fireEvent.click(screen.getByRole('button',{name:'Open Lodestar research'}));
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'What changed?'}});
 fireEvent.click(screen.getByRole('button',{name:'Ask',exact:true}));
 await screen.findByText(/Open the Solstice grid or Tidehunter/);
 expect(global.fetch.mock.calls.some(([url])=>String(url).endsWith('/ask'))).toBe(false);
 // A supported view must restore asking with its own identity.
 view.rerender(<AppShell page='heatseeker'><SkylitDashboard ticker='QQQ' dte={7} data={{...map,ticker:'QQQ'}} spot={500}/></AppShell>);
 await act(async()=>{});
 fireEvent.change(screen.getByRole('textbox'),{target:{value:'What changed now?'}});
 fireEvent.click(screen.getByRole('button',{name:'Ask',exact:true}));
 await waitFor(()=>expect(submitted).toBeDefined());
 expect(submitted.ticker).toBe('QQQ');
 expect(submitted.horizon).toBe('days:7');
});
